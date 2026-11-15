#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_recorded.py — 判定「某主题是否已录制过」（Step 0 第 5.5 条防重复录制门禁）

背景（2026-10-31 首次固化 → 2026-11-15 升级为多源聚合）：
  2026-10-31：早前只查 topic_pool.json 的 status / syllabus.json 的 covered，
    而旧目录只记 19 条、网盘实际 153 条 → 老主题被重复选中。改为以「短视频目录」为准。
  2026-11-15（作者指令「已经录制过的主题，不要再录制了，可以从资产里面读取」）：
    实测又发现写回环节会漏 —— 主工作区 21 个交付文件夹有 5 个未入目录，
    单信 目录/*.md 时这 5 个主题全部被判「未录制」，可以再录一遍。
    故判定底座升级为 `recorded_index.py` 的**多源聚合索引**：目录 / 交付文件夹 /
    metrics.csv / jobs 台账 / 百度网盘归档快照 / 项目资产目录副本 / 技能内状态，
    任一来源命中即判已录制。本文件保留原 CLI 与退出码，作为门禁入口兼容层。

判定层级（命中任一即判为已录制，逻辑与 recorded_index.find_hits 一致）：
  1. exact    —— 规范化后完全一致
  2. substr   —— 规范化后互为子串（含候选被已录标题包含，或反之）
  3. fuzzy    —— 字符 2-gram Jaccard ≥ 阈值（默认 0.55）

退出码：
  0 —— 未录制（可以放心录制）
  3 —— 已录制（打印命中清单，供选题环节拦截）

用法：
  python3 check_recorded.py "候选标题" [--workspace <工作区>] [--threshold 0.55] [--json]
  python3 check_recorded.py --list [--sources]           # 列出多源已录主题总表
  python3 check_recorded.py --batch candidates.txt      # 批量判（每行一个候选）
  python3 check_recorded.py --catalog-only ...          # 调试：只信旧的单源目录
"""
import argparse, json, os, re, sys

CATEGORIES = [
    "架构师训练营", "大数据训练营", "AI 训练营", "产品经理训练营", "前端训练营",
    "测试训练营", "管理训练营", "软技能训练营", "读书训练营",
]
CATEGORY_FILENAMES = {c: f"{i+1:02d}_{c.replace(' ', '_')}.md" for i, c in enumerate(CATEGORIES)}
DEFAULT_WORKSPACE = "/Users/ay/WorkBuddy/2026-08-30-21-04-18"

SUFFIX_RE = re.compile(r"_?\d{8}-\d{2}$")
FULLWIDTH = {"（": "(", "）": ")", "：": ":", "，": ",", "、": ",", "。": ".", "！": "!", "？": "?"}


def norm(t):
    t = (t or "").strip()
    t = SUFFIX_RE.sub("", t)
    for k, v in FULLWIDTH.items():
        t = t.replace(k, v)
    t = re.sub(r"\s+", "", t)
    return t.lower()


def bigrams(s):
    s = norm(s)
    if len(s) <= 1:
        return {s}
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def load_titles(cat_dir):
    """返回 [(camp, title), ...] 全量已录标题。"""
    out = []
    for camp in CATEGORIES:
        p = os.path.join(cat_dir, CATEGORY_FILENAMES[camp])
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln.startswith("|"):
                    continue
                parts = [x.strip() for x in ln.strip().strip("|").split("|")]
                if len(parts) < 5 or not parts[0].isdigit():
                    continue
                out.append((camp, parts[1]))
    return out


def match(candidate, titles, threshold):
    """返回命中清单 [(recorded_title, camp, kind, score)]。"""
    cn = norm(candidate)
    hits = []
    for camp, title in titles:
        tn = norm(title)
        if not tn:
            continue
        if cn == tn:
            hits.append((title, camp, "exact", 1.0))
        elif cn in tn or tn in cn:
            hits.append((title, camp, "substr", 1.0))
        else:
            sc = jaccard(candidate, title)
            if sc >= threshold:
                hits.append((title, camp, "fuzzy", round(sc, 3)))
    # 去重 + 按相似度降序
    seen = set()
    uniq = []
    for h in sorted(hits, key=lambda x: -x[3]):
        key = (h[0], h[1], h[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", nargs="?", help="候选标题")
    ap.add_argument("--workspace", default=DEFAULT_WORKSPACE)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true", help="列出多源已录主题总表")
    ap.add_argument("--sources", action="store_true", help="--list 时附带命中来源")
    ap.add_argument("--catalog-only", action="store_true", help="调试：退回旧的「只信本地目录」单源判定")
    ap.add_argument("--batch", help="批量判：每行一个候选的 txt 路径")
    args = ap.parse_args()

    ws = os.path.abspath(args.workspace)
    if os.path.isfile(os.path.join(ws, "SKILL.md")):
        sys.stderr.write(f"ERROR: --workspace 解析到技能仓库自身（{ws}）\n")
        sys.exit(2)

    # 延迟导入：避免与 recorded_index.py（它复用本文件的 norm/jaccard/load_titles）循环导入
    from recorded_index import build_index, find_hits, dedup_titles

    if args.catalog_only:
        entries = [{"title": t, "camp": c, "source": "catalog", "meta": {}}
                   for c, t in load_titles(os.path.join(ws, "目录"))]
    else:
        entries, _, _ = build_index(workspace=ws)

    if args.list:
        for r in dedup_titles(entries):
            line = f"{r['camp'] or '-'}\t{r['title']}"
            if args.sources:
                line += f"\t{','.join(r['sources'])}"
            print(line)
        sys.exit(0)

    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            cands = [l.strip() for l in f if l.strip()]
        results = []
        for c in cands:
            h = find_hits(c, entries, args.threshold)
            results.append({"candidate": c, "recorded": bool(h), "hits": h})
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for r in results:
                flag = "已录制" if r["recorded"] else "未录制"
                tail = (f"  ← [{r['hits'][0]['source']}] {r['hits'][0]['title']}"
                        if r["hits"] else "")
                print(f"[{flag}] {r['candidate']}{tail}")
        sys.exit(3 if any(r["recorded"] for r in results) else 0)

    if not args.candidate:
        sys.stderr.write("需传 candidate 或 --list / --batch\n")
        sys.exit(2)

    hits = find_hits(args.candidate, entries, args.threshold)
    if args.json:
        print(json.dumps({"candidate": args.candidate, "recorded": bool(hits),
                          "hits": hits}, ensure_ascii=False, indent=2))
    if hits:
        print(f"⛔ 已录制：候选「{args.candidate}」命中 {len(hits)} 条（多源聚合）：")
        for h in hits:
            print(f"   · [{h['source']}/{h['camp'] or '-'}] {h['title']}  ({h['kind']} score={h['score']})")
        sys.exit(3)
    else:
        print(f"✅ 未录制：全部来源无匹配项，可放心录制「{args.candidate}」")
        sys.exit(0)


if __name__ == "__main__":
    main()
