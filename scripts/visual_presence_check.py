#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""visual_presence_check.py -- 画面载体在位门禁（固定规范第 34 条配套）

把「实战内容必须上屏、不许纯文字口述」从自觉遵守变成**确定性门禁**。
本脚本检查**画面层**（PPT.html），与 `content_depth_check.py`（口播稿层）互补：
  - content_depth_check：口播稿里有没有代码/数据/操作/案例等实战形态信号
  - 本脚本            ：排出来的幻灯片里有没有对应的真实视觉载体

判定依据（与 references/practical-visualization.md §2 载体清单一致）：
  1) 存在 `build/visual_plan.md` 时做**双向核对**——plan 里声明的载体必须在 PPT 里找到
     对应实现；口播段数与载体数不得严重失配。
  2) 无 visual_plan.md 时退化为**独立启发式**：统计 PPT 内代码块 / 终端块 / 图示 /
     图表 / 对比表 / 指标卡数量，与幻灯片总数比对，算出实战视觉页占比。
  3) 纯文字页 = 既无代码块、又无图形组件、文本量超阈值的页。连续纯文字页 > 3 → BLOCK。

退出码：0 = PASS/WARN；1 = BLOCK；2 = 参数/文件错误
用法：
  python3 visual_presence_check.py <PPT.html> [--plan build/visual_plan.md] [--json] [--no-fail]
