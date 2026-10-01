#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""训练营生成开关（camp switch）

控制 9 大训练营里哪些允许进入生产。

默认策略（作者 2026-10-01 决策）：
    只有「读书训练营」开启；其余 8 类（架构师 / 大数据 / AI / 产品经理 /
    前端 / 测试 / 管理 / 软技能）一律暂停——暂停的营不生成、不轮转、不做
    选题，直到作者明确发话（「开始」）才恢复。作者原话依据：其它营成片质量
    不达标，先停，等作者发话再开。

状态文件：<workspace>/camp_switches.json
    {
      "version": 1,
      "updatedAt": "2026-10-01T21:45:00+08:00",
      "enabled": ["读书训练营"],
      "history": [{"ts": "...", "action": "off", "camp": "架构师训练营", "note": "..."}]
    }
    文件不存在 => 使用默认策略（只开读书训练营）。

子命令
    status                     打印 9 营开关表
    list-enabled               逐行打印启用营（供脚本/流程消费）
    check <营名>               启用 -> exit 0；暂停 -> exit 3
    on  <营名|--all>           开启
    off <营名|--all>           暂停
    next [--rotation FILE]     依「启用集合 + 轮转状态」算出本期应做的营（stdout）；
                               启用集合为空 -> exit 4
    reset                      恢复默认（只开读书训练营）

通用选项：--workspace <dir>（默认当前工作目录）、--json、--note/--reason "<说明>"

