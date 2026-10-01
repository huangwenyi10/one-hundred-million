#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输出目录名生成器 / 解析器（固定规范第 12 条配套 · 2026-10-01 起）

命名格式：`<视频标题>_<YYYYMMDD>-<NN>`
  - YYYYMMDD = **生成时刻**的日期（首次建文件夹时定死，后续不改）
  - NN       = **当天序号**，两位补零，**跨天重置**（当天第 1 个 = 01）
  - 标题段   = 打磨后的发布标题（≤20 字），不含时间戳

用法：
  # 生成下一个目录名（只打印，不落盘；默认扫当前工作区、取今天）
  python3 next_output_dir.py --workspace <工作区> --title "Doris读写分离：成本直降90%的秘密"

  # 指定日期（补录/回补场景）
  python3 next_output_dir.py --workspace <工作区> --title "..." --date 2026-10-01

  # 解析一个既有目录名 -> JSON（标题/日期/序号），供其他脚本复用
  python3 next_output_dir.py --parse "Doris读写分离：成本直降90%的秘密_20261001-01"

  # 扫描工作区当天已用序号
  python3 next_output_dir.py --workspace <工作区> --list --date 2026-10-01

本脚本为纯计算，不创建/修改/删除任何文件。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys

# 后缀：_YYYYMMDD-NN（NN 允许 2 位以上，容错 100+ 的极端情况）
SUFFIX_RE = re.compile(r"^(?P<title>.+?)_(?P<date>\d{8})-(?P<seq>\d{2,})$")


def parse_name(name: str) -> dict | None:
    """解析 `<标题>_<YYYYMMDD>-<NN>`；不匹配返回 None。"""
    m = SUFFIX_RE.match(name.strip())
    if not m:
        return None
    d = m.group("date")
    try:
        _dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    except ValueError:
        return None
    return {
        "title": m.group("title"),
        "date": d,
        "date_iso": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
        "seq": int(m.group("seq")),
        "seq_str": m.group("seq").zfill(2),
    }


def strip_suffix(name: str) -> str:
    """去掉时间戳后缀，返回纯标题（无后缀则原样返回）。"""
    p = parse_name(name)
    return p["title"] if p else name


def used_seqs(workspace: str, date_str: str) -> dict:
    """返回 {标题: [已用序号...]}，仅统计顶层目录中匹配该日期的项。"""
    out: dict[str, list[int]] = {}
    if not os.path.isdir(workspace):
        return out
    for e in sorted(os.listdir(workspace)):
        if not os.path.isdir(os.path.join(workspace, e)):
            continue
        p = parse_name(e)
        if p and p["date"] == date_str:
            out.setdefault(p["title"], []).append(p["seq"])
    return out


def next_name(workspace: str, title: str, date_str: str | None = None) -> dict:
    """计算下一个目录名。

    序号口径 = **当天全局序号**（同一天内所有视频共用一个递增序列，跨天重置）。
    若标题本身当天已存在，也一律取当天全局下一个号（不按标题各自计数），
    避免出现两个目录序号相同、看不出先后。
    """
    if date_str is None:
        date_str = _dt.date.today().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", date_str):
        raise SystemExit(f"日期格式应为 YYYYMMDD，收到：{date_str}")

    used = used_seqs(workspace, date_str)
    all_seqs = [s for seqs in used.values() for s in seqs]
    nxt = (max(all_seqs) + 1) if all_seqs else 1
    if nxt > 99:
        # 单日超 99 条属异常，仍给出 3 位号并提示
        sys.stderr.write(f"⚠️  当天序号已超过 99（下一个 = {nxt}），请确认是否异常\n")

    return {
        "dir_name": f"{title}_{date_str}-{nxt:02d}",
        "title": title,
        "date": date_str,
        "date_iso": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
        "seq": nxt,
        "seq_str": f"{nxt:02d}",
        "same_day_existing": used,
        "title_used_seqs": used.get(title, []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="输出目录名生成器（<标题>_<YYYYMMDD>-<NN>）")
    ap.add_argument("--workspace", default=".", help="工作区路径（默认当前目录）")
    ap.add_argument("--title", help="视频标题（打磨后的发布标题，不含时间戳）")
    ap.add_argument("--date", help="日期 YYYYMMDD 或 YYYY-MM-DD（默认今天）")
    ap.add_argument("--parse", help="解析既有目录名并输出 JSON")
    ap.add_argument("--strip", help="去掉时间戳后缀、输出去纯标题")
    ap.add_argument("--list", action="store_true", help="列出该日期已用序号")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = ap.parse_args()

    if args.parse:
        p = parse_name(args.parse)
        if not p:
            sys.stderr.write(f"不匹配 `<标题>_<YYYYMMDD>-<NN>`：{args.parse}\n")
            return 1
        print(json.dumps(p, ensure_ascii=False, indent=2) if args.json
              else f"标题={p['title']}｜日期={p['date_iso']}｜序号={p['seq_str']}")
        return 0

    if args.strip:
        print(strip_suffix(args.strip))
        return 0

    date_str = None
    if args.date:
        date_str = args.date.replace("-", "")
        if not re.fullmatch(r"\d{8}", date_str):
            sys.stderr.write(f"日期格式应为 YYYYMMDD 或 YYYY-MM-DD，收到：{args.date}\n")
            return 1

    if args.list:
        d = date_str or _dt.date.today().strftime("%Y%m%d")
        used = used_seqs(args.workspace, d)
        if args.json:
            print(json.dumps({"date": d, "used": used}, ensure_ascii=False, indent=2))
        else:
            total = sum(len(v) for v in used.values())
            print(f"{d} 已用序号 {total} 个：")
            for t, seqs in sorted(used.items()):
                print(f"  {t}  ->  {', '.join(f'{s:02d}' for s in sorted(seqs))}")
        return 0

    if not args.title:
        sys.stderr.write("需要 --title（或使用 --parse / --strip / --list）\n")
        return 2

    info = next_name(args.workspace, args.title, date_str)
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(info["dir_name"])
        sys.stderr.write(
            f"  标题={info['title']}｜日期={info['date_iso']}｜当天序号={info['seq_str']}"
            f"（当天已存在 {sum(len(v) for v in info['same_day_existing'].values())} 个）\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
