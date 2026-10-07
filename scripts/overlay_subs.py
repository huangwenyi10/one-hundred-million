#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""overlay_subs.py -- 给「已带 Ken Burns 动效的 body」叠加字幕水印，产出最终成片

## 为什么需要这个脚本（实测踩坑链，2026-10-07）

1. 本机 ffmpeg 9.0.1 编译时**未带 libass / freetype / fontconfig**
   （`ffmpeg -filters` 无 subtitles / ass / drawtext），字幕**无法用 ffmpeg 烧录**。
2. `burn_subs_watermark.py --mode burn` 用 Pillow 把字幕画进**静态帧**。但这招对
   **带动效**的视频无效——画面随时间缩放位移，「一页一图」烧完再拼等于抹平动效。
   实测证据：那样产出的成片，内容区在 0.5s 间隔上像素**完全相同**（动效丢失）。
3. 「导出带 Ken Burns 的 6.7 万帧再逐帧烧字幕」不可行：2245s × 30fps，代价与磁盘
   都无法接受。
4. **正解**：`overlay` 滤镜是唯一能在**已编码的视频流**上叠加图层的通路（本机
   `perspective` 不可用，但 `overlay` 可用）。拆成两段：
     ① body（无字幕、无水印、带动效）
     ② 透明字幕+水印层（RGBA PNG 序列 + concat 清单）
     ③ overlay 叠加 → 视频轨；再与 seg_*.mp3 合成音频轨

## 四条必须遵守的约束（都是实测踩出来的）

- **字幕层总长必须与视频逐帧等长**：字幕轴常比视频轴长（上篇字幕 2243.2s vs
  body 2218.8s，差 24.4s）。overlay 以**较长**那条为准，不裁剪会把片尾拉长并卡住
  最后一帧。故 `--video-duration` 必填，导出时按它裁剪，差值 >0.5s 直接报错退出。
- **concat 清单必须写绝对路径**：ffmpeg concat demuxer 解析相对路径以「清单文件
  所在目录」为基准，而脚本运行时 cwd 未必等于它 → "No such file or directory"。
- **`-vsync` 已废弃**，改 `-fps_mode cfr`，且必须放在**输出侧**。
- ★**overlay 必须显式指定 format，不能用 `format=auto`**（性能悬崖，实测）：
  `auto` 会协商到 RGBA 全精度路径，1080p 下 **60 秒要 6 分钟**（全片 2200+ 秒
  = 数小时，等于不可用）。改为「字幕层先 format=yuva420p（保留 alpha）+ overlay
  端 format=yuv420」后，60 秒降到 **8.8 秒**（约 40 倍提速），画质无可见损失
  （本片字幕是白字黑描边，不依赖 alpha 精细渐变）。
  ⚠️ 字幕层 PNG 带 alpha，**绝不能**直接 `format=yuv420p`（会丢 alpha → 字幕带
  变成黑底）。必须 yuva420p → yuv420 两步。
  preset 用 `veryfast`（实测 60 秒 6.6s；`medium` 会翻数倍）。

## 用法

  #1) 先导出字幕层（裁到与视频等长）
  python3 burn_subs_watermark.py --mode overlay --build <build目录> \
      --out <字幕层目录> --video-duration <视频秒数> --wrap 34
  #2) 再叠加合成
  python3 overlay_subs.py --body body.mp4 --overlay-dir <字幕层目录> \
      --build <build目录> --out <成片.mp4> [--limit-dur 60]
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

W, H, FPS = 1920, 1080, 30
ABITRATE = "95k"
ASRATE = 24000
PRESET = "veryfast"
CRF = 20


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("命令失败:", " ".join(cmd[:8]), "...", file=sys.stderr)
        print(r.stderr[-3000:], file=sys.stderr)
    return r


