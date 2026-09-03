#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pick_free_model.py —— 模型限流降级：免费优先 + 自动切换（Step -1 / 限流触发时调用）

背景
----
技能硬规则：内容生成优先用**免费模型**，无可用免费模型才回退 Auto/其他计费模型。
当某个模型「使用量超出频率限制 / credit 额度用完」时，不询问、不停止，自动切到
下一个未耗尽的免费模型继续跑。

免费模型清单**禁止硬编码**——它由服务端下发、会变。本脚本每次实时读取本机产品
配置，以 `models[].credits` 字段判定：
  - credits 以 "x0.00" 开头（或为 "x0.00 credits"）→ 免费
  - 其余（x0.05 / x0.21 / ...）→ 计费
  - credits 为 None/缺失 → 不计入候选（未在下拉列表定价展示，无法判定）

配置读取优先级（第一个命中的生效）：
  1. $ONE_HUNDRED_MILLION_MODEL_CONFIG 环境变量指定路径
  2. ~/.workbuddy/cache/acc-product-config-v3.json   （服务端下发的实时目录，首选）
  3. /Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/product.cloudhosted.json
  4. .../cli/product.json

状态文件（工作区根）：one-hundred-million-model-fallback.json
  {"exhausted": {"<model-id>": {"at": ISO, "reason": "...", "cooldown": 7200}},
   "current": "<model-id>", "history": [{"at": ISO, "from": "", "to": "", "reason": ""}]}

子命令
------
  list                       列出全部免费模型 + 当前耗尽状态（人读）
  pick                       输出下一个可用的免费模型 id（机读，stdout 只有 id）
  exhausted <id> [--reason S] [--cooldown N]   记录该模型已限流，冷却 N 秒（默认 7200）
  reset [--id X]             清除耗尽标记（全部或指定模型）
  current <id>               记录当前正在使用的模型

退出码
------
  0 = 找到可用免费模型
  2 = 免费模型全部处于冷却/耗尽 → stdout 打印回退建议（Auto/均衡），由调用方回退
  3 = 读不到任何产品配置（无法判定），需人工确认模型清单
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

STATE_NAME = "one-hundred-million-model-fallback.json"
DEFAULT_COOLDOWN = 7200  # 2 小时，与定时任务 2h 一轮的节奏对齐

CANDIDATE_PATHS = [
    "/Users/ay/.workbuddy/cache/acc-product-config-v3.json",
    "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/product.cloudhosted.json",
    "/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/product.json",
]


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def load_config():
    paths = []
    env = os.environ.get("ONE_HUNDRED_MILLION_MODEL_CONFIG")
    if env:
        paths.append(env)
    paths.extend(CANDIDATE_PATHS)
    for p in paths:
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        models = d.get("models")
        if isinstance(models, list) and models:
            return p, models
    return None, []


def is_free(m):
    c = m.get("credits")
    if not isinstance(c, str):
        return False
    c = c.strip()
    # 免费判定：x0.00 / x0.00 credits / 0.00
    return c.startswith("x0.00") or c in ("0.00", "0")


def ctx_size(m):
    cw = m.get("contextWindow")
    if isinstance(cw, dict):
        sl = cw.get("supportedLengths") or [cw.get("defaultLength") or 0]
        return max([x for x in sl if isinstance(x, int)] or [0])
    if isinstance(cw, int):
        return cw
    return m.get("maxInputTokens") or 0


def rank(m):
    """能力优先排序：工具调用 > 多模态 > 输出长度 > 上下文长度"""
    return (
        1 if m.get("supportsToolCall") else 0,
        1 if m.get("supportsImages") else 0,
        m.get("maxOutputTokens") or 0,
        ctx_size(m),
    )


def state_path(ws):
    return os.path.join(ws or os.getcwd(), STATE_NAME)


def load_state(ws):
    p = state_path(ws)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict):
                s.setdefault("exhausted", {})
                s.setdefault("history", [])
                return s
        except Exception:
            pass
    return {"exhausted": {}, "history": [], "current": None}


