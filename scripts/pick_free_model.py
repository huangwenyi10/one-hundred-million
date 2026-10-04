#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pick_free_model.py —— 模型限流降级：免费优先 + 自动切换（Step -1 / 限流触发时调用）

背景
----
技能硬规则：内容生成优先用**免费模型**；免费模型额度耗尽时**不暂停**，直接回退
**默认模型（Auto）**继续跑，目标：自动化任务永不因额度暂停。
当某个模型「使用量超出频率限制 / credit 额度用完」时，不询问、不停止，自动切到
下一个未耗尽的免费模型继续跑；免费全耗尽则直接回退默认模型 Auto。

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
  {"exhausted": {"<client>": {"<model-id>": {"at": ISO, "reason": "...", "cooldown": 7200}}},
   "current": "<model-id>", "current_client": "<client>",
   "history": [{"at": ISO, "from": "", "to": "", "reason": ""}]}

跨客户端（2026-10-04 起）
------------------------
限流标记**按客户端命名空间隔离**：`exhausted[client][model]`。
原因——WorkBuddy 的 `hy3` 用完了，不代表 Trae / Codex / Qoder / Kimi 里的同名模型
也用完；额度是各客户端账号独立的。因此：
  * `pick` 只跳过**当前客户端**已耗尽的模型，不会被别的客户端的限流记录误伤；
  * 当前客户端全部耗尽时，除回退 Auto 外还会打印「哪些客户端还有额度」，
    提示可以换客户端接着跑（换客户端后进度不丢，见 scripts/jobctl.py resume）；
  * 客户端注册表 `one-hundred-million-clients.json`（由 client_preflight.py 维护）
    记录各客户端名称与额度状态，本脚本 `clients` 子命令只读展示。

子命令
------
  list                       列出全部免费模型 + 当前耗尽状态（人读）
  pick                       输出下一个可用的免费模型 id（机读，stdout 只有 id）
  exhausted <id> [--reason S] [--cooldown N]   记录该模型已限流，冷却 N 秒（默认 7200）
  reset [--id X]             清除耗尽标记（全部或指定模型）
  current <id>               记录当前正在使用的模型
  clients                    列出各客户端额度状态（跨客户端续跑用）
  register [ok|exhausted] [--reason S]  把当前客户端登记进共享注册表

通用选项：--client <name>（默认取环境变量 OHM_CLIENT，缺省 "workbuddy"）
          --workspace <工作区根目录>

退出码
------
  0 = 找到可用免费模型
  2 = 免费模型全部处于冷却/耗尽 → stdout 输出 AUTO（默认模型）；不切计费模型
  3 = 读不到任何产品配置（无法判定），按默认模型 Auto 继续、标注待人工核对
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

STATE_NAME = "one-hundred-million-model-fallback.json"
CLIENTS_NAME = "one-hundred-million-clients.json"
DEFAULT_COOLDOWN = 7200  # 2 小时，与定时任务 2h 一轮的节奏对齐
DEFAULT_CLIENT = "workbuddy"

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


def credits_val(m):
    """解析 credits 为数值：>0 计费、==0 免费、None 不可判定。"""
    c = m.get("credits")
    if not isinstance(c, str):
        return None
    c = c.strip().lower().replace("credits", "").strip()
    c = c.lstrip("x").strip()
    try:
        return float(c)
    except ValueError:
        return None


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


def paid_models(models):
    """计费模型列表（credits>0），按价格升序、同价能力降序。"""
    paid = [m for m in models if credits_val(m) is not None and credits_val(m) > 0]
    paid.sort(key=lambda m: (credits_val(m), tuple(-x for x in rank(m))))
    return paid


def state_path(ws):
    return os.path.join(ws or os.getcwd(), STATE_NAME)


def clients_path(ws):
    return os.path.join(ws or os.getcwd(), CLIENTS_NAME)


def current_client(explicit=None):
    """当前客户端名：显式参数 > 环境变量 OHM_CLIENT > 默认 workbuddy。

    统一小写归一化——「WorkBuddy」与「workbuddy」必须命中同一份冷却记录，
    否则手工传参与默认值会各记一份，冷却失效。
    """
    raw = (explicit or os.environ.get("OHM_CLIENT") or DEFAULT_CLIENT).strip()
    return (raw or DEFAULT_CLIENT).lower()


def _looks_like_client_map(d):
    """兼容旧结构：旧 exhausted 是 {model-id: {...}}，新结构是 {client: {model-id: {...}}}。"""
    for v in d.values():
        if isinstance(v, dict) and ("at" in v or "cooldown" in v):
            return False
    return True


