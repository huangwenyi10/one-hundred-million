#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_burn.py — 核验成片的「水印 + 字幕」烧录正确性（白底/彩底通用）

水印：固定坐标黑胶囊必须存在 + 胶囊内白字 bbox 与期望一致（位置锚定，背景无关）。
字幕：白字黑描边的「亮像素+暗邻接」bbox 与期望一致（描边锚定，背景无关）。
并核验无字幕区间确实没有字幕、水印全程存在。
"""
import os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

FFMPEG = "/usr/local/bin/ffmpeg"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
W, H = 1920, 1080
WM_X, WM_Y = 36, 30
# 2026-10-15 二次根治：废弃「扫描区内亮像素 bbox」方案——白底封面/读书营白底下
# 整片背景都是亮像素，bbox 必然被污染（误报三次：白底期、彩底标题带期、白封面期）。
# 改为两条与背景无关的检测：
#   · 水印 = 位置锚定：黑胶囊（fill=(0,0,0,92)，合成后亮度恒 ≤0.64×背景 ≤163）
#     必须存在于固定坐标，胶囊内亮像素(>230) bbox 须等于期望文字 bbox；
#   · 字幕 = 描边邻接：白字恒带 2px 黑描边（draw_subtitle 九宫格偏移），
#     「亮像素且 8 邻域含暗像素(<180)」即文字像素，白底裸背景因无暗邻被剔除。
WM_SCAN_X = 240
WM_SCAN_Y = 110
SUB_Y = 928
SUB_BAND_Y0 = 896


def parse_srt(path):
    cues = []
    with open(path, encoding="utf-8") as f:
        blocks = re.split(r'\n\n+', f.read().strip())
    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        ti = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        s, e = lines[ti].replace(" ", "").split("-->")
        def ts(x):
            hh, mm, ss = x.strip().replace(",", ".").split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        cues.append((ts(s), ts(e), "".join(lines[ti + 1:])))
    cues.sort()
    return cues


def bright_bbox(img, y0, y1, thr=200, x1=W):
    """返回 (x0,y0,x1,y1) 亮像素 bbox（仅用于黑底期望图）。"""
    px = img.convert("L").crop((0, y0, x1, y1)).load()
    w, h = x1, y1 - y0
    xs, ys = [], []
    for yy in range(h):
        for xx in range(w):
            if px[xx, yy] > thr:
                xs.append(xx); ys.append(yy)
    if not xs:
        return None
    return (min(xs), min(ys) + y0, max(xs), max(ys) + y0)


def text_bbox(img, y0, y1, thr=200, x1=W, dark_thr=180):
    """实拍帧上的文字像素 bbox：亮(>thr) 且 8 邻域含暗(<dark_thr)。

    白底/彩底通吃——白底裸背景四周皆亮被剔除；黑描边字幕（描边恒 0）与
    黑胶囊水印（合成亮度 ≤163）内的白字被保留。
    """
    g = img.convert("L")
    px = g.load()
    w, h = g.size
    X1, Y1 = min(x1, w), min(y1, h)
    xs, ys = [], []
    for yy in range(max(1, y0), min(Y1, h - 1)):
        for xx in range(1, min(X1, w - 1)):
            if px[xx, yy] <= thr:
                continue
            if (px[xx - 1, yy] < dark_thr or px[xx + 1, yy] < dark_thr or
                    px[xx, yy - 1] < dark_thr or px[xx, yy + 1] < dark_thr or
                    px[xx - 1, yy - 1] < dark_thr or px[xx + 1, yy - 1] < dark_thr or
                    px[xx - 1, yy + 1] < dark_thr or px[xx + 1, yy + 1] < dark_thr):
                xs.append(xx); ys.append(yy)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))  # 整图绝对坐标，无需回加 y0


def wm_expected_bbox(F_WM):
    """黑底期望图上的水印文字 bbox。"""
    wm_exp_img = Image.new("RGB", (W, 200), (0, 0, 0))
    d = ImageDraw.Draw(wm_exp_img)
    d.text((WM_X, WM_Y), "作者：@Map", font=F_WM, fill=(255, 255, 255))
    return bright_bbox(wm_exp_img, 0, WM_SCAN_Y, 200)


def wm_check(img, F_WM, exp):
    """水印核验：固定坐标黑胶囊存在 + 胶囊内白字 bbox == 期望。背景无关。"""
    g = img.convert("L")
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tw = d.textlength("作者：@Map", font=F_WM)
    x0, y0 = WM_X - 8, WM_Y - 6                 # 胶囊矩形（与 draw_watermark/render_wm_png 一致）
    x1, y1 = int(WM_X + tw + 8), WM_Y + 38
    cp = g.crop((x0, y0, x1, y1)).load()
    w, h = x1 - x0, y1 - y0
    n = w * h
    if n <= 0:
        return False
    ndark = 0
    xs, ys = [], []
    for yy in range(h):
        for xx in range(w):
            v = cp[xx, yy]
            if v < 190:
                ndark += 1
            elif v > 230:
                xs.append(xx); ys.append(yy)
    if ndark / n < 0.30 or not xs:              # 胶囊缺失（白底无胶囊=全亮）或文字缺失（彩底无胶囊=无字）
        return False
    got = (min(xs) + x0, min(ys) + y0, max(xs) + x0, max(ys) + y0)
    return exp is not None and all(abs(a - b) <= 6 for a, b in zip(exp, got))


def main(mp4, srt, samples):
    cues = parse_srt(srt)
    F_SUB = ImageFont.truetype(FONT, 44)
    F_WM = ImageFont.truetype(FONT, 30)
    tmp = tempfile.mkdtemp(prefix="verify_")
    # 默认采样点边界避让：烧录层（concat+fps+qtrle 字幕母版）对 cue 边界有
    # ±2 帧（≤~130ms）整帧量化偏置（实测有界、不累积；音频同步由 check_sync
    # 权威把关）。盲采样点若落在边界 ±0.25s 内，期望文本本身歧义 → 必 FAIL。
    # 故未显式给采样点时，自动选「距任一 cue 边界 ≥0.25s」的三个时刻
    #（早/中/晚各一）；显式传入的采样点仍按原样执行（靠近边界时打印提示）。
    if not samples:
        picks = []
        for frac in (0.08, 0.5, 0.92):
            t = frac * (cues[-1][1] if cues else 1.0)
            while any(abs(t - b) < 0.25 for c in cues for b in (c[0], c[1])):
                t += 0.05
            picks.append(round(t, 2))
        samples = picks
        print(f"[自动采样] 边界避让后: {samples}")
    ok = True
    for t in samples:
        near_bnd = any(abs(t - b) < 0.2 for c in cues for b in (c[0], c[1]))
        out = os.path.join(tmp, f"f_{t}.png")
        subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", out],
                       capture_output=True, check=True)
        img = Image.open(out)

        # ---- 水印：固定坐标黑胶囊 + 胶囊内白字 bbox（背景无关）
        exp = wm_expected_bbox(F_WM)
        wm_ok = wm_check(img, F_WM, exp)
        ok &= wm_ok

        # ---- 字幕：t 落在哪个 cue（描边邻接检测，背景无关）
        txt = next((x[2] for x in cues if x[0] <= t < x[1]), "")
        if txt:
            ref = Image.new("RGB", (W, 200), (0, 0, 0))
            dr = ImageDraw.Draw(ref)
            tw = dr.textlength(txt, font=F_SUB)
            dr.text(((W - tw) / 2, 0), txt, font=F_SUB, fill=(255, 255, 255))
            exp_s = bright_bbox(ref, 0, 200, 200)
            got_s = text_bbox(img, SUB_Y - 6, min(SUB_Y + 70, H))
            if exp_s is None:
                s_ok = True
                note = "blank(band-clean)"
            else:
                # 期望 bbox 的 x 区间与 y 偏移需与成片一致
                s_ok = got_s is not None and \
                    abs(exp_s[0] - got_s[0]) <= 6 and abs(exp_s[2] - got_s[2]) <= 6 and \
                    abs((exp_s[1] + SUB_Y) - got_s[1]) <= 6 and \
                    abs((exp_s[3] + SUB_Y) - got_s[3]) <= 6
                note = f"x[{got_s[0]},{got_s[2]}] y[{got_s[1]},{got_s[3]}]"
            ok &= s_ok
            bnd_note = "  [采样点靠近cue边界,FAIL或为量化偏置而非烧录错误]" if (near_bnd and not s_ok) else ""
            print(f"t={t:7.2f} 水印 {'OK ' if wm_ok else 'FAIL'}  字幕 {'OK ' if s_ok else 'FAIL'}  {note}  「{txt[:18]}」{bnd_note}")
        else:
            got_s = text_bbox(img, SUB_Y - 6, min(SUB_Y + 70, H))
            gap_ok = got_s is None
            ok &= gap_ok
            print(f"t={t:7.2f} 水印 {'OK ' if wm_ok else 'FAIL'}  字幕片段间隙 {'OK(空)' if gap_ok else 'FAIL'}")
    print("VERIFY_BURN", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    mp4, srt = sys.argv[1], sys.argv[2]
    # 未显式给采样点时传空列表 → main() 内按「边界避让」自动选点
    # （原 [1.0,5.0,12.5] 盲采样易踩 cue 边界，见 main() 内注释）
    samples = [float(x) for x in sys.argv[3:]]
    sys.exit(main(mp4, srt, samples))
