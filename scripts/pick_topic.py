#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pick_topic.py — 从共享主题候选池挑选题（跨客户端一致的去重与配比门禁）。

背景:
  主题候选池 assets/topics/topic_pool.json 随技能仓库分发，WorkBuddy / Trae /
  Codex / Qoder / Kimi 读的是同一份文件 -> 各客户端选出的候选不会互相重复。
  已讲进度记在 assets/state/syllabus.json（同样在技能内），切客户端后仍能去重。

用法:
  # 列出全部训练营及候选数
  python3 pick_topic.py list

  # 挑某营的候选（默认过滤已出片，按传播力降序）
  python3 pick_topic.py pick --camp 架构师训练营 -n 5

  # 只要动手型（凑「每 4 期≥1 期动手型」配比）
  python3 pick_topic.py pick --camp 架构师训练营 --hands-on -n 2

  # 只看未覆盖的能力维度（用 syllabus.json 的 covered 去重）
  python3 pick_topic.py pick --camp AI 训练营 --uncovered-only

  # 选题定稿后回写状态：出片 / 弃用+ 原因
  python3 pick_topic.py mark ARC-01 --status done
  python3 pick_topic.py mark ARC-02 --status dropped --reason "热点已过时"

  # 新增自主生成的候选（池内耗尽或追热点时回写）
  python3 pick_topic.py add --camp 架构师训练营 --title "标题锚点" \\
      --dimension 高并发 --angle "切入角度" --tier M --reach 高 --ai-angle "..." --hands-on

  # 校验池与进度一致性（ids 唯一、必填字段齐、状态合法）
  python3 pick_topic.py verify

设计约束:
  - 仅标准库。任一客户端（不限WorkBuddy）都能跑，不连任何私有 API。
  - 状态回写为原子替换（临时文件 + os.replace），避免写到一半被另一客户端读到。
  - 人工在文件里手改过也认：每次读盘都重新解析，不依赖任何内存缓存。
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
POOL_PATH = os.path.join(SKILL_ROOT, "assets", "topics", "topic_pool.json")
STATE_PATH = os.path.join(SKILL_ROOT, "assets", "state", "syllabus.json")

VALID_STATUS = ("unused", "done", "dropped")
VALID_TIER = ("S", "M", "L")
VALID_REACH = ("高", "中", "低")
REACH_RANK = {"高": 0, "中": 1, "低": 2}
REQUIRED = ("id", "title", "dimension", "angle", "tier", "reach", "status")


def die(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_pool():
    if not os.path.exists(POOL_PATH):
        die(f"主题池不存在: {POOL_PATH}")
    try:
        with open(POOL_PATH, encoding="utf-8") as f:
            pool = json.load(f)
    except json.JSONDecodeError as e:
        die(f"主题池 JSON 解析失败: {e}")
    if "pools" not in pool:
        die("主题池缺少 pools 字段")
    return pool


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f).get("camps", {})
    except json.JSONDecodeError as e:
        die(f"进度文件 JSON 解析失败: {e}（{STATE_PATH}）")


