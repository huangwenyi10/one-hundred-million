#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_book_assets.py -- 从原书 PDF 提取代码清单与图表（practical-visualization.md 配套）

按技能规范 §3.1 把书中代码清单、图表提取为可上屏素材：
  - 代码清单 → code_snippets/chNN_pNN_slug.txt（顶部写入出处注释）
  - 图表/插图 → book_figs/chNN_pNN_figN.png + manifest.json

清洗：去书页页眉页脚页码、去跨页断行异常、去章节装饰残留；保留中文注释。

用法：
  python3 extract_book_assets.py --pdf <书.pdf> --out <交付目录> [--dpi 200] [--min-code-lines 3]
  python3 extract_book_assets.py --pdf <书.pdf> --out <目录> --scan-only# 只看统计不动文件
"""
import argparse
import json
import os
import re
import sys

try:
    import pymupdf
except ImportError:
    print("ERROR: 需要 PyMuPDF。安装：pip install PyMuPDF", file=sys.stderr)
    sys.exit(1)

# 代码块识别：等宽字体名特征
MONO_HINTS = ("mono", "courier", "consol", "menlo", "monaco", "source code", "code")
# 需要剔除的页眉页脚噪声
NOISE_RE = re.compile(
    r"^\s*(第\s*\d+\s*页|本章|上一页|下一页|目录|Contents|"
    r"人邮传媒|人民邮电出版社|www\.|http|本书|配套资源|扫码|二维码|"
    r"Vue\.js 设计与实现\s*$|霍春阳\s*$)",
    re.IGNORECASE,
)

# 书中代码行号前缀（如 `01 ` / `1 ` / `001`），提取时须剥离
LINENO_RE = re.compile(r"^\s*(\d{1,3})\s+")
# 段落切分标记：行号回退到 1（说明是新一段代码）
def _is_new_block(nums):
    """nums = 当前页所有代码行的原始行号序列（None 表示无编号）；返回切分点索引列表。"""
    cuts = [0]
    for i in range(1, len(nums)):
        cur, prev = nums[i], nums[i - 1]
        if cur == 1:
            cuts.append(i)
        elif cur is not None and prev is not None and cur < prev:
            cuts.append(i)
    return cuts


def strip_lineno(s):
    m = LINENO_RE.match(s)
    if m:
        return s[m.end():].rstrip(), int(m.group(1))
    return s, None


def classify_font(font_name):
    f = (font_name or "").lower()
    return any(h in f for h in MONO_HINTS)


def clean_line(s):
    s = s.replace("　", " ").rstrip()
    if not s.strip():
        return None
    if NOISE_RE.match(s):
        return None
    return s


def extract(pdf_path, out_dir, dpi, min_code_lines, scan_only):
    doc = pymupdf.open(pdf_path)
    code_dir = os.path.join(out_dir, "code_snippets")
    fig_dir = os.path.join(out_dir, "book_figs")
    if not scan_only:
        os.makedirs(code_dir, exist_ok=True)
        os.makedirs(fig_dir, exist_ok=True)
    manifest = {"pdf": os.path.basename(pdf_path), "pages": len(doc), "code": [], "figs": []}

    print(f"PDF: {os.path.basename(pdf_path)} · {len(doc)} 页")

    for pno in range(len(doc)):
        page = doc[pno]
        pno1 = pno + 1  # 1-based，对应书里印的页码大致值

        # ---------- 代码清单 ----------
        # 逐行收集：等宽字体行 +剥离书中行号前缀
        raw = []
        for blk in page.get_text("dict").get("blocks", []):
            for ln in blk.get("lines", []):
                spans = ln.get("spans", [])
                if not spans:
                    continue
                txt = "".join(s.get("text", "") for s in spans)
                if not txt.strip():
                    continue
                mono = sum(1 for s in spans if classify_font(s.get("font", "")))
                if mono >= max(1, len(spans) * 0.6):
                    body, num = strip_lineno(txt)
                    if body is None:
                        continue
                    if num is not None:
                        raw.append((body, num))
                    elif not raw or raw[-1][0].strip():   # 无编号的等宽行，多为噪声，跳过
                        continue
                    else:
                        raw.append((body, None))

        # 按行号回退切分成多段代码（同页可能有多段独立代码）
        cuts = _is_new_block([n for _, n in raw])
        blocks = []
        for bi, start in enumerate(cuts):
            end = cuts[bi + 1] if bi + 1 < len(cuts) else len(raw)
            lines = [t for t, _ in raw[start:end] if t.strip()]
            if lines:
                blocks.append(lines)
        # 合并过短碎片：与后一块拼或自身拼前一块，避免产出大量 3~5 行噪声段
        merged = []
        for lines in blocks:
            if merged and len(merged[-1]) + len(lines) <= 30:
                merged[-1] = merged[-1] + lines
            else:
                merged.append(lines)
        blocks = [b for b in merged if len(b) >= min_code_lines]

        for bi, lines in enumerate(blocks):
            body = "\n".join(lines)
            suffix = "" if bi == 0 else f"_b{bi + 1}"
            rel = f"code_snippets/p{pno1:03d}{suffix}_code.txt"
            manifest["code"].append({
                "id": f"C-{pno1:03d}{suffix}",
                "kind": "code",
                "page": pno1,
                "lines": len(lines),
                "file": rel,
                "preview": lines[0][:60],
            })
            if not scan_only:
                with open(os.path.join(out_dir, rel), "w", encoding="utf-8") as f:
                    f.write(f"// 来源：《Vue.js 设计与实现》 P.{pno1}\n")
                    f.write(f"// 提取自原书 PDF，{len(lines)} 行；上屏时按规范截取 10~25 行\n\n")
                    f.write(body + "\n")

        # ---------- 图表 ----------
        for i, img in enumerate(page.get_images(full=True), 1):
            xref = img[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                w, h = pix.width, pix.height
                if w < 120 or h < 120:      # 跳过图标/装饰小图
                    continue
                rel = f"book_figs/p{pno1:03d}_fig{i}.png"
                manifest["figs"].append({"id": f"F-{pno1:03d}-{i}", "page": pno1, "file": rel,
                                         "w": w, "h": h})
                if not scan_only:
                    pix.save(os.path.join(out_dir, rel))
            except Exception:
                continue

    if not scan_only:
        with open(os.path.join(fig_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"代码候选段: {len(manifest['code'])}  图表: {len(manifest['figs'])}")
    if manifest["code"]:
        print("--- 代码段页码分布（前 30）---")
        print(", ".join(f"P{c['page']}({c['lines']}行)" for c in manifest["code"][:30]))
    if manifest["figs"]:
        print("--- 图表所在页（前 20）---")
        print(", ".join(str(f["page"]) for f in manifest["figs"][:20]))
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--min-code-lines", type=int, default=3)
    ap.add_argument("--scan-only", action="store_true")
    a = ap.parse_args()
    if not os.path.isfile(a.pdf):
        print(f"ERROR: PDF 不存在 {a.pdf}", file=sys.stderr)
        return 1
    if not a.scan_only:
        os.makedirs(a.out, exist_ok=True)
    extract(a.pdf, a.out, a.dpi, a.min_code_lines, a.scan_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
