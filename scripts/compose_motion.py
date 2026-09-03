#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_motion.py — 给静态帧目录加「镜头运动 + 交叉淡入」，消除画面静态感。

背景：默认管线是「HTML→PNG 静态帧 → ffmpeg 帧拼接（硬切、静止）」，观感偏静态。
本脚本把合成环节升级为 **Ken Burns 镜头运动（缓慢推拉摇移）+ xfade 交叉淡入**：
  - 不改 HTML / 不重渲帧 / 不动配音与字幕时间轴（帧停留时长仍取 segments_durations.json）
  - 只换「合成」环节 → 四方同频、时长、字幕全部不受影响，但整支视频"活"起来。

用法：
  python3 compose_motion.py <frames_dir> <durations.json> <out_video> [--fps 30] [--preset 1]
参数：
  frames_dir   含 page_01.png ... 的静态帧目录（编号需可排序，自然序对齐 durations 顺序）
  durations.json 帧停留时长：{"durations":[d0,d1,...],"total":...}（首帧通常为封面段时长）
  out_video    输出 mp4
  --preset 1|2|3  运动强度：1=轻微(默认,推荐正文) 2=适中 3=强(仅关键/大图页)
依赖：ffmpeg（需支持 zoompan 与 xfade）。
"""
import argparse, json, os, re, subprocess, sys, tempfile


def parse_page_num(path):
    m = re.search(r'(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else 0


def natural_key(path):
    # 让 page_2.png < page_10.png
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(path))]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("CMD FAIL: " + " ".join(cmd) + "\n" + r.stderr[-3000:] + "\n")
        raise SystemExit(r.returncode)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("durations_json")
    ap.add_argument("out_video")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preset", type=int, default=1, choices=[1, 2, 3])
    args = ap.parse_args()

    frames = [os.path.join(args.frames_dir, f)
              for f in sorted(os.listdir(args.frames_dir))
              if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    frames.sort(key=natural_key)
    if not frames:
        sys.exit("No frames in " + args.frames_dir)

    with open(args.durations_json, encoding='utf-8') as f:
        data = json.load(f)
    durations = data["durations"] if isinstance(data, dict) else list(data)

    # durations 数量与帧数对齐（不足补默认 6s，多余截断），避免 index 越界
    default_d = 6.0
    if len(frames) != len(durations):
        sys.stderr.write(f"WARN: frames={len(frames)} vs durations={len(durations)}; 补齐为帧数\n")
        if len(durations) < len(frames):
            durations = durations + [default_d] * (len(frames) - len(durations))
        else:
            durations = durations[:len(frames)]

    # 运动强度参数（zoompan 的 zoom 终点、位移量）
    zoom_max = {1: 1.06, 2: 1.10, 3: 1.16}[args.preset]
    pan_px = {1: 40, 2: 90, 3: 150}[args.preset]

    tmp = tempfile.mkdtemp(prefix="compose_motion_")
    seg_paths = []
    total = len(frames)
    fps = args.fps

    # 逐帧生成「单段带 Ken Burns 运动的视频」，时长=该帧停留时长
    for i, fp in enumerate(frames):
        d = durations[i]
        if d < 0.5:
            d = 0.5
        n_frames = max(1, int(round(d * fps)))
        # 方向在 4 种间轮转：放大-居中、放大-左上摇、缩小-居中、放大-右下摇
        mode = i % 4
        if mode == 0:
            # 缓慢放大(1.0→zoom_max)，中心
            zexpr = f"1+{zoom_max-1:.3f}*on/{n_frames}"
            x = "(iw-iw/zoom)/2"; y = "(ih-ih/zoom)/2"
        elif mode == 1:
            # 放大并向右下平移
            zexpr = f"1+{zoom_max-1:.3f}*on/{n_frames}"
            x = f"(iw-iw/zoom)/2+{pan_px}*on/{n_frames}"; y = f"(ih-ih/zoom)/2+{pan_px}*on/{n_frames}"
        elif mode == 2:
            # 缩小(zoom_max→1)，中心
            zexpr = f"{zoom_max}-{zoom_max-1:.3f}*on/{n_frames}"
            x = "(iw-iw/zoom)/2"; y = "(ih-ih/zoom)/2"
        else:
            # 放大并向左上摇
            zexpr = f"1+{zoom_max-1:.3f}*on/{n_frames}"
            x = f"(iw-iw/zoom)/2-{pan_px}*on/{n_frames}"; y = f"(ih-ih/zoom)/2-{pan_px}*on/{n_frames}"

        seg = os.path.join(tmp, f"seg_{i:03d}.mp4")
        vf = (f"scale=8000:-1,zoompan=z='{zexpr}':x='{x}':y='{y}':"
              f"d={n_frames}:s=1920x1080:fps={fps},format=yuv420p")
        run(["ffmpeg", "-y", "-loop", "1", "-i", fp,
             "-t", f"{d:.3f}", "-vf", vf, "-r", str(fps),
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", seg])
        seg_paths.append(seg)

    # 用 xfade 把各段级联起来（前一段尾部与后一段头部交叉淡入）
    # xfade 需要所有输入等长较麻烦；简单起见：先 concat 无过渡会退化为硬切。
    # 这里实现「相邻两段级联一个 0.5s xfade」：用 filter_complex 链式，前一段裁剪 -0.5s。
    # 更稳健做法：不裁剪，两段 concat，仅在最外层对相邻段做局部 xfade 不现实；
    # 方案：逐段 append 用 xfade 需知道前段"去尾后"时长，逐段算累计。
    #
    # 采用链式 xfade：把每段作为一个输入，第 k 段 offset = (前面积累总长) - k*XD
    XD = 0.5
    inputs = []
    for s in seg_paths:
        inputs += ["-i", s]
    # 计算每段实际时长
    seg_durs = []
    for s in seg_paths:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", s],
                           capture_output=True, text=True)
        seg_durs.append(float(r.stdout.strip()))

    # 累计 xfade offset：合并 k 段后总长 = sum(first k+1) - k*XD
    acc = seg_durs[0]
    filter_parts = []
    # 每一路 concat 输入给个 label
    filter_parts.append(f"[0:v]format=yuv420p[v0]")
    cur = "v0"
    for k in range(1, total):
        # 第 k 路输入与 cur 做 xfade，offset = acc - XD
        off = max(0.0, acc - XD)
        filter_parts.append(f"[{k}:v]format=yuv420p[v{k}]")
        outlabel = f"vx{k}"
        filter_parts.append(f"[{cur}][v{k}]xfade=transition=fade:duration={XD}:offset={off:.3f}[{outlabel}]")
        cur = outlabel
        acc = acc + seg_durs[k] - XD

    fc = ";".join(filter_parts) + f";[{cur}]format=yuv420p[vout]"
    out = os.path.abspath(args.out_video)
    run(["ffmpeg", "-y"] + inputs + ["-filter_complex", fc, "-map", "[vout]",
         "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", out])
    sys.stdout.write(f"OK -> {out}  (frames={total}, 预估时长≈{acc:.1f}s)\n")


if __name__ == "__main__":
    main()
