#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_catalog.py — 维护「已生成视频的分类目录」（项目资产位，供作者按大类查看历史产出）。

背景：技能每产出一条视频，作者希望能有一个「按训练营大类查看已生成过哪些视频」的目录，
方便日后查看/回看某一大类（如架构师训练营）的全部产出与当前体系覆盖进度。
本脚本把一次产出**幂等追加**进一个大类的目录索引，并更新跨大类总览。

目录位置：工作区根目录下 `目录/`（项目资产，随工作区留存，不随单条视频删除）。
  - `目录/00_总览.md`         —— 全部 9 大类的目录入口（含每个大类累计条数 / 最新一条）
  - `目录/01_架构师训练营.md`  —— 单类索引：每行 = 期序 | 标题 | 档位 | 能力维度/主题 | 日期
  - `目录/02_大数据训练营.md`  … 依此类推，9 大类各一个文件
其中「期序」为该作者在该类下累计的第几条（0 起自增，幂等：标题已存在则不动期序只更新信息）。

用法：
  python3 update_catalog.py --camp 大数据训练营 --title 物化视图原理实战：74秒到2.3秒 \
      --tier S --dim "数据平台·物化视图" --date 2026-09-02 [--workspace /path/to/工作区]
  （--workspace 缺省 = 脚本运行时所在目录；--date 缺省 = 今天。）

