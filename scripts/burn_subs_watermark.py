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
# 单行最大字数。字幕带只有画面高度 88%~95% 共 76px，只放得下一行 46px 字；
# 一旦折成两行，顶部会越过 88% 上界压住幻灯片内容（实测压到「据原书 P.N 重绘」
# 出处标注行）。实测三部字幕最长 32~47 字，故默认 34：绝大多数保持单行。
SUB_WRAP = 34
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
    """解析 SRT → [(start, end, text)]（秒，text 已合并多行）。

    ★ 2026-10-07 修复：改为「按时间行锚定扫全文」，不再按空行分块。
    【实测踩到的两个坑】旧实现对以下两类文件都只能解析出**1 条**（把全文当成
    一行文本），导致字幕层完全错乱：
      1. **CRLF 行尾**：`split("\\n")` 切出的每行尾部残留 `\\r`，使
         `len(lines) >= 2 and "-->" in lines[1]` 判断落空。
      2. **cue 之间没有空行**：本机三部 Vue 成片的 subtitles_clean.srt /
         subtitles.srt 是「序号行 + 时间行 + 文本行」直接换行、**块间无空行**
         （疑似某次用 '\\n'.join 拼回时把空行丢了）。
    现在逐行找 `-->` 锚点，再向下收集到下一个序号/时间/空行为止，两种格式都能解析。
    """
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read().replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")
    tline = re.compile(
        r"^(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*$")
    items = []
    i = 0
    while i < len(lines):
        m = tline.match(lines[i].strip())
        if not m:
            i += 1
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        j = i + 1
        txt = []
        while j < len(lines):
            t = lines[j].strip()
            if not t or t.isdigit() or tline.match(t):
                break
            txt.append(t)
            j += 1
        if txt:
            items.append((start, end, "".join(txt)))
        i = j
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
        lines = wrap_text(sub_text)
        lh = SUB_FONT_SIZE + 12
        y = SUB_BOTTOM - lh * len(lines)
        for ln in lines:
            burn_text_line(dr, ln, sub_font, y, stroke=SUB_STROKE)
            y += lh
    im.save(dst, "PNG")
    return dst


def wrap_text(text, width=SUB_WRAP):
    """按最大字数折行（见 SUB_WRAP 处说明：两行会越过字幕带压住内容）。"""
    lines, cur = [], ""
    for ch in text:
        if len(cur) >= width:
            lines.append(cur)
            cur = ""
        cur += ch
    if cur:
        lines.append(cur)
    return lines