仅依赖标准库。
"""

import argparse
import json
import os
import sys
from datetime import datetime

CAMP_ORDER = [
    "架构师训练营",
    "大数据训练营",
    "AI 训练营",
    "产品经理训练营",
    "前端训练营",
    "测试训练营",
    "管理训练营",
    "软技能训练营",
    "读书训练营",
]

DEFAULT_ENABLED = ["读书训练营"]
STATE_FILE = "camp_switches.json"
DEFAULT_ROTATION_FILE = "one-hundred-million-rotation.json"

ALIASES = {
    "架构师": "架构师训练营",
    "架构": "架构师训练营",
    "architect": "架构师训练营",
    "大数据": "大数据训练营",
    "bigdata": "大数据训练营",
    "ai": "AI 训练营",
    "人工智能": "AI 训练营",
    "产品": "产品经理训练营",
    "产品经理": "产品经理训练营",
    "pm": "产品经理训练营",
    "前端": "前端训练营",
    "fe": "前端训练营",
    "测试": "测试训练营",
    "qa": "测试训练营",
    "管理": "管理训练营",
    "软技能": "软技能训练营",
    "读书": "读书训练营",
    "读书营": "读书训练营",
    "读书训练营": "读书训练营",
    "book": "读书训练营",
    "reading": "读书训练营",
}


# ---------------------------------------------------------------- 基础工具

def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm_camp(name):
    """把简称/别名归一为 9 大训练营全名；无法识别返回 None。"""
    if name is None:
        return None
    raw = name.strip()
    if raw in CAMP_ORDER:
        return raw
    key = raw.lower().replace(" ", "")
    if key in ALIASES:
        return ALIASES[key]
    for full in CAMP_ORDER:          # 容错：去掉空格后比对
        if full.lower().replace(" ", "") == key:
            return full
    return None


def state_path(ws):
    return os.path.join(os.path.abspath(ws), STATE_FILE)


def default_state():
    return {
        "version": 1,
        "updatedAt": None,
        "policy": "default-only-reading-camp",
        "enabled": list(DEFAULT_ENABLED),
        "history": [],
    }


def load_state(ws):
    """读状态；文件缺失或损坏时回落到默认策略（并标记来源）。"""
    p = state_path(ws)
    if not os.path.exists(p):
        return default_state(), "default"
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:                                    # noqa: BLE001
        sys.stderr.write("[WARN] 状态文件无法解析（%s），回落默认策略：%s\n" % (e, p))
        return default_state(), "default"
    enabled = data.get("enabled")
    if not isinstance(enabled, list):
        sys.stderr.write("[WARN] 状态文件缺少 enabled 列表，回落默认策略\n")
        return default_state(), "default"
    clean = [c for c in CAMP_ORDER if c in enabled]            # 白名单过滤 + 固定顺序
    unknown = [c for c in enabled if c not in CAMP_ORDER]
    if unknown:
        sys.stderr.write("[WARN] 忽略无法识别的训练营：%s\n" % ", ".join(unknown))
    data["enabled"] = clean
    data.setdefault("version", 1)
    data.setdefault("history", [])
    return data, "file"


def save_state(ws, state, action, camp, note):
    state["version"] = 1
    state["updatedAt"] = now_iso()
    hist = state.setdefault("history", [])
    hist.append({"ts": state["updatedAt"], "action": action, "camp": camp, "note": note or ""})
    del hist[:-30]                                            # 只留最近 30 条
    p = state_path(ws)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)
    return p


# ---------------------------------------------------------------- 子命令

def cmd_status(args):
    ws = os.path.abspath(args.workspace)
    state, src = load_state(ws)
    enabled = set(state["enabled"])
    if getattr(args, "json", False):
        print(json.dumps({
            "workspace": ws,
            "stateFile": state_path(ws),
            "source": src,
            "updatedAt": state.get("updatedAt"),
            "camps": [{"camp": c, "enabled": c in enabled} for c in CAMP_ORDER],
            "enabledCount": len(enabled),
            "totalCount": len(CAMP_ORDER),
        }, ensure_ascii=False, indent=2))
        return 0
    print("训练营生成开关")
    print("  工作区  : %s" % ws)
    print("  状态文件: %s（%s）" % (state_path(ws), "已存在" if src == "file" else "不存在 → 用默认策略"))
    print("  更新于  : %s" % (state.get("updatedAt") or "—"))
    print("")
    for c in CAMP_ORDER:
        mark = "ON " if c in enabled else "OFF"
        tag = "  ← 默认常开" if (c in enabled and src == "default") else ""
        print("  [%s] %s%s" % (mark, c, tag))
    print("")
    print("启用 %d / %d" % (len(enabled), len(CAMP_ORDER)))
    if not enabled:
        print("⚠️ 启用集合为空：本轮不生成任何内容（轮转返回 exit 4）")
    return 0


def cmd_list_enabled(args):
    ws = os.path.abspath(args.workspace)
    state, _ = load_state(ws)
    for c in state["enabled"]:
        print(c)
    return 0


def cmd_check(args):
    ws = os.path.abspath(args.workspace)
    camp = norm_camp(args.camp)
    if camp is None:
        sys.stderr.write("[ERROR] 无法识别的训练营：%s\n" % args.camp)
        return 2
    state, src = load_state(ws)
    if camp in state["enabled"]:
        print("ENABLED %s" % camp)
        return 0
    print("PAUSED %s（来源：%s）" % (camp, "状态文件" if src == "file" else "默认策略"))
    return 3


def _apply(args, turn_on):
    ws = os.path.abspath(args.workspace)
    state, _ = load_state(ws)
    if args.all:
        targets = list(CAMP_ORDER)
        label = "全部训练营"
    else:
        camp = norm_camp(args.camp)
        if camp is None:
            sys.stderr.write("[ERROR] 无法识别的训练营：%s\n" % (args.camp or "(空)"))
            return 2
        targets = [camp]
        label = camp
    enabled = list(state["enabled"])
    changed = []
    for c in targets:
        if turn_on and c not in enabled:
            enabled.append(c)
            changed.append(c)
        elif (not turn_on) and c in enabled:
            enabled.remove(c)
            changed.append(c)
    state["enabled"] = [c for c in CAMP_ORDER if c in enabled]
    note = getattr(args, "note", "") or ""
    p = save_state(ws, state, "on" if turn_on else "off", label, note)
    action_cn = "开启" if turn_on else "暂停"
    if not changed:
        print("NOOP %s：%s 无变化" % (action_cn, label))
    else:
        print("OK %s：%s → %s" % (action_cn, "、".join(changed), p))
    print("当前启用：%s" % ("、".join(state["enabled"]) or "（空）"))
    for c in DEFAULT_ENABLED:
        if c not in state["enabled"]:
            print("⚠️ 注意：默认常开的「%s」当前处于暂停状态" % c)
    return 0


def cmd_on(args):
    return _apply(args, True)


def cmd_off(args):
    return _apply(args, False)


def cmd_reset(args):
    ws = os.path.abspath(args.workspace)
    state = default_state()
    note = getattr(args, "note", "") or "reset 恢复默认策略"
    p = save_state(ws, state, "reset", "--all-to-default", note)
    print("OK 已恢复默认策略（只开：%s）→ %s" % ("、".join(DEFAULT_ENABLED), p))
    for c in DEFAULT_ENABLED:
        print("  [ON ] %s" % c)
    return 0


def cmd_next(args):
    """按「启用集合 + 轮转状态」算本期应做的营，写到 stdout。

    规则：在启用集合内按 CAMP_ORDER 顺序推进（相对上次类别），
    上次类别不在启用集合内时从启用集合第一个开始。
    """
    ws = os.path.abspath(args.workspace)
    state, _ = load_state(ws)
    enabled = state["enabled"]
    if not enabled:
        sys.stderr.write("[INFO] 启用集合为空：本轮不生成任何内容\n")
        return 4
    rot_path = args.rotation or os.path.join(ws, DEFAULT_ROTATION_FILE)
    last = ""
    if os.path.exists(rot_path):
        try:
            with open(rot_path, "r", encoding="utf-8") as f:
                last = (json.load(f) or {}).get("lastCategory", "") or ""
        except Exception as e:                                # noqa: BLE001
            sys.stderr.write("[WARN] 轮转状态读取失败（%s），按首项开始\n" % e)
    last = norm_camp(last) or last
    if last in enabled:
        idx = enabled.index(last)
        nxt = enabled[(idx + 1) % len(enabled)]
    else:
        nxt = enabled[0]
    print(nxt)
    return 0


# ---------------------------------------------------------------- CLI

def _common_parser():
    """通用选项：主命令与子命令共享，放前放后都能用。

    default 用 SUPPRESS —— argparse 的 subparser 默认值会覆盖外层同名属性，
    用 SUPPRESS 才能让 `--workspace X status` 与 `status --workspace X` 等价。
    """
    c = argparse.ArgumentParser(add_help=False)
    c.add_argument("--workspace", default=argparse.SUPPRESS, help="工作区目录（默认当前目录）")
    c.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                   help="机器可读输出（status）")
    c.add_argument("--note", "--reason", dest="note", default=argparse.SUPPRESS,
                   help="变更说明，写入 history")
    return c


def build_parser():
    common = _common_parser()
    p = argparse.ArgumentParser(
        prog="camp_switch.py",
        description="训练营生成开关（默认只开读书训练营）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    sub = p.add_subparsers(dest="cmd")

    def add(name, help_text, func):
        sp = sub.add_parser(name, help=help_text, parents=[common])
        sp.set_defaults(func=func)
        return sp

    add("status", "打印开关表", cmd_status)
    add("list-enabled", "逐行打印启用营", cmd_list_enabled)

    sp = add("check", "检查单个营：启用 exit 0 / 暂停 exit 3", cmd_check)
    sp.add_argument("camp")

    sp = add("on", "开启（营名 或 --all）", cmd_on)
    sp.add_argument("camp", nargs="?", default=None)
    sp.add_argument("--all", action="store_true")

    sp = add("off", "暂停（营名 或 --all）", cmd_off)
    sp.add_argument("camp", nargs="?", default=None)
    sp.add_argument("--all", action="store_true")

    sp = add("next", "算本期应做的营（启用集合为空 exit 4）", cmd_next)
    sp.add_argument("--rotation", default=None, help="轮转状态文件路径")

    add("reset", "恢复默认策略（只开读书训练营）", cmd_reset)
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        args.cmd = "status"
        args.func = cmd_status
    if not getattr(args, "workspace", None):
        args.workspace = os.getcwd()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
