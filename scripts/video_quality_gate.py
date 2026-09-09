#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video_quality_gate.py — 短视频统一质量总门禁（渲染/合成前一次性自检）

合并三类检查，输出单一结论（PASS / FAIL / WARN），供自动化任务与人工 CI 直接用来
在「跑 ffmpeg 之前」拦下质量问题，避免"渲染完才发现画面抖/脏/发虚"。

  [MOTION] 画面抖（复用 motion_quality_check 的确定性逻辑：整数帧 / 三角波连续 / offset 整数帧）
  [ENCODE] 编码画质（检查 compose_motion.py / render_animated.js 是否守住 craft-quality.md §3.6 契约）
  [ASSET ] 素材合规（源帧尺寸 / 非空 / 数量对齐 / 命名连续）

与子门禁关系：
  - 本脚本是**总闸门**，MOTION 子项直接复用 motion_quality_check（唯一权威实现，避免双份判定漂移）。
  - ENCODE 检查的是「源码契约」：若有人改坏 compose_motion.py 的 qp0/crf、或把 scale=8000
    改回来、或把 render_animated.js 的 SwiftShader 去掉，本门禁会在合成前 FAIL 告警，防回归。
  - ASSET 检查的是「输入素材」：源帧不是 1920x1080 会导致合成 s=1920x1080 拉伸/裁切、运动失真。

退出码：
  0 = PASS（无阻断项）
  1 = FAIL（存在阻断项：抖动 / 编码契约违约 / 素材尺寸错误）
  2 = WARN-only（仅提示项，非 --strict 时不阻断）

可 import：
  from video_quality_gate import run_gate
  code = run_gate(frames, durations, fps, preset,
                  scripts_dir="/path/to/scripts", XD=0.5, strict=False, quiet=False)
  # frames: 帧文件绝对路径列表；durations: 每帧停留秒数列表
