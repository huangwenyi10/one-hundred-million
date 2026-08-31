#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_sync_subs.py — 分段同步字幕与时长生成（Step 3/5 强制）

把口播稿按幻灯片切成 N 段（首行=封面段，其余每行=一页内容），
逐段 edge-tts（SentenceBoundary 真实时间轴）TTS 并拼接为 voiceover.mp3，
同时产出：
  - subtitles.srt        真实时间轴、逐字字幕（句内按字符比例切行，单行）
  - segments_durations.json  {durations:[每页真实秒数], starts:[], ends:[]}
字幕与画面切换时间轴的唯一来源。禁止按字数比例估算全局时间轴。

用法:
  python3 gen_sync_subs.py <segments.txt> <out_dir> <voice> [cover_min_sec]

依赖: edge_tts (pip install edge-tts)，ffmpeg (PATH)
"""
import argparse, asyncio, json, os, subprocess, sys, re

TICK = 1e-7  # edge-tts offset/duration 单位：100 纳秒
MAX_CHARS = 32  # 单行最大中文字符数（render 端仍会按需缩字号兜底）
COVER_MIN = 2.0  # 封面最短显示秒数（不足则补静音，保持画面可读且时间轴一致）


def split_lines(text, max_chars=MAX_CHARS):
    """把一句拆成多个单行显示片段（在标点处断，否则硬断）。返回 [(line_text, char_start, char_end)]。"""
    # 先按句末标点切成子句，再在子句内按 max_chars 硬断
    pieces = re.split(r'(?<=[\，。、；：！？])', text)
    out = []
    buf = ""
    for p in pieces:
        if not p:
            continue
        # 若单子句超长，按 max_chars 硬断
        while len(p) > max_chars:
            out.append(p[:max_chars])
            p = p[max_chars:]
        out.append(p)
    # 合并过碎的尾部
    lines = []
    for ln in out:
        if lines and len(lines[-1]) + len(ln) <= max_chars and not ln.endswith(('。', '！', '？')):
            lines[-1] += ln
        else:
            lines.append(ln)
    # 计算每条在原文中的字符位置（用于按比例映射时间）
    pos_map = []
    idx = 0
    for ln in lines:
        pos_map.append((ln, idx, idx + len(ln)))
        idx += len(ln)
    return pos_map


def strip_tail_period(s):
    s = s.strip()
    if s.endswith('。'):
        s = s[:-1]
    return s


async def tts_segment(text, voice, max_retries=6):
    """返回 (audio_bytes, [(sent_start_sec, sent_end_sec, sent_text)])

    带指数退避重试：edge-tts 在长稿多段连续请求时会抛 NoAudioReceived
    （服务端限流/瞬时故障），不重试会导致整批前功尽弃。
    """
    import edge_tts
    last_err = None
    for attempt in range(1, max_retries + 1):
        audio = bytearray()
        sents = []
        try:
            comm = edge_tts.Communicate(text, voice)
            async for msg in comm.stream():
                if msg["type"] == "audio":
                    audio += msg["data"]
                elif msg["type"] == "SentenceBoundary":
                    start = msg.get("offset", 0) * TICK
                    dur = msg.get("duration", 0) * TICK
                    sents.append((start, start + dur, msg.get("text", "")))
            if audio:
                # 若没有 SentenceBoundary（极短），兜底整段
                if not sents:
                    sents.append((0.0, 0.0, text))  # 时长稍后由 ffprobe 修正
                return bytes(audio), sents
            last_err = RuntimeError("empty audio")
        except Exception as e:
            last_err = e
        if attempt < max_retries:
            wait = min(2 ** attempt, 20)
            print(f"    [retry {attempt}/{max_retries}] "
                  f"{type(last_err).__name__}: {last_err} -> wait {wait}s",
                  flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"TTS 失败（已重试 {max_retries} 次）: {last_err}")


def load_cached(out_dir, i):
    """断点续跑：复用已成功的分段音频 + 句级时间轴，避免整批重跑。"""
    mp3 = os.path.join(out_dir, f"seg_{i:02d}.mp3")
    js = os.path.join(out_dir, f"seg_{i:02d}.json")
    if (os.path.exists(mp3) and os.path.exists(js)
            and os.path.getsize(mp3) > 1024):
        try:
            with open(js, encoding="utf-8") as f:
                sents = [tuple(x) for x in json.load(f)]
            with open(mp3, "rb") as f:
                return f.read(), sents
        except Exception:
            return None, None
    return None, None


def save_cached(out_dir, i, audio, sents):
    with open(os.path.join(out_dir, f"seg_{i:02d}.json"), "w",
              encoding="utf-8") as f:
        json.dump([list(s) for s in sents], f, ensure_ascii=False)


def ffprobe_dur(path):
    r = subprocess.run(
        ["/usr/local/bin/ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def pad_audio(src, dst, min_dur):
    subprocess.run(
        ["/usr/local/bin/ffmpeg", "-y", "-i", src, "-af",
         f"apad=whole_dur={min_dur:.3f}", "-c:a", "copy", dst],
        capture_output=True)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("segments_txt")
    ap.add_argument("out_dir")
    ap.add_argument("voice")
    ap.add_argument("cover_min", nargs="?", type=float, default=COVER_MIN)
    args = ap.parse_args()

    # edge-tts >= 7.x 强制要求带区域前缀的完整 voice 名（如 zh-CN-YunxiNeural）。
    # 兼容用户习惯的缩写：YunxiNeural -> zh-CN-YunxiNeural（技能默认中文男声）。
    if "-" not in args.voice:
        args.voice = "zh-CN-" + args.voice
        print(f"  [voice] 自动补全区域前缀 -> {args.voice}")

    os.makedirs(args.out_dir, exist_ok=True)
    args.out_dir = os.path.abspath(args.out_dir)
    with open(args.segments_txt, encoding="utf-8") as f:
        segs = [ln.strip() for ln in f.read().split("\n") if ln.strip()]

    if not segs:
        print("ERROR: segments.txt 为空", file=sys.stderr)
        sys.exit(2)

    durations = []
    starts = []
    ends = []
    subs = []  # (global_start, global_end, text)
    seg_paths = []

    cum = 0.0
    for i, seg_text in enumerate(segs):
        audio, sents = load_cached(args.out_dir, i)
        if audio is not None:
            print(f"  [{i+1}/{len(segs)}] 复用缓存 seg_{i:02d}.mp3", flush=True)
        else:
            print(f"  [{i+1}/{len(segs)}] TTS {len(seg_text)} 字 ...", flush=True)
            audio, sents = asyncio.run(tts_segment(seg_text, args.voice))
            save_cached(args.out_dir, i, audio, sents)
        seg_path = os.path.join(args.out_dir, f"seg_{i:02d}.mp3")
        with open(seg_path, "wb") as wf:
            wf.write(audio)
        seg_dur = ffprobe_dur(seg_path)
        # 封面补静音到最短时长
        if i == 0 and seg_dur < args.cover_min:
            padded = os.path.join(args.out_dir, f"seg_{i:02d}_pad.mp3")
            pad_audio(seg_path, padded, args.cover_min)
            seg_path = padded
            seg_dur = ffprobe_dur(seg_path)
        seg_paths.append(seg_path)
        durations.append(round(seg_dur, 3))
        starts.append(round(cum, 3))
        ends.append(round(cum + seg_dur, 3))

        # 句级时间轴映射到全局
        for (s_start, s_end, s_text) in sents:
            gs = cum + s_start
            ge = cum + s_end
            if s_end <= s_start:  # 兜底：整段均分
                ge = cum + seg_dur
            s_text = s_text.strip()
            if not s_text:
                continue
            # 句内按字符比例切行
            pos_map = split_lines(s_text)
            L = max(1, len(s_text))
            span = max(0.01, ge - gs)
            for (ln, a, b) in pos_map:
                ln = strip_tail_period(ln)
                if not ln:
                    continue
                ls = gs + (a / L) * span
                le = gs + (b / L) * span
                subs.append((round(ls, 3), round(le, 3), ln))
        cum += seg_dur

    # 全局去重叠 + 最小时长（句边界处比例切行可能产生 <0.1s 重叠）
    subs.sort(key=lambda c: c[0])
    clean = []
    prev_end = 0.0
    for (s, e, t) in subs:
        if s < prev_end:
            s = prev_end
        if e <= s:
            e = s + 0.15
        if e - s < 0.15:
            e = s + 0.15
        clean.append((round(s, 3), round(e, 3), t))
        prev_end = e
    subs = clean

    # 拼接 voiceover.mp3
    concat_list = os.path.join(args.out_dir, "segs_concat.txt")
    with open(concat_list, "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    voiceover = os.path.join(args.out_dir, "voiceover.mp3")
    subprocess.run(
        ["/usr/local/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", concat_list, "-c:a", "copy", voiceover],
        capture_output=True)

    # 写 SRT
    srt_path = os.path.join(args.out_dir, "subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (s, e, t) in enumerate(subs, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt_time(s)} --> {fmt_time(e)}\n")
            f.write(f"{t}\n\n")

    # 写时长 JSON
    with open(os.path.join(args.out_dir, "segments_durations.json"), "w", encoding="utf-8") as f:
        json.dump({"durations": durations, "starts": starts, "ends": ends,
                   "total": round(cum, 3)}, f, ensure_ascii=False, indent=2)

    total_audio = ffprobe_dur(voiceover)
    print(f"OK: {len(segs)} 段, 总配音 {total_audio:.2f}s, 字幕 {len(subs)} 条")
    print(f"  voiceover.mp3 -> {voiceover}")
    print(f"  subtitles.srt  -> {srt_path}")
    print(f"  segments_durations.json -> {os.path.join(args.out_dir, 'segments_durations.json')}")


def fmt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


if __name__ == "__main__":
    main()
