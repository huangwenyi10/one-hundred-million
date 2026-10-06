#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jobctl.py —— 跨客户端「未完成视频」台账与断点续跑控制器。

为什么需要它
------------
本技能会被 WorkBuddy / Trae / Codex / Qoder / Kimi 等不同客户端加载执行，而这些
客户端的模型额度彼此独立：A 客户端在生成第 3 条视频时额度用完，纯靠对话记忆是
**换不回 B 客户端**的——B 客户端不知道 A 做到哪一步、不知道产物落在哪个目录、
不知道哪一步是确定性脚本（可直接跑）、哪一步必须重新调模型。

本脚本把「做到哪一步」从对话记忆搬到**磁盘上的事实**：
  1. 进度不靠自报，靠**扫描磁盘实物**（口播稿/PPT/配音/字幕/帧/body/成片是否真的在）；
  2. 任何客户端开工第一件事跑 `scan` + `resume`，直接拿到「本工作区有哪些没做完的
     视频、我该从哪一步继续、跑什么命令」；
  3. 额度用完时跑 `block` 写明原因，下一个客户端 `resume` 时第一眼就看到
     「上一客户端在 step X 因额度中断」，无需作者复述。

台账文件（工作区根，唯一事实来源）
--------------------------------
`one-hundred-million-jobs.json`
  {
    "version": 1,
    "updatedAt": "...",
    "clients": {"<client>": {"platform": "...", "quota": "ok|exhausted",
                            "reason": "...", "model": "...", "at": "..."}},
    "jobs": {
      "<job_id>": {
        "dir": "<工作区>/<标题>_<YYYYMMDD>-<NN>",
        "title": "...", "camp": "...", "tier": "S|M|L",
        "created_at": "...", "updated_at": "...",
        "owner_client": "...", "claimed_at": "...", "lease_min": 120,
        "blocked": {"stage": "tts", "reason": "credit 额度已用完",
                    "by_client": "WorkBuddy", "at": "..."},
        "done_stages": ["script", "ppt"],
        "history": [{"at": "...", "event": "resume", "client": "..."}]
      }
    }
  }

子命令
------
  scan      扫描工作区，实物判定每个视频做到哪一步（自动登记新目录 = adopt）
  status    列出全部任务进度 / 单个任务详情
  next      打印某任务「下一步该做什么」（含可直接复制的命令）
  claim     认领任务（写 owner_client + 租约），防两个客户端并行做同一条
  release   释放租约
  done      标记某阶段完成（会立即重新扫描校正，不盲信自报）
  block     标记因额度/能力中断而卡住（跨客户端交接的核心动作）
  unblock   清除阻塞
  resume    为「刚接手的新客户端」生成续跑包（含上一客户端中断原因 + 精确下一步）
  list      只列未完成任务（= 可续跑清单），--all 含已完成
  forget    移除某任务登记（不删文件）

退出码
------
  0 = 正常        1 = 参数错 / 任务不存在
  3 = 没有未完成任务（无活可干）    4 = 有未完成任务（供脚本判断，配合 --json）

仅依赖 Python 标准库。任何客户端只要能跑 `python3` 就能用，不绑定任何客户端私有 API。
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

STATE_NAME = "one-hundred-million-jobs.json"
TZ = timezone(timedelta(hours=8))
DEFAULT_LEASE_MIN = 120

# 目录名 = <视频标题>_<YYYYMMDD>-<NN>；标题段可含短横线，时间戳段固定 8 位-2 位
DIR_RE = re.compile(r"^(?P<title>.+)_(?P<date>\d{8})-(?P<seq>\d{2,})$")

