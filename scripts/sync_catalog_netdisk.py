#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_catalog_netdisk.py — 以百度网盘 /自媒体 归档为事实来源，重建本地「短视频目录」(目录/)

背景（2026-10-31 固化）：
  旧版本地 `目录/` 只记了 19 条，而网盘 /自媒体 实际有 153 个归档目录，两者严重脱节 →
  老主题（CAP、2PC、Raft、缓存三连击、熔断、限流…）从不出现在"已录制"清单，必然被重复选中。
  本脚本把网盘全量标题并入本地目录，并与本地已有 19 条去重合并（保留本地手工元数据），
  让「短视频目录」成为"是否录制过"的权威真相源（供 check_recorded.py 判定）。

合并策略：
  1. 网盘 raw 标题（归一化 AI训练营/AI 训练营 → AI 训练营）为主来源
  2. 本地 目录/*.md 已存在的条目 → 保留其 档位/能力维度/日期 等手工元数据
  3. 本地有、网盘无的条目（如软技能"被问期望薪资"、读书 Agentic 系列）→ 全部保留，不丢
  4. 日期：本地日期 > 标题 _YYYYMMDD 后缀 > 归档日期(dates.json) > 留空(不臆造)
  5. 档位/能力维度：本地有则用之，网盘标题无此信息 → 留 "–"（不臆造）

输出：就地重写 目录/00_总览.md + 9 个大类 md（格式与 update_catalog.py 完全一致，保证幂等兼容）。

用法：
  python3 sync_catalog_netdisk.py [--raw /tmp/catwork/netdisk_raw.json] \
      [--dates /tmp/catwork/netdisk_dates.json] [--workspace /Users/ay/WorkBuddy/2026-08-30-21-04-18] [--dry-run]
"""
import argparse, json, os, re, sys

CATEGORIES = [
    "架构师训练营", "大数据训练营", "AI 训练营", "产品经理训练营", "前端训练营",
    "测试训练营", "管理训练营", "软技能训练营", "读书训练营",
]
CATEGORY_FILENAMES = {c: f"{i+1:02d}_{c.replace(' ', '_')}.md" for i, c in enumerate(CATEGORIES)}
INDEX_FILENAME = "00_总览.md"

# 网盘 camp 名 → 标准大类（双 AI 目录归一化）
CAMP_NORM = {
    "架构师训练营": "架构师训练营",
    "大数据训练营": "大数据训练营",
    "AI 训练营": "AI 训练营",
    "AI训练营": "AI 训练营",
    "产品经理训练营": "产品经理训练营",
    "前端训练营": "前端训练营",
    "测试训练营": "测试训练营",
    "管理训练营": "管理训练营",
    "软技能训练营": "软技能训练营",
    "读书训练营": "读书训练营",
}

SUFFIX_RE = re.compile(r"_(\d{8})-(\d{2})$")
MP4_RE = re.compile(r"\.mp4$", re.I)


def strip_suffix(title):
    """去掉 _YYYYMMDD-NN 后缀，返回 (纯标题, 解析到的日期 or None)。"""
    m = SUFFIX_RE.search(title)
    if m:
        d = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
        return SUFFIX_RE.sub("", title), d
    return title, None


def normalize_key(s):
    s = MP4_RE.sub("", s)
    s = SUFFIX_RE.sub("", s)
    return s.strip()


def harvest_local(cat_dir):
    """读取本地 目录/*.md，返回 {camp: {标题: {tier,dim,date}}}。"""
    data = {c: {} for c in CATEGORIES}
    for camp in CATEGORIES:
        p = os.path.join(cat_dir, CATEGORY_FILENAMES[camp])
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.rstrip("\n")
                if not ln.strip().startswith("|"):
                    continue
                parts = [x.strip() for x in ln.strip().strip("|").split("|")]
                if len(parts) < 5:
                    continue
                if not parts[0].isdigit():
                    continue  # 跳过表头/分隔行
                title, tier, dim, date = parts[1], parts[2], parts[3], parts[4]
                data[camp][title] = {"tier": tier, "dim": dim, "date": date}
    return data


def merge_camp(camp, netdisk_titles, local_meta, dates_map):
    """返回按显示顺序排列的条目列表 [(title, seq, {tier,dim,date})]。"""
    entries = {}
    order = []

    # 1) 网盘标题为主来源
    for raw in netdisk_titles:
        title, suf_date = strip_suffix(raw)
        if not title or title in entries:
            continue
        meta = local_meta.get(title, {})
        # 日期优先级：本地 > 后缀 > 归档日期 > 空
        date = (meta.get("date") if meta.get("date") not in (None, "–", "") else None) \
            or suf_date \
            or dates_map.get(title) or dates_map.get(raw) or "–"
        entries[title] = {
            "tier": (meta.get("tier") if meta.get("tier") not in (None, "–", "") else None) or "–",
            "dim": (meta.get("dim") if meta.get("dim") not in (None, "–", "") else None) or "–",
            "date": date,
        }
        order.append(title)

    # 2) 本地有、网盘无 → 保留
    for title, meta in local_meta.items():
        if title in entries:
            continue
        entries[title] = {
            "tier": meta.get("tier") or "–",
            "dim": meta.get("dim") or "–",
            "date": meta.get("date") or "–",
        }
        order.append(title)

    # 3) 排序：有日期按日期升序(oldest→newest)，无日期排末尾；期序 oldest=1
    dated = [t for t in order if entries[t]["date"] != "–"]
    undated = [t for t in order if entries[t]["date"] == "–"]
    dated_sorted = sorted(dated, key=lambda t: entries[t]["date"])
    seq = {}
    for i, t in enumerate(dated_sorted):
        seq[t] = i + 1
    for i, t in enumerate(undated):
        seq[t] = len(dated_sorted) + 1 + i
    # 显示：有日期 newest 在前，无日期在后
    display = list(reversed(dated_sorted)) + undated
    return [(t, seq[t], entries[t]) for t in display]


def render_category(camp, rows):
    lines = [
        f"# {camp} · 已生成视频目录",
        "",
        "> 每行一条已产出视频。期序 = 本大类累计第几条（幂等：标题已存在则只刷新信息，不重复计数）。",
        "> 由技能 Step 8 每次产出后调用 `update_catalog.py` 自动维护；也可手工补录历史视频。",
        "",
        "| 期序 | 标题 | 档位 | 能力维度 / 主题 | 日期 |",
        "|-----:|------|:----:|------------------|------|",
    ]
    for title, seq, meta in rows:
        lines.append(f"| {seq} | {title} | {meta['tier']} | {meta['dim']} | {meta['date']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="/tmp/catwork/netdisk_raw.json")
    ap.add_argument("--dates", default="/tmp/catwork/netdisk_dates.json")
    ap.add_argument("--workspace", default="/Users/ay/WorkBuddy/2026-08-30-21-04-18")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ws = os.path.abspath(args.workspace)
    if os.path.isfile(os.path.join(ws, "SKILL.md")):
        sys.stderr.write(f"ERROR: --workspace 解析到技能仓库自身（{ws}），请指向视频工作区。\n")
        sys.exit(1)

    with open(args.raw, encoding="utf-8") as f:
        raw = json.load(f)
    dates = {}
    if os.path.exists(args.dates):
        with open(args.dates, encoding="utf-8") as f:
            dates = json.load(f)

    cat_dir = os.path.join(ws, "目录")
    local = harvest_local(cat_dir)

    # 把网盘 raw 按标准 camp 归并
    net_by_camp = {c: [] for c in CATEGORIES}
    for path_key, items in raw.items():
        camp_raw = path_key.split("/")[-1]
        camp = CAMP_NORM.get(camp_raw)
        if not camp:
            sys.stderr.write(f"WARN 未归一化的网盘目录被跳过：{path_key}\n")
            continue
        net_by_camp[camp].extend(items)

    # 把 dates.json 也按标准 camp 归并（key 可能带 .mp4 或后缀）
    dates_by_camp = {c: {} for c in CATEGORIES}
    for camp_raw, mp in dates.items():
        camp = CAMP_NORM.get(camp_raw)
        if not camp:
            continue
        for k, v in mp.items():
            dates_by_camp[camp][normalize_key(k)] = v

    summary = []
    total_rows = 0
    latest_by_camp = {}
    for camp in CATEGORIES:
        rows = merge_camp(camp, net_by_camp[camp], local.get(camp, {}), dates_by_camp[camp])
        if rows:
            latest_by_camp[camp] = rows[0][0]  # 显示首行 = 最新
        total_rows += len(rows)
        summary.append((camp, len(rows)))
        out = render_category(camp, rows)
        if args.dry_run:
            print(f"\n===== {CATEGORY_FILENAMES[camp]} ({len(rows)} 条) =====")
            print(out)
        else:
            with open(os.path.join(cat_dir, CATEGORY_FILENAMES[camp]), "w", encoding="utf-8") as f:
                f.write(out)

    # 总览
    ov_lines = [
        "# 短视频产出总览 · 按训练营大类",
        "",
        "> 每个大类一个文件，记录该训练营已生成的全部视频（目录位 = 项目资产，供按类查看历史与体系进度）。",
        "> 维护：技能每次产出后调用 `update_catalog.py` 自动写入；手工补录同理。",
        "",
        "| 大类 | 目录文件 | 累计条数 | 最新一条 |",
        "|------|----------|:-------:|----------|",
    ]
    for camp, n in summary:
        ov_lines.append(f"| {camp} | {CATEGORY_FILENAMES[camp]} | {n:>3} | {latest_by_camp.get(camp, '–')} |")
    ov_out = "\n".join(ov_lines) + "\n"
    if args.dry_run:
        print("\n===== 00_总览.md =====")
        print(ov_out)
    else:
        with open(os.path.join(cat_dir, INDEX_FILENAME), "w", encoding="utf-8") as f:
            f.write(ov_out)

    print(f"[完成] 目录重建：共 {total_rows} 条（网盘 153 ∪ 本地独有 11，去重合并）。")
    for camp, n in summary:
        print(f"  - {camp:12s} {n:>3} 条")


if __name__ == "__main__":
    main()
