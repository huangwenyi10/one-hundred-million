#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
burn_subtitles.py — 无 libass/drawtext 环境下的成片烧录（PIL 逐帧）

当前沙箱 ffmpeg 缺 libass 与 drawtext 滤镜，无法用 ffmpeg 直接烧录
水印/字幕。本脚本用 PIL 逐帧绘制左上角水印(作者：@Map) + 底部字幕，
再编码成片。

用法:
  python3 burn_subtitles.py <body.mp4> <subtitles.srt> <voiceover.mp3> <out.mp4> \
      [--fps 30] [--font "/System/Library/Fonts/Hiragino Sans GB.ttc"] [--keep]

流程:
  1. 提取 body.mp4 帧到临时目录(body_frames/)
  2. 逐帧绘制水印 + 按 cue 时间绘制字幕 -> final_frames/
  3. 用 image2 序列(-framerate -i %05d.png)编码成片，末帧冻结补齐音频时长

★ 关键修复：编码步必须用 image-sequence 输入，**不要**用 concat demuxer
  大列表——当帧数 > ~5000 时 concat demuxer 会 exit 8 失败（本脚本已规避）。
"""
import os, sys, subprocess, re, shutil, argparse, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"


def pick_font(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    raise SystemExit("找不到可用的中文字体，请用 --font 指定")


def probe_duration(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def parse_srt(path):
    cues = []
    with open(path, encoding="utf-8") as f:
        blocks = re.split(r'\n\n+', f.read().strip())
    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        ti = None
        for k, l in enumerate(lines):
            if "-->" in l:
                ti = k; break
        if ti is None:
            continue
        t = lines[ti].replace(" ", "")
        s, e = t.split("-->")
        def ts(x):
            x = x.strip().replace(",", ".")
            hh, mm, ss = x.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        text = "".join(lines[ti + 1:])
        cues.append((ts(s), ts(e), text))
    cues.sort()
    return cues


def draw_watermark(img, font):
    d = ImageDraw.Draw(img)
    tw = d.textlength("作者：@Map", font=font)
    x, y = 36, 30
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([x - 8, y - 6, x + tw + 8, y + 38], fill=(0, 0, 0, 92))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    ImageDraw.Draw(img).text((x, y), "作者：@Map", font=font, fill=(255, 255, 255, 220))
    return img


def draw_subtitle(img, text, font):
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=font)
    x = (W - tw) / 2
    y = 928
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=(255, 255, 255))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body"); ap.add_argument("srt"); ap.add_argument("audio"); ap.add_argument("out")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font", default=None)
    ap.add_argument("--keep", action="store_true", help="保留临时帧目录")
    args = ap.parse_args()

    font = pick_font(args.font)
    F_WM = ImageFont.truetype(font, 30)
    F_SUB = ImageFont.truetype(font, 44)
    FPS = args.fps

    audio_dur = probe_duration(args.audio)
    body_dur = probe_duration(args.body)
    total_frames = int(audio_dur * FPS + 0.9999)

    tmp = tempfile.mkdtemp(prefix="burn_")
    body_frames = os.path.join(tmp, "body_frames")
    final_frames = os.path.join(tmp, "final_frames")
    os.makedirs(body_frames, exist_ok=True)
    os.makedirs(final_frames, exist_ok=True)

    # 1) 提取 body 帧
    subprocess.run([FFMPEG, "-y", "-i", args.body,
        "-vf", f"fps={FPS},scale=1920:1080:flags=lanczos,format=rgb24",
        os.path.join(body_frames, "%05d.png")], capture_output=True, check=True)
    body_count = len([f for f in os.listdir(body_frames) if f.endswith(".png")])
    last_frame = Image.open(os.path.join(body_frames, f"{body_count:05d}.png")).convert("RGB") if body_count else None
    print(f"body={body_dur:.2f}s audio={audio_dur:.2f}s frames_needed={total_frames} body_frames={body_count}")

    cues = parse_srt(args.srt)
    # 2) 逐帧绘制
    for i in range(total_frames):
        t = i / FPS
        text = ""
        for (s, e, txt) in cues:
            if s <= t < e:
                text = txt
                break
        if i + 1 <= body_count:
            img = Image.open(os.path.join(body_frames, f"{i + 1:05d}.png")).convert("RGB")
        else:
            img = last_frame.copy()
        img = draw_watermark(img, F_WM)
        if text:
            img = draw_subtitle(img, text, F_SUB)
        img.save(os.path.join(final_frames, f"{i + 1:05d}.png"))
        if (i + 1) % 1000 == 0:
            print(f"  rendered {i + 1}/{total_frames}")

    # 3) image-sequence 编码（勿用 concat demuxer 大列表）
    subprocess.run([FFMPEG, "-y", "-framerate", str(FPS), "-start_number", "1",
        "-i", os.path.join(final_frames, "%05d.png"), "-i", args.audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", args.out],
        capture_output=True, check=True)
    print(f"OK -> {args.out}")

    if not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