9 大类别名与映射见下方 CATEGORIES。类别不在列表内时给出可归入的提示并退出（不静默建错误文件）。
"""
import argparse, datetime, os, re, sys

# 固定 9 大类（与 SKILL.md「训练营主题色」表 / 百度网盘自媒体目录一一对应）
CATEGORIES = [
    "架构师训练营", "大数据训练营", "AI 训练营", "产品经理训练营", "前端训练营",
    "测试训练营", "管理训练营", "软技能训练营", "读书训练营",
]
# 别名 → 标准名
ALIAS = {
    "架构师": "架构师训练营", "架构": "架构师训练营",
    "大数据": "大数据训练营",
    "AI": "AI 训练营", "人工智能": "AI 训练营",
    "产品经理": "产品经理训练营", "产品": "产品经理训练营", "PM": "产品经理训练营",
    "前端": "前端训练营",
    "测试": "测试训练营", "QA": "测试训练营",
    "管理": "管理训练营", "管理者": "管理训练营",
    "软技能": "软技能训练营",
    "读书": "读书训练营", "读书训练营": "读书训练营",
}

INDEX_FILENAME = "00_总览.md"
CATEGORY_FILENAMES = {
    c: f"{i+1:02d}_{c.replace(' ', '_')}.md" for i, c in enumerate(CATEGORIES)
}


def norm_camp(raw):
    raw = (raw or "").strip()
    if raw in CATEGORIES:
        return raw
    if raw in ALIAS:
        return ALIAS[raw]
    # 模糊包含：如 "架构师" 已在别名，但 "大数据训练营" 等
    for c in CATEGORIES:
        if c in raw or raw in c:
            return c
    return None


def read_lines(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    return []


def write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def row_exists(lines, title):
    return any(title in ln for ln in lines)


def update_category_file(cat_file, camp, title, tier, dim, date):
    lines = read_lines(cat_file)
    if not lines:
        lines = [
            f"# {camp} · 已生成视频目录",
            "",
            "> 每行一条已产出视频。期序 = 本大类累计第几条（幂等：标题已存在则只刷新信息，不重复计数）。",
            "> 由技能 Step 8 每次产出后调用 `update_catalog.py` 自动维护；也可手工补录历史视频。",
            "",
            "| 期序 | 标题 | 档位 | 能力维度 / 主题 | 日期 |",
            "|-----:|------|:----:|------------------|------|",
        ]
    # 找表格标题行索引（表头后第一行，| 开头且不是分隔行）
    header_sep = None
    for i, ln in enumerate(lines):
        if re.match(r'^\|[-: |]+\|$', ln):  # 分隔行
            header_sep = i
            break
    anchor = header_sep + 1 if header_sep is not None else len(lines)

    # 若标题已存在 → 只更新该行（幂等），不新增
    for i in range(anchor, len(lines)):
        if title in lines[i]:
            seq = lines[i].split("|")[1].strip()
            lines[i] = f"| {seq} | {title} | {tier} | {dim} | {date} |"
            write_lines(cat_file, lines)
            return seq, False
    # 新增：期序 = 现有数据行数 + 1（0 基自增，1 起显示为 1..N）
    data_rows = [ln for ln in lines[anchor:] if ln.strip().startswith("|") and "|" in ln]
    seq = str(len(data_rows) + 1)
    lines.insert(anchor, f"| {seq} | {title} | {tier} | {dim} | {date} |")
    write_lines(cat_file, lines)
    return seq, True


def count_rows(cat_file):
    """统计某大类目录文件中的实际视频条目数（数据行）。"""
    lines = read_lines(cat_file)
    start = None
    for i, ln in enumerate(lines):
        if re.match(r'^\|[-: |]+\|$', ln):
            start = i + 1
            break
    if start is None:
        return 0
    return sum(1 for ln in lines[start:] if ln.strip().startswith("|") and "|" in ln)


def update_overview(cat_dir, camp, title):
    ov_path = os.path.join(cat_dir, INDEX_FILENAME)
    lines = read_lines(ov_path)
    if not lines:
        lines = [
            "# 短视频产出总览 · 按训练营大类",
            "",
            "> 每个大类一个文件，记录该训练营已生成的全部视频（目录位 = 项目资产，供按类查看历史与体系进度）。",
            "> 维护：技能每次产出后调用 `update_catalog.py` 自动写入；手工补录同理。",
            "",
            "| 大类 | 目录文件 | 累计条数 | 最新一条 |",
            "|------|----------|:-------:|----------|",
        ]
    # 真实条数以大类文件数据行为准（幂等，无论本脚本跑几次都一致）
    total = count_rows(os.path.join(cat_dir, CATEGORY_FILENAMES[camp]))
    target = f"| {camp} |"
    hit = False
    for i, ln in enumerate(lines):
        if ln.startswith(target):
            lines[i] = f"| {camp} | {CATEGORY_FILENAMES[camp]} | {total:>3} | {title} |"
            hit = True
            break
    if not hit:
        # 追加到表格末尾（保持与其他大类行同一风格），若空则先补表头
        if not any(ln.startswith("| 大类 |") for ln in lines):
            lines += ["", "| 大类 | 目录文件 | 累计条数 | 最新一条 |",
                      "|------|----------|:-------:|----------|"]
        lines.append(f"| {camp} | {CATEGORY_FILENAMES[camp]} | {total:>3} | {title} |")
    write_lines(ov_path, lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camp", required=True, help="训练营大类（支持别名）")
    ap.add_argument("--title", required=True, help="视频标题（视频标题文件夹名）")
    ap.add_argument("--tier", default="", help="档位 S/M/L")
    ap.add_argument("--dim", default="", help="能力维度/主题（如 架构师·高并发）")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--workspace", default=os.getcwd())
    args = ap.parse_args()

    camp = norm_camp(args.camp)
    if not camp:
        sys.stderr.write(f"类别无法归入 9 大类：'{args.camp}'。可归入：{', '.join(CATEGORIES)}\n")
        sys.exit(1)

    cat_dir = os.path.join(args.workspace, "目录")
    cat_file = os.path.join(cat_dir, CATEGORY_FILENAMES[camp])

    seq, added = update_category_file(cat_file, camp, args.title, args.tier or "–", args.dim or "–", args.date)
    update_overview(cat_dir, camp, args.title)

    verb = "已新增" if added else "已存在(仅刷新信息，未重复计数)"
    print(f"[{camp}] {verb}：期序 #{seq}｜{args.title}")
    print(f"  目录文件 → {cat_file}")
    print(f"  总览文件 → {os.path.join(cat_dir, INDEX_FILENAME)}")


if __name__ == "__main__":
    main()
