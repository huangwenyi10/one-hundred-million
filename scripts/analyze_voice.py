#!/usr/bin/env python3
"""配音音色基线分析：基频 F0（自相关法，推断性别/音高）+ 语速（字/分，需 faster-whisper）。

用途：技能已改为固定音色（zh-CN-YunxiNeural，见 SKILL.md 固定规范第 10 条），不再依赖外部声音模版。
本脚本仅作音色诊断/调参使用（对两个音频各跑一遍，对比客观指标），不再是强制门禁。
  - 性别（由 F0 中位推断，男 <165Hz / 女 >195Hz）
  - 音高（F0 中位与分布）
  - 语速（字/分）

匹配判定参考（客观标准）：
  - 性别一致
  - F0 中位偏差 ≤ ±20Hz
  - 语速偏差 ≤ ±10 字/分

用法：
  python3 analyze_voice.py <音频文件> [更多音频文件...]

依赖：
  - 必需：numpy、ffmpeg（PATH 中）
  - 可选：faster-whisper（无则跳过转写与语速，仅输出 F0 基线）
  - 转写模型下载注意：本机代理会导致 huggingface 下载 502，
    需 unset 代理 + HF_ENDPOINT=https://hf-mirror.com + HF_HUB_DISABLE_XET=1（见 SKILL.md Step 3）。
"""
import argparse
import os
import subprocess
import sys
import tempfile

try:
    import numpy as np
except ImportError:
    sys.stderr.write("缺少依赖 numpy：请先 pip install numpy 再运行本脚本\n")
    sys.exit(1)


def to_wav16k(src):
    """转 16k 单声道 wav（faster-whisper 与 F0 分析共用）。"""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", tmp],
        check=True,
    )
    return tmp


def read_wav(path):
    import wave
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        data = w.readframes(n)
    y = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    return y, sr


def compute_f0(y, sr, fmin=70, fmax=400, thresh=0.4):
    """自相关法基频估计，返回有声段 F0 列表（Hz）。
    过滤：排除过低（<80Hz，常见于背景音乐/底噪）和过高（>250Hz）的异常帧，
    只保留合理语音段 F0，避免含背景音乐的模板被低频拖偏中位值。
    """
    frame_len = int(0.032 * sr)
    hop = int(0.010 * sr)
    f0s = []
    min_lag = max(1, int(sr / fmax))
    max_lag = int(sr / fmin)
    lags = np.arange(min_lag, max_lag + 1)
    for start in range(0, len(y) - frame_len, hop):
        frame = y[start:start + frame_len]
        if np.sqrt(np.mean(frame ** 2)) < 0.015:  # 静音段跳过
            continue
        frame = frame - np.mean(frame)
        n = len(frame)
        valid = lags < n
        lags_v = lags[valid]
        corr = np.array([
            float(np.dot(frame[:n - l], frame[l:])) for l in lags_v
        ])
        if len(corr) == 0 or corr.max() <= 0:
            continue
        peak = int(np.argmax(corr))
        denom = (np.linalg.norm(frame[:n - lags_v[peak]]) *
                 np.linalg.norm(frame[lags_v[peak]:]) + 1e-9)
        if corr[peak] / denom > thresh:
            f0 = sr / lags_v[peak]
            # 只保留合理语音段
            if 80 <= f0 <= 250:
                f0s.append(f0)
    return np.array(f0s)


def transcribe(path):
    """faster-whisper 转写；未安装时返回 None（语速不可算）。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    model = WhisperModel("base", device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = model.transcribe(path, language="zh", vad_filter=True)
    return "".join(seg.text for seg in segments).strip()


def cjk_len(text):
    return sum(1 for ch in text if ord(ch) > 255)


def analyze(src):
    wav = to_wav16k(src)
    try:
        text = transcribe(wav)
        y, sr = read_wav(wav)
    finally:
        os.remove(wav)

    f0s = compute_f0(y, sr)
    dur = len(y) / sr

    print("=" * 60)
    print("文件:", os.path.basename(src))
    if len(f0s) == 0:
        print("F0: 无有效基频帧（音频过短/纯音乐/静音？）")
    else:
        med = float(np.median(f0s))
        p5 = float(np.percentile(f0s, 5))
        p95 = float(np.percentile(f0s, 95))
        if med < 165:
            sex = "男声"
        elif med > 195:
            sex = "女声"
        else:
            sex = "中性/难判"
        print("时长: {:.2f}s | F0 帧数: {}".format(dur, len(f0s)))
        print("F0: 中位 {:.0f}Hz | P5-P95: {:.0f}-{:.0f}Hz | 性别推断: {}".format(med, p5, p95, sex))
    if text:
        words = cjk_len(text)
        speed = words / dur * 60 if dur > 0 else 0
        print("转写字数: {} | 语速: {:.0f} 字/分".format(words, speed))
        print("转写内容:", text)
    else:
        print("语速: 不可算（faster-whisper 未安装，或转写失败）")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="+", help="音频文件（模板与候选配音各给一个即可对比）")
    args = ap.parse_args()
    for f in args.files:
        if not os.path.exists(f):
            sys.stderr.write("文件不存在: {}\n".format(f))
            continue
        analyze(f)
