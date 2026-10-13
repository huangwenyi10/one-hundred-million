#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""capture_book_figs.py -- 从原书文档截取图表区域上屏（读书训练营硬规则配套）

背景（2026-10-13 作者决策）：口播讲到书里的表格 / 图片 / 架构图 / 流程图 / 示意图 /
数据图时，必须把原书对应区域截图放到视频里——读者看不到原图就看不懂、理解不了。
本脚本提供「按页 / 按区域 / 自动探测」三种截图模式，产物供 Step 2 排版直接 <img> 上屏。

依赖：PyMuPDF + Pillow + numpy（managed venv 已装）；不依赖 poppler。
格式支持：
  - PDF（文字版 / 扫描版均可，扫描版整页即图像，渲染+裁切同样工作）
  - DOCX / DOC / EPUB / MOBI：先转 PDF（soffice / ebook-convert），本机没装则明确报错退出，
    不静默跳过（正确性优先：不允许「截不到就当没有」）
  - PNG / JPG 单图：直接作为一页处理

用法：
  # 整页截图（自动裁白边）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --page 112
  # 精确截区域（PDF 点坐标，左上原点，单位 pt）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --page 95 --rect 60,120,540,700
  # 归一化坐标（0~1，相对页面宽高；四个数都 ≤1 时按归一化解析）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --page 95 --rect 0.08,0.15,0.92,0.85
  # 批量整页
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --pages 87,95,112
  # 自动探测疑似图表区域（只出候选清单，不渲染全库）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --auto
  # 从候选清单渲染选中的（编号见 candidates.json）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --from-candidates 3,7,12
  # 去页眉页脚带（比例：顶 6% / 底 5%）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --page 112 --strip-header-footer 0.06,0.05
  # 书名/章节/页码偏移（写入 manifest 出处标注文案）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --page 112 \
      --book "Vue.js设计与实现" --chapter "§3.4" --page-offset 12

产物（--out 目录下）：
  pNNN.png / pNNN_rK.png   截图（默认 200 DPI）
  candidates.json          自动探测的候选区域清单（--auto）
  manifest.json            素材台账：ID / 页码 / 章节 / 文件 / 宽高 / 出处标注文案

退出码：0 成功；1 参数/文件错误；2 格式需转换但转换器缺失；3 依赖缺失。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import pymupdf
except ImportError:
    print("ERROR: 需要 PyMuPDF。安装：pip install PyMuPDF", file=sys.stderr)
    sys.exit(3)
try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("ERROR: 需要 Pillow 与 numpy。安装：pip install Pillow numpy", file=sys.stderr)
    sys.exit(3)

# 自动探测：矢量绘制簇的最小尺寸（pt），小于这个视为装饰线/图标
MIN_FIG_W, MIN_FIG_H = 80.0, 60.0
# 簇间合并间隙（pt）：两个绘制元素距离小于此值并为一簇（表格行距/列距通常 < 60pt）
CLUSTER_GAP = 60.0
# 整页白边裁除的亮度阈值（0~255，低于视为内容）
WHITE_THRESH = 248


def eprint(*a):
    print(*a, file=sys.stderr)


