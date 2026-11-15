#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_recorded.py — 「交付文件夹 ↔ 短视频目录」对账 + 幂等自动补录（Step 8 强制）

背景（2026-11-15 作者指令「已经录制过的主题，不要再录制了」）：
  判定侧已由 recorded_index.py 升级为多源聚合，但**写回侧**仍可能漏：
  `目录/*.md` 靠 Step 8 手工调用 update_catalog.py，某轮中断 / 无人值守就永久漏登，
  下次目录资产同步、换客户端都会带着这个洞。本脚本把写回变成确定性对账：
  扫各工作区里「有交付物」的视频文件夹，与本地目录逐条比对，漏登则自动补录。

自动补录的准入条件（正确性优先 · 不满足一律不写，只列「需人工确认」）：
  1. 文件夹里确有交付物（成片 mp4 / PPT.html / 口播稿 txt 任一）——空文件夹不算已录；
  2. 文件夹标题与成片文件基名一致——不一致说明是书名/分节/改过标题等争议条目；
  3. 能客观判定训练营大类：口播稿文件名前缀 `<营名>-` 或 metrics.csv 同标题行的「训练营」列；
     猜不出来就不写（不臆造档位与维度）。
  档位取 metrics.csv 同标题行，取不到写 `–`；能力维度一律 `–`（无可靠来源，不编）；
  日期取文件夹后缀 `_<YYYYMMDD>-<NN>`，不取「今天」，避免补录日期失真。

用法：
  python3 audit_recorded.py                       # 只出对账清单（不写盘，exit 3 = 有漏登）
  python3 audit_recorded.py --apply              # 幂等自动补录（Step 8 强制口径）
  python3 audit_recorded.py --workspace <ws>     # 追加扫描指定工作区
  python3 audit_recorded.py --json               # 机器可读

退出码：0 = 目录与实物一致（或已补录完成）；3 = 仍有漏登未处理 / 需人工确认。
仅标准库；写操作只落「主工作区 目录/」这一唯一事实来源，不动项目资产与网盘。
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import recorded_index as ri
from check_recorded import load_titles, CATEGORY_FILENAMES
from update_catalog import update_category_file, update_overview, norm_camp


def catalog_entries(workspace):
    cat_dir = os.path.join(workspace, "目录")
    return [{"title": t, "camp": c, "source": "catalog", "meta": {}}
            for c, t in load_titles(cat_dir)]


def metrics_index(workspaces):
    """标题 → {训练营, 档位}，用于补录时客观取元数据。"""
    out = {}
    for ws in workspaces:
        p = os.path.join(ws, "metrics.csv")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    t = (row.get("标题") or "").strip()
                    if t:
                        out[ri.norm(t)] = {"camp": norm_camp(row.get("训练营")) or "",
                                           "tier": (row.get("档位") or "").strip()}
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return out


def main():
    ap = argparse.ArgumentParser(description="交付文件夹 ↔ 目录对账补录")
    ap.add_argument("--workspace", help="追加扫描的工作区（默认自动发现全部）")
    ap.add_argument("--apply", action="store_true", help="幂等自动补录漏登条目")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    entries, folders, ws_list = ri.build_index(args.workspace)
    cat = catalog_entries(args.workspace or ri.DEFAULT_WORKSPACE)
    mindex = metrics_index(ws_list)

    already, fixable, manual = [], [], []
    for f in folders:
        hits = ri.find_hits(f["title"], cat)
        if hits:
            already.append({"title": f["title"], "hit": hits[0]["title"]})
            continue
        m = mindex.get(ri.norm(f["title"]), {})
        camp = f.get("camp") or m.get("camp") or ""
        row = {
            "title": f["title"], "path": f["path"], "date": f.get("date", ""),
            "camp": camp, "tier": m.get("tier") or "–", "dim": "–",
        }
        if f.get("title_mismatch"):
            row["reason"] = "文件夹标题与成片文件基名不一致（书名/分节/改标题等争议条目）"
            manual.append(row)
        elif not camp:
            row["reason"] = "无法客观判定训练营大类（口播稿前缀与 metrics 均无）"
            manual.append(row)
        else:
            fixable.append(row)

    applied = []
    if args.apply and fixable:
        workspace = args.workspace or ri.DEFAULT_WORKSPACE
        cat_dir = os.path.join(workspace, "目录")
        os.makedirs(cat_dir, exist_ok=True)
        for row in fixable:
            cat_file = os.path.join(cat_dir, CATEGORY_FILENAMES[row["camp"]])
            seq, added = update_category_file(
                cat_file, row["camp"], row["title"], row["tier"], row["dim"],
                row["date"] or "–")
            update_overview(cat_dir, row["camp"], row["title"])
            applied.append({**row, "seq": seq, "added": added})

    data = {
        "workspace": args.workspace or ri.DEFAULT_WORKSPACE,
        "workspaces_scanned": ws_list,
        "delivery_folders": len(folders),
        "catalog_rows": len(cat),
        "already_in_catalog": already,
        "missing_fixable": [] if args.apply else fixable,
        "applied": applied,
        "need_manual": manual,
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("交付文件夹 ↔ 短视频目录 对账\n")
        print(f"  扫描工作区 {len(ws_list)} 个｜有交付物的视频 {len(folders)} 个｜目录已登记 {len(cat)} 条")
        print(f"  已入目录 {len(already)} 条｜漏登可补 {len(fixable)} 条｜需人工确认 {len(manual)} 条\n")
        if fixable:
            print("【漏登 · 可自动补录】")
            for r in fixable:
                print(f"  · [{r['camp']}] {r['title']}  ({r['date'] or '日期未知'} · 档位 {r['tier']})")
                print(f"    证据 {r['path']}")
            if applied:
                print(f"\n  ✅ 已自动补录 {len(applied)} 条（幂等，期序见 目录/）")
        if manual:
            print("\n【需人工确认 · 未自动写入】")
            for r in manual:
                print(f"  · {r['title']} —— {r['reason']}")
                print(f"    {r['path']}")
        if not fixable and not manual:
            print("  ✅ 目录与实物一致，无漏登")
    # 未 apply 时，有漏登即视为未闭环；apply 后仍有需人工确认的也提示（exit 3）
    pending = manual or (fixable if not args.apply else [])
    return 3 if pending else 0


if __name__ == "__main__":
    sys.exit(main())