"""
import argparse, json, os, re, struct, sys

# ===== 契约参数（须与 motion_quality_check / compose_motion.py 保持一致）=====
XD_DEFAULT = 0.5

try:
    import motion_quality_check as mqc
    _MQC_OK = True
except Exception:
    _MQC_OK = False


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def natural_key(path):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(path))]


def png_size(path):
    """读 PNG IHDR 返回 (w, h)；非 PNG / 损坏返回 None。"""
    try:
        with open(path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            f.read(4)            # chunk length
            if f.read(4) != b"IHDR":
                return None
            w = struct.unpack(">I", f.read(4))[0]
            h = struct.unpack(">I", f.read(4))[0]
            return w, h
    except Exception:
        return None


# ---------------------------------------------------------------------------
# [MOTION] 画面抖（复用 motion_quality_check）
# ---------------------------------------------------------------------------
def check_motion(frames, durations, fps, preset, XD):
    if not _MQC_OK:
        return [("FAIL", "MOTION", "motion_quality_check 缺失，无法校验运动连续性，终止以确保质量")]
    plan, xd_frames, zoom_max, total_frames = mqc.compute_plan(frames, durations, fps, preset, XD)
    issues = mqc.collect_issues(plan, xd_frames, fps)
    # 归并分组标签
    return [(lv, "MOTION", m) for lv, s, m in issues]


# ---------------------------------------------------------------------------
# [ENCODE] 编码画质契约（检查源码文件）
# ---------------------------------------------------------------------------
def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


def check_encode(scripts_dir):
    issues = []
    cm = os.path.join(scripts_dir, "compose_motion.py")
    ra = os.path.join(scripts_dir, "render_animated.js")
    cm_src = _read(cm)
    ra_src = _read(ra)

    if cm_src is None:
        issues.append(("FAIL", "ENCODE", f"找不到 {cm}，无法校验编码契约"))
        return issues

    # 逐行扫描时跳过 # 注释行，避免注释里的关键字（如「旧实现 scale=8000:-1」）误触发
    def _code_lines(src):
        for ln in src.splitlines():
            if ln.strip().startswith("#"):
                continue
            yield ln
    cm_code = "\n".join(_code_lines(cm_src))

    # --- compose_motion.py 契约（craft-quality.md §3.6）---
    # 1) 中间段无损暂存：实际参数对 '-qp', '0'（只看真实编码参数，不认注释，避免漏判）
    if not re.search(r'["\']-qp["\']\s*,\s*["\']0["\']', cm_code):
        issues.append(("FAIL", "ENCODE",
                       "compose_motion.py 中间段未用无损暂存(qp 0) → 二次有损压缩 → 渐变背景色带/块化"))
    # 2) 禁止盲目4×放大：仅当「实际 filter 行」含 scale=8000 且同现 zoompan 才算违约
    if any(("scale=8000" in ln and "zoompan" in ln) for ln in _code_lines(cm_src)):
        issues.append(("FAIL", "ENCODE",
                       "compose_motion.py 存在 scale=8000 盲目4×放大 → 全片文字/线条发虚"))
    # 3) 最终有损编码 crf≤18（只看真实编码参数对，不认注释，避免漏判）
    if not re.search(r'["\']-crf["\']\s*,\s*["\']1[0-8]["\']', cm_code):
        issues.append(("WARN", "ENCODE",
                       "compose_motion.py 最终编码未用 crf≤18（建议 crf 18, preset medium）→ 画质余量不足"))

    # --- render_animated.js 契约（craft-quality.md §3.6 CSS 动画进视频）---
    if ra_src is None:
        issues.append(("WARN", "ENCODE", f"找不到 {ra}，跳过 CSS 动画编码契约检查"))
        return issues
    ra_low = ra_src.lower()
    if "swiftshader" not in ra_low:
        issues.append(("FAIL", "ENCODE",
                       "render_animated.js 未启用 SwiftShader → transform/opacity 动画被丢弃、页面变静态"))
    ra_code = "\n".join(ln for ln in ra_src.splitlines() if not ln.strip().startswith("#"))
    if "disable-software-rasterizer" in ra_code:
        issues.append(("FAIL", "ENCODE",
                       "render_animated.js 含 --disable-software-rasterizer → 动画丢帧/失真"))
    if "Date.now" not in ra_code or "frameInterval" not in ra_code:
        issues.append(("FAIL", "ENCODE",
                       "render_animated.js 截屏未用累计目标时间戳调度 → 帧间隔漂移、卡顿/跳帧"))
    return issues


# ---------------------------------------------------------------------------
# [ASSET] 素材合规
# ---------------------------------------------------------------------------
def check_asset(frames, durations):
    issues = []
    # 1) 非负、尺寸
    for fp in frames:
        try:
            sz = os.path.getsize(fp)
        except Exception:
            issues.append(("FAIL", "ASSET", f"无法读取文件 {os.path.basename(fp)}"))
            continue
        if sz == 0:
            issues.append(("FAIL", "ASSET", f"空文件 {os.path.basename(fp)}（0 字节）→ 合成会黑帧/崩溃"))
            continue
        if fp.lower().endswith(".png"):
            wh = png_size(fp)
            if wh and wh != (1920, 1080):
                issues.append(("FAIL", "ASSET",
                               f"{os.path.basename(fp)} 尺寸 {wh[0]}x{wh[1]} ≠ 1920x1080 → 合成 s=1920x1080 会拉伸/裁切、运动失真"))
    # 2) 帧数 vs 时长数
    if durations is not None and len(frames) != len(durations):
        issues.append(("WARN", "ASSET",
                       f"帧数 {len(frames)} ≠ 时长数 {len(durations)} → 合成将补齐/截断，可能错位"))
    # 3) 命名自然序连续（仅提示）
    nums = []
    for fp in frames:
        m = re.search(r"(\d+)", os.path.basename(fp))
        if m:
            nums.append(int(m.group(1)))
    if nums:
        lo, hi = min(nums), max(nums)
        missing = [n for n in range(lo, hi + 1) if n not in nums]
        if missing:
            issues.append(("WARN", "ASSET",
                           f"帧编号不连续，缺 {missing}（自然序排序下可能导致某页停留时长错位）"))
    return issues


# ---------------------------------------------------------------------------
# 总门禁
# ---------------------------------------------------------------------------
def run_gate(frames, durations, fps, preset, scripts_dir=None, XD=XD_DEFAULT, strict=False, quiet=False):
    """返回退出码 int（0 PASS / 1 FAIL / 2 WARN-only）。"""
    if scripts_dir is None:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))

    all_issues = []
    all_issues += check_motion(frames, durations, fps, preset, XD)
    all_issues += check_encode(scripts_dir)
    all_issues += check_asset(frames, durations)

    has_fail = any(lv == "FAIL" for lv, _, _ in all_issues)
    has_warn = any(lv == "WARN" for lv, _, _ in all_issues)

    if has_fail:
        code = 1
    elif has_warn and strict:
        code = 1
    elif has_warn:
        code = 2
    else:
        code = 0

    if not quiet:
        _print_report(all_issues, code, scripts_dir)
    return code


def _print_report(issues, code, scripts_dir):
    print("=" * 78)
    print(f"[统一质量总门禁] video_quality_gate  scripts_dir={scripts_dir}")
    print("-" * 78)
    groups = {}
    for lv, g, m in issues:
        groups.setdefault(g, []).append((lv, m))
    for g in ("MOTION", "ENCODE", "ASSET"):
        gi = groups.get(g, [])
        print(f"■ {g}  {'✅ 通过' if not gi else f'{len(gi)} 项'}")
        for lv, m in gi:
            print(f"    [{lv}] {m}")
    if not issues:
        print("  全部通过 ✅")
    print("-" * 78)
    verdict = {0: "PASS ✅", 1: "FAIL ❌", 2: "WARN ⚠️ (非阻断)"}[code]
    print(f"结论: {verdict}  (0=PASS / 1=FAIL / 2=WARN-only)")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description="短视频统一质量总门禁（渲染/合成前自检）")
    ap.add_argument("frames_dir", help="含 page_01.png ... 的静态帧目录")
    ap.add_argument("durations_json", help='{"durations":[...]} 帧停留时长')
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preset", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--xd", type=float, default=XD_DEFAULT)
    ap.add_argument("--scripts-dir", default=None,
                    help="compose_motion.py / render_animated.js 所在目录（默认本脚本同目录）")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败（退出码1）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（便于自动化解析）")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    frames = [os.path.join(args.frames_dir, f) for f in sorted(os.listdir(args.frames_dir))
              if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    frames.sort(key=natural_key)
    if not frames:
        print("No frames in " + args.frames_dir, file=sys.stderr)
        return 2
    with open(args.durations_json, encoding="utf-8") as f:
        data = json.load(f)
    durations = data["durations"] if isinstance(data, dict) else list(data)

    scripts_dir = args.scripts_dir or os.path.dirname(os.path.abspath(__file__))
    all_issues = (check_motion(frames, durations, args.fps, args.preset, args.xd)
                  + check_encode(scripts_dir)
                  + check_asset(frames, durations))

    has_fail = any(lv == "FAIL" for lv, _, _ in all_issues)
    has_warn = any(lv == "WARN" for lv, _, _ in all_issues)
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
            "exit_code": code,
            "issues": [{"level": lv, "group": g, "msg": m} for lv, g, m in all_issues],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return code

    if not args.quiet:
        _print_report(all_issues, code, scripts_dir)
    return code


if __name__ == "__main__":
    sys.exit(main())
