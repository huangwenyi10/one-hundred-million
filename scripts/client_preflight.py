#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""client_preflight.py —— 跨客户端开工自检：能力探测 + 客户端额度登记。

为什么需要它
------------
同一个技能会被 WorkBuddy / Trae / Codex / Qoder / Kimi 等客户端加载，各客户端：
  - **模型额度互相独立**（A 客户端的额度不等于 B 客户端的），A 用完了 B 往往还有；
  - **系统依赖不一样**（ffmpeg / edge-tts / node / Chrome / 无头浏览器 / 中文字体
    可能只装在其中一台机器上），缺依赖时应该报「缺什么、怎么补」，而不是静默失败；
  - **连接器不一样**（百度网盘 / tdrive 只有装了对应 MCP 的客户端能用）。

所以任何客户端开工前先跑一次 preflight：把「我能不能干这一步」变成确定性事实，
而不是靠试错。探测结果登记进工作区共享文件，于是换客户端时下一台机器立刻
知道上一台的能力边界与额度状态。

子命令
------
  probe     探测本机能力（python/ffmpeg/ffprobe/edge-tts/node/Chrome/字体/PIL），
            输出人读报告 + 建议；--json 机读
  register  把本客户端登记进工作区共享注册表（名称 + 平台 + 额度状态）
  clients   列出所有已登记客户端及其额度状态（换客户端时先看这个）
  quota     只更新本客户端额度状态：quota <客户端名> <ok|exhausted> [--reason ...]
  check     门禁模式：探测 + 校验，若「核心流水线依赖」缺失则 exit 1（否则 0）

退出码
------
  0 = 核心依赖齐全，可开工
  1 = 缺核心依赖（ffmpeg / ffprobe / Python），无法出片
  3 = 非 WorkBuddy 客户端读不到产品模型配置（正常，按 Auto 继续，不阻塞）

仅依赖 Python 标准库。不硬编码任何客户端私有 API——探测全部走通用可执行文件与
通用路径，因此换到别的客户端/别的机器照样能跑。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
REGISTRY_NAME = "one-hundred-million-clients.json"

# 核心依赖：缺任何一个都出不了片
CORE = ["python3", "ffmpeg", "ffprobe"]
# 配音与字幕依赖
PIPELINE = ["edge-tts", "ffmpeg"]
# 可选增强：缺了要降级但能出片
OPTIONAL = ["node", "chrome", "playwright"]

# 字体候选（macOS 优先，其次 Linux 常见路径）
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def reg_path(ws):
    return os.path.join(ws or os.getcwd(), REGISTRY_NAME)


def load_reg(ws):
    p = reg_path(ws)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("clients", {})
                return d
        except Exception:
            pass
    return {"version": 1, "clients": {}}


def save_reg(ws, d):
    d["updatedAt"] = now_iso()
    tmp = reg_path(ws) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, reg_path(ws))


def which(name):
    return shutil.which(name)


def ver(cmd, args=("--version",)):
    try:
        out = subprocess.run([cmd] + list(args), capture_output=True, text=True, timeout=8)
        return (out.stdout or out.stderr).strip().splitlines()[0][:60]
    except Exception:
        return ""


def first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return ""


def detect_platform():
    if sys.platform == "darwin":
        return "macOS"
    if sys.platform.startswith("win"):
        return "Windows"
    return "Linux"


