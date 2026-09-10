#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motion_quality_check.py — 视频「画面抖」质量门禁（渲染前自检，纯 Python，不调 ffmpeg）

背景（2026-09-10 重写）：旧版门禁只校验「xfade offset 整数帧 / 三角波缩放平移连续 /
段不过短」——这三项都达标，成片**依然抖**。根因不在转场，而在 **ffmpeg zoompan 把裁剪
窗口量化到源图像素整数格点**：本项目单帧位移仅 0.1~0.5 px，被量化成「3~4 帧静止 +
突然跳 1 像素」的阶梯（实测成片运动段 37% 的帧与前一帧像素完全相同）。
参数调优无法根治，故合成侧改用 ffmpeg `perspective`（浮点四角 + eval=frame + 三次插值
亚像素采样）。本门禁相应重写为**复算 perspective 的逐帧裁剪窗闭式解**，并新增两条
直击抖动根因的判定：

  ① 运动段「零位移帧」——相邻帧裁剪窗完全相同 = 量化停顿指纹（回归到整数裁剪必 FAIL）；
  ② 裁剪窗越界——越界会被滤镜夹边 → 边缘涂抹 / 运动截断。

契约参数（ZOOM_MAX / PAN_FRAC / PAN_DIRS / SMOOTHSTEP 公式）从 compose_motion.py 复制，
⚠️ 改动 compose_motion.py 的运动模型时必须同步本脚本常量/公式，否则门禁失效。

用法：
  python3 motion_quality_check.py <frames_dir> <durations.json> [--fps 30] [--preset 1]
                                  [--xd 0.5] [--strict] [--json] [--quiet]

退出码：
  0 = PASS（无阻断项）
  1 = FAIL（存在阻断项：零位移帧 / 越界 / 跨段不连续 / offset 非整数帧 / 段极短）
  2 = WARN-only（仅提示项，非 --strict 时不阻断）

也可被 compose_motion.py / video_quality_gate.py 直接 import：
  from motion_quality_check import run_gate
  code = run_gate(frames, durations, fps, preset, XD=0.5, strict=False, quiet=False)