# 各阶段的实物探针（相对任务目录）。第一个命中的路径即视为该阶段完成。
# 顺序 = 真实流水线顺序，next_stage 依赖它，故必须与 Step 1→8 一致。
STAGES = [
    ("script",   "Step 1 口播稿",        ["*_口播稿.txt"]),
    ("ppt",      "Step 2 HTML 幻灯片",   ["*_PPT.html"]),
    ("frames",   "Step 2 导出帧",        ["build/frames/page_*.png", "frames/page_*.png"]),
    ("tts",      "Step 3 配音音频",      ["build/voiceover.mp3", "voiceover.mp3"]),
    ("segments", "Step 5 分段真实时间轴", ["build/segments_durations.json", "segments_durations.json"]),
    ("subs",     "Step 5 逐字字幕",      ["build/subtitles.srt", "build/subtitles_fixed.srt",
                                          "subtitles.srt", "subtitles_fixed.srt"]),
    ("body",     "Step 6 正文 body",     ["build/body.mp4", "body.mp4"]),
    ("final",    "Step 6 成片",          ["*_成片.mp4", "*.mp4"]),
    ("publish",  "Step 8 发布物料",      ["发布/*"]),
]

# 未完成阶段 → 下一步该做什么（换客户端后直接照做，不需要作者复述上下文）
NEXT_ACTION = {
    "script":   ("写口播稿", [
        "1) 读 references/script-writing-guide.md 与 references/content-formats.md 定档位",
        "2) 检索权威来源（国内外同等，英文主题须核英文一手原文）并记入 build/sources.md",
        "3) 写 <训练营全名>-<标题>_口播稿.txt（正文纯口播，顶部不带标题行）",
        "4) python3 scripts/polyphone_check.py scan \"<口播稿>\"",
        "5) python3 scripts/content_depth_check.py \"<口播稿>\" --camp <训练营全名>"]),
    "ppt":      ("生成 HTML 幻灯片", [
        "1) 复制 templates/slide-template.html 改 --accent/--hilite/--bg/--bg2 为训练营主题色",
        "2) 填 <section class=\"slide\">，每页套 5 大版式之一（见 references/visual-design.md）",
        "3) 内容收在顶部 85% 内，左上角预留水印安全区、底部预留字幕带",
        "4) 页脚/角标不得出现训练营名称与期号（固定规范第 14 条）"]),
    "tts":      ["python3 scripts/polyphone_check.py apply \"<口播稿>\" --out build/script_tts.txt "
                 "--map build/polyphone_map.json",
                 "python3 scripts/gen_sync_subs.py --script build/script_tts.txt --out-dir build "
                 "--voice zh-CN-YunxiNeural",
                 "python3 scripts/polyphone_check.py restore --srt build/subtitles.srt "
                 "--map build/polyphone_map.json --out build/subtitles_fixed.srt"],
    "segments": ["确认 build/segments_durations.json 与配音真实时长一致；禁止按字数比例估算"],
    "subs":     ["字幕文本必须来自配音真实朗读；末尾标点用 "
                 "python3 scripts/video_tool.py sub_clean 清洗"],
    "frames":   ["用无头浏览器把每页导出为 1920×1080 PNG 到 build/frames/page_NN.png",
                 "scripts/render_frames.py 或 render_animated.js（动画增强，Step 6 第 2.1 条）"],
    "body":     ["python3 scripts/compose_motion.py <frames_dir> build/segments_durations.json "
                 "build/body.mp4（内部先过 video_quality_gate.py，FAIL 即停）"],
    "final":    ["python3 scripts/burn_subtitles.py build/body.mp4 build/subtitles_fixed.srt "
                 "build/voiceover.mp3 \"<标题>_成片.mp4\" --engine fast",
                 "python3 scripts/check_sync.py <字幕> <口播稿> ...（exit 0 才允许交付）",
                 "python3 scripts/douyin_compliance_check.py \"<口播稿>\" --title \"<标题>\""],
    "publish":  ["按 references/multi-platform-repack.md 派生封面与三平台文案到 <标题目录>/发布/",
                 "Step 7 作者审核通过后按 references/netdisk-archive.md 归档百度网盘"],
}

DONE_NEXT = ["本任务全部阶段均已有实物，交给作者审核（Step 7）即可，不要重跑已完成阶段"]

# 达成即视为「流水线已出片」的阶段。成片存在即说明 Step 1-6 已跑完，
# 其后（Step 7 作者审核 / Step 8 发布归档）属人工环节，不算「未完成的活」——
# 否则历史交付目录一旦按固定规范第 24 条清理掉 build/ 与口播稿，
# 每次 scan 都会把它们误报成"可续跑"。
TERMINAL = "final"


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def state_path(ws):
    return os.path.join(ws or os.getcwd(), STATE_NAME)


