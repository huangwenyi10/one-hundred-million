#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mux_final.py -- body(镜头运动) + 配音 + 字幕水印 → 成片（one-hundred-million 配套）

**流程分工**（对齐 SKILL.md Step 6）：
  1. export_frames.py       静态帧（一页一图，不带字幕）
  2. compose_motion.py      Ken Burns 推拉摇移 + xfade 0.5s 交叉淡入 → body.mp4
  3. mux_final.py（本脚本） body + 配音分段 + 字幕切片 + 水印 → 成片

**为什么字幕在合成阶段才叠**：字幕必须**跟着运动后的画面**走。若先把字幕
烧进静态帧，Ken Burns 推拉时字幕会一起被放大位移、边缘发虚；且 xfade
衔接处会出现字幕跳变。故此处用「按时间切片烧字幕 → 与 body 帧对齐拼接」
的方式，字幕恒定不动、只有画面在动。

**字幕实现**：本机 ffmpeg 9.0.1 未带 libass/drawtext（实测），故沿用
burn_subs_watermark.py 的 Pillow 方案——把 body 视频按字幕 cue 切片，
每片烧对应字幕与水印，再按原时长拼回。

用法：
  python3 mux_final.py --body <body.mp4> --build <build目录> \
      --out <成片.mp4> [--work <工作目录>]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from burn_subs_watermark import (W, H, FPS, ABITRATE, ASRATE, load_font,  # noqa: E402
                                 parse_srt, burn_one)
from PIL import Image  # noqa: E402


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("命令失败:", " ".join(x for x in cmd[:8] if not x.startswith("/")), file=sys.stderr)
        print(r.stderr[-2000:], file=sys.stderr)
    return r


def concat_audio(build, n):
    segs = [f"seg_{i:02d}.mp3" for i in range(n)]
    segs = [s for s in segs if os.path.isfile(os.path.join(build, s))]
    if not segs:
        return None
    lst = os.path.join(tempfile.gettempdir(), "mux_segs.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{os.path.join(build, s)}'\n")
    return lst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", required=True, help="compose_motion.py 产出的 body 视频")
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--work")
    ap.add_argument("--slice", type=float, default=1.0, help="字幕切片间隔（秒）")
    ap.add_argument("--slice-wm-only", action="store_true",
                    help="只烧水印不烧字幕（画面已含字幕时用）")
    ap.add_argument("--keep-subs", help="已烧好字幕的帧目录（跳过本脚本烧录）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = json.load(open(os.path.join(a.build, "segments_durations.json"), encoding="utf-8"))
    durations = d["durations"] if isinstance(d, dict) else d
    starts = d.get("starts") if isinstance(d, dict) else None
    if starts is None:
        starts, acc = [], 0.0
        for x in durations:
            starts.append(acc)
            acc += x

    srt = None
    for name in ("subtitles_fixed.srt", "subtitles_clean.srt", "subtitles.srt"):
        p = os.path.join(a.build, name)
        if os.path.isfile(p):
            srt = p
            break
    cues = parse_srt(srt) if srt else []
    print(f"body: {a.body}")
    print(f"分段 {len(durations)} · 总时长 {sum(durations):.1f}s · 字幕 {len(cues)} 条")

    if a.dry_run:
        return 0

    t0 = time.time()
    work = a.work or os.path.join(a.build, "_mux")
    os.makedirs(work, exist_ok=True)

    # 1) 抽 body 的所有帧（body 已含镜头运动）
    frames = os.path.join(work, "body_frames")
    if os.path.isdir(frames):
        shutil.rmtree(frames)
    os.makedirs(frames)
    r = run(["ffmpeg", "-y", "-i", a.body, "-vsync", "0",
             "-start_number", "0", os.path.join(frames, "f_%06d.png")])
    if r.returncode != 0:
        print("ERROR: 抽 body 帧失败", file=sys.stderr)
        return 2
    nframes = len([f for f in os.listdir(frames) if f.endswith(".png")])
    print(f"  body 抽帧 {nframes} 张")

    # 2) 按字幕 cue 烧字幕+水印到每帧
    sub_font = load_font(46, index=1)
    wm_font = load_font(30, index=1)
    files = sorted(f for f in os.listdir(frames) if f.endswith(".png"))
    for k, fn in enumerate(files):
        t = k / FPS
        txt = ""
        if not a.slice_wm_only:
            for c0, c1, tx in cues:
                if c0 <= t < c1:
                    txt = tx
                    break
        burn_one(os.path.join(frames, fn), os.path.join(frames, fn), txt,
                 wm=True, sub_font=sub_font, wm_font=wm_font)
    print(f"  字幕+水印烧录完成（{time.time()-t0:.0f}s）")

    # 3) 帧 + 配音 → 成片
    lst = os.path.join(work, "body_concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for fn in files:
            f.write(f"file '{os.path.join(frames, fn)}'\n")
    audio = concat_audio(a.build, len(durations))
    out = os.path.join(work, "final.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    if audio:
        cmd += ["-f", "concat", "-safe", "0", "-i", audio, "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-s", f"{W}x{H}",
            "-fps_mode", "cfr", "-movflags", "+faststart"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", ABITRATE, "-ar", str(ASRATE), "-ac", "1"]
    else:
        cmd += ["-an"]
    cmd += [out]
    print("合成成片 …", flush=True)
    r = run(cmd)
    if r.returncode != 0:
        return 2
    shutil.copy2(out, a.out)
    print(f"\n成片: {a.out}（{os.path.getsize(a.out)//1024//1024}MB，用时 {time.time()-t0:.0f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
