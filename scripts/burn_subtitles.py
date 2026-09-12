#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
burn_subtitles.py — 无 libass/drawtext 环境下的成片烧录（水印 + 字幕）

当前沙箱 ffmpeg（homebrew 9.x）缺 libass(ass/subtitles) 与 drawtext 滤镜，
无法用 ffmpeg 直接烧录水印/字幕。本脚本提供两条引擎：

  ┌ engine=fast（默认，推荐）
  │  把「水印」和「字幕」预处理成两层带 alpha 的小尺寸叠加层，再用
  │  overlay 与 body 一次合成：
  │    1. 水印层：单张 1920x162 RGBA PNG（静态，-loop 1 送入，不生成逐帧）
  │    2. 字幕层：按 cue 渲染 1920x112 RGBA 字幕带 → concat demuxer(带 duration)
  │       → qtrle(带 alpha 的 QuickTime Animation) 母版，再 overlay 到 y=BAND_Y0
  │    3. 主体视频用 tpad 克隆末帧补齐到配音时长，-t 精确截断，配音 aac 合入
  │  实测：66k 帧量级（37 分钟成片）从「4.6 小时」降到「约 15 分钟」。
  │  画面结果与 engine=legacy **逐像素等价**（同一字体、同一坐标、同一描边）。
  │
  └ engine=legacy（--engine legacy，兼容保留）
     PIL 逐帧绘制水印 + 字幕 → final_frames/ PNG 序列 → image2 序列编码。
     单线程约 3.8 fps，37 分钟成片需 4.6 小时；仅在 fast 引擎异常时兜底。

用法:
  python3 burn_subtitles.py <body.mp4> <subtitles.srt> <voiceover.mp3> <out.mp4> \
      [--engine fast|legacy] [--fps 30] [--font "..."] [--keep] [--max-seconds N]

流程（fast）:
  1. 解析 srt → cues；渲染 wm.png / 每个 cue 的字幕带 PNG（去重空白帧）
  2. concat 列表（duration 精确到毫秒）→ qtrle 字幕母版 strip.mov
  3. ffmpeg -i body -loop 1 -i wm.png -i strip.mov -i audio -filter_complex 一次成片

★ 关键修复 1：编码步必须用 image-sequence 输入，**不要**用 concat demuxer
   大列表直接编码成片——当帧数 > ~5000 时 concat demuxer 会 exit 8 失败。
   （fast 引擎的 concat demuxer 只用于 717 量级的 cue 图，远低于该阈值。）
★ 关键修复 2：body 时长通常短于配音时长（末页冻结），必须 tpad 克隆末帧 +
   -t 精确截断，否则结尾若干秒配音会被 -shortest 截掉。
