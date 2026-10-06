#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""burn_subs_watermark.py -- 在帧图片上烧字幕与水印（不依赖 ffmpeg 的 libass）

**为什么需要这个脚本**：本机 ffmpeg 9.0.1 编译时未带 libass / drawtext
（`ffmpeg -version | grep libass` 为空，滤镜列表里也没有 subtitles/ass），
所以字幕**无法用 ffmpeg 烧录**。而字幕是交付硬门槛（固定规范第15 条），
故改用 Pillow 在**导帧阶段**就把字幕与水印画进图片。

烧录内容（与原成片一致）：
- 字幕：白字 + 黑描边，底部居中，落在字幕带（画面高度 88%~95%）
- 水印：「作者：@Map」左上角（x 0~25% × y 0~15% 安全区内）

关键点：
- **一帧一字幕**：视频每段配音对应一页幻灯片，字幕随时间变化。因此不能
  只在静态图上烧一次——**按字幕 cue 逐帧切片**，每片烧对应时刻的字幕。
  即：对每页幻灯片，按该页时间区间内的 cue 生成多张图。
- 帧命名 `page_<页号>_<序号>.png`，供 compose_final 按 duration 引用。
"""
import argparse
import os
import re
import sys
import time
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
# 字幕带位置（固定规范第 15 条：y 88%~95%）
SUB_BOTTOM = int(H * 0.955)
SUB_FONT_SIZE = 46
SUB_STROKE = 4
# 水印（左上角安全区）
WM_TEXT = "作者：@Map"
WM_FONT_SIZE = 30
WM_POS = (36, 30)
# 字体候选（macOS自带，按优先级）
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]


# 供 mux_final.py 复用
ABITRATE = "95k"
ASRATE = 24000
FPS = 30


def load_font(size, index=0):
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size, index=index)
            except Exception:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    raise SystemExit("ERROR: 未找到可用中文字体")


def parse_srt(path):
    """解析 SRT → [(start, end, text)]（秒，text 已合并多行）。"""
    raw = open(path, encoding="utf-8-sig").read()
    items = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for b in blocks:
        lines = [x.strip() for x in b.strip().split("\n") if x.strip()]
        if len(lines) >= 2 and "-->" in lines[1]:
            m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)",
                         lines[1])
            if not m:
                continue
            g = [int(x) for x in m.groups()]
            start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            text = "".join(lines[2:]).strip()
            items.append((start, end, text))
    return items


def burn_text_line(draw, text, font, y, stroke=0, fill=(255, 255, 255)):
    """把一行文字水平居中画在 y 处（y 为文字顶部）。"""
    if not text:
        return
    try:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(text) * SUB_FONT_SIZE
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=fill,
              stroke_width=stroke, stroke_fill=(0, 0, 0) if stroke else None)


def burn_one(src, dst, sub_text, wm=True, sub_font=None, wm_font=None):
    im = Image.open(src).convert("RGB")
    dr = ImageDraw.Draw(im)
    if wm:
        dr.text(WM_POS, WM_TEXT, font=wm_font, fill=(255, 255, 255),
                stroke_width=2, stroke_fill=(0, 0, 0))
    if sub_text:
        # 底部对齐到字幕带，必要时换行
        lines = []
        cur = ""
        for ch in sub_text:
            if len(cur) >= 26:
                lines.append(cur)
                cur = ""
            cur += ch
        if cur:
            lines.append(cur)
        lh = SUB_FONT_SIZE + 12
        y = SUB_BOTTOM - lh * len(lines)
        for ln in lines:
            burn_text_line(dr, ln, sub_font, y, stroke=SUB_STROKE)
            y += lh
    im.save(dst, "PNG")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True, help="原始帧目录（page_NNN.png）")
    ap.add_argument("--out", required=True, help="输出目录（page_NNN_K.png）")
    ap.add_argument("--build", required=True, help="含 segments_durations.json 与 srt")
    ap.add_argument("--slice", type=float, default=1.0,
                    help="字幕切片间隔（秒）；1.0 表示每秒一张")
    ap.add_argument("--only", help="只处理这些页（逗号分隔）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import json
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
    if not srt:
        print("ERROR: 未找到字幕文件", file=sys.stderr)
        return 1
    cues = parse_srt(srt)
    print(f"字幕 {len(cues)} 条 · 帧 {len(durations)} 页")
    if not cues:
        return 1

    sub_font = load_font(SUB_FONT_SIZE, index=1)
    wm_font = load_font(WM_FONT_SIZE, index=1)

    files = sorted(f for f in os.listdir(a.frames) if f.endswith(".png"))
    targets = list(range(1, len(files) + 1))
    if a.only:
        targets = [int(x) for x in a.only.split(",") if x.strip()]

    if a.dry_run:
        for i in targets[:3]:
            s0, s1 = starts[i - 1], starts[i - 1] + durations[i - 1]
            n = max(1, int(durations[i - 1] / a.slice))
            print(f"  P{i:03d} {s0:.0f}~{s1:.0f}s → {n} 张")
        return 0

    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    total = 0
    manifest = []
    for i in targets:
        src = os.path.join(a.frames, files[i - 1])
        s0 = starts[i - 1]
        dur = durations[i - 1]
        n = max(1, int(dur / a.slice))
        for k in range(n):
            t = s0 + (k + 0.5) * dur / n        # 该切片的中点时刻
            txt = ""
            for c0, c1, tx in cues:
                if c0 <= t < c1:
                    txt = tx
                    break
            dst = os.path.join(a.out, f"page_{i:03d}_{k:03d}.png")
            burn_one(src, dst, txt, wm=True, sub_font=sub_font, wm_font=wm_font)
            total += 1
        manifest.append({"page": i, "slices": n, "duration": round(dur, 3)})
        if i % 10 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] 已生成 {total} 张（{time.time()-t0:.0f}s）")

    with open(os.path.join(a.out, "slices.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n完成：{total} 张 → {a.out}（{time.time()-t0:.0f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
