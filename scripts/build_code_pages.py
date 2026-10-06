#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_code_pages.py -- 批量生成代码页 HTML（practical-visualization.md 配套）

从 build/code_snippets/ 取材，为指定口播段生成代码页 <section>，
插入 PPT.html 的</body> 前。遵守规范硬约束：
  - 字号 26px、单屏 10~25 行（超长截断并显式标注省略）
  - 必带「原书 P.N §章节」出处标注
  - 关键行加 .hi 高亮
  - 主体收在顶部 85% 内（.slide.code-page 已处理）

用法：
  python3 build_code_pages.py --ppt <PPT.html> --snippets <code_snippets目录> \
      --plan <visual_plan.json> --out <输出PPT.html>
"""
import argparse
import html
import json
import os
import re
import sys

# 语法着色规则（按优先级顺序）
SYNTAX = [
    (re.compile(r"//.*$"), "cc"),# 注释
    (re.compile(r"(['\"])(?:(?!\1).)*\1"), "cs"),                      # 字符串
    (re.compile(r"\b(const|let|var|function|return|if|else|for|while|new|class|extends|"
                r"import|export|from|default|typeof|instanceof|in|of|try|catch|finally|"
                r"throw|switch|case|break|continue|async|await|yield|delete|void)\b"), "ck"),
    (re.compile(r"\b(true|false|null|undefined|NaN|Infinity)\b"), "cn"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\b"), "cn"),
    (re.compile(r"\b([A-Za-z_$][\w$]*)(?=\s*\()"), "cf"),              # 函数调用
]


def esc(t):
    return html.escape(t, quote=False)


def colorize(line):
    """对单行做最简语法着色（先转义再按规则包裹，避免嵌套冲突）。"""
    out = []
    # 注释单独处理（其后均为注释）
    m = re.search(r"//.*$", line)
    code_part, cmt = (line[:m.start()], m.group(0)) if m else (line, None)
    for s, tok in re.findall(r"('[A-Za-z_$][\w$]*')|(\b\d+(?:\.\d+)?\b)", code_part)[:0]:
        pass
    # 用占位法：先把字符串与数字替换成哨兵，避免后续规则误伤
    holds = []

    def hold(m):
        holds.append(m.group(0))
        return f"\x00{len(holds) - 1}\x00"

    tmp = re.sub(r"(['\"])(?:(?!\1).)*\1", hold, code_part)
    tmp = re.sub(r"\b(\d+(?:\.\d+)?)\b", hold, tmp)
    tmp = esc(tmp)
    for rx, cls in SYNTAX:
        if cls == "cc":
            continue
        tmp = rx.sub(lambda m: f'<span class="{cls}">{m.group(0)}</span>', tmp)
    # 还原哨兵（字符串绿、数字橙）
    for i, h in enumerate(holds):
        cls = "cs" if h[0] in "\"'" else "cn"
        tmp = tmp.replace(f"\x00{i}\x00", f'<span class="{cls}">{esc(h)}</span>')
    if cmt:
        tmp += f'<span class="cc">{esc(cmt)}</span>'
    return tmp or "&nbsp;"


MAX_LINES = 25


def build_block(lines, hi_lines, start_no=1):
    """生成代码块 HTML；超长截断并显式标注省略。"""
    truncated = 0
    if len(lines) > MAX_LINES:
        truncated = len(lines) - MAX_LINES
        lines = lines[:MAX_LINES]
    out = ['<div class="code-block">']
    for i, ln in enumerate(lines, start=start_no):
        hi = " hi" if i in hi_lines else ""
        out.append(f'<div class="code-line{hi}"><span class="ln">{i}</span>'
                   f'<span>{colorize(ln)}</span></div>')
    if truncated:
        out.append(f'<div class="code-note" style="margin-top:10px">'
                   f'（此处省略 {truncated} 行，完整代码见原书 P.{hi_lines.get("page","") if isinstance(hi_lines, dict) else ""}）</div>')
    out.append("</div>")
    return "\n".join(out)


def read_snippet(path, max_lines=MAX_LINES):
    raw = open(path, encoding="utf-8").read()
    body = raw.split("\n\n", 1)[1] if "\n\n" in raw else raw
    lines = [l.rstrip() for l in body.split("\n") if l.strip()]
    lines = dedupe_adjacent(lines)
    return lines[:max_lines]


def dedupe_adjacent(lines):
    """折叠相邻且完全相同的重复行。

    PDF 提取时若同页多段代码被合并，会出现 `const obj = {...}` 连着两遍
    这类重复，画面上很显眼。仅折叠**相邻且完全相同**的行；一旦内容变化
    即重新计数，故不会误伤 for 循环体这类正常重复。
    """
    out = []
    for ln in lines:
        if out and out[-1] == ln:
            continue        # 与上一行完全相同 → 丢弃
        out.append(ln)
    return out


# 代码行判定：必须像代码而不像输出/图示
_CODEISH = re.compile(
    r"(\bfunction\b|\bconst\b|\blet\b|\bvar\b|\breturn\b|=>|\bif\b|\belse\b|"
    r"\bfor\b|\bwhile\b|\bclass\b|\bnew\b|\bimport\b|\bexport\b|\bawait\b|"
    r"\btry\b|\bcatch\b|\.\w+\s*\(|[{};]\s*$|^\s*//|^\s*\*|^\s*/\*)")
# 纯输出行：单个数字/字符串/短词，典型如运行结果、图示标注
_OUTPUTISH = re.compile(r"^\s*(?:[\d\s'\"│└├─→←+*·.]{1,40}|[\u4e00-\u9fa5]{1,12})\s*$")


def code_quality_ok(lines):
    """判断一段文本是否像「源码」而非「运行输出 / 图示标注」。

    实测踩坑：书中展示执行结果的页面（如 P.93）整页都是等宽字体，
    提取出来是`0 1 0 1 0 1 '结束了'` 这类输出，直接上屏会很突兀。

    判据（两条同时满足才算源码）：
      ① 像代码的行 ≥ 40%（能挡住纯输出页）
      ② 连续纯输出行 ≤ 4行（能放过"树形图 + 真代码"混合页，
         只卡住整页都是输出碎片的极端情况）
    """
    if not lines:
        return False
    codeish = sum(1 for l in lines if _CODEISH.search(l))
    if codeish / len(lines) < 0.4:
        return False
    # 连续纯输出行的最大长度
    run = best = 0
    for l in lines:
        if _OUTPUTISH.match(l) and not _CODEISH.search(l):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best <= 4


def trim_to_code(lines):
    """裁掉开头的输出/图示碎片，只保留真正的源码段。

    实测：书中某些页面把「运行结果」和「代码」放在同一页（如 P.93 前 8 行
    是`0 1 0 1 '结束了'` 的输出图示，后 10 行才是 scheduler 代码）。
    直接整页上屏会很突兀，直接整页丢弃又浪费了可用代码。
    策略：从头找到第一行像代码的位置，若前面有噪声则从该处起截。
    """
    start = None
    for i, l in enumerate(lines):
        if _CODEISH.search(l):
            start = i
            break
    if start is None:
        return lines
    if start == 0:
        return lines
    # 噪声占比过高（>60%）说明这页本来就是输出页，不值得裁
    if start / len(lines) > 0.6:
        return []
    return lines[start:]


def make_page(item, snippets_dir, page_no):
    """item = {seg, page, hi:[行号], title, kicker, file_label, note, sides:[{h,p}]}"""
    sp = os.path.join(snippets_dir, item["file"])
    if not os.path.isfile(sp):
        return None, f"缺素材 {item['file']}"
    lines = trim_to_code(read_snippet(sp))
    if not lines:
        return None, f"非源码内容（疑似运行输出/图示）{item['file']}"
    if not code_quality_ok(lines):
        return None, f"非源码内容（疑似运行输出/图示）{item['file']}"

    hi = set(item.get("hi", []))
    block = build_block(lines, hi)

    sides = "".join(
        f'<div class="side-card"><h4>{esc(s["h"])}</h4><p>{s["p"]}</p></div>'
        for s in item.get("sides", []))

    note = f'<div class="code-note">{item["note"]}</div>' if item.get("note") else ""
    src = item.get("page", "")
    section = f'''<section class="slide code-page">
  <div class="slide-head">
    <div class="kicker">{esc(item.get("kicker",""))}</div>
    <div class="title">{esc(item["title"])}</div>
  </div>
  <div class="code-wrap">
    <div class="code-main">
      <div class="code-file">{esc(item.get("file_label",""))}</div>
      {block}
      {note}
    </div>
    <div class="code-side">{sides}</div>
  </div>
  <div class="code-src">原书 P.{src} ·《Vue.js 设计与实现》</div>
  <div class="page-num">{page_no:02d}</div>
</section>'''
    return section, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ppt", required=True)
    ap.add_argument("--snippets", required=True)
    ap.add_argument("--plan", required=True, help="visual_plan.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--marker", default="<!--CODE_PAGES-->")
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    items = [x for x in plan if x.get("type") == "code"]
    if not items:
        print("计划里没有代码页", file=sys.stderr)
        return 1

    s = open(a.ppt, encoding="utf-8").read()
    # 移除旧标记
    s = re.sub(r"\s*" + re.escape(a.marker) + r"\s*", "\n", s)
    if a.marker not in s:
        s = s.replace("</body>", a.marker + "\n</body>", 1)

    ok, fail = 0, []
    pages = []
    base = 900  # 代码页页码从900 起，避免与原页码冲突
    for i, item in enumerate(items, 1):
        sec, err = make_page(item, a.snippets, base + i)
        if sec:
            pages.append(sec)
            ok += 1
        else:
            fail.append(f"{item['file']}: {err}")
    # CSS：若 PPT 还没有代码组件，则提示
    if ".code-block{" not in s:
        print("WARN: PPT 缺少 .code-block 样式，请先用 templates/slide-template.html 的代码组件", file=sys.stderr)

    blob = "\n".join(pages)
    s = s.replace(a.marker, "  " + blob)
    open(a.out, "w", encoding="utf-8").write(s)
    print(f"生成 {ok} 个代码页 → {a.out}")
    for f in fail:
        print("  跳过:", f, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