def load_state(ws):
    p = state_path(ws)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict):
                s.setdefault("exhausted", {})
                s.setdefault("history", [])
                # 迁移旧结构到按客户端命名空间
                if s["exhausted"] and not _looks_like_client_map(s["exhausted"]):
                    legacy = s["exhausted"]
                    s["exhausted"] = {"workbuddy": legacy}
                    s.setdefault("migrated_at", now_iso())
                return s
        except Exception:
            pass
    return {"exhausted": {}, "history": [], "current": None}


def save_state(ws, s):
    with open(state_path(ws), "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def client_bucket(exhausted, client):
    """取某客户端的限流桶，键大小写不敏感（历史文件里可能存了 `WorkBuddy`）。"""
    for k, v in (exhausted or {}).items():
        if str(k).lower() == str(client).lower() and isinstance(v, dict):
            return v
    return {}


def exhausted_ids(s, client):
    """返回该客户端仍处于冷却期的模型 id 集合（过冷却期自动释放）。

    按客户端隔离：别的客户端的限流记录不影响本客户端 pick。
    """
    out = {}
    bucket = client_bucket(s.get("exhausted"), client)
    now = time.time()
    for mid, info in list(bucket.items()):
        try:
            at = datetime.fromisoformat(info.get("at", "")).timestamp()
        except Exception:
            continue
        cd = info.get("cooldown", DEFAULT_COOLDOWN)
        left = at + cd - now
        if left > 0:
            out[mid] = int(left)
    return out


def other_clients_with_quota(s, ws, me):
    """从共享注册表里找出「额度还好、且不是本客户端」的候选，用于换客户端提示。"""
    out = []
    p = clients_path(ws)
    if not os.path.isfile(p):
        return out
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return out
    for name, info in (d.get("clients") or {}).items():
        if str(name).lower() == str(me).lower():
            continue
        if info.get("quota") != "exhausted":
            out.append(info.get("display") or name)
    return out


def cmd_clients(ws, me):
    """列出各客户端额度状态（跨客户端续跑用）。"""
    p = clients_path(ws)
    if not os.path.isfile(p):
        print("尚无客户端注册表（各客户端跑 client_preflight.py register 后在此汇总）：%s" % p)
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        print("注册表读取失败：%s" % p, file=sys.stderr)
        return 1
    clients = d.get("clients") or {}
    if not clients:
        print("注册表为空：%s" % p)
        return 0
    print("客户端额度状态（更新时间 %s）：" % d.get("updatedAt", "-"))
    for name, info in clients.items():
        flag = "额度用完" if info.get("quota") == "exhausted" else "可用"
        mark = " ← 当前客户端" if str(name).lower() == str(me).lower() else ""
        print("  - %-12s %-9s %s%s" % (
            info.get("display") or name, flag, info.get("reason") or "", mark))
    others = other_clients_with_quota(None, ws, me)
    if others:
        print("\n可换客户端继续：%s（额度独立，换过去即可接着跑，"
              "进度用 jobctl.py resume 读取，不丢）" % "、".join(others))
    return 0


def cmd_register(ws, me, status, reason, display=None):
    p = clients_path(ws)
    d = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("version", 1)
    d.setdefault("clients", {})
    # 同一客户端只留一条（大小写不敏感去重）
    for k in list(d["clients"]):
        if str(k).lower() == me and k != me:
            d["clients"][me] = d["clients"].pop(k)
    prev = d["clients"].get(me) or {}
    d["clients"][me] = {
        "quota": status,
        "reason": reason,
        # 未显式给展示名时保留原值（client_preflight 可能已写入 "WorkBuddy" 这类写法）
        "display": display or prev.get("display") or me,
        "at": now_iso(),
    }
    for k, v in prev.items():
        d["clients"][me].setdefault(k, v)   # 保住 platform/ffmpeg/edge_tts 等已登记字段
    d["updatedAt"] = now_iso()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print("OK 已登记客户端 %s 额度=%s -> %s" % (display or me, status, p))
    return 0


def main():
    ap = argparse.ArgumentParser(description="免费模型挑选与限流降级（按客户端隔离额度）")
    ap.add_argument("cmd", choices=["list", "pick", "exhausted", "reset", "current",
                                    "clients", "register"])
    ap.add_argument("model", nargs="?", help="模型 id（exhausted/reset/current 用）")
    ap.add_argument("status", nargs="?", choices=["ok", "exhausted"],
                    help="register 用的额度状态")
    ap.add_argument("--reason", default="", help="限流原因摘要")
    ap.add_argument("--cooldown", type=int, default=DEFAULT_COOLDOWN, help="冷却秒数，默认 7200")
    ap.add_argument("--workspace", default=None, help="工作区根目录（状态文件位置）")
    ap.add_argument("--client", default=None,
                    help="客户端名（WorkBuddy/Trae/Codex/Qoder/Kimi...），默认取 OHM_CLIENT")
    ap.add_argument("--display", default="", help="register 时的展示名（默认同 --client）")
    args = ap.parse_args()

    ws = args.workspace
    me = current_client(args.client)

    if args.cmd == "clients":
        return cmd_clients(ws, me)

    if args.cmd == "register":
        # 兼容 `register exhausted`（被第一个位置参数 model 吞掉）的情况
        status = args.status or (args.model if args.model in ("ok", "exhausted") else "ok")
        return cmd_register(ws, me, status, args.reason, args.display)

    cfg_path, models = load_config()

    if args.cmd == "exhausted":
        if not args.model:
            print("ERROR: exhausted 需要 <model id>", file=sys.stderr)
            return 1
        s = load_state(ws)
        s.setdefault("exhausted", {})
        # 归一化客户端键，避免同一客户端因大小写不同记成两份
        old = client_bucket(s["exhausted"], me)
        for k in list(s["exhausted"]):
            if str(k).lower() == me and k != me:
                s["exhausted"][me] = s["exhausted"].pop(k)
        s["exhausted"].setdefault(me, {})[args.model] = {
            "at": now_iso(),
            "reason": args.reason or "rate limit / quota exceeded",
            "cooldown": args.cooldown,
        }
        s.setdefault("history", []).append(
            {"at": now_iso(), "event": "exhausted", "client": me,
             "model": args.model, "reason": args.reason}
        )
        save_state(ws, s)
        print("OK 已标记限流: [%s] %s（冷却 %ds）" % (me, args.model, args.cooldown))
        return 0

    if args.cmd == "reset":
        s = load_state(ws)
        if args.model:
            for k in list(s.get("exhausted") or {}):
                if str(k).lower() == me:
                    s["exhausted"][k].pop(args.model, None)
            print("OK 已释放: [%s] %s" % (me, args.model))
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
        s["current_client"] = me
        save_state(ws, s)
        print("OK 当前模型: [%s] %s" % (me, args.model))
        return 0

    # list / pick 需要读模型目录
    if not cfg_path:
        print("ERROR: 未找到产品配置文件，无法判定免费模型清单", file=sys.stderr)
        print("       非 WorkBuddy 客户端读不到属正常——直接用本客户端自带模型继续，不阻塞。",
              file=sys.stderr)
        print("       可用 ONE_HUNDRED_MILLION_MODEL_CONFIG 指定路径", file=sys.stderr)
        return 3

    free = [m for m in models if is_free(m)]
    free.sort(key=rank, reverse=True)
    s = load_state(ws)
    ex = exhausted_ids(s, me)

    if args.cmd == "list":
        print("配置来源: %s" % cfg_path)
        print("当前客户端: %s" % me)
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
            print("本客户端冷却中: %s" % ", ".join("%s(剩%ds)" % (k, v) for k, v in ex.items()))
        # 跨客户端：别的客户端限流不影响本客户端，但额度用完时可以换客户端接着跑
        all_ex = (s.get("exhausted") or {})
        for cname, bucket in all_ex.items():
            if str(cname).lower() != str(me).lower() and bucket:
                print("（参考）客户端 %s 曾限流: %s —— 与本客户端额度独立，不影响本机 pick"
                      % (cname, ", ".join(bucket.keys())))
        paid = paid_models(models)
        if paid:
            print("\n计费模型（列出仅供了解，本技能免费耗尽后不切计费、直接回退默认模型 Auto）：")
            for m in paid[:5]:
                left = ex.get(m["id"])
                flag = "  [冷却中]" if left else ""
                print("  - %-18s credits=%-6s%s" % (m["id"], m.get("credits"), flag))
        print(
            "\n回退建议: 免费模型全部耗尽时，直接回退默认模型 Auto 继续生产，不切计费模型、不阻塞。"
        )
        return 0 if free else 2

    # pick
    avail = [m for m in free if m["id"] not in ex]
    if avail:
        print(avail[0]["id"])
        return 0
    # 免费模型全耗尽 → 直接回退默认模型（Auto），不切计费模型，目标：不暂停
    print("FALLBACK: [%s] 免费模型耗尽 -> 直接回退默认模型 Auto 继续生产" % me, file=sys.stderr)
    others = other_clients_with_quota(None, ws, me)
    if others:
        print("HINT: 额度按客户端独立，可换客户端接着跑：%s" % "、".join(others), file=sys.stderr)
        print("      换客户端后先跑 scripts/client_preflight.py probe，再跑 "
              "scripts/jobctl.py resume --workspace <工作区> --client <新客户端名>",
              file=sys.stderr)
    else:
        print("      若要换客户端续跑：scripts/jobctl.py resume --workspace <工作区> "
              "--client <新客户端名>（进度在磁盘，换客户端不丢）", file=sys.stderr)
    print("AUTO")
    return 2


if __name__ == "__main__":
    sys.exit(main())