def to_pdf(doc_path, workdir):
    """非 PDF 格式转 PDF；返回 (pdf_path, tmpdir或None)。转不了就明确报错。"""
    ext = os.path.splitext(doc_path)[1].lower()
    if ext == ".pdf":
        return doc_path, None
    converters = {
        ".docx": ["soffice", "libreoffice"],
        ".doc": ["soffice", "libreoffice"],
        ".epub": ["ebook-convert"],
        ".mobi": ["ebook-convert"],
    }
    if ext in (".png", ".jpg", ".jpeg"):
        return doc_path, None  # 单图直接当一页
    cands = converters.get(ext)
    if not cands:
        eprint(f"ERROR: 不支持的格式 {ext}（支持 pdf/docx/doc/epub/mobi/png/jpg）")
        sys.exit(1)
    exe = next((c for c in cands if shutil.which(c)), None)
    if not exe:
        eprint(
            f"ERROR: {ext} 需要先转 PDF，但本机未找到 {'/'.join(cands)}。\n"
            f"请先用其他工具把《{os.path.basename(doc_path)}》导出为 PDF 再截图"
            f"（不允许截不到就当没有——正确性优先）。"
        )
        sys.exit(2)
    tmp = tempfile.mkdtemp(prefix="capfig_", dir=workdir)
    eprint(f"转换中：{exe} {os.path.basename(doc_path)} -> PDF ...")
    r = subprocess.run(
        [exe, os.path.abspath(doc_path), os.path.join(tmp, "book.pdf")],
        capture_output=True, text=True, timeout=600,
    )
    out = os.path.join(tmp, "book.pdf")
    if r.returncode != 0 or not os.path.isfile(out):
        # soffice 用 --convert-to 语法，ebook-convert 用 输入 输出 语法
        r = subprocess.run(
            [exe, "--headless", "--convert-to", "pdf", "--outdir", tmp, os.path.abspath(doc_path)],
            capture_output=True, text=True, timeout=600,
        )
        produced = os.path.join(tmp, os.path.splitext(os.path.basename(doc_path))[0] + ".pdf")
        if r.returncode != 0 or not os.path.isfile(produced):
            eprint(f"ERROR: 转换失败：{(r.stderr or r.stdout or '')[:300]}")
            sys.exit(2)
        out = produced
    return out, tmp


def parse_rect(s, page_rect):
    """'x0,y0,x1,y1'；四值全 ≤1 按归一化解析，否则按 PDF 点坐标。"""
    try:
        vals = [float(x) for x in s.split(",")]
        if len(vals) != 4:
            raise ValueError
    except ValueError:
        eprint("ERROR: --rect 需为 x0,y0,x1,y1（如 60,120,540,700 或 0.08,0.15,0.92,0.85）")
        sys.exit(1)
    if all(0 <= v <= 1 for v in vals):
        r = pymupdf.Rect(vals[0] * page_rect.width, vals[1] * page_rect.height,
                         vals[2] * page_rect.width, vals[3] * page_rect.height)
    else:
        r = pymupdf.Rect(*vals)
    return r & page_rect  # 夹到页面内


def render_clip(page, clip, dpi, trim=True, pad=6):
    """渲染页面的 clip 区域（pt）为 PIL 图；trim=自动裁除四周近白边。"""
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if trim:
        arr = np.asarray(img).min(axis=2)
        mask = arr < WHITE_THRESH
        if mask.any():
            ys, xs = np.where(mask)
            x0, x1 = max(0, xs.min() - pad), min(img.width, xs.max() + pad + 1)
            y0, y1 = max(0, ys.min() - pad), min(img.height, ys.max() + pad + 1)
            if x1 - x0 > 20 and y1 - y0 > 20:
                img = img.crop((x0, y0, x1, y1))
    return img


def strip_bands(clip, page_rect, top, bottom):
    """按比例去掉页眉/页脚带，返回新 clip。"""
    h = page_rect.height
    return pymupdf.Rect(clip.x0, clip.y0 + h * top, clip.x1, clip.y1 - h * bottom)