def probe():
    caps = {"platform": detect_platform()}

    for binname in CORE + PIPELINE + OPTIONAL:
        if binname in ("google-chrome", "chrome"):
            p = first_existing(CHROME_CANDIDATES) or (which("google-chrome") or which("chromium") or "")
        else:
            p = which(binname)
        caps[binname] = {"found": bool(p), "path": p or ""}

    # edge-tts 也可能是 python -m 形式
    if not caps.get("edge-tts", {}).get("found"):
        try:
            r = subprocess.run([sys.executable, "-m", "edge_tts", "--version"],
                               capture_output=True, text=True, timeout=10)
            caps["edge-tts"] = {"found": r.returncode == 0, "path": "python -m edge_tts"}
        except Exception:
            pass

    caps["chrome_path"] = first_existing(CHROME_CANDIDATES)
    caps["font_path"] = first_existing(FONT_CANDIDATES)

    try:
        import PIL  # noqa: F401
        caps["PIL"] = {"found": True, "path": getattr(PIL, "__version__", "")}
    except Exception:
        caps["PIL"] = {"found": False, "path": ""}

    # 模型目录（WorkBuddy 系客户端才有；别的客户端读不到属正常）
    cfg = os.path.expanduser("~/.workbuddy/cache/acc-product-config-v3.json")
    caps["model_config"] = {"found": os.path.isfile(cfg), "path": cfg}

    missing_core = [b for b in CORE if not caps[b]["found"]]
    missing_pipe = [b for b in PIPELINE if not caps[b]["found"]]
    caps["missing_core"] = missing_core
    caps["missing_pipeline"] = missing_pipe
    caps["ready"] = not missing_core
    return caps


FIX_HINT = {
    "ffmpeg": "brew install ffmpeg / apt install ffmpeg；缺它出不了片（合成/字幕/水印全靠它）",
    "ffprobe": "随 ffmpeg 一起装；缺它读不了真实时长，时间轴会退化成估算（硬违规）",
    "python3": "装 Python 3.9+；所有技能脚本靠它",
    "edge-tts": "pip install edge-tts；缺它做不了配音与逐字字幕（固定音色 zh-CN-YunxiNeural）",
    "node": "node ≥ 22；缺它只能走静态帧导出，render_animated.js 动画增强不可用",
    "chrome": "装 Chrome；缺它 render_animated.js 不可用（可回退静态帧导出）",
    "playwright": "非必需，仅影响部分无头导出路径",
    "PIL": "pip install pillow；缺它字幕/水印 fast 引擎的 alpha 叠加层做不出来",
}


def cmd_probe(args):
    caps = probe()
    if args.json:
        print(json.dumps(caps, ensure_ascii=False, indent=2))
        return 0 if caps["ready"] else 1

    print("本机能力探测（%s，%s）" % (caps["platform"], now_iso()))
    print("-" * 52)
    print("核心依赖：")
    for b in CORE:
        c = caps[b]
        print("  [%s] %-10s %s" % ("✓" if c["found"] else "✗", b, c["path"] or "未安装"))
    print("流水线依赖：")
    for b in PIPELINE:
        c = caps[b]
        print("  [%s] %-10s %s" % ("✓" if c["found"] else "✗", b, c["path"] or "未安装"))
    print("可选增强（缺则降级，仍能出片）：")
    for b in OPTIONAL:
        c = caps.get(b, {"found": False, "path": ""})
        print("  [%s] %-14s %s" % ("✓" if c["found"] else "✗", b, c["path"] or "未安装"))
    print("其它：")
    print("  [%s] Chrome 可执行  %s" % ("✓" if caps["chrome_path"] else "✗",
                                        caps["chrome_path"] or "未找到（动画增强不可用）"))
    print("  [%s] 中文字体        %s" % ("✓" if caps["font_path"] else "✗",
                                        caps["font_path"] or "未找到（字幕会变方框）"))
    print("  [%s] PIL             %s" % ("✓" if caps["PIL"]["found"] else "✗",
                                        caps["PIL"]["path"] or "未安装"))
    print("  [%s] 模型目录        %s" % ("✓" if caps["model_config"]["found"] else "✗",
                                        caps["model_config"]["path"]))

    print("-" * 52)
    if caps["missing_core"]:
        print("结论：缺核心依赖，无法出片。")
        for b in caps["missing_core"]:
            print("  - %s：%s" % (b, FIX_HINT.get(b, "请安装")))
        print("补齐后再开工；或换一台已装齐的机器/客户端接手（台账在共享工作区，进度不丢）。")
        return 1
    if caps["missing_pipeline"]:
        print("结论：核心依赖齐，但流水线依赖缺失，相关能力降级：")
        for b in caps["missing_pipeline"]:
            print("  - %s：%s" % (b, FIX_HINT.get(b, "请安装")))
    else:
        print("结论：核心 + 流水线依赖齐全，可直接开工。")
    if not caps["model_config"]["found"]:
        print("提示：读不到 WorkBuddy 产品模型配置（非 WorkBuddy 客户端属正常）——"
              "按当前客户端自带模型继续，不要因读不到而停工。")
    if not caps["font_path"]:
        print("警告：未找到中文字体，字幕会渲染成方框，必须先装字体再合成。")
    return 0