def load(ws):
    p = state_path(ws)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict):
                s.setdefault("jobs", {})
                s.setdefault("clients", {})
                return s
        except Exception:
            pass
    return {"version": 1, "jobs": {}, "clients": {}}


def save(ws, s):
    s["updatedAt"] = now_iso()
    tmp = state_path(ws) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_path(ws))


def strip_ts(dirname):
    """目录名 -> 纯标题；不符合命名则原样返回。"""
    m = DIR_RE.match(dirname)
    return m.group("title") if m else dirname


def probe_stages(job_dir):
    """按实物判定阶段完成情况，绝不信自报。返回 (done_stage_list, stage_detail)。"""
    done, detail = [], {}
    for key, _name, pats in STAGES:
        hit = None
        for pat in pats:
            hits = sorted(glob.glob(os.path.join(job_dir, pat)))
            if hits:
                hit = hits
                break
        detail[key] = hit[0] if hit else None
        if hit:
            done.append(key)
    return done, detail


def scan(ws):
    """扫描工作区顶层视频目录，登记/校正台账。返回 (state, new_ids)。"""
    s = load(ws)
    root = os.path.abspath(ws or os.getcwd())
    new_ids = []
    existing = {os.path.abspath(v.get("dir", "")): k for k, v in s["jobs"].items()}
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d) or name.startswith("."):
            continue
        if not DIR_RE.match(name):
            continue
        # 成品目录而非待建目录：没有口播稿也没有 PPT，且不含 build/，多半是纯交付物目录
        done, _detail = probe_stages(d)
        if not done and not os.path.isdir(os.path.join(d, "build")):
            continue
        jid = existing.get(os.path.abspath(d)) or strip_ts(name)
        if jid in s["jobs"] and os.path.abspath(s["jobs"][jid].get("dir", "")) != os.path.abspath(d):
            jid = strip_ts(name)  # 标题改名过 → 用新标题段做新 id
        if jid not in s["jobs"]:
            s["jobs"][jid] = {"created_at": now_iso(), "done_stages": []}
            new_ids.append(jid)
        job = s["jobs"][jid]
        job["dir"] = os.path.abspath(d)
        job["title"] = strip_ts(name)
        job["updated_at"] = now_iso()
        job["done_stages"] = done          # 实物为准，覆盖自报
        job.pop("_detail", None)
    save(ws, s)
    return s, new_ids


def find_job(s, key):
    """按 job_id / 标题 / 目录名片段定位任务。"""
    if key in s["jobs"]:
        return key, s["jobs"][key]
    for jid, job in s["jobs"].items():
        if key in (job.get("title", ""), os.path.basename(job.get("dir", "")), job.get("dir", "")):
            return jid, job
    return None, None


def next_stage(done):
    """下一个该做的阶段；已出片则返回 None（成片之后都是人工环节）。

    以成片（TERMINAL）为唯一完工判据，**不能只看「最高完成下标」**——
    否则 `发布/` 先于成片存在时（封面已派生但还没合成）会被误判为已完工。
    """
    if TERMINAL in done:
        return None
    for key, _n, _p in STAGES:
        if key not in done:
            return key
    return None


def human(stage):
    for k, n, _p in STAGES:
        if k == stage:
            return n
    return stage


def cmd_scan(args):
    s, new = scan(args.workspace)
    open_jobs = unfinished(s)
    if args.json:
        print(json.dumps({"new": new, "open": open_jobs}, ensure_ascii=False, indent=2))
        return 4 if open_jobs else 3
    if new:
        print("新登记任务 %d 个：%s" % (len(new), "、".join(new)))
    if not open_jobs:
        # 区分「干净」与「未登记」：台账 jobs 为空意味着本工作区从未跑过 register/scan，
        # 跨客户端续跑规则（固定规范第 33 条）会失效——必须先 register 再开工。
        if not s.get("jobs"):
            print("⚠ 台账为空：本工作区从未登记过任务（未跑过 register + scan）。")
            print("  跨客户端续跑规则要求开工前先登记客户端与依赖：")
            print("    python3 scripts/client_preflight.py register <客户端名> --probe --workspace <工作区>")
            print("  登记后再跑本命令，台账才会非空；否则换客户端时无人能续跑此工作区的活。")
            return 5
        print("没有未完成任务，工作区干净。")
        return 3
    print("\n可续跑任务 %d 个：" % len(open_jobs))
    for j in open_jobs:
        line = "- [%s] %s（%s）→ 下一步：%s" % (
            j["job_id"], j["title"], j.get("camp") or "未标注营",
            human(j["next_stage"]) if j["next_stage"] else "已完工，待作者审核")
        if j.get("blocked"):
            line += "  ⚠ 上次中断：%s（%s）" % (j["blocked"].get("reason"), j["blocked"].get("by_client"))
        print(line)
    return 4


