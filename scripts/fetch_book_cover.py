#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_book_cover.py — 按 ISBN 抓取原书封皮，落为读书训练营封面底图。

用法:
  python3 fetch_book_cover.py <ISBN> <out_path> [--local <本地封皮路径>] [--timeout 8]

回退链(按顺序尝试，成功即停):
  1) Open Library Covers API: https://covers.openlibrary.org/b/isbn/<ISBN>-L.jpg
  2) Google Books API: https://www.googleapis.com/books/v1/volumes?q=isbn:<ISBN>
     -> items[0].volumeInfo.imageLinks.thumbnail (http 升 https, zoom=1 升 zoom=3)
  3) 本地回退: --local 指定的文件(如 作者书籍库/<书名>/封面.jpg)
  4) 全部失败 -> 退出码 2，并打印提示，由调用方决定提示作者手动提供

设计:
  - 仅依赖标准库(urllib/ssl/json)，无第三方依赖。
  - 校验: 返回须为图片(content-type 含 image 且字节 > 2KB)；Open Library 无封面会返回
    1x1 占位图，按体积过滤。
  - 超时 / TLS / 网络异常均被捕获，继续回退，绝不抛栈。
  - 沙箱可能无外网: 抓取失败自动落到 --local，再失败才退出 2。
"""
import sys, os, json, ssl, urllib.request, urllib.error

IMG_MAGICS = (b"\xff\xd8\xff\xe0", b"\x89PNG", b"GIF8")


def _http_get(url, timeout, accept="*/*"):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; bookcover-fetch/1.0)",
            "Accept": accept,
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "")
        return data, ctype


def _is_valid_image(data, ctype):
    if not data or len(data) < 2048:
        return False
    if "image" in ctype.lower():
        return True
    return data[:4] in IMG_MAGICS


def fetch_openlibrary(isbn, timeout):
    url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    try:
        data, ctype = _http_get(url, timeout, accept="image/jpeg")
        if _is_valid_image(data, ctype):
            return data
    except Exception:
        pass
    return None


def fetch_googlebooks(isbn, timeout):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        data, ctype = _http_get(url, timeout, accept="application/json")
        if not data:
            return None
        obj = json.loads(data.decode("utf-8", "ignore"))
        items = obj.get("items") or []
        for it in items:
            links = (it.get("volumeInfo") or {}).get("imageLinks") or {}
            thumb = links.get("thumbnail") or links.get("smallThumbnail")
            if not thumb:
                continue
            thumb = thumb.replace("http://", "https://")
            if "zoom=1" in thumb:
                thumb = thumb.replace("zoom=1", "zoom=3")
            d2, c2 = _http_get(thumb, timeout, accept="image/*")
            if _is_valid_image(d2, c2):
                return d2
    except Exception:
        pass
    return None


def fetch_local(path):
    if path and os.path.isfile(path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if _is_valid_image(data, "image/jpeg"):
                return data
        except Exception:
            pass
    return None


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.stderr.write(
            "用法: python3 fetch_book_cover.py <ISBN> <out_path> [--local <path>] [--timeout 8]\n"
        )
        return 1
    isbn = args[0].strip()
    out_path = args[1].strip()
    local_path = None
    timeout = 8
    i = 2
    while i < len(args):
        a = args[i]
        if a == "--local" and i + 1 < len(args):
            local_path = args[i + 1]
            i += 2
            continue
        if a == "--timeout" and i + 1 < len(args):
            try:
                timeout = int(args[i + 1])
            except Exception:
                pass
            i += 2
            continue
        i += 1

    sources = [
        ("Open Library", lambda: fetch_openlibrary(isbn, timeout)),
        ("Google Books", lambda: fetch_googlebooks(isbn, timeout)),
        ("本地回退(%s)" % (local_path or "未指定"), lambda: fetch_local(local_path)),
    ]
    for name, fn in sources:
        try:
            data = fn()
        except Exception:
            data = None
        if data:
            out_abs = os.path.abspath(out_path)
            os.makedirs(os.path.dirname(out_abs), exist_ok=True)
            with open(out_abs, "wb") as f:
                f.write(data)
            sys.stderr.write(f"OK [{name}] -> {out_abs} ({len(data)} bytes)\n")
            return 0

    sys.stderr.write(
        "FAIL: 所有来源均未取到原书封皮。请作者手动提供该书封皮图，"
        "或放入 作者书籍库/<书名>/封面.jpg 后重跑。\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