def cmd_register(args):
    ws = args.workspace
    d = load_reg(ws)
    caps = probe() if args.probe else {}
    key = args.name.strip().lower()          # 与 pick_free_model.py 同一套键（大小写不敏感）
    # 同一客户端只留一条，保留用户写的展示名
    for k in list(d["clients"]):
        if str(k).lower() == key and k != key:
            d["clients"][key] = d["clients"].pop(k)
    d["clients"][key] = {
        "display": args.name.strip(),
        "platform": args.platform or caps.get("platform", ""),
        "quota": args.quota,
        "reason": args.reason or "",
        "model": args.model or "",
        "ffmpeg": bool(caps.get("ffmpeg", {}).get("found")) if caps else None,
        "edge_tts": bool(caps.get("edge-tts", {}).get("found")) if caps else None,
        "at": now_iso(),
    }
    save_reg(ws, d)
    print("已登记客户端 %s（额度=%s）-> %s" % (args.name.strip(), args.quota, reg_path(ws)))
    return 0


def cmd_clients(args):
    d = load_reg(args.workspace)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    if not d["clients"]:
        print("尚无客户端登记（各客户端 register 后在此汇总）。")
        return 0
    print("已登记客户端（工作区 %s）：" % now_iso())
    for k, v in d["clients"].items():
        flag = "额度用完" if v.get("quota") == "exhausted" else "可用"
        print("  - %-12s 额度=%-9s 平台=%-8s ffmpeg=%s edge-tts=%s %s" % (
            v.get("display") or k, flag, v.get("platform") or "-",
            "Y" if v.get("ffmpeg") else "-" if v.get("ffmpeg") is None else "N",
            "Y" if v.get("edge_tts") else "-" if v.get("edge_tts") is None else "N",
            v.get("reason") or ""))
    return 0


def cmd_quota(args):
    d = load_reg(args.workspace)
    key = args.name.strip().lower()
    if key not in d["clients"]:
        d["clients"][key] = {"display": args.name.strip()}
    c = d["clients"][key]
    c["quota"] = args.status
    c["reason"] = args.reason or ""
    c["at"] = now_iso()
    save_reg(args.workspace, d)
    print("%s 额度标记为 %s" % (args.name.strip(), args.status))
    return 0


def cmd_check(args):
    caps = probe()
    if caps["ready"]:
        return 0
    for b in caps["missing_core"]:
        print("BLOCK 缺核心依赖：%s（%s）" % (b, FIX_HINT.get(b, "")), file=sys.stderr)
    return 1


def main():
    ap = argparse.ArgumentParser(description="跨客户端开工自检与额度登记")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="探测本机能力")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("register", help="登记本客户端")
    p.add_argument("name")
    p.add_argument("--quota", default="ok", choices=["ok", "exhausted"])
    p.add_argument("--reason", default="")
    p.add_argument("--model", default="")
    p.add_argument("--platform", default="")
    p.add_argument("--workspace", default=None)
    p.add_argument("--probe", action="store_true", help="同时记录 ffmpeg/edge-tts 能力")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("clients", help="列出已登记客户端")
    p.add_argument("--workspace", default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_clients)

    p = sub.add_parser("quota", help="更新某客户端额度状态")
    p.add_argument("name")
    p.add_argument("status", choices=["ok", "exhausted"])
    p.add_argument("--reason", default="")
    p.add_argument("--workspace", default=None)
    p.set_defaults(func=cmd_quota)

    p = sub.add_parser("check", help="门禁模式：缺核心依赖 exit 1")
    p.add_argument("--workspace", default=None)
    p.set_defaults(func=cmd_check)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
