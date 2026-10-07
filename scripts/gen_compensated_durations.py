#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_compensated_durations.py — 生成「xfade 补偿后」的时长文件

## 为什么需要（实测踩坑，本项目最隐蔽的一个坑）

`compose_motion.py` 用 **xfade 交叉淡入**串接各段，视频总长会被压缩：

    body总长 = Σd_i − (段数−1) × xfade

而配音音频总长 = Σd_i（各段 seg_*.mp3 与时间轴逐段**完全相等**）。
两者天生不等长 —— 上篇差 24.5s、中篇 26.4s、下篇 22.5s。

直接把完整音频灌进 body 会出现两种后果，**都实测踩过**：
1. 不处理 → 音轨比视频长 22~26 秒，片尾黑屏/静帧；
2. 按「每段裁尾 0.5s」把音频裁到与视频等长 → **每段末尾 0.5~1.0s 语音被削掉**
   （上篇实测尾部静音 38 秒、末句口播缺失）。这是更糟的错误，因为它无声无息。

## 正解：让视频侧自己补回来

给每段时长补 `c`，使 body 总长恰好等于音频总长：

    Σ(d_i + c) − (n−1)×xfade = Σd_i
    ⇒ n·c = (n−1)×xfade
    ⇒ c = (n−1)×xfade / n

补的是「段与段之间的 0.5s 交叉淡化时间」——那段时间画面本来是重叠的，
多出来的时长落在这段画面静止的尾部（compose_motion 的运动在 80% 时长内完成、
尾 20% 静止），**不会动到该段的口播内容**。音频保持原样，一字不裁。

验证（三部实测）：补完后 body 总长与音频总长差0.000s。
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--xfade", type=float, default=0.5)
    ap.add_argument("--out", help="默认写<build>/durations_compensated.json")
    ap.add_argument("--in", dest="src",
                    default="segments_durations.json")
    a = ap.parse_args()

    src = os.path.join(a.build, a.src)
    d = json.load(open(src, encoding="utf-8"))
    durs = d["durations"] if isinstance(d, dict) else list(d)
    n = len(durs)
    if n < 2:
        print("ERROR: 段数 < 2，无需补偿", file=sys.stderr)
        return 1

    c = (n - 1) * a.xfade / n
    new = [round(x + c, 3) for x in durs]

    body_total = sum(new) - (n - 1) * a.xfade
    audio_total = sum(durs)
    out = a.out or os.path.join(a.build, "durations_compensated.json")
    payload = {
        "durations": new,
        "total": round(body_total, 3),
        "xfade": a.xfade,
        "compensationPerPage": round(c, 4),
        "sourceTotal": round(audio_total, 3),
        "note": ("compose_motion 会再扣 (n-1)×xfade，故补 c=(n-1)×xfade/n 后"
                 "body 总长恰等于音频总长；音频无需任何裁剪"),
    }
    if isinstance(d, dict) and d.get("starts"):
        st, acc = [], 0.0
        for x in new:
            st.append(round(acc, 3))
            acc += x
        payload["starts"] = st
        payload["ends"] = [round(st[i] + new[i], 3) for i in range(n)]

    json.dump(payload, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"段数 {n} · 每段补 {c:.4f}s")
    print(f"补偿后 body 总长 {body_total:.2f}s")
    print(f"音频总长       {audio_total:.2f}s")
    print(f"差{body_total - audio_total:+.3f}s")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())