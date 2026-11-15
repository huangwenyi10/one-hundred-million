#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recorded_index.py — 「已录制主题」多源聚合索引（防重复录制的唯一判定底座）

背景（2026-11-15 作者指令「已经录制过的主题，不要再录制了，可以从资产里面读取」）：
  旧判定只信本地 `目录/*.md` 一处，且写回靠 Step 8 手工调用 update_catalog.py，
  某轮中断就永久漏登 → 实测主工作区 21 个交付文件夹里有 5 个未入目录，
  老门禁对它们全部返回「未录制」，可以再录一遍。
  本脚本把「录过什么」从单源改为多源聚合，任一来源命中即判已录制。

聚合来源（优先级仅影响展示，不影响判定；任一命中即拦）：
  1. catalog          本地 `目录/*.md` 9 大类（原权威源，含期序/档位/维度元数据）
  2. delivery_dir     各工作区顶层 `<标题>_<YYYYMMDD>-<NN>/` 交付文件夹
                      —— 只认「有交付物」的目录（成片 mp4 / PPT.html / 口播稿 txt 任一），
                         空文件夹或仅建了目录的废弃任务不算已录（正确性优先，不臆造）
  3. metrics          `metrics.csv` 的标题列
  4. jobs             `one-hundred-million-jobs.json` 中 done_stages 含 final/publish 的 title
  5. netdisk          百度网盘 `/自媒体/<营>/` 归档目录名（离线快照 assets/state/recorded_netdisk.json）
  6. tdrive_catalog   项目资产 `短视频目录/` 的 9 类 md（离线快照 assets/state/tdrive_catalog/）
  7. topic_pool_done  技能内 `assets/topics/topic_pool.json` 中 status=done 的标题锚点
  8. syllabus_topic   技能内 `assets/state/syllabus.json` 各营 lastTopic

明确「不纳入标题级判定」的两类（避免误杀，见 references/recorded-topics.md）：
  - `syllabus.json` 的 `covered` 是能力维度词（如「高并发」），不是视频标题，
    拿它做子串/模糊匹配会把同维度下的新主题全误判为已录 → 只作体系定位提示。
  - `reading_camp_progress.json` 的书目状态含「作废·待重录」，把书名当已录标题会
    挡住作者明确要重录的书 → 读书营走 reading_progress_scan.py 的原有门禁。

离线快照说明（诚实边界）：本脚本**不联网、不调 MCP**。网盘 / 项目资产由 AI 在会话里
用 MCP 只读拉取后，通过 `import-netdisk` / `import-tdrive` 落成技能内快照；
快照带 updated 日期，`stats` / `snapshot-status` 会提示陈旧。快照缺失不阻塞判定，
其余 6 个本地来源照常生效。

用法：
  python3 recorded_index.py stats                          # 各来源条数 + 快照新鲜度
  python3 recorded_index.py list [--json] [--source X]     # 去重后的已录主题总表
  python3 recorded_index.py check "<候选标题>" [--json]    # exit 0 未录 / 3 已录
  python3 recorded_index.py batch candidates.txt          # 批量判定
  python3 recorded_index.py import-netdisk <mcp.json>     # 导入网盘归档目录清单
  python3 recorded_index.py import-tdrive <md目录>        # 导入项目资产目录副本
  python3 recorded_index.py snapshot-status               # 只看快照状态

