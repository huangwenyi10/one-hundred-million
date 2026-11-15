#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evolution.py — one-hundred-million 技能「双环自我进化」确定性门禁
（固定规范第 43 条配套 · 完整规范见 references/self-evolution.md）

职责边界（重要）：
  * 本脚本只负责「可确定的事实」：台账读写、到期计算、统计、状态机、收尾校验。
  * 本脚本 **绝不** 自动修改 SKILL.md / scripts / references / templates 里的任何规则或常量。
    所有「阈值提档 / 蒸馏成条款 / 改脚本」一律先生成 pending_author 提议，
    经作者明确确认（approve）后才由 AI 执行固化。
  * 本脚本 **不臆造任何结论**：评分、证据、复发判定、根因归类全部由调用方显式传入；
    没有数据就明确输出「暂无数据」，不生成占位数字。

两个数据层：
  * 技能内 assets/state/ —— 跨客户端共享的长期事实（评分库 / 事实卡片库 / 提议状态机 / 留痕）
  * 工作区 .evolution_state.json —— 本轮执行凭证（brief / score / check 的确定性凭据）

退出码：
  0  成功 / 门禁通过
  1  参数或数据校验失败 / 收尾门禁 FAIL
  2  文件缺失或格式损坏（不静默兜底）
  3  无数据（仅 list/find/stats 类查询，调用方自行判断是否异常）

依赖：仅标准库。不联网、不删除文件、不执行外部命令。
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ASSETS = os.path.join(SKILL_ROOT, "assets", "state")

DIMENSIONS = ("content", "visual", "audio", "subtitle", "delivery")
DIM_CN = {
    "content": "内容",
    "visual": "视觉",
    "audio": "音频",
    "subtitle": "字幕",
    "delivery": "交付",
}
LEVELS = ("L1", "L2", "L3", "L4", "L5")
DEFAULT_REVIEW_DAYS = 180
REGRESSION_DELTA = 1.5        # 比近 10 期均值低 ≥1.5 分判退步
RAISE_MIN_SCORE = 9.0         # 连续 3 期该维 ≥9 且零返工 → 生成提档提议
RAISE_STREAK = 3
TREND_WINDOW = 10

LID_RE = re.compile(r"^###\s+(L\d{3})\s+\[([^\]]+)\]\s*(.*)$", re.M)
STATUS_RE = re.compile(r"^\s*-\s*\*\*状态\*\*\s*[：:]\s*(.+)$", re.M)


# ---------------------------------------------------------------------------
# 基础 IO
# ---------------------------------------------------------------------------