def save_state(ws, s):
    with open(state_path(ws), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def exhausted_ids(s):
    """返回仍处于冷却期的模型 id 集合（过冷却期自动释放）"""
    out = {}
    now = time.time()
    for mid, info in list(s.get("exhausted", {}).items()):
        try:
            at = datetime.fromisoformat(info.get("at", "")).timestamp()
        except Exception:
            continue
        cd = info.get("cooldown", DEFAULT_COOLDOWN)
        left = at + cd - now
        if left > 0:
            out[mid] = int(left)
    return out


def main():
    ap = argparse.ArgumentParser(description="免费模型挑选与限流降级")
    ap.add_argument("cmd", choices=["list", "pick", "exhausted", "reset", "current"])
    ap.add_argument("model", nargs="?", help="模型 id（exhausted/reset/current 用）")
    ap.add_argument("--reason", default="", help="限流原因摘要")
    ap.add_argument("--cooldown", type=int, default=DEFAULT_COOLDOWN, help="冷却秒数，默认 7200")
    ap.add_argument("--workspace", default=None, help="工作区根目录（状态文件位置）")
    args = ap.parse_args()

    ws = args.workspace
    cfg_path, models = load_config()

    if args.cmd == "exhausted":
        if not args.model:
            print("ERROR: exhausted 需要 <model id>", file=sys.stderr)
            return 1
        s = load_state(ws)
        s["exhausted"][args.model] = {
            "at": now_iso(),
            "reason": args.reason or "rate limit / quota exceeded",
            "cooldown": args.cooldown,
        }
        s.setdefault("history", []).append(
            {"at": now_iso(), "event": "exhausted", "model": args.model, "reason": args.reason}
        )
        save_state(ws, s)
        print("OK 已标记限流: %s（冷却 %ds）" % (args.model, args.cooldown))
        return 0

    if args.cmd == "reset":
        s = load_state(ws)
        if args.model:
            s.get("exhausted", {}).pop(args.model, None)
            print("OK 已释放: %s" % args.model)
        else:
            s["exhausted"] = {}
            print("OK 已释放全部模型")
        save_state(ws, s)
        return 0

    if args.cmd == "current":
        if not args.model:
            print("ERROR: current 需要 <model id>", file=sys.stderr)
            return 1
        s = load_state(ws)
        s["current"] = args.model
        save_state(ws, s)
        print("OK 当前模型: %s" % args.model)
        return 0

    # list / pick 需要读模型目录
    if not cfg_path:
        print("ERROR: 未找到产品配置文件，无法判定免费模型清单", file=sys.stderr)
        print("       可用 ONE_HUNDRED_MILLION_MODEL_CONFIG 指定路径", file=sys.stderr)
        return 3

    free = [m for m in models if is_free(m)]
    free.sort(key=rank, reverse=True)
    s = load_state(ws)
    ex = exhausted_ids(s)

    if args.cmd == "list":
        print("配置来源: %s" % cfg_path)
        print("免费模型（credits=x0.00）共 %d 个：" % len(free))
        for m in free:
            left = ex.get(m["id"])
            flag = "  [冷却中 剩%ds]" % left if left else "  [可用]"
            print(
                "  - %-14s %-14s ctx=%-8s out=%-6s img=%s tool=%s%s"
                % (
                    m["id"],
                    m.get("name", ""),
                    ctx_size(m),
                    m.get("maxOutputTokens"),
                    "Y" if m.get("supportsImages") else "N",
                    "Y" if m.get("supportsToolCall") else "N",
                    flag,
                )
            )
        if not free:
            print("  （无）")
        print("\n当前模型: %s" % (s.get("current") or "(未记录)"))
        if ex:
            print("冷却中: %s" % ", ".join("%s(剩%ds)" % (k, v) for k, v in ex.items()))
        print("\n回退建议: 免费模型全部耗尽时用 Auto / 均衡档（计费）继续，不阻塞生产。")
        return 0 if free else 2

    # pick
    avail = [m for m in free if m["id"] not in ex]
    if avail:
        print(avail[0]["id"])
        return 0
    if free:
        print("FALLBACK: 免费模型全部处于冷却期 -> 回退 Auto（计费）", file=sys.stderr)
        print("AUTO")
        return 2
    print("FALLBACK: 产品配置中无 credits=x0.00 的模型 -> 回退 Auto（计费）", file=sys.stderr)
    print("AUTO")
    return 2


if __name__ == "__main__":
    sys.exit(main())
