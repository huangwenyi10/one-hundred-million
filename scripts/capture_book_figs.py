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
  # 一键渲染所有探测到的图表区域（自动裁掉正文；可用 --pages 限定页范围）
  python3 capture_book_figs.py --doc 书.pdf --out build/book_caps --figures --pages 19,110
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
# 页面背景框判定：绘制元素面积占页面比例超过此值 → 视为页面底板/边框，不是图
BG_AREA_RATIO = 0.50
# 文字高亮条判定：长宽比超过此值且高度小于 HILITE_MAX_H → 视为正文高亮底条，不是图
HILITE_ASPECT = 15.0
HILITE_MAX_H = 30.0
# 矢量图的文字密度门禁：候选区内正文文本块面积占比超过此值 → 判为「文字页」而非图
TEXT_DENSITY_MAX = 0.35


def eprint(*a):
    print(*a, file=sys.stderr)


def _is_page_bg(rect, page_area):
    """页面底板/边框：面积占比过高，且填充为白或近白。"""
    if page_area <= 0:
        return False
    if rect.get_area() / page_area < BG_AREA_RATIO:
        return False
    return True


def _is_highlight_bar(rect):
    """正文高亮底条：极扁极长（如 520x17pt 的彩色条），是文字背景不是图。"""
    w, h = rect.width, rect.height
    if h <= 0 or w <= 0:
        return False
    if h >= HILITE_MAX_H:
        return False
    return (w / h) >= HILITE_ASPECT


def _is_complex(d):
    """复杂矢量图形（真实图示）：路径段数多，或带描边。"""
    items = d.get("items") or []
    if len(items) >= 4:
        return True
    if d.get("color") is not None and len(items) >= 2:
        return True
    return False


def text_density(rect, blocks):
    """候选区被正文文本块覆盖的面积占比（0~1）。图内自带标签也会被计入，
    因此该指标只用于「矢量候选」的兜底筛查，位图候选不走此门禁。"""
    if rect.get_area() <= 0:
        return 0.0
    covered = 0.0
    for b in blocks:
        br = pymupdf.Rect(b[:4])
        if br.is_empty:
            continue
        inter = br & rect
        if inter.is_valid and not inter.is_empty:
            covered += inter.get_area()
    return min(1.0, covered / rect.get_area())


def find_figures(page):
    """在单页上找出**真实的图表区域**，返回 [{bbox, source, score, kind}]。

    两条探测路径，均带排除规则（2026-10-15 强化，修复三类误报）：
      A. 嵌入位图（书中插图常以位图嵌入）——用 page.get_image_info() 拿
         **实际放置**的图及其 bbox。
         ⚠️ 历史 bug：旧实现用 page.get_images(full=True) 列资源池，会把
         全文档共享的 86 张图在每一页都报一遍，再靠 get_image_rects() 取回
         空列表 → 位图路径实际失效；且绘制路径只拿到页面底板，导致**每一页**
         都被误判成「有图」，--pages 整页截图于是把纯文字页也当图上屏。
      B. 矢量绘制簇（SVG/HTML 渲染出的架构图、流程图）——聚类后排除：
         · 页面底板/边框（面积占页 > 50%）
         · 正文高亮底条（长宽比 ≥ 15 且高 < 30pt）
         · 装饰细线/图标（尺寸不足或路径过简）
         并通过文字密度门禁剔除「纯文字页」。

    score 用于人工挑图：位图 100；矢量按元素复杂度与密度折减。
    """
    page_area = page.rect.get_area()
    out = []

    # ---- A. 嵌入位图：实际放置的图 ----
    for info in page.get_image_info():
        b = info.get("bbox")
        if not b:
            continue
        r = pymupdf.Rect(b)
        if r.is_empty:
            continue
        if r.width < MIN_FIG_W or r.height < MIN_FIG_H:
            continue
        if r.get_area() >= page_area * 0.85:      # 整页扫描件不算「图」
            continue
        ratio = r.width / max(r.height, 1)
        kind = "横长图" if ratio > 1.6 else ("方正图" if 0.8 <= ratio <= 1.6 else "竖长图")
        out.append({
            "bbox_pt": [round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)],
            "source": "位图", "score": 100, "kind_guess": kind,
            "w_pt": round(r.width, 1), "h_pt": round(r.height, 1),
            "src_px": f"{info.get('width')}x{info.get('height')}",
        })

    # ---- B. 矢量绘制簇 ----
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if not r or r.is_empty:
            continue
        rr = pymupdf.Rect(r.x0 - 0.5, r.y0 - 0.5, r.x1 + 0.5, r.y1 + 0.5)
        if _is_page_bg(rr, page_area):
            continue
        if _is_highlight_bar(rr):
            continue
        if not _is_complex(d):
            continue
        rects.append(rr)
    if rects:
        blocks = page.get_text("blocks")
        # 贪心聚类：距离 < CLUSTER_GAP 的元素并为一簇
        clusters = []
        for r in sorted(rects, key=lambda x: (x.y0, x.x0)):
            hit = None
            for c in clusters:
                inter = r & c
                if (inter.is_valid and not inter.is_empty) or \
                   min(abs(r.x0 - c.x1), abs(c.x0 - r.x1),
                       abs(r.y0 - c.y1), abs(c.y0 - r.y1)) < CLUSTER_GAP:
                    hit = c
                    break
            if hit:
                clusters[clusters.index(hit)] = hit | r
            else:
                clusters.append(pymupdf.Rect(r))
        for c in clusters:
            if c.width < MIN_FIG_W or c.height < MIN_FIG_H:
                continue
            if c.get_area() >= page_area * 0.92:
                continue
            dens = text_density(c, blocks)
            if dens > TEXT_DENSITY_MAX:
                continue                      # 纯文字页，不是图
            ratio = c.width / max(c.height, 1)
            kind = "横长图" if ratio > 1.6 else ("方正图" if 0.8 <= ratio <= 1.6 else "竖长图")
            out.append({
                "bbox_pt": [round(c.x0, 1), round(c.y0, 1), round(c.x1, 1), round(c.y1, 1)],
                "source": "矢量", "score": max(40, int(80 - dens * 100)),
                "kind_guess": kind,
                "w_pt": round(c.width, 1), "h_pt": round(c.height, 1),
                "text_density": round(dens, 2),
            })
    return out


