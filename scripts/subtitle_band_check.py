#!/usr/bin/env python3
"""字幕带内容侵入门禁（固定规范第 15 条配套脚本 · 2026-10-25 新增）

背景（learnings.md L004）：封面 .hero 用 flex-end + padding-bottom 把文字推入
底部字幕带，人眼排版检查漏过，烧录后字幕与内容重叠。本脚本把「导帧后、烧录前
扫字幕带」产品化为确定性门禁：任何帧的字幕带区域出现非白像素即 FAIL。

判定口径（与 build 帧实测对齐）：
  - 字幕带硬门禁区：y 918~1001（1080p 高约 8%）；排除右下页码区 x>1800
  - 非白像素阈值：灰度 < 245（白底 #FFFFFF 通吃，允许压缩噪点）
  - 全帧清零才 exit 0；任一帧 FAIL 即 exit 1 并列出违规帧与像素数

用法：
  python3 subtitle_band_check.py build/frames            # 目录（page_*.png）
  python3 subtitle_band_check.py build/frames/page_01.png # 单帧
  python3 subtitle_band_check.py build/frames --band-top 918 --band-bottom 1001
"""
import argparse
import glob
import os
import sys

try:
    from PIL import Image
except ImportError:
    print("缺少 Pillow：pip install Pillow", file=sys.stderr)
    sys.exit(2)

BAND_TOP_DEFAULT = 918
BAND_BOTTOM_DEFAULT = 1001
PAGE_NUM_X_MIN = 1800          # 右下页码区右界，页码不计入侵入
NONWHITE_THRESHOLD = 245       # <245 视为有内容（白底通吃）
EXPECT_SIZE = (1920, 1080)


def check_frame(path, top, bottom):
    """返回 (violation_px, size)。size 异常时 violation_px 返回 None。"""
    im = Image.open(path).convert("L")
    if im.size != EXPECT_SIZE:
        return None, im.size
    w, h = im.size
    top = max(0, min(top, h))
    bottom = max(0, min(bottom, h))
    band = im.crop((40, top, PAGE_NUM_X_MIN, bottom))
    import numpy as np
    arr = np.asarray(band)
    return int((arr < NONWHITE_THRESHOLD).sum()), im.size


def main():
    ap = argparse.ArgumentParser(description="字幕带内容侵入门禁（固定规范第 15 条）")
    ap.add_argument("target", help="帧目录或单个 png")
    ap.add_argument("--band-top", type=int, default=BAND_TOP_DEFAULT)
    ap.add_argument("--band-bottom", type=int, default=BAND_BOTTOM_DEFAULT)
    a = ap.parse_args()

    if os.path.isdir(a.target):
        files = sorted(glob.glob(os.path.join(a.target, "page_*.png")))
        if not files:
            print(f"[FAIL] 目录无 page_*.png：{a.target}", file=sys.stderr)
            return 1
    else:
        files = [a.target]

    print(f"字幕带门禁：y[{a.band_top},{a.band_bottom}] x[40,{PAGE_NUM_X_MIN}) 非白阈值<{NONWHITE_THRESHOLD}")
    violations = []
    size_bad = []
    for f in files:
        px, size = check_frame(f, a.band_top, a.band_bottom)
        name = os.path.basename(f)
        if px is None:
            size_bad.append((name, size))
            print(f"  {name}: 尺寸异常 {size}（期望 {EXPECT_SIZE[0]}x{EXPECT_SIZE[1]}）")
        elif px == 0:
            print(f"  {name}: OK")
        else:
            violations.append((name, px))
            print(f"  {name}: FAIL 字幕带非白像素 {px}（内容侵入，典型陷阱：封面 hero flex-end+padding 推字入带）")

    print(f"\n共检 {len(files)} 帧：OK {len(files) - len(violations) - len(size_bad)} / "
          f"FAIL {len(violations)} / 尺寸异常 {len(size_bad)}")
    if size_bad or violations:
        print("[FAIL] 字幕带门禁未过——内容上移/缩小后重导帧复跑，不得带侵入进烧录", file=sys.stderr)
        return 1
    print("[PASS] 字幕带全净，可进入烧录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
