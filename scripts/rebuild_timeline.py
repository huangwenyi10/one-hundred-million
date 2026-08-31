#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 whisper 词级时间戳重建字幕时间轴（拆片级精确对齐）。

旧方案缺陷：长 cue 内部拆片按"字符宽度比例"线性分配时间，
与配音真实发音时刻错位 -> 字幕切换点和声音对不上。

本方案：对每个拆片文本在 whisper 词流中对齐，得到该片文字
真实发音的起止时刻，字幕切换严格跟随声音。

用法：
    python rebuild_timeline.py <subs_clean.vtt> <whisper_words.json> <out.vtt> [max_w]

依赖：faster-whisper 输出词级 JSON（word_timestamps=True）, e.g.
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(audio, language="zh", word_timestamps=True, vad_filter=True)
    words = [{"w": w.word.strip(), "s": w.start, "e": w.end} for seg in segments for w in seg.words]
"""
import json, re, io, sys
from difflib import SequenceMatcher

if len(sys.argv) < 4:
    print("Usage: python rebuild_timeline.py <subs_clean.vtt> <whisper_words.json> <out.vtt> [max_w]")
    sys.exit(1)

VTT = sys.argv[1]
WHISPER = sys.argv[2]
OUT = sys.argv[3]
MAX_W = float(sys.argv[4]) if len(sys.argv) > 4 else 15.0

def parse_time(t):
    h, m, s = t.split(":")
    s, ms = s.split(",")
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def load_vtt(path):
    cues = []
    with io.open(path, encoding="utf-8") as f:
        lines = [ln.rstrip() for ln in f]
    i = 0
    while i < len(lines):
        if "-->" not in lines[i]:
            i += 1
            continue
        start, end = [t.strip() for t in lines[i].split("-->")]
        text_lines = []
        i += 1
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i].strip())
            i += 1
        cues.append({"start": parse_time(start), "end": parse_time(end),
                     "text": " ".join(text_lines)})
    return cues

def char_width(text):
    return sum(1.0 if ord(ch) > 255 else 0.5 for ch in text)

def split_cue_text(text, max_w=MAX_W):
    """按标点停顿拆片（保持拼接=原文本）。"""
    break_chars = "，；、：,.;: "
    parts = []
    buf = ""
    for ch in text:
        buf += ch
        if char_width(buf) >= max_w and ch in break_chars:
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    final = []
    for p in parts:
        while p:
            if char_width(p) <= max_w:
                final.append(p)
                break
            cut = 0
            acc = 0.0
            for i, c in enumerate(p):
                acc += 1.0 if ord(c) > 255 else 0.5
                if acc > max_w:
                    cut = i
                    break
            if cut == 0:
                cut = int(max_w)
            final.append(p[:cut])
            p = p[cut:]
    return final

def norm(s):
    return re.sub(r"[\s，。、；：,.!?！？\"'“”‘’（）()《》<>「」\-—…·]", "", s).lower()

# ---------- whisper 词级 ----------
words = json.load(io.open(WHISPER, encoding="utf-8"))["words"]
wn_chars = []
wn_char2word = []
for wi, w in enumerate(words):
    for ch in norm(w["w"]):
        wn_chars.append(ch)
        wn_char2word.append(wi)
w_norm = "".join(wn_chars)

# ---------- VTT 归一化全文 ----------
cues = load_vtt(VTT)
v_norm = ""
cue_offsets = []
for ci, c in enumerate(cues):
    cue_offsets.append(len(v_norm))
    for ch in norm(c["text"]):
        v_norm += ch

# ---------- 全局顺序对齐 ----------
sm = SequenceMatcher(None, v_norm, w_norm, autojunk=False)
blocks = [b for b in sm.get_matching_blocks() if b.size > 0]

def map_pos(p):
    for (i, j, n) in blocks:
        if i <= p < i + n:
            return j + (p - i)
    prev = next_ = None
    for (i, j, n) in blocks:
        if i + n <= p:
            prev = (i, j, n)
        elif i > p:
            next_ = (i, j, n)
            break
    if prev and next_:
        (pi, pj, pn), (ni, nj, nn) = prev, next_
        gap_v = ni - (pi + pn)
        gap_w = nj - (pj + pn)
        if gap_v > 0:
            return pj + pn + (p - (pi + pn)) / gap_v * gap_w
        return pj + pn
    if prev:
        return prev[1] + prev[2]
    return 0

def time_at_vpos(p, end=False):
    q = int(round(map_pos(p)))
    q = max(0, min(q, len(wn_char2word) - 1))
    wi = wn_char2word[q]
    return words[wi]["e"] if end else words[wi]["s"]

# ---------- 拆片并逐片对齐 ----------
aligned = []
for ci, c in enumerate(cues):
    off = cue_offsets[ci]
    slices = split_cue_text(c["text"])
    pos = off
    for sl in slices:
        txt_norm = norm(sl)
        if not txt_norm:
            continue
        p0 = pos
        p1 = pos + len(txt_norm) - 1
        s = time_at_vpos(p0)
        e = time_at_vpos(p1, end=True)
        if not (e > s):
            e = s + 1.0
        if e - s < 0.4:
            e = min(s + 1.2, e + 1.0)
        aligned.append({"start": s, "end": e, "text": sl})
        pos = p1 + 1

# ---------- 平滑：去重叠、合并小缝隙 ----------
aligned.sort(key=lambda x: x["start"])
MIN_GAP = 0.35
smoothed = []
for a in aligned:
    if smoothed:
        ps = smoothed[-1]
        if a["start"] < ps["end"]:
            ps["end"] = a["start"]
        gap = a["start"] - ps["end"]
        if 0 < gap < MIN_GAP:
            ps["end"] = a["start"]
    smoothed.append(a)

# ---------- 输出 ----------
def fmt(t):
    ms = int(round((t - int(t)) * 1000))
    if ms >= 1000:
        t += 1; ms = 0
    sec = int(t)
    return f"{sec//3600:02d}:{sec%3600//60:02d}:{sec%60:02d},{ms:03d}"

lines = ["WEBVTT", ""]
for i, a in enumerate(smoothed, 1):
    lines.append(str(i))
    lines.append(f"{fmt(a['start'])} --> {fmt(a['end'])}")
    lines.append(a["text"])
    lines.append("")
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"对齐后拆片数: {len(smoothed)} -> {OUT}")
