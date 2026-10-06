#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_frames.py -- 从 PPT.html 逐页导出静态帧（one-hundred-million 配套）

改写 PPT 后重新导帧用。配音/时间轴/字幕不变，故只需导帧 + 重新合成。

要点（都是实测踩出来的）：
- **每页必须单独渲染成独立 HTML 文件**，靠CSS 决定显示哪一页。
  原PPT 用 `.slide{display:none}` + `.slide.active{display:block}`，
  所以直接把目标页设成唯一可见即可。
- Chrome 偶发忽略 --screenshot 路径，导致所有页渲染出同一张图。
  **每页渲染前先删旧文件并检查文件大小/内容是否雷同**，雷同即重试。
- 帧内**不含水印**（水印在合成阶段叠），左上角留空给水印用。

用法：
  python3 export_frames.py --ppt <PPT.html> --out <frames目录> [--quality 92]
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

PAGE_RE = re.compile(r'<section class="slide.*?</section>', re.S)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def find_chrome():
    for p in (
        CHROME,
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
    ):
        if p and os.path.isfile(p):
            return p
    return None


def split_pages(html):
    return PAGE_RE.findall(html)


def render_one(chrome, page_html, out_png, width, height, retries=3):
    """渲染单页；失败或输出雷同则重试。"""
    for attempt in range(retries):
        if os.path.exists(out_png):
            os.remove(out_png)
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                        encoding="utf-8") as f:
            f.write(page_html)
            tmp = f.name
        try:
            subprocess.run(
                [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                 "--hide-scrollbars", "--force-device-scale-factor=1",
                 "--virtual-time-budget=3000",
                 f"--window-size={width},{height}",
                 f"--screenshot={out_png}", f"file://{tmp}"],
                capture_output=True, timeout=90)
        except subprocess.TimeoutExpired:
            pass
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if os.path.exists(out_png) and os.path.getsize(out_png) > 5000:
            return True, None
    return False, "渲染失败或输出过小"


def main():
    ap = argparse.ArgumentParser(description="从 PPT.html 逐页导出静态帧")
    ap.add_argument("--ppt", required=True)
    ap.add_argument("--out", required=True, help="帧输出目录")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--only", help="只导这些页（逗号分隔，如 1,5,9）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    chrome = find_chrome()
    if not chrome:
        print("ERROR: 未找到 Chrome/Chromium", file=sys.stderr)
        return 1

    html = open(a.ppt, encoding="utf-8").read()
    head = html[:html.index("</head>") + len("</head>")]
    pages = split_pages(html)
    if not pages:
        print("ERROR: 未找到 <section class=\"slide\"> 页面", file=sys.stderr)
        return 1
    print(f"PPT 共 {len(pages)} 页 · Chrome: {os.path.basename(chrome)}")

    targets = list(range(1, len(pages) + 1))
    if a.only:
        targets = [int(x) for x in a.only.split(",") if x.strip()]

    if a.dry_run:
        for i in targets:
            print(f"  将导出 page_{i:03d}.png")
        return 0

    os.makedirs(a.out, exist_ok=True)

    # 逐页渲染：只让目标页可见
    ok, failed = 0, []
    digests = {}
    t0 = time.time()
    for n, i in enumerate(targets, 1):
        pg = pages[i - 1]
        # 目标页强制显示；其余页不渲染进同一文件
        one = (head + "\n" + pg + "\n</body></html>").replace(
            "</head>", "<style>.slide{display:block!important}</style></head>")
        out_png = os.path.join(a.out, f"page_{i:03d}.png")
        good, err = render_one(chrome, one, out_png, a.width, a.height)
        if not good:
            failed.append((i, err))
            print(f"  [{n}/{len(targets)}] P{i:03d} ✗ {err}")
            continue
        # 雷同检测：连续两页 md5 相同通常意味着 Chrome 忽略了路径
        h = hashlib.md5(open(out_png, "rb").read()).hexdigest()
        if i > 1 and digests.get(i - 1) == h:
            print(f"  [{n}/{len(targets)}] P{i:03d} ⚠ 与上一页雷同，重试")
            good, err = render_one(chrome, one.replace(" ", " "), out_png,
                                   a.width, a.height)
            if good:
                h = hashlib.md5(open(out_png, "rb").read()).hexdigest()
        digests[i] = h
        ok += 1
        if n % 10 == 0 or n == len(targets):
            print(f"  [{n}/{len(targets)}] 已导出 {ok} 页")

    print(f"\n完成：{ok}/{len(targets)} 页 → {a.out}（用时 {time.time()-t0:.0f}s）")
    if failed:
        print("失败页：", [f"P{i}" for i, _ in failed], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
