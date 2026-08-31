# -*- coding: utf-8 -*-
"""
render_subs2.py — 按 cue 时间把字幕烧到对应页帧，拼接+配音+水印 → 成片.mp4
读书训练营·书墨棕主题。字幕单行白字、固定底部安全区（y≈930），不遮挡内容。
用法: python3 render_subs2.py <build_dir> <out_mp4> [voice zh-CN-YunxiNeural]
"""
import os, sys, json, importlib.util, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
F_SUB = ImageFont.truetype(FONT_PATH, 44) if os.path.exists(FONT_PATH) else ImageFont.load_default()
FFMPEG = "/usr/local/bin/ffmpeg"


def load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def parse_srt(path):
    cues = []
    with open(path, encoding="utf-8") as f:
        blocks = f.read().strip().split("\n\n")
    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        # 找时间轴行
        ti = None
        for k, l in enumerate(lines):
            if "-->" in l:
                ti = k
                break
        if ti is None:
            continue
        t = lines[ti].replace(" ", "")
        s, e = t.split("-->")
        def to_sec(x):
            x = x.strip().replace(",", ".")
            hh, mm, ss = x.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        text = "".join(lines[ti + 1:])
        cues.append((round(to_sec(s), 3), round(to_sec(e), 3), text))
    cues.sort()
    return cues


def draw_subtitle(img, text):
    d = ImageDraw.Draw(img)
    # 描边增强可读性
    tw = d.textlength(text, font=F_SUB)
    x = (W - tw) / 2
    y = 928
    for dx in (-2, 0, 2):
        for dy in (-2, 0, 2):
            d.text((x + dx, y + dy), text, font=F_SUB, fill=(0, 0, 0))
    d.text((x, y), text, font=F_SUB, fill=(255, 255, 255))
    return img


WATERMARK = "作者：@Map"


def draw_watermark(img):
    """用 PIL 烧录左上角作者标识（ffmpeg 该环境未编入 drawtext 滤镜，故在画面层做）。"""
    f = load_font(30)
    d = ImageDraw.Draw(img)
    tw = d.textlength(WATERMARK, font=f)
    x, y = 36, 30
    # 半透明黑底（alpha 合成，兼容 RGB 帧）
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([x - 8, y - 6, x + tw + 8, y + 38], fill=(0, 0, 0, 92))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    ImageDraw.Draw(img).text((x, y), WATERMARK, font=f, fill=(255, 255, 255, 220))
    return img


def main():
    build_dir = os.path.abspath(sys.argv[1])
    out_mp4 = sys.argv[2]
    frames_dir = os.path.join(build_dir, "frames")
    dur_path = os.path.join(build_dir, "segments_durations.json")
    srt_path = os.path.join(build_dir, "subtitles.srt")
    vo_path = os.path.join(build_dir, "voiceover.mp3")

    with open(dur_path, encoding="utf-8") as f:
        dur = json.load(f)
    starts, ends = dur["starts"], dur["ends"]
    cues = parse_srt(srt_path)

    sub_frames_dir = os.path.join(build_dir, "sub_frames")
    os.makedirs(sub_frames_dir, exist_ok=True)

    seg_files = []
    idx = 0
    for pi in range(len(starts)):
        base = draw_watermark(Image.open(os.path.join(frames_dir, f"page_{pi:02d}.png")).convert("RGB"))
        s, e = starts[pi], ends[pi]
        page_cues = [c for c in cues if s <= c[0] < e]
        cur = s
        for (cs, ce, txt) in page_cues:
            if cs > cur + 0.05:
                emit(sub_frames_dir, seg_files, base, None, cs - cur, idx); idx += 1
            dur_c = max(0.2, ce - cs)
            emit(sub_frames_dir, seg_files, base, txt, dur_c, idx); idx += 1
            cur = ce
        if cur < e - 0.05:
            emit(sub_frames_dir, seg_files, base, None, e - cur, idx); idx += 1

    # concat 列表（image2 + duration）
    concat = os.path.join(build_dir, "subs_concat.txt")
    with open(concat, "w") as f:
        for fp, d in seg_files:
            f.write(f"file '{fp}'\nduration {d:.3f}\n")
    body = os.path.join(build_dir, "body.mp4")
    # ffmpeg 9.x 用 -fps_mode 取代已移除的 -vsync；旧版本兼容写法放在后一条。
    r1 = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
                         "-fps_mode", "vfr", "-pix_fmt", "yuv420p", "-r", "30", body],
                        capture_output=True)
    if r1.returncode != 0:
        # 退回兼容：-r 30 默认 cfr 同样可正确按 duration 生成帧
        r1 = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat,
                             "-pix_fmt", "yuv420p", "-r", "30", body],
                            capture_output=True)
    if r1.returncode != 0:
        sys.stderr.write(r1.stderr.decode(errors="replace")[:2000] + "\n")
        sys.exit(1)
    # 配音 + 水印（水印已用 PIL 烧入画面，此处直接合成音视频出片）
    r2 = subprocess.run([FFMPEG, "-y", "-i", body, "-i", vo_path, "-c:v", "libx264",
                         "-c:a", "aac", "-shortest", out_mp4], capture_output=True)
    if r2.returncode != 0:
        sys.stderr.write(r2.stderr.decode(errors="replace")[:2000] + "\n")
        sys.exit(1)
    print(f"OK: 成片 -> {out_mp4}")


def emit(sub_frames_dir, seg_files, base, txt, duration, idx):
    img = base.copy()
    if txt:
        draw_subtitle(img, txt)
    fp = os.path.join(sub_frames_dir, f"f{idx:05d}.png")
    img.save(fp)
    seg_files.append((fp, duration))


if __name__ == "__main__":
    main()
