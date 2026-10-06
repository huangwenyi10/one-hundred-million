#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compose_final.py -- 用新帧 + 原配音/字幕重新合成成片（one-hundred-million 配套）

**复用**原有 build/ 里的配音分段（seg_*.mp3）、时间轴（segments_durations.json）、
字幕（subtitles_fixed.srt）——PPT 改写后页数与顺序不变，故这些全部不动。

产出规格与原成片一致（实测对齐）：
  视频 h264 1920x1080 30fps yuv420p High profile ~2.1Mbps
  音频 aac 24000Hz 单声道 ~95kbps

用法：
  python3 compose_final.py --frames <帧目录> --build <build目录> \
      --out <成片.mp4> [--work <工作目录>] [--crf 20] [--dry-run]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

W, H, FPS = 1920, 1080, 30
# 原成片实测规格
VBITRATE = "2126k"
ABITRATE = "95k"
ASRATE = 24000


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("命令失败:", " ".join(cmd[:6]), "...", file=sys.stderr)
        print(r.stderr[-2500:], file=sys.stderr)
    return r


def load_timeline(build):
    p = os.path.join(build, "segments_durations.json")
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict) and "durations" in d:
        return d["durations"], d.get("starts"), d.get("ends"), d.get("total", 0)
    if isinstance(d, list):
        return d, None, None, sum(d)
    raise SystemExit(f"无法解析时间轴: {p}")


def build_concat(frames_dir, durations, work):
    """按每段时长把帧拼成 concat 清单，返回清单路径。

    兼容两种帧目录：
      A. 静态帧 `page_001.png`（无字幕版，一页一图）
      B. 字幕切片 `page_001_000.png` + slices.json（字幕已烧进图里）
         —— 此时每页按其切片数量与总时长展开，slice = duration / 切片数
    """
    if os.path.isfile(os.path.join(frames_dir, "slices.json")):
        import json as _json
        sl = _json.load(open(os.path.join(frames_dir, "slices.json"), encoding="utf-8"))
        lines = []
        for it in sl:
            i, n, dur = it["page"], it["slices"], it["duration"]
            per = dur / n
            files = []
            for k in range(n):
                cand = os.path.join(frames_dir, f"page_{i:03d}_{k:03d}.png")
                if os.path.isfile(cand):
                    files.append(cand)
            if not files:
                continue
            for f in files:
                lines.append(f"file '{f}'")
                lines.append(f"duration {per:.3f}")
            lines.append(f"file '{files[-1]}'")   # 末帧重复，防止被 concat 忽略
        lst = os.path.join(work, "frames_concat.txt")
        with open(lst, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return lst, len(sl)

    files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not files:
        raise SystemExit(f"帧目录为空: {frames_dir}")
    if len(files) != len(durations):
        print(f"⚠ 帧数({len(files)}) 与分段数({len(durations)}) 不一致，"
              f"按较少的一方对齐", file=sys.stderr)
    n = min(len(files), len(durations))
    lines = []
    for i in range(n):
        f = os.path.join(frames_dir, files[i])
        dur = durations[i]
        lines.append(f"file '{f}'")
        lines.append(f"duration {dur:.3f}")
    # concat 格式最后一帧需重复一次，否则会被忽略
    lines.append(f"file '{os.path.join(frames_dir, files[n - 1])}'")
    lst = os.path.join(work, "frames_concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return lst, n


def pick_subtitle(build):
    """优先用还原后的字幕（代理字已还原），其次其他。"""
    for name in ("subtitles_fixed.srt", "subtitles_clean.srt", "subtitles.srt"):
        p = os.path.join(build, name)
        if os.path.isfile(p):
            return p
    return None


def pick_cover(build, title):
    for cand in ("cover.png", "cover.jpg", "cover_frame.png"):
        p = os.path.join(build, cand)
        if os.path.isfile(p):
            return p
    return None


def pick_audio(build, n):
    """拼接所有分段音频。"""
    segs = [f"seg_{i:02d}.mp3" for i in range(n)]
    segs = [s for s in segs if os.path.isfile(os.path.join(build, s))]
    if not segs:
        af = os.path.join(build, "voiceover.mp3")
        if os.path.isfile(af):
            return af, "concat"
        return None, None
    lst = os.path.join(tempfile.gettempdir(), "segs_concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{os.path.join(build, s)}'\n")
    return lst, "concat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", help="中间文件目录（默认 build/_compose）")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    durations, starts, ends, total = load_timeline(a.build)
    work = a.work or os.path.join(a.build, "_compose")
    os.makedirs(work, exist_ok=True)
    lst, n = build_concat(a.frames, durations, work)
    audio, amode = pick_audio(a.build, n)
    srt = pick_subtitle(a.build)
    print(f"帧 {n} 段· 总时长 {total:.1f}s")
    print(f"  concat 清单: {lst}")
    print(f"  音频: {audio or '（无）'}")
    print(f"  字幕: {srt or '（无）'}")
    if a.dry_run:
        return 0

    t0 = time.time()
    # 1) 帧 + 配音 → 成片
    #    注意 ffmpeg 9.x：-vsync 已废弃，改 -fps_mode；且它必须放在**输出**侧
    #    （放输入侧会报 "cannot be applied to input url"）。
    body = os.path.join(work, "body.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    if audio:
        cmd += ["-f", "concat", "-safe", "0", "-i", audio,
                "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-s", f"{W}x{H}",
            "-fps_mode", "cfr", "-movflags", "+faststart"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", ABITRATE, "-ar", str(ASRATE), "-ac", "1"]
    else:
        cmd += ["-an"]
    cmd += [body]
    print("合成body …", flush=True)
    r = run(cmd)
    if r.returncode != 0:
        return 2
    print(f"  body 完成 {os.path.getsize(body)//1024//1024}MB（{time.time()-t0:.0f}s）")

    # 字幕已在 burn_subs_watermark.py 阶段烧进帧图里（ffmpeg 无 libass，
    # 无法用 subtitles 滤镜烧录），故此处不再尝试二次烧录。
    final = body
    shutil.copy2(final, a.out)
    print(f"\n成片: {a.out}（{os.path.getsize(a.out)//1024//1024}MB，用时 {time.time()-t0:.0f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
