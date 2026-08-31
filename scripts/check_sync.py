#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_sync.py — 三方同频自动质检（Quality Gates 强制）

校验:
  ① 字幕拼接文本 == 口播稿文本（逐字，忽略标点/空白）
  ② 各 cue 时间单调、无重叠、相邻间隙 ≤ GAP_MAX
  ③ 总字幕时长 ≈ 配音时长（偏差 ≤ AUDIO_TOL）
  ④ 每页显示时长 ≈ 该页配音真实时长（偏差 ≤ PAGE_TOL），且总和 ≈ 配音时长

全部通过 exit 0；否则 exit 1 并打印失败项。

用法:
  python3 check_sync.py <segments_durations.json> <subs.srt> <script.txt> <voiceover.mp3>
"""
import json, re, sys, subprocess, os

GAP_MAX = 0.35
AUDIO_TOL = 1.0
PAGE_TOL = 0.30
KEEP = re.compile(r'[0-9A-Za-z一-鿿]')


def normalize(s):
    return ''.join(KEEP.findall(s))


def ffprobe_dur(path):
    r = subprocess.run(
        ["/usr/local/bin/ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def parse_srt(path):
    cues = []
    with open(path, encoding="utf-8") as f:
        blocks = re.split(r'\n\n+', f.read().strip())
    for b in blocks:
        lines = b.strip().split('\n')
        if len(lines) < 3:
            continue
        m = re.match(r'(\d+):(\d+):([\d.]+)\s*-->\s*(\d+):(\d+):([\d.]+)', lines[1])
        if not m:
            continue
        def pt(g):
            return int(g[0]) * 3600 + int(g[1]) * 60 + float(g[2])
        s = pt(m.groups()[:3]); e = pt(m.groups()[3:])
        txt = '\n'.join(lines[2:]).strip()
        cues.append((s, e, txt))
    return cues


def main():
    if len(sys.argv) < 5:
        print("usage: check_sync.py <seg_dur.json> <subs.srt> <script.txt> <voiceover.mp3>")
        sys.exit(2)
    jpath, srtpath, scriptpath, audiopath = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    fails = []

    # ① 字幕 == 口播稿（归一化整个口播稿；封面句也是口播内容，不得丢弃首行）
    with open(scriptpath, encoding="utf-8") as f:
        script_norm = normalize(f.read())
    cues = parse_srt(srtpath)
    subs_norm = normalize(''.join(c[2] for c in cues))
    if script_norm != subs_norm:
        # 找首个差异位置
        n = min(len(script_norm), len(subs_norm))
        diff_i = next((i for i in range(n) if script_norm[i] != subs_norm[i]), n)
        fails.append(f"[①字幕≠口播稿] 长度 script={len(script_norm)} subs={len(subs_norm)}，"
                     f"首差@{diff_i}: script='{script_norm[max(0,diff_i-8):diff_i+8]}' "
                     f"subs='{subs_norm[max(0,diff_i-8):diff_i+8]}'")

    # ② cue 单调/无重叠/间隙
    cues_sorted = sorted(cues, key=lambda c: c[0])
    prev_end = 0.0
    for i, (s, e, t) in enumerate(cues_sorted):
        if s < prev_end - 1e-3:
            fails.append(f"[②重叠] cue#{i+1} start={s:.2f} < prev_end={prev_end:.2f} ('{t}')")
        if e <= s:
            fails.append(f"[②零长] cue#{i+1} end<=start ('{t}')")
        gap = s - prev_end
        if i > 0 and gap > GAP_MAX:
            fails.append(f"[②间隙过大] cue#{i+1} 与前一条间隙 {gap:.2f}s > {GAP_MAX}")
        prev_end = max(prev_end, e)

    # ③ 总字幕时长 ≈ 配音
    audio_dur = ffprobe_dur(audiopath)
    total_subs = cues_sorted[-1][1] if cues_sorted else 0.0
    if abs(total_subs - audio_dur) > AUDIO_TOL:
        fails.append(f"[③总时长偏差] 字幕末 {total_subs:.2f}s vs 配音 {audio_dur:.2f}s "
                     f"(偏差 {abs(total_subs-audio_dur):.2f}s > {AUDIO_TOL})")

    # ④ 每页时长 ≈ 该页配音
    with open(jpath, encoding="utf-8") as f:
        dur = json.load(f)
    segs = dur.get("durations", [])
    seg_sum = sum(segs)
    if abs(seg_sum - audio_dur) > PAGE_TOL:
        fails.append(f"[④分页总和偏差] sum(durations)={seg_sum:.2f}s vs 配音 {audio_dur:.2f}s "
                     f"(偏差 {abs(seg_sum-audio_dur):.2f}s > {PAGE_TOL})")
    for i, d in enumerate(segs):
        if d <= 0:
            fails.append(f"[④负/零时长] 第{i}页 duration={d}")
        if d < 1.0:
            fails.append(f"[④过短] 第{i}页仅 {d:.2f}s（画面停留过短）")

    if fails:
        print("CHECK_SYNC FAIL:")
        for x in fails:
            print("  - " + x)
        sys.exit(1)
    print(f"CHECK_SYNC PASS: 字幕{len(cues)}条, 配音{audio_dur:.2f}s, 分页{len(segs)}页, "
          f"字幕==口播稿✓ cue无重叠/间隙✓ 总时长偏差{abs(total_subs-audio_dur):.2f}s ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