def probe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def build_audio(build, work, xfade=0.5):
    """拼所有 seg_*.mp3，并把音频**对齐到视频的真实时长**。

    ★ 为什么必须逐段裁尾（本项目最隐蔽的一个坑，实测）：
    body 由 compose_motion.py 用 **xfade 交叉淡入**串接，每段之间重叠
    `xfade` 秒，故视频总长 = Σdurations − (段数−1)×xfade。
    实测上篇：音频合计 2243.26s、50 段 → 视频应短 (50−1)×0.5 = **24.5s**，
    实测 body 正是 2218.77s = 2243.26 − 24.5，完全吻合。
    若直接把完整音频灌进去，音轨会比视频长 22~26 秒 → **片尾出现无画面的黑屏/
    静帧**，且末句口播对不上画面。
    故按同一节奏裁：第 1..n-1 段各裁掉尾部 xfade 秒（xfade 期间本就与下一段画面
    交叉淡化，无需保留该段音频），最后一段完整保留。
    实测各段音频时长与时间轴**完全相等**（差 0.000），说明时间轴未额外加 padding，
    裁 0.5s 落在段内而非句间空白——为避免切到字，裁剪点选在段尾。

    另外**不能复用 build/segs_concat.txt**——实测那份清单指向已搬迁的旧路径
    （~/Documents/ChatGPT/HundredMillion/...），会直接 "No such file or directory"。
    注意 seg 编号不一定从 00 起（下篇是 01~46）。
    """
    import json as _json
    segs = sorted(f for f in os.listdir(build)
                  if f.startswith("seg_") and f.endswith(".mp3"))
    if not segs:
        af = os.path.join(build, "voiceover.mp3")
        return af if os.path.isfile(af) else None, 0.0

    # 时间轴（用于取每段原始时长）
    tl = os.path.join(build, "segments_durations.json")
    durs = []
    if os.path.isfile(tl):
        d = _json.load(open(tl, encoding="utf-8"))
        durs = d["durations"] if isinstance(d, dict) else list(d)

    n = len(segs)
    babs = os.path.abspath(build)
    work_abs = os.path.abspath(work)
    if n == 1:
        return os.path.join(babs, segs[0]), 0.0

    # 裁剪后的段**统一转成 wav**再拼。
    # ★ 实测踩坑：清单里混用 mp3（末段未裁）与 wav（已裁）时，concat demuxer
    #   对两种容器的时间基处理不一致，实测中篇清单逐段累加 2364.91s、实际只输出
    #   2322.43s——**凭空丢了 42.5 秒音频**（表现为片尾 40 秒无声，且末句口播缺失）。
    #   故末段也要转 wav，保证清单内格式统一、时间基一致。
    tmpdir = os.path.join(work_abs, "atrime")
    os.makedirs(tmpdir, exist_ok=True)
    lst = os.path.join(work_abs, "audio_concat.txt")
    total_cut = 0.0
    lines = []
    for i, s in enumerate(segs):
        src = os.path.join(babs, s)
        cut = 0.0 if i == n - 1 else xfade
        sdur = probe_dur(src)
        keep = max(0.1, sdur - cut)
        piece = os.path.join(tmpdir, f"a{i:03d}.wav")
        r = run(["ffmpeg", "-y", "-v", "error", "-i", src,
                 "-t", f"{keep:.3f}", "-c:a", "pcm_s16le",
                 "-ar", str(ASRATE), "-ac", "1", piece])
        if r.returncode != 0 or not os.path.isfile(piece):
            # 裁剪失败则退回用原段（宁可音画略长，也不能丢音频）
            print(f"  ⚠ 段{i}裁剪失败，改用原段", file=sys.stderr)
            lines.append(f"file '{src}'")
            continue
        lines.append(f"file '{piece}'")
        total_cut += cut
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 自检：逐段累加必须与「原始合计 − 裁掉」吻合，不吻合就别让下游拿到一份坏音频
    got = sum(probe_dur(p) for p in
              (l[6:-1] for l in lines if l.startswith("file ")))
    want = sum(probe_dur(os.path.join(babs, s)) for s in segs) - total_cut
    if abs(got - want) > 1.0:
        print(f"  ⚠ 裁剪后逐段累加 {got:.2f}s 与预期 {want:.2f}s 不符（差 "
              f"{got-want:+.2f}s）", file=sys.stderr)
    else:
        print(f"  音频裁剪自检通过：{got:.2f}s（{n} 段，共裁 {total_cut:.1f}s）")
    return lst, total_cut