def find_candidates(doc, page_range=None):
    """全文档（或指定页范围）扫描疑似图表区域候选。"""
    cands = []
    lo, hi = 0, len(doc)
    if page_range:
        lo, hi = max(0, page_range[0] - 1), min(len(doc), page_range[1])
    for pno in range(lo, hi):
        for f in find_figures(doc[pno]):
            f["page"] = pno + 1
            cands.append(f)
    return cands


def _page_range(s):
    """'19,27,50' → (19, 50)，用于限定扫描范围；None/空 → None。"""
    if not s:
        return None
    nums = [int(x) for x in s.split(",") if x.strip()]
    if not nums:
        return None
    return (min(nums), max(nums))


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
    ap.add_argument("--pages", help="批量整页，逗号分隔：87,95,112；也用于限定 --auto/--figures 的页范围（同格式）")
    ap.add_argument("--rect", help="截取区域 x0,y0,x1,y1（pt 或 0~1 归一化）")
    ap.add_argument("--auto", action="store_true", help="扫描疑似图表区域，出候选清单（可用 --pages 限定范围）")
    ap.add_argument("--figures", action="store_true",
                    help="一键渲染所有探测到的图表区域（自动裁掉正文，无需人工挑号）")
    ap.add_argument("--min-score", type=int, default=50, help="--figures 的候选质量下限（默认 50）")
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
            pr = _page_range(a.pages)
            cands = find_candidates(doc, pr)
            with open(os.path.join(a.out, "candidates.json"), "w", encoding="utf-8") as f:
                json.dump(cands, f, ensure_ascii=False, indent=2)
            print(f"自动探测：{len(cands)} 个疑似图表区域 → {os.path.join(a.out, 'candidates.json')}")
            for i, c in enumerate(cands, 1):
                extra = f" 文字密度{c.get('text_density')}" if c.get('source') == '矢量' else ""
                print(f"  [{i:>2}] P.{c['page']:<4} {c['source']:<3} {c['kind_guess']:<6} "
                      f"score={c['score']:<3} {c['w_pt']}x{c['h_pt']}pt  bbox={c['bbox_pt']}{extra}")
            print("渲染选中项：--from-candidates 1,5,9")
            print("或一键渲染全部：--figures")
            return 0

        if a.figures:
            # 一键渲染所有探测到的图表区域（无需人工挑号）
            pr = _page_range(a.pages)
            cands = find_candidates(doc, pr)
            if not cands:
                eprint("WARN: 指定范围内未探测到任何图表区域（可能是纯文字页，或图示为矢量细线）")
                return 0
            print(f"探测到 {len(cands)} 个图表区域，开始渲染 …")
            for i, c in enumerate(cands, 1):
                if c['score'] < a.min_score:
                    print(f"  跳过 P.{c['page']}（score={c['score']} < {a.min_score}）")
                    continue
                clip = pymupdf.Rect(*c["bbox_pt"])
                shoot(c["page"], clip, tag=f"_f{i:02d}")
            print(f"完成 {n_done} 张 → {a.out}（manifest.json 已更新）")
            return 0
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
            # 整页模式：若该页探测不到图表区域，明确告警——否则会把纯文字页
            # 当「图」上屏，读者看到的是一屏密密麻麻的正文（2026-10-15 作者反馈）。
            for pno in [int(x) for x in a.pages.split(",")]:
                figs = find_figures(doc[pno - 1])
                if not figs:
                    eprint(f"WARN: P.{pno} 未探测到图表区域——该页可能是纯文字页，"
                           f"整页截图会把大量正文搬上屏。建议改用 --figures 自动裁图，"
                           f"或用 --rect 精确指定图区。")
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