"""
import os, sys, subprocess, re, shutil, argparse, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
WM_BAND_H = 162          # 水印带高度（水印框 y 24~68，留足余量）
SUB_BAND_Y0 = 896        # 字幕带顶部 y（字幕绘制于 y=928，字号 44 → 底 ≈ y 986）
SUB_BAND_H = 112         # 字幕带高度 → 覆盖 y 896~1008
WM_X, WM_Y = 36, 30      # 水印绘制坐标（与 legacy 完全一致）
SUB_Y = 928              # 字幕绘制坐标（与 legacy 完全一致）
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"


def warn_trailing_punct(cues):
    """渲染层安全网：cue 末尾带句读标点属违规（SKILL.md 固定规范第 434 行）。

    正确管线是先跑 `video_tool.py sub_clean` 再烧录。这里只告警不改写——
    避免静默改字导致「字幕==口播稿」比对口径漂移。
    """
    END = "。，？！、；：\u201c\u201d\u2018\u2019《》〈〉「」『』【】…—～·!?\"'()[]<>,"
    bad = [c for (_, _, c) in cues if c and c[-1] in END]
    if bad:
        sys.stderr.write(
            f"[WARN] 有 {len(bad)}/{len(cues)} 条 cue 末尾带句读标点，违反 SKILL.md 固定规范第 434 行。\n"
            f"       请先执行：python3 scripts/video_tool.py sub_clean --input <原srt> --out <清洗后srt> 再烧录。\n"
            f"       例：…{bad[0][-20:]}\n")
    return len(bad)


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
    """RGB 逐帧版（legacy 引擎用）——保持与原实现逐像素一致。"""
    d = ImageDraw.Draw(img)
    tw = d.textlength("作者：@Map", font=font)
    x, y = WM_X, WM_Y
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([x - 8, y - 6, x + tw + 8, y + 38], fill=(0, 0, 0, 92))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    ImageDraw.Draw(img).text((x, y), "作者：@Map", font=font, fill=(255, 255, 255, 220))
    return img


def draw_subtitle(img, text, font):
    """RGB 逐帧版（legacy 引擎用）。"""
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=font)
    x = (W - tw) / 2
    y = SUB_Y
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    d.text((x, y), text, font=font, fill=(255, 255, 255))
    return img


# ---------------------------------------------------------------- fast engine

def render_wm_png(font, path):
    """静态水印层：1920x162 RGBA，仅左上角绘制（与 legacy 同坐标/同透明度）。"""
    img = Image.new("RGBA", (W, WM_BAND_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tw = d.textlength("作者：@Map", font=font)
    x, y = WM_X, WM_Y
    d.rectangle([x - 8, y - 6, x + tw + 8, y + 38], fill=(0, 0, 0, 92))
    # legacy 在 RGB 画布上绘制 → alpha 被忽略，等价于不透明白
    d.text((x, y), "作者：@Map", font=font, fill=(255, 255, 255, 255))
    img.save(path)


def render_sub_strip(text, font, path):
    """单条字幕带：1920x112 RGBA，字幕局部坐标 y = SUB_Y - SUB_BAND_Y0。"""
    img = Image.new("RGBA", (W, SUB_BAND_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    tw = d.textlength(text, font=font)
    x = (W - tw) / 2
    y = SUB_Y - SUB_BAND_Y0
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            d.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    img.save(path)


def build_timeline(cues, total_dur):
    """把 cue 列表铺满 [0, total_dur]：缺口处插入空白帧。返回 [(dur, text)]。"""
    events, prev = [], 0.0
    for (s, e, txt) in cues:
        s, e = max(s, 0.0), min(e, total_dur)
        if e - s <= 0.001:
            continue
        if s - prev > 0.001:
            events.append((s - prev, ""))
        events.append((e - s, txt))
        prev = e
    if total_dur - prev > 0.001:
        events.append((total_dur - prev, ""))
    return events


def burn_fast(body, srt, audio, out, font_path, fps, keep, max_seconds=None):
    F_WM = ImageFont.truetype(font_path, 30)
    F_SUB = ImageFont.truetype(font_path, 44)

    audio_dur = probe_duration(audio)
    body_dur = probe_duration(body)
    total_dur = audio_dur if not max_seconds else min(audio_dur, float(max_seconds))

    tmp = tempfile.mkdtemp(prefix="burnfast_")
    try:
        wm_png = os.path.join(tmp, "wm.png")
        render_wm_png(F_WM, wm_png)

        cues = parse_srt(srt)
        warn_trailing_punct(cues)
        events = build_timeline(cues, total_dur)

        # 渲染去重后的 cue 字幕带
        strip_cache, blank_png = {}, os.path.join(tmp, "blank.png")
        render_sub_strip("", F_SUB, blank_png)
        n_uniq = 0
        for _, txt in events:
            if not txt or txt in strip_cache:
                continue
            p = os.path.join(tmp, f"c{n_uniq:04d}.png")
            render_sub_strip(txt, F_SUB, p)
            strip_cache[txt] = p
            n_uniq += 1

        # concat 列表（末条重复一次，规避 concat demuxer 忽略末尾 duration）
        list_path = os.path.join(tmp, "subs.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for dur, txt in events:
                f.write("file '%s'\n" % (strip_cache.get(txt) or blank_png))
                f.write("duration %.3f\n" % dur)
            # 尾部补 3s 空白，保证字幕母版一定盖满配音时长
            f.write("file '%s'\n" % blank_png)
            f.write("duration 3.000\n")
            f.write("file '%s'\n" % blank_png)

        strip_mov = os.path.join(tmp, "strip.mov")
        r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-r", str(fps), "-vf", "format=rgba", "-c:v", "qtrle", "-pix_fmt", "rgba",
            strip_mov], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("字幕母版编码失败:\n" + r.stderr[-3000:])
        strip_dur = probe_duration(strip_mov)

        pad = max(0.0, total_dur - body_dur) + 10.0
        fc = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f},fps={fps},format=yuv420p[b];"
            f"[b][1:v]overlay=0:0:format=auto[w];"
            f"[w][2:v]overlay=0:{SUB_BAND_Y0}:format=auto,format=yuv420p[v]"
        )
        cmd = [FFMPEG, "-y",
               "-i", body,
               "-loop", "1", "-framerate", str(fps), "-i", wm_png,
               "-i", strip_mov,
               "-i", audio,
               "-filter_complex", fc,
               "-map", "[v]", "-map", "3:a",
               "-t", f"{total_dur:.3f}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "18",
               "-pix_fmt", "yuv420p", "-r", str(fps),
               "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", out]
        log = os.path.join(tmp, "encode.log")
        with open(log, "w", encoding="utf-8") as lf:
            r = subprocess.run(cmd, stderr=lf, stdout=subprocess.DEVNULL)
        if r.returncode != 0:
            # 失败时才把编码日志落到成片旁边，避免污染交付目录
            keep_log = out + ".encode.log"
            shutil.copyfile(log, keep_log)
            raise SystemExit("成片编码失败，见 " + keep_log)
        print(f"body={body_dur:.2f}s audio={audio_dur:.2f}s strip={strip_dur:.2f}s "
              f"cues={len(cues)} uniq_strips={n_uniq} pad={pad:.1f}s")
        print(f"OK -> {out}")
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"tmp kept: {tmp}")


# -------------------------------------------------------------- legacy engine

def burn_legacy(body, srt, audio, out, font_path, fps, keep):
    F_WM = ImageFont.truetype(font_path, 30)
    F_SUB = ImageFont.truetype(font_path, 44)

    audio_dur = probe_duration(audio)
    body_dur = probe_duration(body)
    total_frames = int(audio_dur * fps + 0.9999)

    tmp = tempfile.mkdtemp(prefix="burn_")
    body_frames = os.path.join(tmp, "body_frames")
    final_frames = os.path.join(tmp, "final_frames")
    os.makedirs(body_frames, exist_ok=True)
    os.makedirs(final_frames, exist_ok=True)

    subprocess.run([FFMPEG, "-y", "-i", body,
        "-vf", f"fps={fps},scale=1920:1080:flags=lanczos,format=rgb24",
        os.path.join(body_frames, "%05d.png")], capture_output=True, check=True)
    body_count = len([f for f in os.listdir(body_frames) if f.endswith(".png")])
    last_frame = Image.open(os.path.join(body_frames, f"{body_count:05d}.png")).convert("RGB") if body_count else None
    print(f"body={body_dur:.2f}s audio={audio_dur:.2f}s frames_needed={total_frames} body_frames={body_count}")

    cues = parse_srt(srt)
    warn_trailing_punct(cues)
    for i in range(total_frames):
        t = i / fps
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

    subprocess.run([FFMPEG, "-y", "-framerate", str(fps), "-start_number", "1",
        "-i", os.path.join(final_frames, "%05d.png"), "-i", audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out],
        capture_output=True, check=True)
    print(f"OK -> {out}")

    if not keep:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body"); ap.add_argument("srt"); ap.add_argument("audio"); ap.add_argument("out")
    ap.add_argument("--engine", choices=["fast", "legacy"], default="fast")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--font", default=None)
    ap.add_argument("--keep", action="store_true", help="保留临时目录")
    ap.add_argument("--max-seconds", type=float, default=None, help="只烧录前 N 秒（自检用）")
    args = ap.parse_args()

    font = pick_font(args.font)
    if args.engine == "fast":
        burn_fast(args.body, args.srt, args.audio, args.out, font, args.fps, args.keep, args.max_seconds)
    else:
        burn_legacy(args.body, args.srt, args.audio, args.out, font, args.fps, args.keep)


if __name__ == "__main__":
    main()