def _mux_audio(a, vout, vdur):
    """把音频（按 xfade裁尾对齐）合并到已合成的视频轨上，产出最终成片。"""
    work = a.work or os.path.join(os.path.dirname(os.path.abspath(a.body)), "_mux")
    os.makedirs(work, exist_ok=True)
    t0 = time.time()
    print(f"复用视频轨 {os.path.basename(vout)}（{vdur:.2f}s）")

    audio = build_audio(a.build, work, a.xfade)
    if not audio:
        print("  ⚠ 未找到音频，仅输出视频轨", file=sys.stderr)
        shutil.copy2(vout, a.out)
        print(f"\n成片(无音频): {a.out}")
        return 0

    # build_audio 现在统一返回 (清单路径, 实际裁掉秒数)
    _lst, _cut = audio
    acmd = ["ffmpeg", "-y", "-v", "error", "-i", vout,
            "-f", "concat", "-safe", "0", "-i", _lst,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-c:a", "aac", "-b:a", ABITRATE, "-ar", str(ASRATE), "-ac", "1",
            "-movflags", "+faststart", a.out]

    print(f"合并音频（按 xfade={a.xfade}s裁尾对齐）…", flush=True)
    if run(acmd).returncode != 0:
        return 3
    adur = probe_dur(a.out)
    print(f"\n成片: {a.out}")
    print(f"  {os.path.getsize(a.out)//1024//1024}MB · {adur:.2f}s · "
          f"总用时 {time.time()-t0:.0f}s")
    if abs(adur - vdur) > 1.5:
        print(f"  ⚠ 音画时长仍差 {adur - vdur:+.2f}s（音 {adur:.2f} / 视 {vdur:.2f}）",
              file=sys.stderr)
        return 4
    print("  音画等长 ✅")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, help="无字幕、带动效的 body.mp4")
    ap.add_argument("--overlay-dir", help="含overlay_concat.txt 的目录（audio-only 模式不需要）")
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", help="中间目录（默认 <body同级>/_mux）")
    ap.add_argument("--limit-dur", type=float, help="只处理前 N 秒（冒烟测试）")
    ap.add_argument("--crf", type=int, default=CRF)
    ap.add_argument("--preset", default=PRESET)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--xfade", type=float, default=0.5,
                    help="body 各段之间的 xfade 转场秒数（compose_motion.py 默认 0.5）；"
                         "用于把音频裁到与视频等长")
    ap.add_argument("--audio-only", action="store_true",
                    help="跳过叠加字幕，直接用已存在的 <work>/video_subs.mp4 重做音频。"
                         "实测：字幕叠加是最慢的一步（15 分钟/部），若只需修音画"
                         "等长问题，用它可省掉整个叠加环节")
    a = ap.parse_args()

    if a.audio_only:
        work0 = a.work or os.path.join(os.path.dirname(os.path.abspath(a.body)), "_mux")
        vout = os.path.join(work0, "video_subs.mp4")
        if not os.path.isfile(vout):
            print(f"ERROR: --audio-only 需要已存在的 {vout}", file=sys.stderr)
            return 1
        return _mux_audio(a, vout, probe_dur(vout))

    if not a.overlay_dir:
        print("ERROR: 需要 --overlay-dir（或改用 --audio-only）", file=sys.stderr)
        return 1
    lst = os.path.join(os.path.abspath(a.overlay_dir), "overlay_concat.txt")
    if not os.path.isfile(lst):
        print(f"ERROR: 找不到 overlay 清单: {lst}", file=sys.stderr)
        return 1
    if not os.path.isfile(a.body):
        print(f"ERROR: 找不到 body: {a.body}", file=sys.stderr)
        return 1

    work = a.work or os.path.join(os.path.dirname(os.path.abspath(a.body)), "_mux")
    os.makedirs(work, exist_ok=True)

    vdur = a.limit_dur or probe_dur(a.body)
    if not vdur:
        print("ERROR: 无法探测 body 时长", file=sys.stderr)
        return 1
    print(f"body 时长 {vdur:.2f}s" + ("（冒烟模式）" if a.limit_dur else ""))

    t0 = time.time()
    vout = os.path.join(work, "video_subs.mp4")
    # format=yuva420p 保留字幕层 alpha，再以 yuv420 叠加（见模块 docstring 的性能约束）
    if a.limit_dur:
        fc = (f"[1:v]trim=0:{a.limit_dur},setpts=PTS-STARTPTS,format=yuva420p[s];"
              f"[0:v][s]overlay=0:0:format=yuv420[v]")
    else:
        fc = "[1:v]format=yuva420p[s];[0:v][s]overlay=0:0:format=yuv420[v]"

    # ★ 必须在**输出侧**加 `-t vdur`（实测踩坑）：
    #   overlay 的 framesync 默认 shortest=0 / eof_action=repeat —— 字幕层（60s）
    #   先结束时，它会**重复最后一帧**并继续输出，直到主输入 body 走完 2218s。
    #   于是「冒烟测试 60s」实际产出了 452MB 的全片视频，白等 6 分钟。
    #   输出侧 -t 硬性封顶后，concat 输入也会随之停止读取。
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.body,
           "-f", "concat", "-safe", "0", "-i", lst,
           "-filter_complex", fc, "-map", "[v]",
           "-c:v", "libx264", "-preset", a.preset, "-crf", str(a.crf),
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-fps_mode", "cfr",
           "-t", f"{vdur:.3f}", vout]
    print("叠加字幕 …", flush=True)
    if run(cmd).returncode != 0:
        return 2
    got = probe_dur(vout)
    print(f"  视频轨 {os.path.getsize(vout)//1024//1024}MB · {got:.2f}s"
          f"（{time.time()-t0:.0f}s）")
    if abs(got - vdur) > 1.0:
        print(f"  ⚠ 叠加后 {got:.2f}s 与 body {vdur:.2f}s 不一致", file=sys.stderr)

    if a.no_audio:
        shutil.copy2(vout, a.out)
        print(f"\n成片(无音频): {a.out}")
        return 0

    return _mux_audio(a, vout, got)


if __name__ == "__main__":
    sys.exit(main())