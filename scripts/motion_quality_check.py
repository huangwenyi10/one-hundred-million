#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motion_quality_check.py — 视频「画面抖」质量门禁（渲染前自检）

背景：compose_motion.py 修过的抖动根因有三——①xfade offset 落在非整数帧边界
（浮点秒累加）→ 每次转场抖；②相邻段 zoom/pan 不连续 → 衔接跳变；③段用 -t 浮点秒
导致帧数与 zoompan 差 1 → 段尾不连续。本脚本在 **真正跑 ffmpeg 合成之前**，用纯
Python 复刻 compose_motion.py 的全部确定性逻辑（整数帧驱动 + 三角波连续运动），
校验每一项是否达标，并输出「预期 xfade offset 表」。

与 compose_motion.py 的关系：本脚本是**门禁/检视器**，不调用 ffmpeg。
契约参数（zoom_max/pan_px/XD/三角波公式）从 compose_motion.py 复制而来，
⚠️ 改动 compose_motion.py 的运动参数时，必须同步本脚本对应常量/公式，否则门禁失效。

用法：
  python3 motion_quality_check.py <frames_dir> <durations.json> [--fps 30] [--preset 1] [--xd 0.5]
                                  [--strict] [--json] [--quiet]

退出码：
  0 = PASS（无阻断项）
  1 = FAIL（存在阻断项，如运动不连续 / offset 非整数帧 / 段极短）
  2 = WARN-only（仅提示项，非 --strict 时不阻断）

也可被 compose_motion.py 直接 import：
  from motion_quality_check import run_gate
  code = run_gate(frames, durations, fps, preset, XD=0.5, strict=False, quiet=False)