"""
import argparse
import html
import json
import os
import re
import sys

# ---------- 载体识别特征（基于 templates/slide-template.html 的真实 class 名与结构）----------

# 代码块 / 终端块：模板用 .slide.code-page / .code-block / pre.code
CODE_RE = re.compile(
    r'class="[^"]*\b(code-block|code-page|terminal|terminal-block|codehilite|highlight)\b',
    re.I,
)
# 图形载体：图示 / 架构 / 流程 / 时间线
DIAGRAM_RE = re.compile(
    r'class="[^"]*\b(diagram-stage|diagram-grid|diagram-row|nodebox|flow|flow-step|timeline)\b',
    re.I,
)
# 数据可视化：SVG 图元、图表类
CHART_RE = re.compile(
    r'class="[^"]*\b(bars|bar-chart|line-chart|donut|pie|chart|cmp|stat|metric|kpi)\b',
    re.I,
)
# 内联 SVG（自绘架构图/图表的产物）
SVG_RE = re.compile(r'<svg\b', re.I)
# 对比表 / 表格
TABLE_RE = re.compile(r'class="[^"]*\b(cmp|compare|table)\b', re.I)

CARRIER_RES = [
    ("代码/终端块", CODE_RE),
    ("图示/架构/流程图", DIAGRAM_RE),
    ("数据图表/对比表/指标卡", CHART_RE),
    ("内联SVG 图元", SVG_RE),
    ("对比表/表格", TABLE_RE),
]

SLIDE_SPLIT_RE = re.compile(r'<section[^>]*class="[^"]*\bslide\b[^"]*"', re.I)
TEXT_TAG_RE = re.compile(r'<[^>]+>')
# 去掉代码块内部文本，避免把代码行数算成"文字量"
CODE_STRIP_RE = re.compile(
    r'<(pre|code)[^>]*>.*?</\1>', re.I | re.S)

# 单页去掉代码块后的文本超过此字数、且无任何图形载体 → 判为纯文字页。
# 80 字是实测校准值：真实 PPT 的纯文字页约 115+ 字（标题+要点+注释），
# 而任何有图表/图示的页去掉图形后残留文字远低于此值。
PURE_TEXT_CHAR_LIMIT = 80


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def strip_tags(s):
    s = CODE_STRIP_RE.sub(" ", s)
    s = TEXT_TAG_RE.sub(" ", s)
    return html.unescape(s)


def has_carrier(page_html):
    """该页是否含任一视觉载体。"""
    for _, rx in CARRIER_RES:
        if rx.search(page_html):
            return True
    return False


def split_slides(doc):
    """按 <section class="slide"> 切页；用括号配对定位每页 HTML 片段。"""
    starts = [m.start() for m in SLIDE_SPLIT_RE.finditer(doc)]
    if not starts:
        return []
    pages = []
    for i, st in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(doc)
        pages.append(doc[st:end])
    return pages


def carrier_detail(page_html):
    hit = []
    for name, rx in CARRIER_RES:
        if rx.search(page_html):
            hit.append(name)
    return hit


def read_plan(plan_path):
    """解析 visual_plan.md：返回 (表格行数, 声明载体数, 存在标记)。"""
    if not os.path.isfile(plan_path):
        return None
    txt = read_text(plan_path)
    rows = 0
    carriers = 0
    for line in txt.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        #跳过表头与分隔行
        if set("".join(cells)) <= set("-: "):
            continue
        if "段号" in cells[0] or "口播要点" in cells[0]:
            continue
        rows += 1
        # 载体列（第4 列）非空且非 "—" 即视为声明了载体
        if len(cells) >= 4 and cells[3] and cells[3] not in ("—", "-", "无"):
            carriers += 1
    return {"rows": rows, "carriers": carriers}


def analyze(ppt_path, plan_path=None):
    doc = read_text(ppt_path)
    pages = split_slides(doc)
    blocks, warns = [], []

    if not pages:
        return {
            "verdict": "BLOCK",
            "reason": "PPT 里没找到 <section class=\"slide\"> 页面，文件格式不对或用了非模板骨架",
            "slides": 0,
        }

    # 逐页判定
    pure_text_pages, carrier_pages = [], []
    for i, pg in enumerate(pages, 1):
        if has_carrier(pg):
            carrier_pages.append(i)
        else:
            txt = strip_tags(pg)
            if len(txt.strip()) > PURE_TEXT_CHAR_LIMIT:
                pure_text_pages.append(i)

    total = len(pages)
    carrier_ratio = len(carrier_pages) / total if total else 0.0
    pure_ratio = len(pure_text_pages) / total if total else 0.0

    # 连续纯文字页 > 3 → BLOCK
    max_run, run = 0, 0
    for i in range(1, total + 1):
        if i in pure_text_pages:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    if max_run > 3:
        blocks.append(
            f"连续纯文字页 {max_run} 页（超过 3 页上限）——须插入代码页/图示页/图表页打断"
        )

    # 载体占比：整体实战类内容应 ≥25%；此处只做 WARN，阈值由 plan 决定
    if carrier_ratio < 0.25:
        warns.append(
            f"视觉载体页占比 {carrier_ratio:.0%}（{len(carrier_pages)}/{total}）低于 25% "
            f"——若本期属实战类主题，违反固定规范第 34 条，须补载体"
        )
    if pure_ratio > 0.40:
        blocks.append(
            f"纯文字页占比 {pure_ratio:.0%}（{len(pure_text_pages)}/{total}）超过 40% 上限"
        )

    # visual_plan 双向核对
    plan_info = None
    if plan_path:
        plan_info = read_plan(plan_path)
        if plan_info is None:
            warns.append(f"指定了 --plan 但文件不存在: {plan_path}（跳过 plan 核对）")
        else:
            declared = plan_info["carriers"]
            if declared == 0:
                blocks.append("visual_plan.md 里没有任何一段声明了画面载体——实战段落未配载体")
            elif declared > len(carrier_pages):
                blocks.append(
                    f"visual_plan.md 声明了 {declared} 段载体，PPT 里只落实 {len(carrier_pages)} 页"
                    f"——「用文字描述代码/流程」的头号反模式，须补画面"
                )
            else:
                warns.append(
                    f"plan 声明 {declared} 段载体，PPT 落实 {len(carrier_pages)} 页（含封面/纯文字页，"
                    f"非一一对应属正常，Step 6 仍须逐行目视核对）"
                )

    verdict = "BLOCK" if blocks else "PASS"
    return {
        "verdict": verdict,
        "slides": total,
        "carrier_pages": carrier_pages,
        "carrier_count": len(carrier_pages),
        "carrier_ratio": round(carrier_ratio, 4),
        "pure_text_pages": pure_text_pages,
        "pure_text_ratio": round(pure_ratio, 4),
        "max_pure_text_run": max_run,
        "plan": plan_info,
        "blocks": blocks,
        "warns": warns,
    }


def report(ppt_path, r):
    print("=" * 78)
    print("画面载体在位门禁（固定规范第 34 条 · 全9 大训练营）")
    print("=" * 78)
    print(f"PPT: {ppt_path}")
    if r.get("reason"):
        print(f"\nBLOCK: {r['reason']}")
        return
    print(f"幻灯片总数        : {r['slides']}")
    print(f"含视觉载体页      : {r['carrier_count']} 页（{r['carrier_ratio']:.0%}）"
          f" {r['carrier_pages']}")
    print(f"纯文字页          : {len(r['pure_text_pages'])} 页（{r['pure_text_ratio']:.0%}）"
          f" {r['pure_text_pages']}")
    print(f"最长连续纯文字页  : {r['max_pure_text_run']} 页（上限 3）")
    if r.get("plan"):
        print(f"visual_plan.md    : 声明载体 {r['plan']['carriers']} 段 / 共 {r['plan']['rows']} 段")
    print()
    for w in r["warns"]:
        print(f"WARN : {w}")
    for b in r["blocks"]:
        print(f"BLOCK: {b}")
    print("-" * 78)
    print(f"结论: {'FAIL❌' if r['verdict'] == 'BLOCK' else 'PASS ✅'}"
          f"  (0=PASS / 1=FAIL / 2=参数错误)")


def main():
    ap = argparse.ArgumentParser(description="画面载体在位门禁（实战内容必须上屏）")
    ap.add_argument("ppt", help="PPT.html 路径")
    ap.add_argument("--plan", default="", help="build/visual_plan.md 路径（可选，做双向核对）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fail", action="store_true", help="只报告，不改退出码")
    a = ap.parse_args()

    if not os.path.isfile(a.ppt):
        print(f"ERROR: 文件不存在: {a.ppt}", file=sys.stderr)
        return 2
    r = analyze(a.ppt, a.plan or None)
    if a.json:
        print(json.dumps({"ppt": a.ppt, **r}, ensure_ascii=False, indent=2))
    else:
        report(a.ppt, r)

    if a.no_fail:
        return 0
    return 1 if r["verdict"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