def render_overlay(dst, sub_text, wm_font, sub_font, wrap=SUB_WRAP):
    """生成**透明字幕+水印层**（RGBA），供 ffmpeg overlay 叠加到已合成的视频。

    ★ 为什么需要透明层而不是把字幕烧进静态帧：
    带 Ken Burns 动效的成片，其画面随时间缩放位移，无法用「一页一图」的方式预先
    烧字幕（Pillow 烧帧 = 动效丢失，实测成片内容区 0.5s 间隔像素完全相同）。
    故改为：body（无字幕带动效） + 透明字幕层 → ffmpeg overlay 叠加。
    配套脚本：同目录 overlay_subs.py
    """
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.text(WM_POS, WM_TEXT, font=wm_font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255))
    if sub_text:
        lines = wrap_text(sub_text, wrap)
        lh = SUB_FONT_SIZE + 12
        y = SUB_BOTTOM - lh * len(lines)
        for ln in lines:
            try:
                bb = dr.textbbox((0, 0), ln, font=sub_font, stroke_width=SUB_STROKE)
                tw = bb[2] - bb[0]
            except Exception:
                tw = len(ln) * SUB_FONT_SIZE
            dr.text(((W - tw) // 2, y), ln, font=sub_font, fill=(255, 255, 255, 255),
                    stroke_width=SUB_STROKE, stroke_fill=(0, 0, 0, 255))
            y += lh
    im.save(dst, "PNG")
    return dst


def export_overlays(srt, out_dir, sub_font, wm_font, wrap=SUB_WRAP, limit=None):
    """按 cue 导出透明层 + concat 清单，返回 (cue数, 清单路径, 覆盖时长)。

    `limit` = 视频总长（秒）。**字幕轴与视频轴常不等长**——实测上篇字幕轴2243.2s
    而 body 视频只有 2218.8s（差 24.4s）。不裁剪的话 overlay 会以更长的那条为准，
    把视频末尾拉长并卡住最后一帧。故必须裁到与视频**逐帧等长**。
    """
    cues = parse_srt(srt)
    if not cues:
        raise SystemExit(f"ERROR: 字幕解析为空: {srt}")
    if limit:
        cues = [c for c in cues if c[0] < limit - 0.05]
        cues = [(a, min(b, limit), t) for a, b, t in cues]
        # ★ 字幕轴可能**短于**视频轴（原始字幕文件的缺陷，不是本脚本的 bug）。
        #   实测中篇：字幕止于 2376.22s，而音频/视频到 2391.41s → 末段有 15.2 秒
        #   语音完全没有字幕。若不补，overlay 输入比视频短 → 该区间画面无字幕。
        #   补法：把**最后一条字幕延续**到视频结尾（末段多为收口一句，重复显示
        #   比留空白更符合观感），并在日志里显式报告补了多少秒。
        if cues and limit - cues[-1][1] > 0.5:
            tail = limit - cues[-1][1]
            print(f"  ⚠ 字幕止于 {cues[-1][1]:.2f}s，比视频短 {tail:.2f}s；"
                  f"末条字幕延续至 {limit:.2f}s")
            cues.append((cues[-1][1], limit, cues[-1][2]))
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for idx, (c0, c1, tx) in enumerate(cues):
        render_overlay(os.path.join(out_dir, f"s_{idx:05d}.png"), tx,
                       wm_font, sub_font, wrap)
        items.append({"file": f"s_{idx:05d}.png", "start": c0, "end": c1,
                      "dur": c1 - c0})
    # 补齐cue 之间的空档：用前一条字幕延续，避免出现无字幕画面
    filled = []
    prev_end = 0.0
    for it in items:
        if it["start"] > prev_end + 0.05:
            filled.append({"file": filled[-1]["file"] if filled else items[0]["file"],
                           "start": prev_end, "end": it["start"],
                           "dur": it["start"] - prev_end})
        filled.append(it)
        prev_end = max(prev_end, it["end"])

    # ★ 清单必须写**绝对路径**：concat demuxer 解析相对路径时以「清单文件所在
    #   目录」为基准，而脚本运行时的 cwd 未必等于它 → "No such file or directory"。
    out_abs = os.path.abspath(out_dir)
    lines = []
    for it in filled:
        lines.append(f"file '{os.path.join(out_abs, it['file'])}'")
        lines.append(f"duration {it['dur']:.3f}")
    if filled:
        lines.append(f"file '{os.path.join(out_abs, filled[-1]['file'])}'")
    lst = os.path.join(out_abs, "overlay_concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return len(cues), lst, sum(it["dur"] for it in filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", help="原始帧目录（page_NNN.png）；mode=burn 时必填")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--build", required=True, help="含 segments_durations.json 与 srt")
    ap.add_argument("--slice", type=float, default=1.0,
                    help="字幕切片间隔（秒）；1.0 表示每秒一张")
    ap.add_argument("--only", help="只处理这些页（逗号分隔）")
    ap.add_argument("--mode", choices=("burn", "overlay"), default="burn",
                    help="burn=把字幕烧进静态帧（无动效视频用）；"
                         "overlay=导出透明字幕层+concat 清单（**带动效**视频用，"
                         "配套 overlay_subs.py）")
    ap.add_argument("--srt", help="指定字幕文件（默认按 fixed→clean→srt 自动找）")
    ap.add_argument("--video-duration", type=float,
                    help="mode=overlay 时视频总长；字幕层据此裁剪到逐帧等长")
    ap.add_argument("--wrap", type=int, default=SUB_WRAP, help="单行最大字数")
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

    srt = a.srt
    if not srt:
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

    if a.mode == "overlay":
        if not a.video_duration:
            print("ERROR: mode=overlay 需要 --video-duration（把字幕轴裁到与视频"
                  "逐帧等长，否则 overlay 会拉长片尾并卡住最后一帧）",
                  file=sys.stderr)
            return 1
        n, lst, total = export_overlays(srt, a.out, sub_font, wm_font,
                                        a.wrap, a.video_duration)
        print(f"overlay 模式：cue {n} 条 → 切片，覆盖 {total:.2f}s"
              f"（目标 {a.video_duration:.2f}s）")
        if abs(total - a.video_duration) > 0.5:
            print(f"  ⚠ 差 {total - a.video_duration:+.2f}s，overlay 可能拉长/截断",
                  file=sys.stderr)
            return 2
        print(f"  清单: {lst}")
        print(f"  换行宽度 {a.wrap} 字")
        return 0

    if not a.frames:
        print("ERROR: mode=burn 需要 --frames", file=sys.stderr)
        return 1

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