def save_atomic(path, obj):
    """原子写：同目录临时文件 + os.replace，避免并发读到半截 JSON。"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def find_entry(pool, topic_id):
    for camp, items in pool["pools"].items():
        for i, it in enumerate(items):
            if it.get("id") == topic_id:
                return camp, items, i
    return None, None, None


def cmd_list(args, pool):
    print(f"主题池（{POOL_PATH}）\n")
    total = 0
    for camp in pool["pools"]:
        items = pool["pools"][camp]
        unused = sum(1 for x in items if x.get("status") == "unused")
        done = sum(1 for x in items if x.get("status") == "done")
        dropped = sum(1 for x in items if x.get("status") == "dropped")
        total += len(items)
        print(f"  {camp:<12} 共{len(items):>3}  可用 {unused:>3}  已出片 {done:>2}  弃用 {dropped:>2}")
    print(f"\n合计 {total} 条")
    print("\n用pick --camp <训练营名> 挑候选。训练营名可用简称，如「架构师」。")
    return 0


def cmd_pick(args, pool):
    camp = args.camp
    if not camp:
        die("必须给 --camp")
    # 允许简称：去掉「训练营」后缀或前缀模糊匹配
    if camp not in pool["pools"]:
        norm = camp.replace("训练营", "")
        cands = [c for c in pool["pools"] if c.replace("训练营", "") == norm]
        if len(cands) != 1:
            die(f"未知训练营「{camp}」。可用: {', '.join(pool['pools'])}")
        camp = cands[0]

    items = [dict(x) for x in pool["pools"][camp]]
    if not args.all:
        items = [x for x in items if x.get("status") == "unused"]
    if args.hands_on:
        items = [x for x in items if x.get("handsOn") is True]
    if args.ids_only:
        items = [x for x in items if x.get("id") in set(args.ids_only)]

    if args.uncovered_only:
        state = load_state().get(camp, {})
        covered = state.get("covered", [])
        def covered_hit(dim):
            # 维度关键词与 covered 任一条有2 字以上公共子串即视为已覆盖
            for c in covered:
                common = set(dim) & set(c)
                if len("".join(common)) >= 2:
                    return True
            return False
        before = len(items)
        items = [x for x in items if not covered_hit(x.get("dimension", ""))]
        if before != len(items):
            print(f"[uncovered-only] 过滤掉{before - len(items)} 条与已覆盖维度重合的候选\n")

    if not items:
        print(f"{camp}：没有符合条件的候选（池已耗尽或被过滤完）。")
        print("按 SKILL.md「Step 0 选题引擎」自主生成新候选，并用 add 回写本池。")
        return 4

    items.sort(key=lambda x: (REACH_RANK.get(x.get("reach"), 9), x.get("id", "")))
    if args.n:
        items = items[: args.n]

    print(f"{camp} 候选（{len(items)} 条）\n")
    for it in items:
        flag = " [已出片]" if it.get("status") == "done" else ""
        print(f"  {it['id']}{flag}  {it['title']}")
        print(f"维度  {it['dimension']}   档位 {it.get('tier','?')}   传播力 {it.get('reach','?')}")
        print(f"角度  {it['angle']}")
        if it.get("aiAngle"):
            print(f"AI切口  {it['aiAngle']}")
        if it.get("risk"):
            print(f"风险  {it['risk']}")
        print(f"动手型  {'是' if it.get('handsOn') else '否'}")
        print()
    print("定稿并出片后用 mark <id> --status done 回写，跨客户端自动去重。")
    return 0


def cmd_mark(args, pool):
    camp, items, idx = find_entry(pool, args.id)
    if not items:
        die(f"池中无此 id: {args.id}")
    it = items[idx]
    old = it.get("status")
    if args.status:
        it["status"] = args.status
    if args.reason is not None:
        it["reason"] = args.reason
    if args.title:
        it["title"] = args.title
    it["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_atomic(POOL_PATH, pool)

    # 同步进度：done 写进 covered，供 --uncovered-only 去重
    if it.get("status") == "done":
        st = load_pool_state_standalone()
        # 必须写进 camps 子字典：load_state() 只读 st["camps"]，
        # 写顶层会让 --uncovered-only 读不到已讲维度（2026-10-04 实测踩到）。
        camps = st.setdefault("camps", {})
        c = camps.setdefault(camp, {"expertGoal": "", "lastTopic": "", "covered": []})
        c["lastTopic"] = it["title"]
        if it["dimension"] not in c["covered"]:
            c["covered"].append(it["dimension"])
        write_state(st)
    print(f"{args.id}（{camp}）: {old} -> {it['status']}")
    return 0


def load_pool_state_standalone():
    if not os.path.exists(STATE_PATH):
        return {"schema": "ohl-syllabus-state/1", "updated": "", "camps": {}}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        die(f"进度文件 JSON 解析失败: {e}")


def write_state(st):
    st["updated"] = time.strftime("%Y-%m-%d")
    save_atomic(STATE_PATH, st)


def cmd_add(args, pool):
    camp = args.camp
    if camp not in pool["pools"]:
        norm = camp.replace("训练营", "")
        cands = [c for c in pool["pools"] if c.replace("训练营", "") == norm]
        if len(cands) != 1:
            die(f"未知训练营「{camp}」。可用: {', '.join(pool['pools'])}")
        camp = cands[0]

    pre = re.sub(r"[^A-Za-z]", "", camp)[:3].upper() or "TOP"
    existing = {x["id"] for x in pool["pools"][camp]}
    n = 1
    while f"{pre}-{n:02d}" in existing:
        n += 1
    tid = args.id or f"{pre}-{n:02d}"
    if tid in existing:
        die(f"id 已存在: {tid}")

    if args.tier and args.tier not in VALID_TIER:
        die(f"--tier 须为 {'/'.join(VALID_TIER)}")
    if args.reach and args.reach not in VALID_REACH:
        die(f"--reach 须为 {'/'.join(VALID_REACH)}")

    entry = {
        "id": tid,
        "title": args.title,
        "dimension": args.dimension,
        "angle": args.angle,
        "tier": args.tier or "M",
        "reach": args.reach or "中",
        "hook": args.hook or "",
        "aiAngle": args.ai_angle or "",
        "handsOn": bool(args.hands_on),
        "risk": args.risk or "",
        "status": "unused",
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    pool["pools"][camp].append(entry)
    pool["updated"] = time.strftime("%Y-%m-%d")
    save_atomic(POOL_PATH, pool)
    print(f"已加入 {camp}: {tid} {args.title}")
    return 0


def cmd_verify(args, pool):
    errs, warns, seen = [], [], set()
    if not pool.get("note"):
        warns.append("缺少 note 说明")
    for camp, items in pool["pools"].items():
        for it in items:
            i = it.get("id", "<无 id>")
            for k in REQUIRED:
                if not it.get(k):
                    errs.append(f"{i}: 缺必填字段 {k}")
            if i in seen:
                errs.append(f"{i}: id 重复")
            seen.add(i)
            if it.get("tier") and it["tier"] not in VALID_TIER:
                errs.append(f"{i}: tier 非法 {it['tier']}")
            if it.get("reach") and it["reach"] not in VALID_REACH:
                errs.append(f"{i}: reach 非法 {it['reach']}")
            if it.get("status") not in VALID_STATUS:
                errs.append(f"{i}: status 非法 {it['status']}")
            if it.get("status") == "dropped" and not it.get("reason"):
                warns.append(f"{i}: 标为 dropped 但没写 reason")
    # 覆盖度检查
    for camp in pool["pools"]:
        if camp == "读书训练营":
            continue
        n_hands = sum(
            1 for x in pool["pools"][camp] if x.get("handsOn") and x.get("status") == "unused"
        )
        if n_hands < 2:
            warns.append(f"{camp}: 可用动手型候选仅 {n_hands} 条，配比门禁（每4期≥1动手）难满足")
    if os.path.exists(STATE_PATH):
        try:
            load_pool_state_standalone()
        except SystemExit:
            errs.append("进度文件无法解析")
    else:
        warns.append("进度文件不存在（首次使用时可跑 mark --status done 自动创建）")

    print(f"主题池共 {len(seen)} 条，{len(pool['pools'])} 个训练营")
    for w in warns:
        print(f"  WARN  {w}")
    for e in errs:
        print(f"  ERROR {e}")
    if errs:
        print(f"\n校验未通过：{len(errs)} 个错误", file=sys.stderr)
        return 1
    print("校验通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="共享主题候选池挑选器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出训练营与候选数").set_defaults(fn=cmd_list)

    p = sub.add_parser("pick", help="挑候选")
    p.add_argument("--camp", help="训练营名（支持简称，如「架构师」）")
    p.add_argument("-n", type=int, default=5, help="返回条数，默认 5")
    p.add_argument("--hands-on", action="store_true", help="只要动手型")
    p.add_argument("--uncovered-only", action="store_true", help="过滤与 covered 维度重合的")
    p.add_argument("--all", action="store_true", help="含已出片/弃用条目")
    p.add_argument("--ids-only", nargs="*", help="只取指定 id（调试/复用用）")
    p.set_defaults(fn=cmd_pick)

    m = sub.add_parser("mark", help="回写状态")
    m.add_argument("id")
    m.add_argument("--status", choices=VALID_STATUS)
    m.add_argument("--reason")
    m.add_argument("--title", help="同时改标题（出片后回填优化版）")
    m.set_defaults(fn=cmd_mark)

    a = sub.add_parser("add", help="新增候选")
    a.add_argument("--camp", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--dimension", required=True)
    a.add_argument("--angle", required=True)
    a.add_argument("--tier", choices=VALID_TIER)
    a.add_argument("--reach", choices=VALID_REACH)
    a.add_argument("--hook")
    a.add_argument("--ai-angle", dest="ai_angle")
    a.add_argument("--risk")
    a.add_argument("--hands-on", dest="hands_on", action="store_true")
    a.add_argument("--id")
    a.set_defaults(fn=cmd_add)

    sub.add_parser("verify", help="校验池与进度一致性").set_defaults(fn=cmd_verify)

    args = ap.parse_args()
    sys.exit(args.fn(args, load_pool()))


if __name__ == "__main__":
    main()