def find_candidates(doc):
    """全文档扫描：把页面上的矢量绘制元素 + 嵌入位图聚成簇，输出疑似图表区域候选。

    细线（表格网格）不过滤——聚类后再按尺寸筛，否则整张表会被行距打散。
    """
    cands = []
    for pno in range(len(doc)):
        page = doc[pno]
        rects = []
        for d in page.get_drawings():
            r = d.get("rect")
            if r:
                # 直线在 PyMuPDF 里是零高度/零宽度矩形（is_empty=True），
                # 不过滤——膨胀 0.5pt 让其可参与聚类，否则表格网格整张被漏掉
                rects.append(pymupdf.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5))
        # 嵌入位图也算图表候选（书中插图常以位图嵌入）
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                if r and not r.is_empty:
                    rects.append(pymupdf.Rect(r))
        if not rects:
            continue
        # 贪心聚类：距离 < CLUSTER_GAP 的元素并为一簇
        clusters = []
        for r in sorted(rects, key=lambda x: (x.y0, x.x0)):
            hit = None
            for c in clusters:
                inter = r & c
                if (inter.is_valid and not inter.is_empty) or \
                   min(abs(r.x0 - c.x1), abs(c.x0 - r.x1), abs(r.y0 - c.y1), abs(c.y0 - r.y1)) < CLUSTER_GAP:
                    hit = c
                    break
            if hit:
                clusters[clusters.index(hit)] = hit | r
            else:
                clusters.append(pymupdf.Rect(r))
        for c in clusters:
            if c.width >= MIN_FIG_W and c.height >= MIN_FIG_H and \
               c.get_area() < page.rect.get_area() * 0.92:
                ratio = round(c.width / max(c.height, 1), 2)
                # 只按长宽比给中性标签（架构图/表格无法从形状可靠区分，选哪类以人工确认为准）
                kind = "横长图" if ratio > 1.6 else ("方正图" if 0.8 <= ratio <= 1.6 else "竖长图")
                cands.append({
                    "page": pno + 1,
                    "bbox_pt": [round(c.x0, 1), round(c.y0, 1), round(c.x1, 1), round(c.y1, 1)],
                    "kind_guess": kind,
                    "w_pt": round(c.width, 1), "h_pt": round(c.height, 1),
                })
    return cands