"""
import argparse, json, os, re, struct, sys

# ===== 契约参数（须与 scripts/compose_motion.py 保持一致）=====
ZOOM_MAX = {1: 1.06, 2: 1.10, 3: 1.16}
PAN_FRAC = {1: 0.70, 2: 0.85, 3: 0.95}   # 平移量 = PAN_FRAC × 「缩放可用空间/2」
# 三角波方向表，按 (i//2)%4 取，相邻两段（一放一收）同方向 → 上一段尾 = 下一段头
PAN_DIRS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
XD_DEFAULT = 0.5  # 秒，与 compose_motion.py 的 XD 一致
MOTION_TAIL = 0.8  # 运动在段时长的前 80% 内完成，尾 20% 静止（转场期两段皆静止）


def smoothstep(e):
    """与 ffmpeg 表达式 (e*e*(3-2*e)) 完全一致的缓动：两端速度为 0，无起停跳变。"""
    return e * e * (3 - 2 * e)


def natural_key(path):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(path))]


def load_frames(frames_dir):
    fs = [os.path.join(frames_dir, f) for f in sorted(os.listdir(frames_dir))
          if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    fs.sort(key=natural_key)
    return fs


def png_size(path):
    """读 PNG IHDR 返回 (w, h)；非 PNG / 损坏返回 None。"""
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            f.read(4)
            if f.read(4) != b"IHDR":
                return None
            w = struct.unpack(">I", f.read(4))[0]
            h = struct.unpack(">I", f.read(4))[0]
            return w, h
    except Exception:
        return None


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


def motion_frames(n_frames, xd_frames):
    """运动帧数 N（与 compose_motion.py 完全一致）。"""
    if n_frames <= xd_frames + 1:
        return max(1, n_frames - 1)
    return max(1, int(n_frames * MOTION_TAIL))


def quad_at(i, on, N, preset, W, H):
    """第 i 段、运动内第 on 帧的裁剪窗 (x0, y0, w, h)（输出像素坐标；闭式，浮点）。

    对应 ffmpeg 表达式（compose_motion.py）：
      E  = min(on/N,1)                S = E*E*(3-2*E)           （缓动）
      even: z = 1+(Z-1)*S,  f = S          odd: z = Z-(Z-1)*S,  f = 1-S
      Ux = W*(1-1/z),  Uy = H*(1-1/z)
      w = W/z, h = H/z
      x0 = Ux*(0.5 + 0.5*dx*PAN_FRAC*f)
      y0 = Uy*(0.5 + 0.5*dy*PAN_FRAC*f)
    """
    Z = ZOOM_MAX[preset]
    PF = PAN_FRAC[preset]
    e = min(on / N, 1.0) if N else 1.0
    s = smoothstep(e)
    if i % 2 == 0:
        z = 1 + (Z - 1) * s
        f = s
    else:
        z = Z - (Z - 1) * s
        f = 1 - s
    dx, dy = PAN_DIRS[(i // 2) % 4]
    w, h = W / z, H / z
    ux, uy = W * (1 - 1 / z), H * (1 - 1 / z)
    x0 = ux * (0.5 + 0.5 * dx * PF * f)
    y0 = uy * (0.5 + 0.5 * dy * PF * f)
    return x0, y0, w, h


def compute_plan(frames, durations, fps, preset, XD=XD_DEFAULT, W=None, H=None):
    """复刻 compose_motion.py 的确定性逻辑，返回每段元数据 + 全局参数。"""
    if W is None or H is None:
        wh = png_size(frames[0]) if frames and os.path.exists(frames[0]) else None
        W, H = wh if wh else (1920, 1080)
    xd_frames = max(1, round(XD * fps))
    plan = []
    acc = 0  # 累计帧数（用于计算下一段 xfade offset）
    for i, d in enumerate(durations):
        dd = max(0.5, d)
        n = max(1, int(round(dd * fps)))
        N = motion_frames(n, xd_frames)
        q_first = quad_at(i, 0, N, preset, W, H)
        q_last = quad_at(i, N, N, preset, W, H)
        if i == 0:
            off_frames = 0
        else:
            off_frames = max(0, acc - xd_frames)
        # 运动段逐帧裁剪窗（on=0..N），用于零位移帧 / 越界判定
        quads = [quad_at(i, on, N, preset, W, H) for on in range(N + 1)]
        plan.append({
            "idx": i,
            "frame": os.path.basename(frames[i]) if i < len(frames) else f"seg_{i}",
            "dur": dd,
            "n_frames": n,
            "motion_frames": N,
            "quad_first": q_first,
            "quad_last": q_last,
            "quads": quads,
            "off_frames": off_frames,
            "off_sec": off_frames / fps,
        })
        acc = acc + n - (xd_frames if i > 0 else 0)
    return plan, xd_frames, ZOOM_MAX[preset], acc, W, H


def _out_step(qa, qb, W, H):
    """相邻两帧「输出像素位移」估计：裁剪窗原点位移 + 缩放引起的等效径向位移。

    裁剪窗 (w,h) 映射到输出 (W,H)，故窗内一点在输出空间的位移 ≈ Δx0*(W/w)。
    缩放项取画面 1/4 半径处的径向位移作为整体尺度变化估计。
    """
    x0a, y0a, wa, ha = qa
    x0b, y0b, wb, hb = qb
    mx = (wa + wb) / 2
    my = (ha + hb) / 2
    dx = (x0b - x0a) * (W / mx)
    dy = (y0b - y0a) * (H / my)
    dz = abs((wb - wa) / wa) * 0.25 * W
    return (dx * dx + dy * dy) ** 0.5 + dz


def collect_issues(plan, xd_frames, fps, W, H):
    """运动门禁判定（与 run_gate 共用，唯一权威实现）：返回 [(level, seg, msg)]。"""
    issues = []
    for seg in plan:
        i, n, N = seg["idx"], seg["n_frames"], seg["motion_frames"]
        # 1) 段过短 → 转场占满整段，抖动高风险
        if n < xd_frames + 1:
            issues.append(("FAIL", i, f"段{n}帧(<{xd_frames+1}帧≈{(xd_frames+1)/fps:.2f}s)极短，xfade占满整段→抖动高风险，请加长该段时长"))
        elif n < 2 * xd_frames:
            issues.append(("WARN", i, f"段{n}帧(<{2*xd_frames}帧=2×转场)偏短，转场占比高，建议加长"))
        # 2) 帧时长对齐偏差：d 非 fps 整数倍 → 段尾可能有≤1帧误差
        drift_frames = abs(seg["dur"] * fps - n)
        if drift_frames > 0.5:
            issues.append(("WARN", i, f"时长{seg['dur']:.3f}s非fps整数倍，偏差{drift_frames:.2f}帧（合成以-frames:v锁帧，误差被吸收到段尾静止，影响极小）"))

        quads = seg["quads"]
        # 3) ★零位移帧（画面抖根因）：运动段内相邻两帧裁剪窗完全相同 = 量化停顿
        stall = []
        for k in range(2, len(quads)):     # 从 on=2 起算，跳过缓动起步的亚像素段
            a, b = quads[k - 1], quads[k]
            if all(abs(a[j] - b[j]) < 1e-9 for j in range(4)):
                stall.append(k)
        if stall:
            issues.append(("FAIL", i,
                           f"运动段存在零位移帧（on={stall[:6]}{'…' if len(stall)>6 else ''} 连续两帧裁剪窗完全相同）"
                           f"→ 运动被量化成阶梯 = 「画面抖」，说明用了整数裁剪（zoompan/crop）而非 perspective 亚像素采样"))
        # 4) ★裁剪窗越界：越界会被滤镜夹边 → 边缘涂抹 / 运动截断
        oob = [k for k, (x0, y0, w, h) in enumerate(quads)
               if x0 < -1e-6 or y0 < -1e-6 or x0 + w > W + 1e-6 or y0 + h > H + 1e-6]
        if oob:
            issues.append(("FAIL", i,
                           f"裁剪窗越界 {len(oob)} 帧（on={oob[:6]}{'…' if len(oob)>6 else ''}，画布 {W}×{H}）"
                           f"→ 源采样出界被夹边、边缘涂抹/运动截断；请降低 --preset 或修正 PAN_FRAC"))
        # 5) 运动幅度体检：逐帧输出位移
        steps = [_out_step(quads[k - 1], quads[k], W, H) for k in range(1, len(quads))]
        if not steps:
            issues.append(("WARN", i, "运动帧数不足（N<2），该段近似静止"))
        else:
            mx = max(steps)
            if mx < 0.01:
                issues.append(("WARN", i, f"最大逐帧位移仅{mx:.4f}px，运动弱到肉眼不可见（可提高 --preset）"))
            elif mx > 4.0:
                issues.append(("WARN", i, f"最大逐帧位移{mx:.2f}px 偏大，观感可能眩晕（建议降 --preset）"))
        # 6) 跨段连续：上一段尾 == 本段头（缩放 + 平移一体，用裁剪窗整体比对）
        if i > 0:
            prev = plan[i - 1]
            pa, pb = prev["quad_last"], seg["quad_first"]
            if any(abs(pa[j] - pb[j]) > 1e-6 for j in range(4)):
                issues.append(("FAIL", i,
                               f"跨段运动不连续：段{i-1}尾窗={tuple(round(v,3) for v in pa)} "
                               f"≠ 段{i}头窗={tuple(round(v,3) for v in pb)} → 衔接处画面跳变"))
        # 7) offset 必须整数帧（acc/xd_frames 皆整数 → 必整数；非整数即逻辑 bug）
        if seg["off_frames"] != int(seg["off_frames"]):
            issues.append(("FAIL", i, f"xfade offset={seg['off_frames']}非整数帧→转场混合起点在帧中间→画面抖"))
        if i > 0 and seg["off_frames"] < 0:
            issues.append(("WARN", i, "offset被clamp到0（前段过短），转场从段头开始，可能重叠异常"))
    return issues


def run_gate(frames, durations, fps, preset, XD=XD_DEFAULT, strict=False, quiet=False,
             return_issues=False):
    """执行门禁校验。返回退出码 int（0 PASS / 1 FAIL / 2 WARN-only）；
    return_issues=True 时返回 (code, issues)，供统一总门禁 video_quality_gate 复用。"""
    plan, xd_frames, zoom_max, total_frames, W, H = compute_plan(frames, durations, fps, preset, XD)
    issues = collect_issues(plan, xd_frames, fps, W, H)
    has_fail = any(lv == "FAIL" for lv, _, _ in issues)
    has_warn = any(lv == "WARN" for lv, _, _ in issues)

    if has_fail:
        code = 1
    elif has_warn and strict:
        code = 1
    elif has_warn:
        code = 2
    else:
        code = 0

    if not quiet:
        _print_report(plan, xd_frames, zoom_max, total_frames, fps, preset, XD, issues, code, W, H)
    if return_issues:
        return code, issues
    return code


def _fmt_quad(q):
    return f"{q[0]:.1f}/{q[1]:.1f} {q[2]:.1f}x{q[3]:.1f}"


def _print_report(plan, xd_frames, zoom_max, total_frames, fps, preset, XD, issues, code, W, H):
    print("=" * 96)
    print(f"[抖动门禁] motion_quality_check（亚像素 perspective 模型）  fps={fps} preset={preset} "
          f"XD={XD}s({xd_frames}帧) zoom_max={zoom_max} PAN_FRAC={PAN_FRAC[preset]} 画布={W}×{H} 段数={len(plan)}")
    print(f"预估总时长 ≈ {total_frames/fps:.1f}s")
    print("-" * 96)
    print(f"{'#':>2} {'frame':<16} {'n帧':>4} {'运动帧':>5}  {'头窗 x0/y0':<16} {'尾窗 x0/y0':<16} "
          f"{'峰位移px':>8}  {'xfade偏移':<12} 状态")
    print("-" * 96)
    for s in plan:
        status = "OK"
        for lv, seg_i, _ in issues:
            if seg_i == s["idx"] and lv == "FAIL":
                status = "FAIL"
            elif seg_i == s["idx"] and lv == "WARN" and status != "FAIL":
                status = "WARN"
        steps = [_out_step(s["quads"][k - 1], s["quads"][k], W, H) for k in range(1, len(s["quads"]))]
        pk = max(steps) if steps else 0.0
        off = "--" if s["idx"] == 0 else f"{s['off_frames']}帧/{s['off_sec']:.2f}s"
        print(f"{s['idx']:>2} {s['frame'][:16]:<16} {s['n_frames']:>4} {s['motion_frames']:>5}  "
              f"{s['quad_first'][0]:>7.1f}/{s['quad_first'][1]:<7.1f} "
              f"{s['quad_last'][0]:>7.1f}/{s['quad_last'][1]:<7.1f} "
              f"{pk:>8.3f}  {off:<12} {status}")
    print("-" * 96)
    verdict = {0: "PASS ✅", 1: "FAIL ❌", 2: "WARN ⚠️ (非阻断)"}[code]
    print(f"结论: {verdict}")
    if issues:
        print("问题项:")
        for lv, seg_i, msg in issues:
            print(f"  [{lv}] 段{seg_i}: {msg}")
    print("=" * 96)


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

    plan, xd_frames, zoom_max, total_frames, W, H = compute_plan(
        frames, durations, args.fps, args.preset, args.xd)
    issues = collect_issues(plan, xd_frames, args.fps, W, H)
    has_fail = any(lv == "FAIL" for lv, _, _ in issues)
    has_warn = any(lv == "WARN" for lv, _, _ in issues)
    if has_fail:
        code = 1
    elif has_warn and args.strict:
        code = 1
    elif has_warn:
        code = 2
    else:
        code = 0

    if args.json:
        out = {
            "fps": args.fps, "preset": args.preset, "xd_frames": xd_frames,
            "zoom_max": zoom_max, "pan_frac": PAN_FRAC[args.preset],
            "canvas": [W, H], "total_frames": total_frames, "exit_code": code,
            "issues": [{"level": lv, "seg": s, "msg": m} for lv, s, m in issues],
            "segments": [{k: v for k, v in s.items() if k != "quads"} for s in plan],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    if not args.quiet:
        _print_report(plan, xd_frames, zoom_max, total_frames, args.fps, args.preset,
                      args.xd, issues, code, W, H)
    return code


def _collect_issues_deprecated():
    """已废弃：判定逻辑统一到 collect_issues()。保留空壳避免误调用。"""
    return []


if __name__ == "__main__":
    sys.exit(main())
