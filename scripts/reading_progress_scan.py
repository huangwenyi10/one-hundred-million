#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reading_progress_scan.py — 读书训练营「选书前必查」一键扫描（固定规范配套脚本）

背景（2026-10-05 事故）：读书训练营的产出分散在多个客户端的多个工作区
（WorkBuddy → ~/WorkBuddy/<工作区>/、Qoder → ~/Documents/Qoder/<日期>/<id>/、
另有 ChatGPT/HundredMillion 等），且书单状态字段会滞后于实际进度。
事故经过：书单 #1、#2 已录完但仍标「待录制」，AI 只读当前空工作区、
按「取序号第一本未录制」误取 #1 准备重录。

因此选书前必须先跑本脚本，而不是只看当前工作区或只信书单状态。

做什么：
  1. 全盘扫出所有 reading_camp_progress.json，列出 currentBook / partsDone /
     finishedAt / updatedAt / 工作区路径（含 priorBooks 里的历史书）。
  2. 读 references/author-book-list.md，把书单状态与各工作区 progress 交叉比对，
     不一致即告警（书单标「待录制」但某工作区已录完 → 状态滞后）。
  3. 给出「下一本该录哪本」的建议。

用法：
  python3 scripts/reading_progress_scan.py                # 扫描并给出建议
  python3 scripts/reading_progress_scan.py --json         # 机器可读输出
  python3 scripts/reading_progress_scan.py --fix-list     # 把滞后的书单状态改「已完结」（会改文件，谨慎）

退出码：
  0  正常
  2  发现书单状态与 progress 冲突（需回写书单；不带 --fix-list 时只告警不改文件）
  3  书单文件缺失 / 解析失败
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
BOOK_LIST = SKILL_DIR / "references" / "author-book-list.md"

# 回退遍历用的候选根（mdfind 不可用时的兜底）；限定深度避免超时
FALLBACK_ROOTS = ["WorkBuddy", "Documents", "Desktop"]
MAX_DEPTH = 7
SKIP_DIR_NAMES = {
    "node_modules", ".git", "Library", ".Trash", "Applications",
    "Movies", "Music", "Pictures", "Public", "Caches", ".cache",
}


