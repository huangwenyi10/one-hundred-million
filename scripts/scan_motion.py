#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_motion.py — 运动后安全区复核（在未烧字幕的 body 上跑）

scan_zones.py 只扫「静态帧」；镜头运动（perspective 亚像素位移）会让画面
内容上下漂移，可能把内容推进左上角水印区或底部字幕带。本脚本按固定间隔
从视频抽样，只抽两块区域（水印列区 / 字幕带）做像素判定：

  A. 水印列区 x∈[0,430], y∈[0,162]：亮度>190 的像素必须落在水印文字框内
     （x 22~231, y 18~74）。框外出现亮像素 = 幻灯片内容侵入水印。
  B. 字幕带 y∈[918,1000]：出现亮度>135 的像素即视为内容侵入
     （body 尚未烧字幕，此带应为纯暗背景）。

用法: python3 scan_motion.py <body.mp4> [sample_seconds=2]
"""
import os, subprocess, sys, tempfile
from PIL import Image

FFMPEG = "/usr/local/bin/ffmpeg"
WM_BOX = (22, 18, 231, 74)      # 水印可占区（文字框 + 6px 余量）
WM_SCAN = (430, 162)            # 水印列区裁切尺寸
SUB_Y0, SUB_H = 918, 82         # 字幕带裁切


def main():
    video = sys.argv[1]
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    tmp = tempfile.mkdtemp(prefix="zscan_")
    a = os.path.join(tmp, "wm_%05d.png")
    b = os.path.join(tmp, "sub_%05d.png")
    fc = (f"[0:v]fps=1/{step},split=2[x][y];"
          f"[x]crop={WM_SCAN[0]}:{WM_SCAN[1]}:0:0[o1];"
          f"[y]crop=1920:{SUB_H}:0:{SUB_Y0}[o2]")
    r = subprocess.run([FFMPEG, "-y", "-i", video, "-filter_complex", fc,
                        "-map", "[o1]", a, "-map", "[o2]", b],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("抽帧失败:\n" + r.stderr[-2000:])

    wm_files = sorted(f for f in os.listdir(tmp) if f.startswith("wm_"))
    bad_wm, bad_sub = [], []
    for f in wm_files:
        idx = f[3:8]
        im = Image.open(os.path.join(tmp, f)).convert("L")
        p = im.load()
        out = 0
        for y in range(WM_SCAN[1]):
            for x in range(WM_SCAN[0]):
                if p[x, y] > 190 and not (WM_BOX[0] <= x <= WM_BOX[2] and WM_BOX[1] <= y <= WM_BOX[3]):
                    out += 1
        if out:
            bad_wm.append((f, out))
        im2 = Image.open(os.path.join(tmp, f"sub_{idx}.png")).convert("L")
        p2 = im2.load()
        hits = 0
        for y in range(SUB_H):
            for x in range(0, 1920, 2):
                if p2[x, y] > 135:
                    hits += 1
        if hits:
            bad_sub.append((f, hits))

    print(f"抽样 {len(wm_files)} 帧（每 {step}s 一帧，源 {video}）")
    print(f"水印列区框外亮像素异常帧: {len(bad_wm)}" + (f"  例: {bad_wm[:5]}" if bad_wm else ""))
    print(f"字幕带内容侵入帧:        {len(bad_sub)}" + (f"  例: {bad_sub[:5]}" if bad_sub else ""))
    print("PASS" if not bad_wm and not bad_sub else "FAIL")


if __name__ == "__main__":
    main()
