#!/usr/bin/env python3
"""video_tool.py - 自媒体短视频 ffmpeg 封装工具。

子命令:
  frames   帧图片序列 + 配音 -> 正文视频
  watermark 在左上角叠加 "作者：@Map" 水印（全程，全片唯一）
  sub_clean 去除 VTT/SRT 每条字幕中所有句读/标点类符号（保留数字上下文的小数点、百分号、单位符号等）
  subtitle 将 SRT/ASS 字幕烧录进视频
  cover    将封面 PNG 拼接为片头 3 秒
  portrait 横屏转竖屏（9:16，上下深色补边）
  info     查看媒体时长等信息

用法示例:
  python3 video_tool.py frames --dir frames --audio voiceover.mp3 --out body.mp4 --fps 30
  python3 video_tool.py frames --dir frames --audio voiceover.mp3 --out body.mp4 --durations 5,8.2,6,...
  python3 video_tool.py sub_clean --input subs.vtt --out subs_clean.vtt
  python3 video_tool.py cover --image cover.png --video body.mp4 --out head.mp4
  python3 video_tool.py watermark --input head.mp4 --out final.mp4
  python3 video_tool.py subtitle --input final.mp4 --subs subs.ass --out final_sub.mp4
"""
import argparse
import re
import glob
import json
import os
import shutil
import subprocess
import sys

FONT = "/System/Library/Fonts/PingFang.ttc"
WATERMARK_TEXT = "作者：@Map"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, check=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def cmd_frames(args):
    frames = sorted(glob.glob(os.path.join(args.dir, "*")))
    frames = [f for f in frames if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    if not frames:
        sys.exit(f"no frames found in {args.dir}")
    audio_dur = probe_duration(args.audio)
    n = len(frames)
    if args.durations:
        durs = [float(x) for x in args.durations.split(",")]
        if len(durs) != n:
            sys.exit(f"--durations has {len(durs)} entries but {n} frames")
    else:
        per = audio_dur / n
        durs = [per] * n
    segs = []
    tmpdir = "._vt_segs"
    os.makedirs(tmpdir, exist_ok=True)
    for i, (f, d) in enumerate(zip(frames, durs)):
        seg = os.path.join(tmpdir, f"seg{i:03d}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-t", f"{d:.3f}", "-i", f,
             "-vf", f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,"
                    f"pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
             "-r", str(args.fps), "-c:v", "libx264", "-tune", "stillimage", seg])
        segs.append(seg)
    lst = os.path.join(tmpdir, "list.txt")
    with open(lst, "w") as fh:
        for s in segs:
            fh.write(f"file '{os.path.abspath(s)}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-i", args.audio, "-c:v", "copy", "-c:a", "aac", "-shortest", args.out])
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"OK -> {args.out}")


def cmd_watermark(args):
    vf = (f"drawtext=text='{WATERMARK_TEXT}':fontfile={FONT}:fontsize={args.size}:"
          f"fontcolor=white@0.85:box=1:boxcolor=black@0.35:boxborderw=8:"
          f"x={args.x}:y={args.y}")
    run(["ffmpeg", "-y", "-i", args.input, "-vf", vf, "-c:a", "copy", args.out])
    print(f"OK -> {args.out}")


def clean_sub_text(s):
    """删除字幕行末的句读/标点类符号（循环删到非标点为止），保留行内标点和数字/单位上下文符号。

    仅删**行末连续**标点；行内逗号/句号/书名号等保留。数字/单位符号（小数点 `2.3`、百分号 `90%`、
    单位 `℃`、时间码 `00:01:23`）不删，即使落在行末也不会误伤。
    """
    s = s.rstrip()
    s = re.sub(r'[，。、；：？！“”‘’（）《》〈〉「」『』【】…—～·!?"\'()\[\]{}<>,]+$', '', s)
    return s


def cmd_sub_clean(args):
    """去除 VTT/SRT 每条字幕**末尾**的所有句读/标点类符号（行内标点保留）。只处理 cue 文本行，时间行/序号行不受影响。"""
    text = open(args.input, encoding="utf-8").read()
    out = []
    for ln in text.split("\n"):
        s = ln.strip()
        # 跳过空行、时间行(包含 -->)、序号行(纯数字)、WEBVTT 头
        if s and "-->" not in ln and not s.isdigit() and not s.startswith("WEBVTT"):
            out.append(clean_sub_text(ln))
        else:
            out.append(ln)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"OK -> {args.out}")


def cmd_subtitle(args):
    # 检查 ffmpeg 是否带 libass（ass filter）
    check = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                           capture_output=True, text=True)
    if " ass " not in check.stdout:
        sys.exit("本机 ffmpeg 未编译 libass，无法用 ass= 烧录字幕。"
                 "请改用 PIL 逐帧绘制方案（按 VTT cue 时间在对应帧上绘制/擦除字幕，"
                 "保证字幕与配音逐字一致且随时间出现/消失）。")
    vf = f"ass={os.path.abspath(args.subs)}"
    run(["ffmpeg", "-y", "-i", args.input, "-vf", vf, "-c:a", "copy", args.out])
    print(f"OK -> {args.out}")


def cmd_cover(args):
    vf = (f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,"
          f"pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")
    cover_seg = "._vt_cover.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-t", str(args.duration), "-i", args.image,
         "-vf", vf, "-r", "30", "-c:v", "libx264", cover_seg])
    run(["ffmpeg", "-y", "-i", cover_seg, "-i", args.video,
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-map", "1:a?", "-c:v", "libx264", "-c:a", "aac", args.out])
    os.remove(cover_seg)
    print(f"OK -> {args.out}")


def cmd_portrait(args):
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0B1026")
    run(["ffmpeg", "-y", "-i", args.input, "-vf", vf, "-c:a", "copy", args.out])
    print(f"OK -> {args.out}")


def cmd_info(args):
    print(f"duration: {probe_duration(args.input):.2f}s")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("frames", help="帧序列+配音 -> 视频")
    p.add_argument("--dir", required=True)
    p.add_argument("--audio", required=True)
    p.add_argument("--out", default="body.mp4")
    p.add_argument("--durations", help="逗号分隔的每帧停留秒数；缺省则均分配音时长")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--fps", type=int, default=30)
    p.set_defaults(func=cmd_frames)

    p = sub.add_parser("watermark", help="叠加左上角水印 作者：@Map")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=28)
    p.add_argument("--x", type=int, default=36)
    p.add_argument("--y", type=int, default=28)
    p.set_defaults(func=cmd_watermark)

    p = sub.add_parser("sub_clean", help="去除 VTT/SRT 每条字幕中所有句读/标点类符号")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_sub_clean)

    p = sub.add_parser("subtitle", help="烧录 SRT/ASS 字幕")
    p.add_argument("--input", required=True)
    p.add_argument("--subs", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_subtitle)

    p = sub.add_parser("cover", help="封面拼接为片头")
    p.add_argument("--image", required=True)
    p.add_argument("--video", required=True)
    p.add_argument("--out", default="head.mp4")
    p.add_argument("--duration", type=float, default=3.0)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.set_defaults(func=cmd_cover)

    p = sub.add_parser("portrait", help="横屏转竖屏 9:16")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_portrait)

    p = sub.add_parser("info", help="查看时长")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_info)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