def find_progress_files():
    """全盘定位 reading_camp_progress.json。macOS 走 mdfind（快），失败回退限定深度遍历。"""
    found = set()

    # 1) Spotlight（首选：全盘 find 会超时，mdfind 秒级）
    try:
        r = subprocess.run(
            ["mdfind", "-name", "reading_camp_progress.json"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                p = line.strip()
                if p and os.path.isfile(p):
                    found.add(os.path.abspath(p))
    except Exception:
        pass

    # 2) 回退：限定深度遍历候选根
    home = Path.home()
    for root_name in FALLBACK_ROOTS:
        root = home / root_name
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIR_NAMES and not d.startswith(".")
            ]
            if len(Path(dirpath).parts) - base_depth > MAX_DEPTH:
                dirnames[:] = []
                continue
            if "reading_camp_progress.json" in filenames:
                found.add(os.path.abspath(os.path.join(dirpath, "reading_camp_progress.json")))

    return sorted(found)


def parse_progress(path):
    """解析单个进度文件，容错：坏文件/缺字段都返回 None 而不是崩。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return {"path": path, "error": f"解析失败: {e}"}

    books = []
    cur = d.get("currentBook")
    if cur:
        books.append({
            "book": str(cur),
            "parts": d.get("partsDone") or [],
            "finished": bool(d.get("finishedAt")),
            "status": d.get("currentPartStatus") or "",
        })
    for pb in (d.get("priorBooks") or []):
        if isinstance(pb, dict):
            books.append({
                "book": str(pb.get("book", "")),
                "parts": ["上", "中", "下"] if "三部" in str(pb.get("status", "")) else [],
                "finished": "完结" in str(pb.get("status", "")) or "成片" in str(pb.get("status", "")),
                "status": str(pb.get("status", "")),
                "by": str(pb.get("by", "")),
            })
    return {
        "path": path,
        "workspace": str(Path(path).parent),
        "updatedAt": str(d.get("updatedAt", "")),
        "books": books,
        "nextBookHint": str(d.get("nextBook", "")),
    }


def parse_book_list(path):
    """解析书单 markdown 表格：序号 / 书名 / 作者 / ISBN / 状态 / 备注。"""
    if not path.is_file():
        return None
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 5:
                continue
            if cells[0] in ("序号", "----", ":", "----:") or not cells[0].isdigit():
                continue
            rows.append({
                "no": int(cells[0]),
                "name": cells[1],
                "author": cells[2],
                "isbn": cells[3],
                "status": cells[4].replace("**", "").replace("← 当前书目", "").strip(),
                "current": "当前书目" in cells[4],
            })
    return rows


def name_key(name):
    """书名归一：去书名号、空格、标点，用于模糊匹配。"""
    return re.sub(r"[《》\s\-—:：,，。()（）]", "", str(name))


def match_key(k, done_books):
    """在 done_books 里模糊匹配归一书名，返回命中的记录或 None。"""
    for dk, rec in done_books.items():
        if k and (k in dk or dk in k):
            return rec
    return None


def is_actually_recorded(k, done_books):
    """是否已有实际产出。

    注意：只出现在某 progress 的 currentBook 里（partsDone 为空）不算已录制——
    那只是「计划要录」，不是「已经录过」。2026-10-05 实测踩坑：当前工作区的
    progress 写了 currentBook=#3 但 partsDone=[]，若按「出现过即已录」判定，
    会把 #3 跳过、误建议 #4。
    """
    rec = match_key(k, done_books)
    if not rec:
        return False
    return bool(rec["parts"]) or bool(rec["finished"])


def main():
    ap = argparse.ArgumentParser(description="读书训练营选书前必查：全盘扫进度 + 交叉验证书单状态")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--fix-list", action="store_true", help="把滞后的书单状态改「已完结」（会改文件）")
    args = ap.parse_args()

    book_rows = parse_book_list(BOOK_LIST)
    if not book_rows:
        print(f"[FAIL] 书单解析失败或为空：{BOOK_LIST}", file=sys.stderr)
        return 3

    files = find_progress_files()
    progresses = [parse_progress(p) for p in files]

    # 汇总：每本书在各工作区的实际完成情况
    done_books = {}   # 归一书名 -> {book, parts, finished, sources:[]}
    for pg in progresses:
        if pg.get("error"):
            continue
        for b in pg.get("books", []):
            k = name_key(b["book"])
            rec = done_books.setdefault(k, {
                "book": b["book"], "parts": set(), "finished": False, "sources": []
            })
            rec["parts"].update(b.get("parts") or [])
            rec["finished"] = rec["finished"] or b.get("finished", False)
            rec["sources"].append(pg["workspace"])

    # 交叉验证：书单状态 vs 实际进度
    conflicts = []
    for r in book_rows:
        k = name_key(r["name"])
        actual = None
        for dk, rec in done_books.items():
            # 双向包含匹配，容忍书名写法差异
            if k and (k in dk or dk in k):
                actual = rec
                break
        if actual and r["status"] != "已完结" and len(actual["parts"]) >= 3:
            conflicts.append({
                "no": r["no"], "name": r["name"],
                "list_status": r["status"],
                "actual_parts": sorted(actual["parts"]),
                "sources": actual["sources"],
            })

    # 建议下一本：书单里既非已完结、也未在任何 progress 出现的最小序号
    next_pick = None
    for r in book_rows:
        if r["status"] == "已完结":
            continue
        if is_actually_recorded(name_key(r["name"]), done_books):
            continue
        next_pick = r
        break

    if args.json:
        print(json.dumps({
            "bookList": book_rows,
            "progressFiles": [
                {"path": p["path"], "workspace": p.get("workspace"),
                 "updatedAt": p.get("updatedAt"), "books": p.get("books", []),
                 "error": p.get("error")} for p in progresses
            ],
            "conflicts": conflicts,
            "nextBook": next_pick,
        }, ensure_ascii=False, indent=2))
        return 2 if conflicts else 0

    # ---- 人类可读输出 ----
    print("=" * 78)
    print("读书训练营 · 选书前必查扫描")
    print("=" * 78)

    print("\n【1】书单状态（references/author-book-list.md）")
    print(f"{'序号':<4} {'状态':<10} 书名")
    print("-" * 78)
    for r in book_rows:
        mark = " ← 当前书目" if r["current"] else ""
        flag = ""
        if is_actually_recorded(name_key(r["name"]), done_books):
            flag = " (已有产出)"
        print(f"{r['no']:<4} {r['status']:<10} {r['name']}{flag}{mark}")

    print(f"\n【2】全盘进度文件（共 {len(files)} 个）")
    print("-" * 78)
    if not files:
        print("（未找到任何 reading_camp_progress.json —— 若此前确实录过书，说明扫描根需扩充）")
    for pg in progresses:
        if pg.get("error"):
            print(f"  [坏文件] {pg['path']}: {pg['error']}")
            continue
        print(f"  工作区：{pg['workspace']}")
        print(f"    更新于 {pg.get('updatedAt') or '—'}")
        for b in pg.get("books", []):
            tag = "已完结" if b.get("finished") else "进行中"
            print(f"    · [{tag}] {b['book'][:60]}  部={'/'.join(b.get('parts') or []) or '—'}")
        if pg.get("nextBookHint"):
            print(f"    nextBook 提示：{pg['nextBookHint'][:80]}")

    print("\n【3】书单状态 vs 实际进度 冲突检查")
    print("-" * 78)
    if not conflicts:
        print("  无冲突 ✅")
    else:
        print("  ⚠️ 发现状态滞后（书单标未完结，但实际已录完）—— 必须回写书单，否则会重复录制：")
        for c in conflicts:
            print(f"    #{c['no']} {c['name']}")
            print(f"       书单={c['list_status']} / 实际已录 {c['actual_parts']}")
            print(f"       证据：{c['sources']}")

    print("\n【4】建议下一本")
    print("-" * 78)
    if next_pick:
        print(f"  书单 #{next_pick['no']} 《{next_pick['name']}》")
        print(f"  作者 {next_pick['author']} / ISBN {next_pick['isbn']}")
        print("  从「上部」开始，按一书三分批量出上/中/下")
    else:
        print("  书单已全部录完（或状态需订正），按书单规则进入自由选书/荐书")

    if conflicts:
        if args.fix_list:
            txt = BOOK_LIST.read_text(encoding="utf-8")
            changed = 0
            for c in conflicts:
                old_name = c["name"]
                # 定位该行的状态单元格（第 5 列）并替换为「已完结」
                for line in txt.splitlines():
                    if not line.strip().startswith("|"):
                        continue
                    cells = [x.strip() for x in line.strip().strip("|").split("|")]
                    if len(cells) >= 5 and cells[0].isdigit() and int(cells[0]) == c["no"]:
                        if cells[4].replace("**", "") != "已完结":
                            new_line = line.replace(cells[4], "已完结", 1)
                            txt = txt.replace(line, new_line, 1)
                            changed += 1
                        break
            if changed:
                BOOK_LIST.write_text(txt, encoding="utf-8")
                print(f"\n  已回写书单状态 {changed} 处 → 已完结（{BOOK_LIST}）")
                print("  记得 git commit 并推送 GitHub（书单是技能级共享资产）")
        else:
            print("\n  提示：加 --fix-list 可自动把上述滞后状态回写为「已完结」")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