def atomic_write_json(path, data):
    """临时文件 + os.replace 原子写，避免多客户端读到半截 JSON。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".evo_", suffix=".json",
                               dir=os.path.dirname(os.path.abspath(path)))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_json(path, default, label):
    if not os.path.exists(path):
        return json.loads(json.dumps(default))
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError) as e:
        print("[FAIL] %s 读取失败：%s（%s）" % (label, path, e), file=sys.stderr)
        print("       不静默重建——请先人工检查文件，避免覆盖已有台账。", file=sys.stderr)
        sys.exit(2)


def append_log(assets_dir, text):
    path = os.path.join(assets_dir, "evolution_log.md")
    os.makedirs(assets_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(path, "a", encoding="utf-8") as f:
        f.write("- `%s` %s\n" % (stamp, text))


def state_path(workspace):
    return os.path.join(workspace, ".evolution_state.json")


def load_state(workspace):
    path = state_path(workspace)
    return load_json(path, {}, "本轮执行凭证 .evolution_state.json")


def save_state(workspace, data):
    atomic_write_json(state_path(workspace), data)


def today(args):
    return args.date or date.today().isoformat()


def parse_kv(items, label, allow_empty_key=False):
    """解析重复传入的 key=value；value 允许含 '=' 与逗号。"""
    out = {}
    for raw in items or []:
        if "=" not in raw:
            print("[FAIL] %s 格式错误：%r（应为 key=value）" % (label, raw), file=sys.stderr)
            sys.exit(1)
        k, v = raw.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k and not allow_empty_key:
            print("[FAIL] %s 的 key 不能为空：%r" % (label, raw), file=sys.stderr)
            sys.exit(1)
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# 台账读取
# ---------------------------------------------------------------------------

def read_learnings(assets_dir):
    """返回 [(lid, category, title, status_text)]；文件不存在视为空登记簿。"""
    path = os.path.join(assets_dir, "learnings.md")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    matches = list(LID_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.end():end]
        sm = STATUS_RE.search(block)
        status = sm.group(1).strip() if sm else ""
        out.append((m.group(1), m.group(2).strip(), m.group(3).strip(), status))
    return out


def learning_ids_set(assets_dir):
    return set(x[0] for x in read_learnings(assets_dir))


def load_scores(assets_dir):
    return load_json(os.path.join(assets_dir, "quality_scores.json"),
                     {"schema_version": 1, "entries": []}, "质量评分库")


def load_cards(assets_dir):
    return load_json(os.path.join(assets_dir, "source_cards.json"),
                     {"schema_version": 1, "next_id": 1, "cards": []}, "事实卡片库")


def load_proposals(assets_dir):
    return load_json(os.path.join(assets_dir, "evolution_proposals.json"),
                     {"schema_version": 1, "next_id": 1, "proposals": []}, "提议状态机")


def new_id(store, prefix):
    n = int(store.get("next_id", 1))
    store["next_id"] = n + 1
    return "%s%03d" % (prefix, n)


def add_proposal(assets_dir, ptype, summary, detail, evidence, episode, day):
    store = load_proposals(assets_dir)
    # 去重：同类型 + 同摘要 且仍 pending_author / approved 的不重复生成
    for p in store["proposals"]:
        if (p.get("type") == ptype and p.get("summary") == summary
                and p.get("status") in ("pending_author", "approved")):
            return p["id"], False
    pid = new_id(store, "P")
    store["proposals"].append({
        "id": pid,
        "type": ptype,
        "created_at": day,
        "episode": episode or "",
        "summary": summary,
        "detail": detail,
        "evidence": evidence or "",
        "status": "pending_author",
        "approved_at": None,
        "approved_note": None,
        "verification": {"result": None, "evidence": None, "at": None},
    })
    atomic_write_json(os.path.join(assets_dir, "evolution_proposals.json"), store)
    append_log(assets_dir, "生成提议 %s [%s] %s（待作者确认，未改动任何规则）" % (pid, ptype, summary))
    return pid, True


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------

def trend(entries, current_episode):
    """近 N 期各维均值（排除本轮），返回 {dim: avg} 或 {}。"""
    hist = [e for e in entries if e.get("episode") != current_episode][-TREND_WINDOW:]
    if not hist:
        return {}
    out = {}
    for d in DIMENSIONS:
        vals = [float(e["scores"][d]) for e in hist if d in e.get("scores", {})]
        if vals:
            out[d] = round(sum(vals) / len(vals), 2)
    return out


def raise_candidates(entries):
    """连续 RAISE_STREAK 期某维 ≥9 且零返工 / 零打回 / 零门禁失败 → 提档候选。"""
    if len(entries) < RAISE_STREAK:
        return []
    recent = entries[-RAISE_STREAK:]
    out = []
    for d in DIMENSIONS:
        ok = all(
            float(e.get("scores", {}).get(d, 0)) >= RAISE_MIN_SCORE
            and int(e.get("rework_count", 0)) == 0
            and int(e.get("author_rejections", 0)) == 0
            and int(e.get("gate_failures", 0)) == 0
            for e in recent
        )
        if ok:
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# 子命令：brief（Step 0 第 0 条）
# ---------------------------------------------------------------------------

def cmd_brief(args):
    a = args.assets_dir
    day = today(args)
    # 1) 资料卡片到期（确定性：只改 status，不改任何规则）
    expired = expire_cards(a, day, write=True, quiet=True)

    learnings = read_learnings(a)
    open_items = [(lid, cat, st) for lid, cat, _t, st in learnings if "open" in st.lower()]
    unverified = [(lid, cat, st) for lid, cat, _t, st in learnings
                  if st and "open" not in st.lower()
                  and not any(k in st for k in ("verified", "distilled", "archived"))]

    cards = load_cards(a)["cards"]
    stale_cards = [c for c in cards if c.get("status") == "stale"
                   or (c.get("status") == "valid" and (c.get("review_due") or "9999") <= day)]

    props = load_proposals(a)["proposals"]
    pending = [p for p in props if p.get("status") == "pending_author"]
    pending_verify = [p for p in props
                      if p.get("status") == "approved"
                      and not (p.get("verification") or {}).get("result")]

    scores = load_scores(a)["entries"]
    # 口径与 score 一致：拿「上一轮分数」比「排除上一轮后的近 N 期均值」，避免均值被上轮自身稀释
    last_episode = scores[-1].get("episode", "") if scores else ""
    avgs = trend(scores, last_episode)
    weak = []
    if scores:
        last = scores[-1]
        for d in DIMENSIONS:
            v = float(last.get("scores", {}).get(d, 0))
            if d in avgs and v <= avgs[d] - REGRESSION_DELTA:
                weak.append("%s %s→%.1f（近%d期均值 %.2f）" % (DIM_CN[d], d, v, TREND_WINDOW, avgs[d]))

    print("=" * 62)
    print("本轮进化开工清单 · %s · episode=%s" % (day, args.episode or "(未指定)"))
    print("=" * 62)
    print("\n[A环·防复发] learnings.md 未闭环项：%d" % len(open_items))
    for lid, cat, st in open_items:
        print("  - %s [%s] %s" % (lid, cat, st[:90]))
    if unverified:
        print("  待验证（fixed 未 verified）：%d" % len(unverified))
        for lid, cat, st in unverified:
            print("  - %s [%s] %s" % (lid, cat, st[:90]))
    if not open_items and not unverified:
        print("  （无未闭环项）")

    print("\n[B环·本轮重点改进项]")
    if weak:
        for w in weak:
            print("  - 退步：%s → 本轮须针对性改进，且收尾必须登记 learnings" % w)
    elif avgs:
        print("  - 上轮无维度退步（近%d期均值：%s）" %
              (TREND_WINDOW, ", ".join("%s %.2f" % (DIM_CN[d], v) for d, v in avgs.items())))
    else:
        print("  - 暂无评分数据，本轮无法做趋势对比（不做推断，先录第 1 条评分）")

    retired = [c for c in cards if c.get("status") == "retired"]
    print("\n[内容资料] 到期/待复核事实卡片：%d（本次新标记 stale %d）｜已停用 retired %d（禁复用）" %
          (len(stale_cards), expired, len(retired)))
    for c in stale_cards[:20]:
        print("  - %s [%s] %s（来源 %s，核实于 %s）" %
              (c["id"], c["status"], c["claim"][:60], c.get("source", ""), c.get("verified_at", "")))
    if len(stale_cards) > 20:
        print("  ... 另有 %d 条，用 `source list --status stale` 查看" % (len(stale_cards) - 20))
    if retired:
        print("  retired 结论一律不得复用；`source find` 命中时会明确标注停用原因。")

    print("\n[待作者拍板] 提议：%d" % len(pending))
    for p in pending:
        print("  - %s [%s] %s" % (p["id"], p["type"], p["summary"]))
    print("[待验证] 已批准但尚未验证是否生效：%d" % len(pending_verify))
    for p in pending_verify:
        print("  - %s [%s] %s" % (p["id"], p["type"], p["summary"]))

    print("\n本轮动作：①逐条核对 A 环 ②对 B 环弱项定改进动作 ③涉及 stale 卡片的主题先回源复核")
    print("          ④Step 1 取材先跑 `source find --keyword <关键词>` 复用已核实事实")
    print("=" * 62)

    save_state(args.workspace, {
        "schema_version": 1,
        "episode": args.episode or "",
        "brief_at": datetime.now().isoformat(timespec="seconds"),
        "brief_date": day,
        "checklist": {
            "open_learnings": [x[0] for x in open_items],
            "stale_cards": [c["id"] for c in stale_cards],
            "pending_proposals": [p["id"] for p in pending],
            "pending_verify": [p["id"] for p in pending_verify],
            "weak_dimensions": weak,
        },
        "score_at": None,
        "learning_ids": None,
        "no_issues": None,
        "regression_dims": [],
    })
    print("\n已写本轮执行凭证：%s" % state_path(args.workspace))
    return 0


# ---------------------------------------------------------------------------
# 子命令：score（Step 8 收尾）
# ---------------------------------------------------------------------------

def cmd_score(args):
    a = args.assets_dir
    day = today(args)
    scores = parse_kv(args.scores, "--scores")
    evidences = parse_kv(args.evidence, "--evidence")

    missing = [d for d in DIMENSIONS if d not in scores]
    extra = [d for d in scores if d not in DIMENSIONS]
    if missing or extra:
        print("[FAIL] --scores 必须且只能含 5 维：%s；缺 %s，多 %s" %
              (", ".join(DIMENSIONS), missing or "无", extra or "无"), file=sys.stderr)
        return 1
    numeric = {}
    for d in DIMENSIONS:
        try:
            v = float(scores[d])
        except ValueError:
            print("[FAIL] %s 分值不是数字：%r" % (d, scores[d]), file=sys.stderr)
            return 1
        if not (0 <= v <= 10):
            print("[FAIL] %s 分值须在 0~10：%s" % (d, v), file=sys.stderr)
            return 1
        numeric[d] = v
    # 每维必须有证据：防止凭感觉打分（作者硬规则：正确性优先，不臆造）
    no_evidence = [d for d in DIMENSIONS if not evidences.get(d, "").strip()]
    if no_evidence:
        print("[FAIL] 以下维度缺 --evidence（无证据不录分）：%s" % ", ".join(no_evidence), file=sys.stderr)
        return 1

    if bool(args.learning_ids) == bool(args.no_issues):
        print("[FAIL] 必须二选一：--learning-ids <本轮登记的 LID 列表> 或 --no-issues（本轮确无问题）",
              file=sys.stderr)
        return 1
    lids = [x.strip() for x in (args.learning_ids or "").split(",") if x.strip()]
    if lids:
        known = learning_ids_set(a)
        unknown = [x for x in lids if x not in known]
        if unknown:
            print("[FAIL] 以下 LID 在 learnings.md 中不存在（禁止只写 metrics.csv 备注）：%s" %
                  ", ".join(unknown), file=sys.stderr)
            return 1

    store = load_scores(a)
    # 同一 episode 重复录入视为重跑：替换而非追加，保持台账唯一
    store["entries"] = [e for e in store["entries"] if e.get("episode") != args.episode]
    avgs = trend(store["entries"], args.episode)
    regression = []
    for d in DIMENSIONS:
        if d in avgs and numeric[d] <= avgs[d] - REGRESSION_DELTA:
            regression.append(d)

    entry = {
        "episode": args.episode,
        "date": day,
        "title": args.title,
        "camp": args.camp,
        "tier": args.tier,
        "scores": numeric,
        "evidence": {d: evidences[d] for d in DIMENSIONS},
        "rework_count": args.rework,
        "author_rejections": args.rejections,
        "gate_failures": args.gate_failures,
        "learning_ids": lids,
        "no_issues": bool(args.no_issues),
        "regression_dims": regression,
        "notes": args.notes or "",
    }
    store["entries"].append(entry)
    atomic_write_json(os.path.join(a, "quality_scores.json"), store)

    print("已录评分：%s《%s》 %s/%s" % (args.episode, args.title, args.camp, args.tier))
    for d in DIMENSIONS:
        base = ("近%d期均值 %.2f" % (TREND_WINDOW, avgs[d])) if d in avgs else "暂无历史基线"
        print("  %-4s %-8s %4.1f  %s" % (d, DIM_CN[d], numeric[d], base))
    print("  返工 %d / 作者打回 %d / 门禁 FAIL %d" %
          (args.rework, args.rejections, args.gate_failures))

    if regression:
        print("\n[退步告警] 以下维度比近%d期均值低 ≥%.1f → %s" %
              (TREND_WINDOW, REGRESSION_DELTA, ", ".join(DIM_CN[d] for d in regression)))
        print("  本轮收尾**必须**在 learnings.md 登记一条「流程缺口」并在 --learning-ids 里列出；")
        print("  若填了 --no-issues，check 会 FAIL。")
        if args.no_issues:
            print("  [FAIL] 本轮存在退步却声明 --no-issues，评分已写入但收尾门禁不会通过。", file=sys.stderr)

    # 连续达标 → 合并成 1 条「提档提议」，不自动改任何阈值（避免一次刷屏 5 条）
    candidates = raise_candidates(store["entries"])
    if candidates:
        dim_cn = "、".join(DIM_CN[d] for d in candidates)
        summary = "%d 个维度阈值提档（%s；连续%d期 ≥%.0f 且零返工）" % (
            len(candidates), dim_cn, RAISE_STREAK, RAISE_MIN_SCORE)
        evidence_lines = []
        for d in candidates:
            evidence_lines.append("%s：%s" % (DIM_CN[d], ", ".join(
                "%.1f" % float(e["scores"][d]) for e in store["entries"][-RAISE_STREAK:])))
        pid, created = add_proposal(
            a, "threshold_raise", summary,
            "建议对上述维度各上调一项硬指标一档；具体目标值须由 AI 结合当期门禁输出给出并经作者确认，"
            "确认前脚本与 SKILL.md 一律不动。",
            "最近 %d 期评分｜%s" % (RAISE_STREAK, "；".join(evidence_lines)),
            args.episode, day)
        print("  [提议] %s %s %s" % (pid, "(新建)" if created else "(已存在，跳过)", summary))

    st = load_state(args.workspace)
    if not st.get("brief_at"):
        print("  [WARN] 本轮未跑过 brief，执行凭证缺失；check 会 FAIL。", file=sys.stderr)
    st["episode"] = args.episode
    st["score_at"] = datetime.now().isoformat(timespec="seconds")
    st["learning_ids"] = lids
    st["no_issues"] = bool(args.no_issues)
    st["regression_dims"] = regression
    save_state(args.workspace, st)
    append_log(a, "评分 %s《%s》 总分 %.1f｜退步:%s｜登记:%s" %
               (args.episode, args.title, sum(numeric.values()),
                ",".join(regression) or "无", ",".join(lids) or "无问题"))
    return 0


# ---------------------------------------------------------------------------
# 子命令：check（Step 8 收尾门禁）
# ---------------------------------------------------------------------------

def cmd_check(args):
    a = args.assets_dir
    day = today(args)
    st = load_state(args.workspace)
    results = []

    if not st.get("brief_at"):
        results.append(("FAIL", "开工回顾", "本轮未跑 `evolution.py brief`（执行凭证缺失）"))
    elif st.get("brief_date") != day:
        results.append(("WARN", "开工回顾", "brief 日期 %s ≠ 本轮日期 %s（长篇跨天属正常，需确认是同一轮）" %
                        (st.get("brief_date"), day)))
    else:
        results.append(("PASS", "开工回顾", "brief 已跑（%s）" % st["brief_at"]))

    if not st.get("score_at"):
        results.append(("FAIL", "质量评分", "本轮未跑 `evolution.py score`"))
    else:
        store = load_scores(a)
        hit = [e for e in store["entries"] if e.get("episode") == st.get("episode") and st.get("episode")]
        if not hit:
            results.append(("FAIL", "质量评分", "评分库中找不到 episode=%r 的条目" % st.get("episode")))
        else:
            results.append(("PASS", "质量评分", "已录 5 维评分与逐维证据（%s）" % st["score_at"]))

    lids = st.get("learning_ids")
    no_issues = st.get("no_issues")
    regression = st.get("regression_dims") or []
    if lids is None and no_issues is None:
        results.append(("FAIL", "问题登记", "本轮既未声明登记 LID、也未显式声明 --no-issues"))
    elif lids:
        known = learning_ids_set(a)
        unknown = [x for x in lids if x not in known]
        if unknown:
            results.append(("FAIL", "问题登记", "登记的 LID 在 learnings.md 中不存在：%s" % ", ".join(unknown)))
        else:
            results.append(("PASS", "问题登记", "已登记 %d 条：%s" % (len(lids), ", ".join(lids))))
    elif no_issues and regression:
        results.append(("FAIL", "问题登记", "存在退步维度 %s 却声明无问题，必须登记「流程缺口」" %
                        ", ".join(DIM_CN.get(d, d) for d in regression)))
    else:
        results.append(("PASS", "问题登记", "本轮显式声明无新增问题"))

    props = load_proposals(a)["proposals"]
    pending = [p for p in props if p.get("status") == "pending_author"]
    pending_verify = [p for p in props
                      if p.get("status") == "approved" and not (p.get("verification") or {}).get("result")]
    results.append(("INFO", "待作者拍板", "%d 条提议待确认（不阻塞收尾）：%s" %
                    (len(pending), ", ".join(p["id"] for p in pending) or "无")))
    results.append(("INFO", "待验证", "%d 条已批准提议待下轮验证（不阻塞收尾）：%s" %
                    (len(pending_verify), ", ".join(p["id"] for p in pending_verify) or "无")))

    print("=" * 62)
    print("自我进化收尾门禁 · %s · episode=%s" % (day, st.get("episode") or "(未指定)"))
    print("=" * 62)
    for level, name, msg in results:
        print("  [%-4s] %-8s %s" % (level, name, msg))
    fails = [r for r in results if r[0] == "FAIL"]
    if fails:
        print("\n[BLOCK] %d 项未通过 → 本轮收尾未完成，禁止结束；修好后重跑 check。" % len(fails))
        return 1
    print("\n[PASS] 收尾门禁通过。提醒：所有提档/蒸馏提议仍需作者确认后才可写入技能规则。")
    return 0


# ---------------------------------------------------------------------------
# 子命令：source（内容资料事实卡片库）
# ---------------------------------------------------------------------------

def expire_cards(a, day, write=False, quiet=False):
    store = load_cards(a)
    n = 0
    for c in store["cards"]:
        if c.get("status") == "valid" and (c.get("review_due") or "9999-12-31") <= day:
            c["status"] = "stale"
            n += 1
    if write and n:
        atomic_write_json(os.path.join(a, "source_cards.json"), store)
        append_log(a, "资料复核：%d 条事实卡片到期自动标记 stale（不改结论，仅标记需复核）" % n)
    if not quiet and n:
        print("已把 %d 条到期卡片标记为 stale。" % n)
    return n


def cmd_source(args):
    a = args.assets_dir
    day = today(args)
    sub = args.action
    store = load_cards(a)
    cards = store["cards"]

    if sub == "add":
        if not args.claim or not args.source:
            print("[FAIL] --claim 与 --source 必填", file=sys.stderr)
            return 1
        if args.level not in LEVELS:
            print("[FAIL] --level 须为 %s" % "/".join(LEVELS), file=sys.stderr)
            return 1
        cid = new_id(store, "SC")
        due = (date.fromisoformat(day) + timedelta(days=args.review_days)).isoformat()
        card = {
            "id": cid,
            "claim": args.claim,
            "source": args.source,
            "level": args.level,
            "version": args.version or "",
            "conditions": args.conditions or "",
            "verified_at": day,
            "review_due": due,
            "status": "valid",
            "used_in": [x.strip() for x in (args.used_in or "").split(",") if x.strip()],
            "review_history": [],
        }
        cards.append(card)
        atomic_write_json(os.path.join(a, "source_cards.json"), store)
        append_log(a, "资料入库 %s [%s] %s（复核到期 %s）" % (cid, args.level, args.claim[:50], due))
        print("已入库 %s [%s] %s" % (cid, args.level, args.claim))
        print("  来源：%s｜版本：%s｜核实：%s｜复核到期：%s" %
              (args.source, args.version or "(未填)", day, due))
        return 0

    def find_card(cid):
        for c in cards:
            if c["id"].upper() == cid.upper():
                return c
        return None

    if sub == "list":
        wanted = args.status or "all"
        rows = [c for c in cards if wanted == "all" or c.get("status") == wanted]
        if not rows:
            print("暂无%s事实卡片。用 `source add` 建立第一条。" %
                  ("" if wanted == "all" else " %s 状态的" % wanted))
            return 3
        for c in rows:
            print("%s [%-7s %-3s] %s" % (c["id"], c["status"], c["level"], c["claim"]))
            print("    来源 %s｜版本 %s｜核实 %s｜到期 %s｜用于 %s" %
                  (c["source"], c.get("version") or "-", c["verified_at"],
                   c.get("review_due") or "-", ",".join(c.get("used_in") or []) or "-"))
        print("共 %d 条。" % len(rows))
        return 0

    if sub == "find":
        keyword = args.keyword or getattr(args, "keyword_pos", "") or ""
        if not keyword.strip():
            print("[FAIL] 用法：source find --keyword <词> 或 source find <词>", file=sys.stderr)
            return 1
        kw = keyword.lower()
        rows = [c for c in cards if kw in c["claim"].lower()
                or kw in c.get("source", "").lower()
                or kw in c.get("version", "").lower()]
        if not rows:
            print("未找到含 %r 的事实卡片 → 本轮按 Step 1 双源核验从零取材，收尾记得 `source add`。" % args.keyword)
            return 3
        for c in rows:
            flags = {
                "valid": "可复用，但仍须回源确认版本未变（第 7 条双源核验不豁免）",
                "stale": "已过复核期 → 必须先回源复核并 `source verify` 后才可用",
                "retired": "已停用 → 禁止复用，须重新取权威来源",
            }
            print("%s [%s %s] %s → %s" %
                  (c["id"], c["status"], c["level"], c["claim"],
                   flags.get(c["status"], "状态异常，人工检查")))
            print("    来源 %s｜版本 %s｜核实 %s" %
                  (c["source"], c.get("version") or "-", c["verified_at"]))
            if c["status"] == "retired" and c.get("retire_reason"):
                print("    停用原因：%s" % c["retire_reason"])
        return 0

    if sub in ("verify", "retire"):
        c = find_card(args.id)
        if not c:
            print("[FAIL] 找不到卡片 %s" % args.id, file=sys.stderr)
            return 1
        if sub == "verify":
            c["review_history"] = c.get("review_history", []) + [{
                "at": day, "before_status": c["status"],
                "version_before": c.get("version", ""), "version_after": args.version or c.get("version", ""),
                "note": args.note or "",
            }]
            c["verified_at"] = day
            c["review_due"] = (date.fromisoformat(day) + timedelta(days=args.review_days)).isoformat()
            c["status"] = "valid"
            if args.version:
                c["version"] = args.version
            if args.source:
                c["source"] = args.source
            atomic_write_json(os.path.join(a, "source_cards.json"), store)
            append_log(a, "资料复核 %s 通过（版本 %s → %s）" %
                       (c["id"], c["review_history"][-1]["version_before"], c["version"]))
            print("%s 已复核通过 → valid，新到期 %s" % (c["id"], c["review_due"]))
        else:
            if not args.reason:
                print("[FAIL] retire 必须给 --reason（结论为何失效）", file=sys.stderr)
                return 1
            c["status"] = "retired"
            c["retire_reason"] = args.reason
            c["retired_at"] = day
            atomic_write_json(os.path.join(a, "source_cards.json"), store)
            append_log(a, "资料停用 %s：%s" % (c["id"], args.reason))
            print("%s 已停用（retired），此后不得再用于任何口播稿。" % c["id"])
        return 0

    if sub == "expire":
        n = expire_cards(a, day, write=True)
        print("到期检查完成：%d 条 valid → stale。" % n)
        return 0

    if sub == "stats":
        print("事实卡片库：共 %d 条" % len(cards))
        for s in ("valid", "stale", "retired"):
            print("  %-8s %d" % (s, sum(1 for c in cards if c.get("status") == s)))
        for lv in LEVELS:
            print("  %-8s %d" % (lv, sum(1 for c in cards if c.get("level") == lv)))
        return 0

    print("[FAIL] 未知 source 子命令：%s" % sub, file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# 子命令：蒸馏提议 / 拍板 / 验证
# ---------------------------------------------------------------------------

def cmd_distill(args):
    a = args.assets_dir
    day = today(args)
    lids = [x.strip() for x in (args.lids or "").split(",") if x.strip()]
    if not lids:
        print("[FAIL] --lids 必填（同根因复发的登记编号，逗号分隔）", file=sys.stderr)
        return 1
    known = learning_ids_set(a)
    unknown = [x for x in lids if x not in known]
    if unknown:
        print("[FAIL] 以下 LID 不存在于 learnings.md：%s" % ", ".join(unknown), file=sys.stderr)
        return 1
    summary = args.summary or "蒸馏：%s → %s" % (",".join(lids), args.clause or "待定条款")
    pid, created = add_proposal(
        a, "distill", summary,
        "同根因第 2 次出现（固定规范第 40 条④）。建议固化为 %s；能脚本化的优先脚本化。" %
        (args.clause or "SKILL.md 条款 / 脚本硬门禁"),
        args.evidence or "登记编号：%s" % ",".join(lids), args.episode, day)
    print("%s %s [%s] %s" % (pid, "(新建)" if created else "(已存在，跳过)", "distill", summary))
    print("  状态：pending_author —— 脚本未改动任何规则；作者 approve 后才由 AI 执行固化。")
    return 0


def cmd_proposals(args):
    store = load_proposals(args.assets_dir)
    rows = [p for p in store["proposals"] if not args.status or p.get("status") == args.status]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("暂无提议。")
        return 3
    for p in rows:
        v = p.get("verification") or {}
        print("%s [%-15s %-8s] %s" % (p["id"], p["status"], p["type"], p["summary"]))
        print("    建于 %s｜episode %s｜证据 %s" %
              (p["created_at"], p.get("episode") or "-", (p.get("evidence") or "-")[:100]))
        if p.get("approved_at"):
            print("    批准于 %s：%s" % (p["approved_at"], p.get("approved_note") or "-"))
        if v.get("result"):
            print("    验证：%s（%s）%s" % (v["result"], v.get("at") or "-", (v.get("evidence") or "")[:100]))
    return 0


def set_proposal_status(args, target, note_key):
    a = args.assets_dir
    store = load_proposals(a)
    hit = None
    for p in store["proposals"]:
        if p["id"].upper() == args.id.upper():
            hit = p
            break
    if not hit:
        print("[FAIL] 找不到提议 %s" % args.id, file=sys.stderr)
        return 1
    if hit["status"] == "pending_author" and target == "approved":
        hit["status"] = "approved"
        hit["approved_at"] = today(args)
        hit["approved_note"] = getattr(args, note_key, "") or ""
        atomic_write_json(os.path.join(a, "evolution_proposals.json"), store)
        append_log(a, "作者确认 %s：%s（此后才允许 AI 把规则写入技能，且须下轮验证）" %
                   (hit["id"], hit["approved_note"] or "同意"))
        print("%s → approved。作者已确认；AI 现在才可执行固化，并在下轮 `verify` 验证是否生效。" % hit["id"])
        return 0
    if hit["status"] == "pending_author" and target == "rejected":
        hit["status"] = "rejected"
        hit["approved_note"] = getattr(args, note_key, "") or ""
        atomic_write_json(os.path.join(a, "evolution_proposals.json"), store)
        append_log(a, "作者否决 %s：%s（不改动任何规则）" % (hit["id"], hit["approved_note"] or "不同意"))
        print("%s → rejected。技能规则保持原样。" % hit["id"])
        return 0
    print("[FAIL] %s 当前状态 %s，不能转为 %s（只允许 pending_author → approved/rejected）" %
          (hit["id"], hit["status"], target), file=sys.stderr)
    return 1


def cmd_verify(args):
    a = args.assets_dir
    store = load_proposals(a)
    hit = None
    for p in store["proposals"]:
        if p["id"].upper() == args.id.upper():
            hit = p
            break
    if not hit:
        print("[FAIL] 找不到提议 %s" % args.id, file=sys.stderr)
        return 1
    if hit["status"] != "approved":
        print("[FAIL] 只有 approved 的提议才能验证；%s 当前 %s" % (hit["id"], hit["status"]), file=sys.stderr)
        return 1
    if not args.evidence:
        print("[FAIL] --evidence 必填（验证结论必须带证据，禁止凭感觉）", file=sys.stderr)
        return 1
    hit["verification"] = {"result": args.result, "evidence": args.evidence,
                           "at": datetime.now().isoformat(timespec="seconds")}
    if args.result == "recurred":
        hit["status"] = "failed"
    atomic_write_json(os.path.join(a, "evolution_proposals.json"), store)
    append_log(a, "进化验证 %s → %s：%s" % (hit["id"], args.result, args.evidence[:120]))
    print("%s 验证结果：%s" % (hit["id"], args.result))
    if args.result == "recurred":
        print("  [提级] 固化后仍复发 → 状态 failed；须重新登记 learnings 并按第 40 条④ 提级蒸馏。")
    elif args.result == "no-recurrence":
        print("  [生效] 未复发，本轮进化闭环完成（status=verified 语义，保留 approved 供审计）。")
    elif args.result == "improved":
        print("  [生效] 指标确有提升，本轮进化闭环完成。")
    else:
        print("  [存疑] no-data：下轮 brief 会继续列为待验证项。")
    return 0


def cmd_status(args):
    a = args.assets_dir
    s = load_scores(a)["entries"]
    c = load_cards(a)["cards"]
    p = load_proposals(a)["proposals"]
    l = read_learnings(a)
    print("技能自我进化状态总览 · assets=%s" % a)
    print("  登记簿 learnings : %d 条（open %d / distilled %d）" %
          (len(l), sum(1 for x in l if "open" in x[3].lower()),
           sum(1 for x in l if "distilled" in x[3].lower())))
    print("  质量评分         : %d 期" % len(s))
    if s:
        e = s[-1]
        print("    最近 %s《%s》总分 %.1f｜退步 %s" %
              (e["episode"], e["title"], sum(float(v) for v in e["scores"].values()),
               ",".join(e.get("regression_dims") or []) or "无"))
        avgs = trend(s, "")
        for d, v in avgs.items():
            print("    %-4s %-4s 近%d期均值 %.2f" % (d, DIM_CN[d], TREND_WINDOW, v))
    print("  事实卡片         : %d 条（valid %d / stale %d / retired %d）" %
          (len(c), sum(1 for x in c if x["status"] == "valid"),
           sum(1 for x in c if x["status"] == "stale"),
           sum(1 for x in c if x["status"] == "retired")))
    print("  提议             : %d 条（待拍板 %d / 待验证 %d / 已否决 %d）" %
          (len(p), sum(1 for x in p if x["status"] == "pending_author"),
           sum(1 for x in p if x["status"] == "approved" and not (x.get("verification") or {}).get("result")),
           sum(1 for x in p if x["status"] == "rejected")))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMON_DEFAULTS = {
    "assets_dir": DEFAULT_ASSETS,
    "workspace": os.getcwd(),
    "date": None,
}


def add_common(parser, suppress=False):
    """全局选项同时挂在顶层与每个子命令上 —— 让 `--workspace` 写在子命令前后都能识别。
    子命令侧用 SUPPRESS，避免默认值把顶层已解析的显式值覆盖掉。"""
    d = argparse.SUPPRESS if suppress else DEFAULT_ASSETS
    w = argparse.SUPPRESS if suppress else os.getcwd()
    t = argparse.SUPPRESS if suppress else None
    parser.add_argument("--assets-dir", default=d,
                        help="资产目录（默认技能内 assets/state；仅测试时可覆盖）")
    parser.add_argument("--workspace", default=w,
                        help="工作区路径，用于读写 .evolution_state.json 执行凭证")
    parser.add_argument("--date", default=t, help="覆盖本轮日期 YYYY-MM-DD（测试/补录用）")


def build_parser():
    p = argparse.ArgumentParser(
        description="one-hundred-million 双环自我进化门禁（固定规范第 43 条）")
    add_common(p)
    sub = p.add_subparsers(dest="cmd", required=True)

    def make(name, help_text):
        sp = sub.add_parser(name, help=help_text)
        add_common(sp, suppress=True)
        return sp

    b = make("brief", "Step 0 开工回顾：生成本轮防复发清单 + 提升目标")
    b.add_argument("--episode", help="本轮标识（期号/日期序号）")
    b.set_defaults(func=cmd_brief)

    s = make("score", "Step 8 录入五维质量评分（每维须带证据）")
    s.add_argument("--episode", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--camp", required=True)
    s.add_argument("--tier", required=True, choices=("S", "M", "L", "读书长篇"))
    s.add_argument("--scores", nargs="+", required=True,
                   help="content=8 visual=9 audio=9 subtitle=10 delivery=8")
    s.add_argument("--evidence", nargs="+", required=True,
                   help="逐维证据，可重复：content='content_depth_check PASS…' …")
    s.add_argument("--rework", type=int, default=0, help="本轮返工次数")
    s.add_argument("--rejections", type=int, default=0, help="作者审核打回次数")
    s.add_argument("--gate-failures", type=int, default=0, help="门禁 FAIL 次数")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--learning-ids", help="本轮登记进 learnings.md 的 LID，逗号分隔")
    g.add_argument("--no-issues", action="store_true", help="显式声明本轮确无问题")
    s.add_argument("--notes", help="本轮复盘备注（好/坑/下次改）")
    s.set_defaults(func=cmd_score)

    c = make("check", "Step 8 收尾门禁：校验回顾/评分/登记三项均已落实")
    c.set_defaults(func=cmd_check)

    src = make("source", "内容资料事实卡片库")
    src.add_argument("action", choices=("add", "list", "find", "verify", "retire", "expire", "stats"))
    src.add_argument("keyword_pos", nargs="?", help="find 的关键词也可直接写在这里")
    src.add_argument("--review-days", type=int, default=DEFAULT_REVIEW_DAYS)
    src.add_argument("--claim")
    src.add_argument("--source")
    src.add_argument("--level", default="L1")
    src.add_argument("--version")
    src.add_argument("--conditions")
    src.add_argument("--used-in")
    src.add_argument("--status")
    src.add_argument("--keyword")
    src.add_argument("--id")
    src.add_argument("--note")
    src.add_argument("--reason")
    src.set_defaults(func=cmd_source)

    d = make("distill", "同根因复发 → 生成蒸馏提议（不自动改规则）")
    d.add_argument("--lids", required=True)
    d.add_argument("--clause", help="建议固化到哪个条款/脚本")
    d.add_argument("--summary")
    d.add_argument("--evidence")
    d.add_argument("--episode")
    d.set_defaults(func=cmd_distill)

    pr = make("proposals", "列出提议")
    pr.add_argument("--status")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_proposals)

    ap = make("approve", "作者确认提议（确认后才允许 AI 固化规则）")
    ap.add_argument("id")
    ap.add_argument("--note")
    ap.set_defaults(func=lambda a: set_proposal_status(a, "approved", "note"))

    rj = make("reject", "作者否决提议")
    rj.add_argument("id")
    rj.add_argument("--note")
    rj.set_defaults(func=lambda a: set_proposal_status(a, "rejected", "note"))

    v = make("verify", "下轮验证进化是否生效（必须带证据）")
    v.add_argument("id")
    v.add_argument("--result", required=True,
                   choices=("no-recurrence", "recurred", "improved", "no-data"))
    v.add_argument("--evidence", required=True)
    v.set_defaults(func=cmd_verify)

    st = make("status", "打印自我进化状态总览")
    st.set_defaults(func=cmd_status)
    return p


def main():
    args = build_parser().parse_args()
    for k, v in COMMON_DEFAULTS.items():
        if not hasattr(args, k):
            setattr(args, k, v)
    # assets-dir / workspace 可以是相对路径，统一转绝对
    args.assets_dir = os.path.abspath(args.assets_dir)
    args.workspace = os.path.abspath(args.workspace)
    # 防污染守卫（沿用 learnings.md L009 的教训：update_catalog.py 在技能仓库根执行会写入仓库）
    # brief/score/check 会写 <workspace>/.evolution_state.json，绝不能落进技能仓库自身。
    if (args.cmd in ("brief", "score", "check")
            and os.path.exists(os.path.join(args.workspace, "SKILL.md"))):
        print("[FAIL] --workspace 指向技能仓库自身（%s）—— 执行凭证不得写进技能仓库。" % args.workspace,
              file=sys.stderr)
        print("       请显式传 `--workspace <本轮视频工作区>` 后重跑（见 references/self-evolution.md §3）。",
              file=sys.stderr)
        return 1
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as e:
        print("[FAIL] %s：%s" % (args.cmd, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