约束：仅标准库；路径相对技能根自定位，任何客户端可跑；读操作零副作用。
"""
import argparse
import csv
import glob as globmod
import json
import os
import re
import shutil
import sys
import time

from check_recorded import (
    norm, jaccard, CATEGORIES, CATEGORY_FILENAMES, load_titles,
)
from update_catalog import norm_camp

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)  # 从技能根 / 任意 cwd 导入本模块时都能找到同目录脚本
SKILL_ROOT = os.path.dirname(HERE)
STATE_DIR = os.path.join(SKILL_ROOT, "assets", "state")
NETDISK_SNAPSHOT = os.path.join(STATE_DIR, "recorded_netdisk.json")
TDRIVE_SNAPSHOT_DIR = os.path.join(STATE_DIR, "tdrive_catalog")
POOL_PATH = os.path.join(SKILL_ROOT, "assets", "topics", "topic_pool.json")
SYLLABUS_PATH = os.path.join(STATE_DIR, "syllabus.json")

DEFAULT_WORKSPACE = os.environ.get(
    "ONE_HUNDRED_MILLION_WORKSPACE", "/Users/ay/WorkBuddy/2026-08-30-21-04-18")
WORKSPACE_GLOB = os.environ.get(
    "ONE_HUNDRED_MILLION_WORKSPACE_GLOB", "/Users/ay/WorkBuddy/*")

DIR_SUFFIX_RE = re.compile(r"_(\d{8})-(\d{2})$")
MP4_RE = re.compile(r"\.mp4$", re.I)
DELIVERABLE_PATTERNS = ("*_成片.mp4", "*_PPT.html", "*_口播稿.txt")

SOURCE_ORDER = [
    "catalog", "delivery_dir", "metrics", "jobs", "netdisk",
    "tdrive_catalog", "topic_pool_done", "syllabus_topic",
]


def strip_dir_suffix(name):
    """`<标题>_<YYYYMMDD>-<NN>` → (纯标题, YYYY-MM-DD or None)。"""
    m = DIR_SUFFIX_RE.search(name)
    if m:
        d = m.group(1)
        return DIR_SUFFIX_RE.sub("", name), f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return name, None


def clean_title(raw):
    """网盘/台账里可能出现的 `.mp4` 尾缀与日期后缀一并去掉。"""
    s = MP4_RE.sub("", (raw or "").strip())
    s, _ = strip_dir_suffix(s)
    return s.strip()


def entry(title, source, camp="", meta=None):
    return {"title": title, "source": source, "camp": camp, "meta": meta or {}}


def discover_workspaces(explicit=None):
    """主工作区 + /Users/ay/WorkBuddy/* 下所有会话工作区（自动发现，换客户端不丢）。"""
    found = []
    for p in [explicit, DEFAULT_WORKSPACE]:
        if p and os.path.isdir(p) and os.path.abspath(p) not in found:
            found.append(os.path.abspath(p))
    for p in sorted(globmod.glob(WORKSPACE_GLOB)):
        if os.path.isdir(p) and os.path.abspath(p) not in found:
            found.append(os.path.abspath(p))
    return found


def has_deliverable(path):
    for pat in DELIVERABLE_PATTERNS:
        if globmod.glob(os.path.join(path, pat)):
            return True
    return False


def scan_delivery_dirs(workspaces):
    """返回 (entries, folder_meta)。folder_meta 供 audit_recorded.py 对账补录用。"""
    entries, folders = [], []
    for ws in workspaces:
        try:
            names = os.listdir(ws)
        except OSError:
            continue
        for name in names:
            if not DIR_SUFFIX_RE.search(name):
                continue
            path = os.path.join(ws, name)
            if not os.path.isdir(path) or not has_deliverable(path):
                continue  # 空目录 / 废弃任务不算已录
            title, date = strip_dir_suffix(name)

            # 交付物基名与文件夹标题是否一致：不一致属争议条目，仍纳入「已录」判定，
            # 但 audit --apply 不自动补录（如 书名文件夹 vs 实际分节成片）。
            mismatch = False
            mp4s = globmod.glob(os.path.join(path, "*_成片.mp4"))
            if mp4s:
                base = os.path.basename(mp4s[0])[: -len("_成片.mp4")]
                a, b = norm(title), norm(base)
                mismatch = not (a == b or a in b or b in a)

            # 训练营可从 `<营名>-<标题>_口播稿.txt` 前缀客观推断：
            # 先查交付目录内，再查工作区顶层散落的口播稿（历史上有稿件没放进目录的情况）。
            camp = ""
            scripts = globmod.glob(os.path.join(path, "*_口播稿.txt"))
            if scripts:
                prefix = os.path.basename(scripts[0]).split("-", 1)[0]
                camp = norm_camp(prefix) or ""
            if not camp:
                needle = "-" + title + "_口播稿.txt"
                for fn in names:
                    if fn.endswith(needle):
                        camp = norm_camp(fn[: -len(needle)]) or ""
                        if camp:
                            break

            meta = {"path": path, "date": date or "", "camp": camp,
                    "title_mismatch": mismatch}
            folders.append({"title": title, **meta})
            entries.append(entry(title, "delivery_dir", camp, meta))
    return entries, folders


def scan_metrics(workspaces):
    out = []
    for ws in workspaces:
        p = os.path.join(ws, "metrics.csv")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    t = (row.get("标题") or "").strip()
                    if not t:
                        continue
                    out.append(entry(t, "metrics", norm_camp(row.get("训练营")) or "",
                                     {"date": row.get("日期", ""), "tier": row.get("档位", "")}))
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return out


def scan_jobs(workspaces):
    out = []
    for ws in workspaces:
        p = os.path.join(ws, "one-hundred-million-jobs.json")
        if not os.path.isfile(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            stages = job.get("done_stages") or []
            if not ({"final", "publish"} & set(stages)):
                continue  # 只写稿/未成片，不算已录
            t = (job.get("title") or key or "").strip()
            if t:
                out.append(entry(t, "jobs", "", {"dir": job.get("dir", "")}))
    return out


def scan_netdisk_snapshot():
    if not os.path.isfile(NETDISK_SNAPSHOT):
        return []
    try:
        data = json.load(open(NETDISK_SNAPSHOT, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for row in data.get("dirs") or []:
        if not isinstance(row, dict):
            continue
        t = clean_title(row.get("name") or "")
        if t:
            out.append(entry(t, "netdisk", norm_camp(row.get("camp")) or "",
                             {"raw": row.get("name", "")}))
    return out


def scan_tdrive_snapshot():
    if not os.path.isdir(TDRIVE_SNAPSHOT_DIR):
        return []
    out = []
    for camp in CATEGORIES:
        p = os.path.join(TDRIVE_SNAPSHOT_DIR, CATEGORY_FILENAMES[camp])
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    if not ln.strip().startswith("|"):
                        continue
                    parts = [x.strip() for x in ln.strip().strip("|").split("|")]
                    if len(parts) < 5 or not parts[0].isdigit():
                        continue
                    out.append(entry(parts[1], "tdrive_catalog", camp))
        except (OSError, UnicodeDecodeError):
            continue
    return out


def scan_skill_state():
    out = []
    if os.path.isfile(POOL_PATH):
        try:
            pool = json.load(open(POOL_PATH, encoding="utf-8"))
            for camp, items in (pool.get("pools") or {}).items():
                for it in items:
                    if it.get("status") == "done" and it.get("title"):
                        out.append(entry(it["title"], "topic_pool_done", camp,
                                         {"id": it.get("id", "")}))
        except (OSError, ValueError):
            pass
    if os.path.isfile(SYLLABUS_PATH):
        try:
            st = json.load(open(SYLLABUS_PATH, encoding="utf-8"))
            for camp, cfg in (st.get("camps") or {}).items():
                t = (cfg.get("lastTopic") or "").strip() if isinstance(cfg, dict) else ""
                if t:
                    out.append(entry(t, "syllabus_topic", camp))
        except (OSError, ValueError):
            pass
    return out


def build_index(workspace=None, sources=None):
    """返回 (entries, folders, workspaces)。sources 为 None 时全来源。"""
    ws_list = discover_workspaces(workspace)
    want = set(sources or SOURCE_ORDER)
    entries = []

    cat_dir = os.path.join(workspace or DEFAULT_WORKSPACE, "目录")
    if "catalog" in want:
        # 目录唯一事实来源：始终以主工作区为准（catalog-sync.md 顶部硬规则），
        # 显式传 --workspace 时以其为准。
        for camp, title in load_titles(cat_dir):
            entries.append(entry(title, "catalog", camp))

    if "delivery_dir" in want:
        de, folders = scan_delivery_dirs(ws_list)
        entries.extend(de)
    else:
        folders = []
    if "metrics" in want:
        entries.extend(scan_metrics(ws_list))
    if "jobs" in want:
        entries.extend(scan_jobs(ws_list))
    if "netdisk" in want:
        entries.extend(scan_netdisk_snapshot())
    if "tdrive_catalog" in want:
        entries.extend(scan_tdrive_snapshot())
    if want & {"topic_pool_done", "syllabus_topic"}:
        entries.extend([e for e in scan_skill_state() if e["source"] in want])
    return entries, folders, ws_list


def find_hits(candidate, entries, threshold=0.55):
    """与 check_recorded.py 完全一致的 exact / substr / fuzzy 三级判定，附带来源。"""
    cn = norm(candidate)
    hits = []
    for e in entries:
        tn = norm(e["title"])
        if not tn:
            continue
        if cn == tn:
            kind, score = "exact", 1.0
        elif cn in tn or tn in cn:
            kind, score = "substr", 1.0
        else:
            score = jaccard(candidate, e["title"])
            if score < threshold:
                continue
            kind = "fuzzy"
        hits.append({"title": e["title"], "camp": e["camp"], "source": e["source"],
                     "kind": kind, "score": round(score, 3), "meta": e["meta"]})
    seen, uniq = set(), []
    for h in sorted(hits, key=lambda x: -x["score"]):
        key = (h["title"], h["source"], h["kind"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


def is_recorded(title, workspace=None, threshold=0.55, entries=None):
    """供 pick_topic.py 等脚本直接调用；导入失败不得静默放行。"""
    if entries is None:
        entries, _, _ = build_index(workspace)
    return bool(find_hits(title, entries, threshold))


def dedup_titles(entries):
    """按规范化标题去重，合并来源。"""
    merged = {}
    for e in entries:
        k = norm(e["title"])
        if not k:
            continue
        if k not in merged:
            merged[k] = {"title": e["title"], "camp": e["camp"], "sources": set()}
        merged[k]["sources"].add(e["source"])
        if not merged[k]["camp"] and e["camp"]:
            merged[k]["camp"] = e["camp"]
    out = []
    for v in merged.values():
        v["sources"] = [s for s in SOURCE_ORDER if s in v["sources"]]
        out.append(v)
    return sorted(out, key=lambda x: x["title"])


def snapshot_info():
    info = {"netdisk": {"exists": False}, "tdrive_catalog": {"exists": False}}
    if os.path.isfile(NETDISK_SNAPSHOT):
        try:
            d = json.load(open(NETDISK_SNAPSHOT, encoding="utf-8"))
            info["netdisk"] = {"exists": True, "updated": d.get("updated", ""),
                               "count": len(d.get("dirs") or []), "path": NETDISK_SNAPSHOT}
        except (OSError, ValueError):
            info["netdisk"] = {"exists": True, "error": "解析失败"}
    if os.path.isdir(TDRIVE_SNAPSHOT_DIR):
        mds = [f for f in os.listdir(TDRIVE_SNAPSHOT_DIR) if f.endswith(".md")]
        info["tdrive_catalog"] = {"exists": True, "count": len(mds),
                                  "path": TDRIVE_SNAPSHOT_DIR}
    return info


def import_netdisk(path):
    """接受 MCP file_list 原始结构 / {"dirs":[...]} / 字符串路径数组。"""
    raw = json.load(open(path, encoding="utf-8"))
    rows = []
    items = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("dirs"), list):
            items = raw["dirs"]
        elif isinstance(raw.get("list"), list):
            items = raw["list"]
        elif isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("list"), list):
            items = raw["data"]["list"]
        elif all(isinstance(v, list) for v in raw.values()):
            # 紧凑格式：{"<训练营>": ["<归档目录名>", ...], ...}
            for camp, names in raw.items():
                for name in names:
                    items.append({"camp": camp, "name": name})
    for it in items:
        if isinstance(it, str):
            p = it
            name = p.rstrip("/").split("/")[-1]
            camp = p.rstrip("/").split("/")[-2] if "/" in p.rstrip("/") else ""
        elif isinstance(it, dict):
            p = it.get("path") or ""
            name = it.get("name") or it.get("filename") or (p.rstrip("/").split("/")[-1] if p else "")
            camp = it.get("camp") or (p.rstrip("/").split("/")[-2] if p.count("/") >= 2 else "")
        else:
            continue
        if not name:
            continue
        rows.append({"camp": norm_camp(camp) or camp, "name": name})
    # 按 (camp, name) 去重
    seen, uniq = set(), []
    for r in rows:
        k = (r["camp"], r["name"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    os.makedirs(STATE_DIR, exist_ok=True)
    payload = {"schema": "ohl-recorded-netdisk/1",
               "updated": time.strftime("%Y-%m-%d"),
               "note": "百度网盘 /自媒体/<营>/ 归档目录名快照；由 AI 用 MCP 只读拉取后导入，脚本本身不联网",
               "dirs": uniq}
    tmp = NETDISK_SNAPSHOT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, NETDISK_SNAPSHOT)
    return payload


def import_tdrive(src_dir):
    if not os.path.isdir(src_dir):
        raise SystemExit(f"ERROR: 目录不存在 {src_dir}")
    os.makedirs(TDRIVE_SNAPSHOT_DIR, exist_ok=True)
    n = 0
    for f in sorted(os.listdir(src_dir)):
        if f.endswith(".md"):
            shutil.copyfile(os.path.join(src_dir, f), os.path.join(TDRIVE_SNAPSHOT_DIR, f))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="已录制主题多源聚合索引")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stats", help="各来源条数 + 快照状态")
    p.add_argument("--workspace")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("list", help="去重后的已录主题总表")
    p.add_argument("--workspace")
    p.add_argument("--source", action="append", choices=SOURCE_ORDER)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check", help="判定候选是否已录制")
    p.add_argument("candidate")
    p.add_argument("--workspace")
    p.add_argument("--threshold", type=float, default=0.55)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("batch", help="批量判定（每行一个候选）")
    p.add_argument("file")
    p.add_argument("--workspace")
    p.add_argument("--threshold", type=float, default=0.55)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("import-netdisk", help="导入百度网盘归档目录清单 JSON")
    p.add_argument("file")

    p = sub.add_parser("import-tdrive", help="导入项目资产目录 md 副本")
    p.add_argument("dir")

    sub.add_parser("snapshot-status", help="查看离线快照状态")
    args = ap.parse_args()

    if args.cmd == "import-netdisk":
        payload = import_netdisk(args.file)
        print(f"已写入网盘快照：{NETDISK_SNAPSHOT}")
        print(f"  {len(payload['dirs'])} 条归档目录，updated={payload['updated']}")
        return 0
    if args.cmd == "import-tdrive":
        n = import_tdrive(args.dir)
        print(f"已写入项目资产目录快照：{TDRIVE_SNAPSHOT_DIR}（{n} 个 md）")
        return 0
    if args.cmd == "snapshot-status":
        print(json.dumps(snapshot_info(), ensure_ascii=False, indent=2))
        return 0

    workspace = getattr(args, "workspace", None)
    sources = getattr(args, "source", None)
    entries, folders, ws_list = build_index(workspace, sources)

    if args.cmd == "stats":
        counts = {s: 0 for s in SOURCE_ORDER}
        for e in entries:
            counts[e["source"]] = counts.get(e["source"], 0) + 1
        data = {"sources": counts, "entries_total": len(entries),
                "unique_titles": len(dedup_titles(entries)),
                "workspaces": ws_list, "snapshots": snapshot_info()}
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print("已录制主题 · 多源聚合\n")
            for s in SOURCE_ORDER:
                print(f"  {s:<18} {counts.get(s, 0):>4} 条")
            print(f"\n  原始条目 {len(entries)} / 去重标题 {data['unique_titles']}")
            print(f"  扫描工作区 {len(ws_list)} 个")
            sn = data["snapshots"]
            print(f"  网盘快照   {'已导入 ' + str(sn['netdisk'].get('count', 0)) + ' 条 @ ' + sn['netdisk'].get('updated', '?') if sn['netdisk']['exists'] else '未导入（可选）'}")
            print(f"  项目资产快照 {'已导入 ' + str(sn['tdrive_catalog'].get('count', 0)) + ' 个 md' if sn['tdrive_catalog']['exists'] else '未导入（可选）'}")
        return 0

    if args.cmd == "list":
        rows = dedup_titles(entries)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for r in rows:
                print(f"{r['camp'] or '-'}\t{r['title']}\t{','.join(r['sources'])}")
        return 0

    if args.cmd == "check":
        hits = find_hits(args.candidate, entries, args.threshold)
        if args.json:
            print(json.dumps({"candidate": args.candidate, "recorded": bool(hits),
                              "hits": hits}, ensure_ascii=False, indent=2))
        elif hits:
            print(f"⛔ 已录制：「{args.candidate}」命中 {len(hits)} 条（多源聚合）")
            for h in hits:
                print(f"   · [{h['source']}/{h['camp'] or '-'}] {h['title']}  ({h['kind']} {h['score']})")
        else:
            print(f"✅ 未录制：8 类来源均无匹配，可录制「{args.candidate}」")
        return 3 if hits else 0

    if args.cmd == "batch":
        with open(args.file, encoding="utf-8") as f:
            cands = [ln.strip() for ln in f if ln.strip()]
        results = [{"candidate": c, "recorded": bool(find_hits(c, entries, args.threshold)),
                    "hits": find_hits(c, entries, args.threshold)} for c in cands]
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for r in results:
                flag = "已录制" if r["recorded"] else "未录制"
                first = r["hits"][0]
                tail = f"  ← [{first['source']}] {first['title']}" if r["hits"] else ""
                print(f"[{flag}] {r['candidate']}{tail}")
        return 3 if any(r["recorded"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