def unfinished(s):
    out = []
    for jid, job in s["jobs"].items():
        ns = next_stage(job.get("done_stages", []))
        if ns is None:
            continue
        out.append({"job_id": jid, "title": job.get("title", jid), "camp": job.get("camp"),
                    "dir": job.get("dir"), "done_stages": job.get("done_stages", []),
                    "next_stage": ns, "blocked": job.get("blocked"),
                    "owner_client": job.get("owner_client"), "claimed_at": job.get("claimed_at")})
    out.sort(key=lambda x: (x.get("claimed_at") or "", x["job_id"]))
    return out


def cmd_status(args):
    s = load(args.workspace)
    if not s["jobs"]:
        s, _ = scan(args.workspace)
    if args.job:
        jid, job = find_job(s, args.job)
        if not job:
            print("未找到任务：%s" % args.job, file=sys.stderr)
            return 1
        done, detail = probe_stages(job["dir"])
        if args.json:
            print(json.dumps({"job_id": jid, **job, "probe": detail}, ensure_ascii=False, indent=2))
            return 0
        print("任务：%s" % jid)
        print("标题：%s" % job.get("title", ""))
        print("目录：%s" % job.get("dir", ""))
        print("训练营：%s   档位：%s" % (job.get("camp") or "-", job.get("tier") or "-"))
        print("认领：%s（%s，租约 %s 分钟）" % (job.get("owner_client") or "-",
                                              job.get("claimed_at") or "-",
                                              job.get("lease_min") or DEFAULT_LEASE_MIN))
        if job.get("blocked"):
            print("中断：%s（%s，%s）" % (job["blocked"].get("reason"), job["blocked"].get("by_client"),
                                         job["blocked"].get("at")))
        print("\n阶段实物核对：")
        for key, name, _p in STAGES:
            p = detail[key]
            print("  [%s] %-22s %s" % ("✓" if p else " ", name, p or "缺失"))
        ns = next_stage(done)
        print("\n下一步：%s" % (human(ns) if ns else "已完工（交作者审核）"))
        return 0
    if args.json:
        print(json.dumps({"jobs": s["jobs"]}, ensure_ascii=False, indent=2))
        return 0
    if not s["jobs"]:
        print("台账为空，先跑 jobctl.py scan。")
        return 0
    for jid, job in s["jobs"].items():
        done = job.get("done_stages", [])
        print("[%s] %s  %d/%d 阶段完成%s" % (
            jid, job.get("title", jid), len(done), len(STAGES),
            "  ⚠ " + job["blocked"]["reason"] if job.get("blocked") else ""))
    return 0


