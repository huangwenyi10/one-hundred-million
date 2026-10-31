#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_recorded.py — 判定「某主题是否已录制过」，权威来源 = 短视频目录 (目录/*.md)

背景（2026-10-31 用户纠偏，固化）：
  早前判定"是否录制过"只查 topic_pool.json 的 status / syllabus.json 的 covered，
  而旧目录只记 19 条、网盘实际 153 条 → 老主题从不出现在任何"已录制"清单，被重复选中。
  用户明确：必须从「短视频目录」判断是否录制过。
  本脚本即该判定的唯一权威实现：读 目录/*.md 全量标题，对候选标题做
  规范化 + 子串 + 字符 2-gram Jaccard 模糊匹配，命中即视为"已录制"。

判定层级（命中任一即判为已录制）：
  1. exact    —— 规范化后完全一致
  2. substr   —— 规范化后互为子串（含候选被已录标题包含，或反之）
  3. fuzzy    —— 字符 2-gram Jaccard ≥ 阈值（默认 0.55）

退出码：
  0 —— 未录制（可以放心录制）
  3 —— 已录制（打印命中清单，供选题环节拦截）

用法：
  python3 check_recorded.py "候选标题" [--workspace /Users/ay/.../2026-08-30-21-04-18] [--threshold 0.55] [--json]
  python3 check_recorded.py --list                      # 列出目录里全部已录标题
  python3 check_recorded.py --batch candidates.txt      # 批量判（每行一个候选）
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
    ap.add_argument("--list", action="store_true", help="列出全部已录标题")
    ap.add_argument("--batch", help="批量判：每行一个候选的 txt 路径")
    args = ap.parse_args()

    ws = os.path.abspath(args.workspace)
    if os.path.isfile(os.path.join(ws, "SKILL.md")):
        sys.stderr.write(f"ERROR: --workspace 解析到技能仓库自身（{ws}）\n")
        sys.exit(2)
    cat_dir = os.path.join(ws, "目录")
    titles = load_titles(cat_dir)

    if args.list:
        for camp, t in titles:
            print(f"{camp}\t{t}")
        sys.exit(0)

    if args.batch:
        with open(args.batch, encoding="utf-8") as f:
            cands = [l.strip() for l in f if l.strip()]
        results = []
        for c in cands:
            h = match(c, titles, args.threshold)
            results.append({"candidate": c, "recorded": bool(h), "hits": [
                {"title": x[0], "camp": x[1], "kind": x[2], "score": x[3]} for x in h]})
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for r in results:
                flag = "已录制" if r["recorded"] else "未录制"
                print(f"[{flag}] {r['candidate']}" + (f"  ← {r['hits'][0]['title']}" if r['hits'] else ""))
        sys.exit(3 if any(r["recorded"] for r in results) else 0)

    if not args.candidate:
        sys.stderr.write("需传 candidate 或 --list / --batch\n")
        sys.exit(2)

    hits = match(args.candidate, titles, args.threshold)
    if args.json:
        print(json.dumps({"candidate": args.candidate, "recorded": bool(hits), "hits": [
            {"title": x[0], "camp": x[1], "kind": x[2], "score": x[3]} for x in hits]}, ensure_ascii=False, indent=2))
    if hits:
        print(f"⛔ 已录制：候选「{args.candidate}」命中短视频目录 {len(hits)} 条：")
        for title, camp, kind, score in hits:
            print(f"   · [{camp}] {title}  ({kind} score={score})")
        sys.exit(3)
    else:
        print(f"✅ 未录制：短视频目录中无匹配项，可放心录制「{args.candidate}」")
        sys.exit(0)


if __name__ == "__main__":
    main()
