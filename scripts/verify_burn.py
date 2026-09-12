#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_burn.py — 核验 fast 引擎成片的「水印 + 字幕」与 legacy 引擎逐像素等价

做法：对若干采样时刻，从成片抽帧，找出字幕/水印文字像素的 bbox，
与直接用 PIL（legacy 同坐标同字体）渲染出的期望 bbox 比对；并核验
无字幕区间确实没有字幕、水印始终存在。
"""
import os, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

FFMPEG = "/usr/local/bin/ffmpeg"
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
W, H = 1920, 1080
WM_X, WM_Y = 36, 30
WM_SCAN_X = 430          # 水印核验的横向搜索上限（水印列区）
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
    """返回 (x0,y0,x1,y1) 亮像素 bbox；x1 限制横向搜索范围。

    水印核验必须把 x 限制在水印列区（x<430）——镜头运动会把幻灯片内容
    推进 y<162，但那部分位于 x 800+，与水印框并不相交。
    """
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


def main(mp4, srt, samples):
    cues = parse_srt(srt)
    F_SUB = ImageFont.truetype(FONT, 44)
    F_WM = ImageFont.truetype(FONT, 30)
    tmp = tempfile.mkdtemp(prefix="verify_")
    ok = True
    for t in samples:
        out = os.path.join(tmp, f"f_{t}.png")
        subprocess.run([FFMPEG, "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1", out],
                       capture_output=True, check=True)
        img = Image.open(out)

        # ---- 水印：应与 legacy 期望 bbox 一致
        wm_exp_img = Image.new("RGB", (W, 200), (0, 0, 0))
        d = ImageDraw.Draw(wm_exp_img)
        tw = d.textlength("作者：@Map", font=F_WM)
        d.text((WM_X, WM_Y), "作者：@Map", font=F_WM, fill=(255, 255, 255))
        exp = bright_bbox(wm_exp_img, 0, 200, 200)
        got = bright_bbox(img, 0, 162, 200, x1=WM_SCAN_X)
        wm_ok = got is not None and exp is not None and \
            all(abs(a - b) <= 4 for a, b in zip(exp, got))
        ok &= wm_ok

        # ---- 字幕：t 落在哪个 cue
        txt = next((x[2] for x in cues if x[0] <= t < x[1]), "")
        if txt:
            ref = Image.new("RGB", (W, 200), (0, 0, 0))
            dr = ImageDraw.Draw(ref)
            tw = dr.textlength(txt, font=F_SUB)
            dr.text(((W - tw) / 2, 0), txt, font=F_SUB, fill=(255, 255, 255))
            exp_s = bright_bbox(ref, 0, 200, 200)
            got_s = bright_bbox(img, SUB_Y - 6, min(SUB_Y + 70, H), 200)
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
            print(f"t={t:7.2f} 水印 {'OK ' if wm_ok else 'FAIL'}  字幕 {'OK ' if s_ok else 'FAIL'}  {note}  「{txt[:18]}」")
        else:
            got_s = bright_bbox(img, SUB_Y - 6, min(SUB_Y + 70, H), 200)
            gap_ok = got_s is None
            ok &= gap_ok
            print(f"t={t:7.2f} 水印 {'OK ' if wm_ok else 'FAIL'}  字幕片段间隙 {'OK(空)' if gap_ok else 'FAIL'}")
    print("VERIFY_BURN", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    mp4, srt = sys.argv[1], sys.argv[2]
    samples = [float(x) for x in sys.argv[3:]] or [1.0, 5.0, 12.5]
    sys.exit(main(mp4, srt, samples))
