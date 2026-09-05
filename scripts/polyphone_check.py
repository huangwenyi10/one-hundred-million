#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多音字检查 / 同音字代理（固定规范第 29 条配套）

子命令：
  scan     <口播稿.txt> [--dict D] [--json] [--strict]
           扫稿，列出所有命中多音字（含期望读音、常见误读、建议动作、代理字）
  apply    <口播稿.txt> --out <tts_input.txt> --map <map.json> [--dict D]
           生成「TTS 输入版」：把需代理的字换成同音代理字（字幕仍用原稿）
  restore  --srt <in.srt> --map <map.json> --out <out.srt>
           把 TTS 产生的字幕里的代理字换回原字（保证字幕==口播稿）

设计要点：
- 只按 context 词精确替换，不做整字全局替换（避免把「执行」的「行」也换掉）
- apply 前检测代理字冲突：原稿若已含该代理字，则该条跳过并告警（避免 restore 误伤）
- 依赖：仅标准库。numpy/edge-tts 不需要。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DICT = os.path.join(HERE, "polyphone_dict.json")

SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])|\n+")


def load_dict(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sentences(text):
    parts = [s.strip() for s in SENT_SPLIT.split(text) if s and s.strip()]
    return parts


def scan(text, entries):
    """返回命中列表：[(句序号, 句, 字, 期望, 误读, 命中词, 动作, 代理)]"""
    hits = []
    for i, s in enumerate(sentences(text), 1):
        for e in entries:
            for ctx in e["contexts"]:
                if ctx in s:
                    hits.append({
                        "no": i, "sentence": s, "char": e["char"], "want": e["want"],
                        "wrong": e["wrong"], "ctx": ctx, "action": e.get("action", "check"),
                        "proxy": e.get("proxy"), "note": e.get("note", ""),
                    })
                    break  # 同一 entry 在一句里只报一次
    return hits


def cmd_scan(args):
    d = load_dict(args.dict)
    with open(args.script, "r", encoding="utf-8") as f:
        text = f.read()
    hits = scan(text, d["entries"])
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        print(f"多音字扫稿：{os.path.basename(args.script)}  命中 {len(hits)} 处"
              f"（词典 v{d.get('version','?')} / 音色 {d.get('voice','?')}）")
        print("-" * 96)
        if not hits:
            print("未命中任何已知多音字条目（仍建议对专业术语抽检试听）。")
        for h in hits:
            flag = "【需代理】" if h["action"] == "proxy" and h["proxy"] else "【抽检】  "
            proxy = f"→ 代理『{h['proxy']}』" if h["action"] == "proxy" and h["proxy"] else ""
            print(f"{flag} #{h['no']:>3} 「{h['ctx']}」 {h['char']} 读 {h['want']}"
                  f"（易误读 {h['wrong']}）{proxy}")
            print(f"         句：{h['sentence']}")
            if h["note"]:
                print(f"         注：{h['note']}")
        n_proxy = sum(1 for h in hits if h["action"] == "proxy" and h["proxy"])
        print("-" * 96)
        print(f"需代理 {n_proxy} 处 / 抽检 {len(hits) - n_proxy} 处。"
              f"代理处必须走 apply → TTS → restore 三步，字幕始终用原稿。")
    if args.strict and any(h["action"] == "proxy" and h["proxy"] for h in hits):
        return 1
    return 0


def cmd_apply(args):
    d = load_dict(args.dict)
    with open(args.script, "r", encoding="utf-8") as f:
        text = f.read()

    # 选代理字：优先主代理字，原稿已含则自动切备选（避免 restore 误伤原稿本字）
    mapping, skipped, used = {}, [], set()
    for e in d["entries"]:
        if e.get("action") != "proxy" or not e.get("proxy"):
            continue
        picked = None
        for cand in [e["proxy"]] + list(e.get("proxy_alt") or []):
            if cand not in text and cand not in used:
                picked = cand
                break
        if picked is None:
            skipped.append((e["char"], e["proxy"],
                            "主代理字与备选均与原稿冲突（或已被占用），跳过以免 restore 误伤"))
            continue
        used.add(picked)
        mapping.setdefault(picked, {"char": e["char"], "want": e["want"],
                                    "count": 0, "contexts": [], "orig_proxy": e["proxy"]})

    out = text
    # 长 context 优先，避免短 context 抢先替换
    entries = sorted(
        [e for e in d["entries"] if e.get("action") == "proxy" and e.get("proxy")
         and any(e["proxy"] == v.get("orig_proxy") for v in mapping.values())],
        key=lambda e: -max(len(c) for c in e["contexts"]))
    for e in entries:
        p = next((k for k, v in mapping.items() if v.get("orig_proxy") == e["proxy"]), None)
        if not p:
            continue
        for ctx in sorted(e["contexts"], key=len, reverse=True):
            if ctx in out:
                n = out.count(ctx)
                out = out.replace(ctx, ctx.replace(e["char"], p))
                mapping[p]["count"] += n
                mapping[p]["contexts"].append(ctx)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    with open(args.map, "w", encoding="utf-8") as f:
        json.dump({"voice": d.get("voice"), "version": d.get("version"),
                   "source": os.path.abspath(args.script), "mapping": mapping},
                  f, ensure_ascii=False, indent=2)

    total = sum(v["count"] for v in mapping.values())
    print(f"已生成 TTS 输入版：{args.out}（替换 {total} 处）")
    for p, v in mapping.items():
        if v["count"]:
            print(f"  {v['char']} → {p}（{v['want']}）× {v['count']}：{'/'.join(sorted(set(v['contexts'])))}")
    for c, p, why in skipped:
        print(f"  跳过：{c} → {p}（{why}）")
    print(f"映射文件：{args.map}  —— TTS 出字幕后执行 restore 把代理字换回原字")
    if total == 0:
        print("（本次无需代理，可跳过 apply/restore，直接用原稿跑 TTS）")
    return 0


def cmd_restore(args):
    with open(args.map, "r", encoding="utf-8") as f:
        m = json.load(f)["mapping"]
    with open(args.srt, "r", encoding="utf-8") as f:
        srt = f.read()
    n = 0
    for p, v in m.items():
        if v.get("count"):
            n += srt.count(p)
            srt = srt.replace(p, v["char"])
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(srt)
    print(f"已还原 {n} 处代理字：{args.out}")
    print("下一步：用还原后的 srt 跑 check_sync.py，校验 字幕 == 口播稿")
    return 0


def main():
    ap = argparse.ArgumentParser(description="多音字检查与同音字代理（第 29 条配套）")
    ap.add_argument("--dict", default=DEFAULT_DICT, help="词典路径（默认 scripts/polyphone_dict.json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫稿列出多音字命中")
    s.add_argument("script")
    s.add_argument("--json", action="store_true")
    s.add_argument("--strict", action="store_true", help="有『需代理』命中时 exit 1")
    s.set_defaults(func=cmd_scan)

    a = sub.add_parser("apply", help="生成 TTS 输入版（替换同音代理字）")
    a.add_argument("script")
    a.add_argument("--out", required=True)
    a.add_argument("--map", required=True)
    a.set_defaults(func=cmd_apply)

    r = sub.add_parser("restore", help="把字幕里的代理字换回原字")
    r.add_argument("--srt", required=True)
    r.add_argument("--map", required=True)
    r.add_argument("--out", required=True)
    r.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