def load_meta(out):
    p = os.path.join(out, "_meta.json")
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_meta(out, meta):
    with open(os.path.join(out, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def load_manifest(out):
    p = os.path.join(out, "manifest.json")
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            pass
    return {"captures": []}


def save_manifest(out, mf):
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(mf, f, ensure_ascii=False, indent=2)


def add_entry(mf, out, page, chapter, book, offset, fname, img):
    printed = page + offset
    cap = f"《{book}》" if book else "原书"
    loc = f"{chapter} · P.{printed}" if chapter else f"P.{printed}"
    entry = {
        "id": f"C-p{page:03d}-{len(mf['captures']) + 1}",
        "page_pdf": page, "page_printed": printed, "chapter": chapter or "",
        "file": fname, "w": img.width, "h": img.height,
        "caption": f"{cap} {loc}",  # Step 2 上屏时作为出处标注文案
    }
    mf["captures"] = [c for c in mf["captures"] if c.get("file") != fname] + [entry]
    save_manifest(out, mf)
    return entry


def main():
    ap = argparse.ArgumentParser(description="从原书文档截取图表区域上屏（读书训练营硬规则配套）")
    ap.add_argument("--doc", required=True, help="原书文件：pdf/docx/doc/epub/mobi/png/jpg")
    ap.add_argument("--out", required=True, help="输出目录（一般传 build/book_caps）")
    ap.add_argument("--page", type=int, help="整页截图（PDF 物理页，1-based）")
    ap.add_argument("--pages", help="批量整页，逗号分隔：87,95,112")
    ap.add_argument("--rect", help="截取区域 x0,y0,x1,y1（pt 或 0~1 归一化）")
    ap.add_argument("--auto", action="store_true", help="全文档扫描疑似图表区域，出候选清单")
    ap.add_argument("--from-candidates", help="渲染候选清单中编号，逗号分隔（编号见 candidates.json）")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--no-trim", action="store_true", help="不自动裁白边")
    ap.add_argument("--strip-header-footer", help="去页眉页脚比例 top,bottom（如 0.06,0.05）")
    ap.add_argument("--book", default="", help="书名（写入 manifest 出处文案）")
    ap.add_argument("--chapter", default="", help="章节（如 §3.4，写入 manifest 出处文案）")
    ap.add_argument("--page-offset", type=int, default=0, help="PDF 物理页 → 书上印次页码 的偏移")
    a = ap.parse_args()

    if not os.path.isfile(a.doc):
        eprint(f"ERROR: 文件不存在 {a.doc}")
        return 1
    os.makedirs(a.out, exist_ok=True)
    bands = (0.0, 0.0)
    if a.strip_header_footer:
        try:
            bands = tuple(float(x) for x in a.strip_header_footer.split(","))
            assert len(bands) == 2
        except Exception:
            eprint("ERROR: --strip-header-footer 需为 top,bottom（如 0.06,0.05）")
            return 1

    pdf_path, tmp = to_pdf(a.doc, a.out)
    # 书名/章节/页码偏移持久化：本次没传就用上次的（避免每次重传）
    meta = load_meta(a.out)
    for k, v in (("book", a.book), ("chapter", a.chapter), ("page_offset", a.page_offset)):
        if v:
            meta[k] = v
    save_meta(a.out, meta)
    book = meta.get("book", "")
    chapter = meta.get("chapter", "")
    offset = int(meta.get("page_offset", 0) or 0)
    try:
        doc = pymupdf.open(pdf_path)
        mf = load_manifest(a.out)
        n_done = 0

        def shoot(pno, clip=None, tag=""):
            nonlocal n_done
            if pno < 1 or pno > len(doc):
                eprint(f"ERROR: 页码 {pno} 超出范围（文档共 {len(doc)} 页）")
                sys.exit(1)
            page = doc[pno - 1]
            c = clip or page.rect
            if bands != (0.0, 0.0):
                c = strip_bands(c, page.rect, *bands)
            img = render_clip(page, c, a.dpi, trim=not a.no_trim)
            fname = f"p{pno:03d}{tag}.png"
            img.save(os.path.join(a.out, fname))
            e = add_entry(mf, a.out, pno, chapter, book, offset, fname, img)
            n_done += 1
            print(f"  ✓ {fname}  {img.width}x{img.height}px  出处标注：{e['caption']}")

        if a.auto:
            cands = find_candidates(doc)
            with open(os.path.join(a.out, "candidates.json"), "w", encoding="utf-8") as f:
                json.dump(cands, f, ensure_ascii=False, indent=2)
            print(f"自动探测：{len(cands)} 个疑似图表区域 → {os.path.join(a.out, 'candidates.json')}")
            for i, c in enumerate(cands, 1):
                print(f"  [{i:>2}] P.{c['page']:<4} {c['kind_guess']:<10} {c['w_pt']}x{c['h_pt']}pt  bbox={c['bbox_pt']}")
            print("渲染选中项：--from-candidates 1,5,9")
            return 0

        if a.from_candidates:
            cpath = os.path.join(a.out, "candidates.json")
            if not os.path.isfile(cpath):
                eprint("ERROR: 先跑 --auto 生成 candidates.json")
                return 1
            cands = json.load(open(cpath, encoding="utf-8"))
            for idx in [int(x) for x in a.from_candidates.split(",")]:
                if idx < 1 or idx > len(cands):
                    eprint(f"ERROR: 候选编号 {idx} 超出范围（1~{len(cands)}）")
                    return 1
                c = cands[idx - 1]
                clip = pymupdf.Rect(*c["bbox_pt"])
                shoot(c["page"], clip, tag=f"_r{idx}")
            print(f"完成 {n_done} 张 → {a.out}（manifest.json 已更新）")
            return 0

        if a.pages:
            for pno in [int(x) for x in a.pages.split(",")]:
                shoot(pno)
            print(f"完成 {n_done} 张 → {a.out}（manifest.json 已更新）")
            return 0

        if a.page:
            clip = None
            if a.rect:
                clip = parse_rect(a.rect, doc[a.page - 1].rect)
            shoot(a.page, clip, tag="_r1" if a.rect else "")
            print(f"完成 {n_done} 张 → {a.out}（manifest.json 已更新）")
            return 0

        eprint("ERROR: 需指定 --page / --pages / --rect / --auto / --from-candidates 之一")
        return 1
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