"""
import argparse, json, os, re, sys

# ===== 契约参数（须与 scripts/compose_motion.py 保持一致）=====
ZOOM_MAX = {1: 1.06, 2: 1.10, 3: 1.16}
PAN_PX = {1: 40, 2: 90, 3: 150}
# 三角波方向表，按 (i//2)%4 取，相邻两段同方向 → 上一段尾=下一段头
PAN_DIRS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
XD_DEFAULT = 0.5  # 秒，与 compose_motion.py 的 XD 一致


def natural_key(path):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(path))]


def load_frames(frames_dir):
    fs = [os.path.join(frames_dir, f) for f in sorted(os.listdir(frames_dir))
          if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    fs.sort(key=natural_key)
    return fs


def load_durations(durations_json, n_frames):
    with open(durations_json, encoding='utf-8') as f:
        data = json.load(f)
    durs = data["durations"] if isinstance(data, dict) else list(data)
    default_d = 6.0
    if len(durs) < n_frames:
        durs = durs + [default_d] * (n_frames - len(durs))
    else:
        durs = durs[:n_frames]
    return durs


def compute_plan(frames, durations, fps, preset, XD=XD_DEFAULT):
    """复刻 compose_motion.py 的确定性逻辑，返回每段元数据 + 全局参数。"""
    zoom_max = ZOOM_MAX[preset]
    pan_px = PAN_PX[preset]
    xd_frames = max(1, round(XD * fps))
    plan = []
    acc = 0  # 累计帧数（用于计算下一段 xfade offset）
    for i, d in enumerate(durations):
        dd = max(0.5, d)
        n = max(1, int(round(dd * fps)))
        if n <= xd_frames + 1:
            N = max(1, n - 1)
        else:
            N = max(1, int(n * 0.8))
        dx, dy = PAN_DIRS[(i // 2) % 4]
        if i % 2 == 0:
            z_start, z_end = 1.0, zoom_max
            pan_start = (0, 0)
            pan_end = (pan_px * dx, pan_px * dy)
        else:
            z_start, z_end = zoom_max, 1.0
            pan_start = (pan_px * dx, pan_px * dy)
            pan_end = (0, 0)
        if i == 0:
            off_frames = 0
            off_sec = 0.0
        else:
            off_frames = acc - xd_frames
            if off_frames < 0:
                off_frames = 0
            off_sec = off_frames / fps
        plan.append({
            "idx": i,
            "frame": os.path.basename(frames[i]) if i < len(frames) else f"seg_{i}",
            "dur": dd,
            "n_frames": n,
            "motion_frames": N,
            "z_start": z_start,
            "z_end": z_end,
            "pan_start": pan_start,
            "pan_end": pan_end,
            "off_frames": off_frames,
            "off_sec": off_sec,
        })
        acc = acc + n - (xd_frames if i > 0 else 0)
    return plan, xd_frames, zoom_max, acc


def run_gate(frames, durations, fps, preset, XD=XD_DEFAULT, strict=False, quiet=False):
    """执行门禁校验。返回退出码 int（0 PASS / 1 FAIL / 2 WARN-only）。"""
    plan, xd_frames, zoom_max, total_frames = compute_plan(frames, durations, fps, preset, XD)
    issues = []  # (level, seg, msg)

    for seg in plan:
        i = seg["idx"]
        n = seg["n_frames"]
        # 1) 段过短 → 转场占满整段，抖动高风险
        if n < xd_frames + 1:
            issues.append(("FAIL", i, f"段{n}帧(<{xd_frames+1}帧≈{(xd_frames+1)/fps:.2f}s)极短，xfade占满整段→抖动高风险，请加长该段时长"))
        elif n < 2 * xd_frames:
            issues.append(("WARN", i, f"段{n}帧(<{2*xd_frames}帧=2×转场)偏短，转场占比高，建议加长"))
        # 2) 帧时长对齐偏差：d 非 fps 整数倍 → 段尾可能有≤1帧误差
        drift_frames = abs(seg["dur"] * fps - n)
        if drift_frames > 0.5:
            issues.append(("WARN", i, f"时长{seg['dur']:.3f}s非fps整数倍，偏差{drift_frames:.2f}帧（合成以-frames:v锁帧，误差被吸收到段尾静止，影响极小）"))
        # 3) 运动连续性：上一段尾 == 本段头
        if i > 0:
            prev = plan[i - 1]
            if abs(prev["z_end"] - seg["z_start"]) > 1e-6:
                issues.append(("FAIL", i, f"缩放不连续：段{i-1}尾z={prev['z_end']} ≠ 段{i}头z={seg['z_start']}"))
            if (abs(prev["pan_end"][0] - seg["pan_start"][0]) > 1e-6 or
                    abs(prev["pan_end"][1] - seg["pan_start"][1]) > 1e-6):
                issues.append(("FAIL", i, f"平移不连续：段{i-1}尾pan={prev['pan_end']} ≠ 段{i}头pan={seg['pan_start']}"))
        # 4) offset 必须整数帧（acc/xd_frames 皆整数 → 必整数；非整数即逻辑 bug）
        if seg["off_frames"] != int(seg["off_frames"]):
            issues.append(("FAIL", i, f"xfade offset={seg['off_frames']}非整数帧→转场混合起点在帧中间→画面抖"))
        if i > 0 and seg["off_frames"] < 0:
            issues.append(("WARN", i, "offset被clamp到0（前段过短），转场从段头开始，可能重叠异常"))

    has_fail = any(lv == "FAIL" for lv, _, _ in issues)
    has_warn = any(lv == "WARN" for lv, _, _ in issues)

    # 退出码判定
    if has_fail:
        code = 1
    elif has_warn and strict:
        code = 1
    elif has_warn:
        code = 2
    else:
        code = 0

    if not quiet:
        _print_report(plan, xd_frames, zoom_max, total_frames, fps, preset, XD, issues, code)
    return code


def _fmt_pan(p):
    return f"{p[0]:g},{p[1]:g}"


def _print_report(plan, xd_frames, zoom_max, total_frames, fps, preset, XD, issues, code):
    print("=" * 78)
    print(f"[抖动门禁] motion_quality_check  fps={fps} preset={preset} "
          f"XD={XD}s({xd_frames}帧)  zoom_max={zoom_max}  段数={len(plan)}")
    print(f"预估总时长 ≈ {total_frames/fps:.1f}s")
    print("-" * 78)
    print(f"{'#':>2} {'frame':<18} {'n帧':>4}  {'z(起→止)':<14}  {'pan(起→止)':<16}  {'xfade偏移(帧/秒)':<18} 状态")
    print("-" * 78)
    for s in plan:
        status = "OK"
        for lv, seg_i, _ in issues:
            if seg_i == s["idx"] and lv == "FAIL":
                status = "FAIL"
            elif seg_i == s["idx"] and lv == "WARN" and status != "FAIL":
                status = "WARN"
        off = "--" if s["idx"] == 0 else f"{s['off_frames']}/{s['off_sec']:.2f}s"
        print(f"{s['idx']:>2} {s['frame'][:18]:<18} {s['n_frames']:>4}  "
              f"{s['z_start']:.2f}→{s['z_end']:.2f}      "
              f"{_fmt_pan(s['pan_start'])}→{_fmt_pan(s['pan_end'])}      "
              f"{off:<18} {status}")
    print("-" * 78)
    verdict = {0: "PASS ✅", 1: "FAIL ❌", 2: "WARN ⚠️ (非阻断)"}[code]
    print(f"结论: {verdict}")
    if issues:
        print("问题项:")
        for lv, seg_i, msg in issues:
            print(f"  [{lv}] 段{seg_i}: {msg}")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description="视频画面抖质量门禁（渲染前自检）")
    ap.add_argument("frames_dir")
    ap.add_argument("durations_json")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preset", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--xd", type=float, default=XD_DEFAULT)
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败（退出码1）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（便于自动化解析）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    frames = load_frames(args.frames_dir)
    if not frames:
        print("No frames in " + args.frames_dir, file=sys.stderr)
        return 2
    durations = load_durations(args.durations_json, len(frames))

    if args.json:
        plan, xd_frames, zoom_max, total_frames = compute_plan(
            frames, durations, args.fps, args.preset, args.xd)
        issues = []
        # 复用 run_gate 的判定逻辑但不打印
        code = run_gate(frames, durations, args.fps, args.preset, XD=args.xd,
                        strict=args.strict, quiet=True)
        # 重新收集 issues（quiet 模式不返回，这里直接重算一次以便 JSON 输出）
        issues = _collect_issues(frames, durations, args.fps, args.preset, args.xd, args.strict)
        out = {
            "fps": args.fps, "preset": args.preset, "xd_frames": xd_frames,
            "zoom_max": zoom_max, "total_frames": total_frames,
            "exit_code": code, "issues": issues,
            "segments": plan,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    code = run_gate(frames, durations, args.fps, args.preset, XD=args.xd,
                    strict=args.strict, quiet=args.quiet)
    return code


def _collect_issues(frames, durations, fps, preset, XD, strict):
    """与 run_gate 相同的判定，返回 issue 列表（供 JSON 模式）。"""
    plan, xd_frames, zoom_max, total_frames = compute_plan(frames, durations, fps, preset, XD)
    issues = []
    for seg in plan:
        i, n = seg["idx"], seg["n_frames"]
        if n < xd_frames + 1:
            issues.append({"level": "FAIL", "seg": i,
                           "msg": f"段{n}帧极短，xfade占满整段→抖动高风险，请加长该段时长"})
        elif n < 2 * xd_frames:
            issues.append({"level": "WARN", "seg": i, "msg": f"段{n}帧偏短，转场占比高"})
        drift_frames = abs(seg["dur"] * fps - n)
        if drift_frames > 0.5:
            issues.append({"level": "WARN", "seg": i,
                           "msg": f"时长非fps整数倍，偏差{drift_frames:.2f}帧"})
        if i > 0:
            prev = plan[i - 1]
            if abs(prev["z_end"] - seg["z_start"]) > 1e-6:
                issues.append({"level": "FAIL", "seg": i, "msg": "缩放不连续"})
            if (abs(prev["pan_end"][0] - seg["pan_start"][0]) > 1e-6 or
                    abs(prev["pan_end"][1] - seg["pan_start"][1]) > 1e-6):
                issues.append({"level": "FAIL", "seg": i, "msg": "平移不连续"})
        if seg["off_frames"] != int(seg["off_frames"]):
            issues.append({"level": "FAIL", "seg": i, "msg": "xfade offset非整数帧"})
    return issues


if __name__ == "__main__":
    sys.exit(main())