def cmd_next(args):
    s = load(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        print("未找到任务：%s" % args.job, file=sys.stderr)
        return 1
    done, _ = probe_stages(job["dir"])
    ns = next_stage(done)
    print("任务 %s ｜ 下一步：%s" % (jid, human(ns) if ns else "已完工"))
    if ns is None:
        for line in DONE_NEXT:
            print("  - %s" % line)
        return 0
    act = NEXT_ACTION.get(ns)
    if isinstance(act, tuple):
        print("动作：%s" % act[0])
        for line in act[1]:
            print("  - %s" % line)
    else:
        for line in act or []:
            print("  - %s" % line)
    return 0


def cmd_claim(args):
    s, _ = scan(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        print("未找到任务：%s" % args.job, file=sys.stderr)
        return 1
    prev = job.get("owner_client")
    job["owner_client"] = args.client
    job["claimed_at"] = now_iso()
    job["lease_min"] = args.lease
    job.setdefault("history", []).append(
        {"at": now_iso(), "event": "claim", "client": args.client, "prev": prev})
    s["clients"].setdefault(args.client, {})["at"] = now_iso()
    save(args.workspace, s)
    print("已认领：%s（%s → %s，租约 %d 分钟）" % (jid, prev or "无", args.client, args.lease))
    if prev and prev != args.client:
        print("提示：上一认领方是 %s —— 接手前先确认它已停手，否则两边会互相覆盖 build/。" % prev)
    return 0


def cmd_release(args):
    s = load(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        return 1
    job.pop("owner_client", None)
    job.pop("claimed_at", None)
    job.setdefault("history", []).append(
        {"at": now_iso(), "event": "release", "client": args.client})
    save(args.workspace, s)
    print("已释放：%s" % jid)
    return 0


def cmd_done(args):
    s, _ = scan(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        print("未找到任务：%s" % args.job, file=sys.stderr)
        return 1
    done, _ = probe_stages(job["dir"])
    job["done_stages"] = done
    job.setdefault("history", []).append(
        {"at": now_iso(), "event": "stage_done", "stage": args.stage, "client": args.client})
    save(args.workspace, s)
    ok = args.stage in done
    print("标记 %s 完成：%s（实物%s）" % (
        args.stage, "OK" if ok else "未通过——磁盘上没找到该阶段产物，请检查路径",
        "已核对" if ok else "缺失"))
    return 0 if ok else 1


def cmd_block(args):
    s, _ = scan(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        print("未找到任务：%s" % args.job, file=sys.stderr)
        return 1
    job["blocked"] = {"stage": args.stage or next_stage(job.get("done_stages", [])),
                      "reason": args.reason, "by_client": args.client, "at": now_iso()}
    job.setdefault("history", []).append(
        {"at": now_iso(), "event": "block", "stage": args.stage, "reason": args.reason,
         "client": args.client})
    s["clients"].setdefault(args.client, {}).update({"quota": "exhausted", "reason": args.reason,
                                                     "at": now_iso()})
    save(args.workspace, s)
    print("已记录中断：%s 卡在 %s，原因「%s」（%s）" % (jid, job["blocked"]["stage"], args.reason, args.client))
    print("换客户端后：python3 scripts/jobctl.py resume --workspace <工作区> --job %s" % jid)
    return 0


def cmd_unblock(args):
    s = load(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        return 1
    job.pop("blocked", None)
    job.setdefault("history", []).append({"at": now_iso(), "event": "unblock", "client": args.client})
    save(args.workspace, s)
    print("已清除阻塞：%s" % jid)
    return 0


def cmd_resume(args):
    """为刚接手的新客户端生成续跑包。"""
    s = load(args.workspace)
    if not s["jobs"]:
        s, _ = scan(args.workspace)
    if args.job:
        jid, job = find_job(s, args.job)
        if not job:
            print("未找到任务：%s" % args.job, file=sys.stderr)
            return 1
        cand = [(jid, job)]
    else:
        cand = [(k, v) for k, v in s["jobs"].items() if next_stage(v.get("done_stages", []))]

    if not cand:
        print("无未完成任务。")
        return 3

    lines = ["# 跨客户端续跑包（生成于 %s）" % now_iso(), ""]
    if args.client:
        lines.append("接手客户端：%s" % args.client)
        lines.append("")
    for jid, job in cand:
        done, detail = probe_stages(job["dir"])
        ns = next_stage(done)
        lines.append("## 任务 %s" % jid)
        lines.append("- 标题：%s" % job.get("title", ""))
        lines.append("- 训练营：%s   档位：%s" % (job.get("camp") or "未标注", job.get("tier") or "-"))
        lines.append("- 目录：`%s`" % job.get("dir", ""))
        if job.get("blocked"):
            b = job["blocked"]
            lines.append("- **上一客户端中断**：`%s` 在 `%s` 因「%s」中断（%s）" % (
                b.get("by_client"), human(b.get("stage")), b.get("reason"), b.get("at")))
        if job.get("owner_client"):
            lines.append("- 认领方：%s（%s）——接手前先确认对方已停手" % (
                job["owner_client"], job.get("claimed_at")))
        lines.append("- 已完成阶段（磁盘实物核对）：%s" % (
            "、".join(human(k) for k in done) or "无"))
        lines.append("")
        if ns is None:
            lines.append("→ 已全部完成，**不要重跑任何阶段**，直接进入 Step 7 交作者审核。")
            lines.append("")
            continue
        lines.append("### 下一步：%s" % human(ns))
        act = NEXT_ACTION.get(ns)
        if isinstance(act, tuple):
            lines.append("动作：%s" % act[0])
            for x in act[1]:
                lines.append("- %s" % x)
        else:
            for x in act or []:
                lines.append("- %s" % x)
        lines.append("")
        lines.append("纪律：已完成阶段一律**不重做**；换客户端不豁免任何质量门禁"
                     "（check_sync.py exit 0 / 禁句禁标识扫描 / 字幕带与水印区像素扫描 / 素材双源核验）。")
        lines.append("")

    if args.client:
        first = cand[0][0]
        s["jobs"][first]["owner_client"] = args.client
        s["jobs"][first]["claimed_at"] = now_iso()
        s["jobs"][first].setdefault("history", []).append(
            {"at": now_iso(), "event": "resume", "client": args.client})
        s["clients"].setdefault(args.client, {})["at"] = now_iso()
        save(args.workspace, s)

    text = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print("续跑包已写入：%s" % args.out)
    print(text)
    return 0


def cmd_list(args):
    s = load(args.workspace)
    if not s["jobs"]:
        s, _ = scan(args.workspace)
    rows = [(k, v) for k, v in s["jobs"].items()
            if args.all or next_stage(v.get("done_stages", []))]
    if args.json:
        print(json.dumps([{"job_id": k, **v} for k, v in rows], ensure_ascii=False, indent=2))
        return 4 if rows else 3
    if not rows:
        print("无未完成任务。")
        return 3
    for jid, job in rows:
        done = job.get("done_stages", [])
        print("[%s] %s  %d/%d  下一步=%s%s" % (
            jid, job.get("title", jid), len(done), len(STAGES),
            human(next_stage(done)) if next_stage(done) else "已完工",
            "  ⚠ %s" % job["blocked"]["reason"] if job.get("blocked") else ""))
    return 4


def cmd_forget(args):
    s = load(args.workspace)
    jid, job = find_job(s, args.job)
    if not job:
        return 1
    del s["jobs"][jid]
    save(args.workspace, s)
    print("已从台账移除（磁盘文件未动）：%s" % jid)
    return 0


def main():
    ap = argparse.ArgumentParser(description="跨客户端未完成任务台账与断点续跑控制器")
    ap.add_argument("cmd", choices=["scan", "status", "next", "claim", "release", "done",
                                    "block", "unblock", "resume", "list", "forget"])
    ap.add_argument("job", nargs="?", help="任务 id / 标题 / 目录名片段")
    ap.add_argument("--workspace", default=None, help="工作区根目录")
    ap.add_argument("--client", default=os.environ.get("OHM_CLIENT", ""),
                    help="当前客户端名（WorkBuddy / Trae / Codex / Qoder / Kimi ...）")
    ap.add_argument("--stage", default="", help="阶段 key（block/done 用）")
    ap.add_argument("--reason", default="", help="中断原因（block 用）")
    ap.add_argument("--lease", type=int, default=DEFAULT_LEASE_MIN, help="认领租约分钟数")
    ap.add_argument("--out", default="", help="resume 续跑包输出路径")
    ap.add_argument("--all", action="store_true", help="list 含已完成任务")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args()

    fn = {
        "scan": cmd_scan, "status": cmd_status, "next": cmd_next, "claim": cmd_claim,
        "release": cmd_release, "done": cmd_done, "block": cmd_block, "unblock": cmd_unblock,
        "resume": cmd_resume, "list": cmd_list, "forget": cmd_forget,
    }[args.cmd]

    if args.cmd in ("scan", "list") and not args.job:
        pass
    elif args.cmd in ("status", "next", "claim", "release", "done", "block", "unblock", "forget") \
            and not args.job:
        print("ERROR: %s 需要 <任务 id / 标题>" % args.cmd, file=sys.stderr)
        return 1
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
