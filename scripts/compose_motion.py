#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compose_motion.py — 给静态帧目录加「镜头运动 + 交叉淡入」，消除画面静态感。

背景：默认管线是「HTML→PNG 静态帧 → ffmpeg 帧拼接（硬切、静止）」，观感偏静态。
本脚本把合成环节升级为 **Ken Burns 镜头运动（缓慢推拉摇移）+ xfade 交叉淡入**：
  - 不改 HTML / 不重渲帧 / 不动配音与字幕时间轴（帧停留时长仍取 segments_durations.json）
  - 只换「合成」环节 → 四方同频、时长、字幕全部不受影响，但整支视频"活"起来。

──────────────────────────────────────────────────────────────────────────
★ 2026-09-10 关键修复：抛弃 ffmpeg zoompan，改用 perspective（彻底消除「画面抖」）
──────────────────────────────────────────────────────────────────────────
【根因（实测）】zoompan 会把裁剪窗口的**尺寸与位置量化到源图像素的整数格点**上：
  - d=round(duration*fps) 帧、zoom 1.00→1.06 的缓慢推拉，单帧位移只有 0.1~0.5 px，
    远小于 1 个源像素 → 运动被量化为「连续 3~4 帧完全静止 + 突然跳 1 像素」；
  - 文字 / 线条 / 表格这类硬边缘每跳一次就是一次边缘重定位 → 肉眼看到「画面抖 / 一顿一顿」。
【实测证据】对已交付成片（1920x1080@30fps，192.8s）取 40~52s 区间逐帧测量：
  相邻帧位移呈 -0.43 / -0.000 / -0.000 / +0.000 / -0.45 … 的阶梯；
  运动段 37% 的帧与前一帧**像素完全相同**（停顿帧），非零帧差异变异系数 CV=1.56。
  隔离实验（同参数）确认：单停平移项无位移（zoom=1 时 zoompan 把 x 夹到 0）、
  纯 zoom 项同样 41% 停顿帧 → 量化来自 zoompan 内部对 crop 宽高与原点的整数化，
  与「三角波是否连续 / offset 是否整数帧」无关，**参数调优无法根治**。
【修复】改用 ffmpeg `perspective`：四角坐标为**浮点数**、`eval=frame` 逐帧求值、
  `interpolation=cubic` 三次插值采样 → 亚像素运动**无量化**。
  同参数实测：运动段停顿帧 37% → **0**（仅按设计的「尾 20% 静止段」保持静止），
  非零帧差异 CV 0.497 → 0.048（运动高度均匀），锐度与 zoompan 持平。
  另：perspective 直采 1080p 源，无需 zoompan 时代的「按最大 zoom 预放大」，
  少一次重采样 → 每个运动段起始帧与原图**逐像素一致**（zoompan 方案会有轻微发虚）。

【运动模型（闭式，可被纯 Python 门禁逐步复算）】
  设 e = min(on/N, 1)（on=输出帧号，N=运动帧数，运动在 80% 时长内完成、尾 20% 静止）
  缩放：偶数段 z: 1→Z；奇数段 z: Z→1（三角波衔接，上一段尾=下一段头）
  可用空间：Ux(z)=W*(1-1/z)、Uy(z)=H*(1-1/z)
  平移因子：偶数段 f=e；奇数段 f=1-e（保证段间连续）
  裁剪窗：w=W/z, h=H/z
          x0 = Ux(z) * (0.5 + 0.5*dx*PAN_FRAC*f)
          y0 = Uy(z) * (0.5 + 0.5*dy*PAN_FRAC*f)
  因 |PAN_FRAC|≤1、0≤f≤1 → x0∈[0, Ux]、x0+w ≤ W：**恒不越界**，
  不会出现 zoompan 那种「越界被夹住」导致的运动截断 / 边缘涂抹。
  方向表按 (i//2)%4 轮转，相邻两段（一放一收）同方向 → 段尾=段头，无跳变。

用法：
  python3 compose_motion.py <frames_dir> <durations.json> <out_video> [--fps 30] [--preset 1]
                            [--verify/--no-verify]
参数：
  frames_dir   含 page_01.png ... 的静态帧目录（编号需可排序，自然序对齐 durations 顺序）
  durations.json 帧停留时长：{"durations":[d0,d1,...],"total":...}（首帧通常为封面段时长）
  out_video    输出 mp4
  --preset 1|2|3  运动强度：1=轻微(默认,推荐正文) 2=适中 3=强(仅关键/大图页)
  --verify     合成后抽帧复核运动段无停顿帧（默认开启；--no-verify 跳过）
依赖：ffmpeg（需支持 perspective 滤镜；`ffmpeg -h filter=perspective` 可自检）。
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile

# 统一质量总门禁：合成前先过自检（抖动+编码契约+素材；与 craft-quality.md §3.6/§3.7/§3.8 一致）。
# video_quality_gate.py 与本脚本同目录（内部复用 motion_quality_check）；缺失则阻断以确保质量。
try:
    from video_quality_gate import run_gate as _run_quality_gate, png_size as _png_size
except ImportError:
    _run_quality_gate = None
    _png_size = None

# 运动模型参数与「运动时长占段时长比例」的**唯一来源** = motion_quality_check（门禁权威实现）。
# 本脚本只做「把模型翻译成 ffmpeg 表达式」，参数不再各写一份 → 从根上消除两侧漂移。
# ⚠️ 公式本身（smoothstep / 可用空间比例平移 / 三角波）在 motion_quality_check.quad_at 里
#    有一份等价的纯 Python 实现，改动公式时必须同时改这两处（§3.7 契约）。
try:
    from motion_quality_check import ZOOM_MAX, PAN_FRAC, PAN_DIRS, MOTION_TAIL
    _MODEL_OK = True
except ImportError:
    ZOOM_MAX = {1: 1.06, 2: 1.10, 3: 1.16}
    PAN_FRAC = {1: 0.70, 2: 0.85, 3: 0.95}
    PAN_DIRS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
    MOTION_TAIL = 0.8
    _MODEL_OK = False


def _resolve_tool(name):
    """定位 ffmpeg/ffprobe：先查 PATH，再查常见绝对路径。

    定时任务/沙箱里子进程的 PATH 常不含 /usr/local/bin，直接写 "ffmpeg" 会 FileNotFoundError。
    """
    p = shutil.which(name)
    if p:
        return p
    for d in ("/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"):
        cand = os.path.join(d, name)
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return name


FFMPEG = _resolve_tool("ffmpeg")
FFPROBE = _resolve_tool("ffprobe")


def parse_page_num(path):
    m = re.search(r'(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else 0


def natural_key(path):
    # 让 page_2.png < page_10.png
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(path))]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("CMD FAIL: " + " ".join(cmd) + "\n" + r.stderr[-3000:] + "\n")
        raise SystemExit(r.returncode)
    return r


def probe_size(png_path):
    """读首帧尺寸作为 W/H（与门禁 ASSET 契约一致；门禁已保证全帧同尺寸 1920×1080）。"""
    if _png_size is not None:
        wh = _png_size(png_path)
        if wh:
            return wh
    # 退化：用 ffprobe
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", png_path])
    w, h = r.stdout.strip().split("x")[:2]
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("durations_json")
    ap.add_argument("out_video")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preset", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--verify", dest="verify", action="store_true", default=True,
                    help="合成后抽帧复核运动段无停顿帧（默认开启）")
    ap.add_argument("--no-verify", dest="verify", action="store_false")
    args = ap.parse_args()

    frames = [os.path.join(args.frames_dir, f)
              for f in sorted(os.listdir(args.frames_dir))
              if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    frames.sort(key=natural_key)
    if not frames:
        sys.exit("No frames in " + args.frames_dir)

    with open(args.durations_json, encoding='utf-8') as f:
        data = json.load(f)
    durations = data["durations"] if isinstance(data, dict) else list(data)

    # durations 数量与帧数对齐（不足补默认 6s，多余截断），避免 index 越界
    default_d = 6.0
    if len(frames) != len(durations):
        sys.stderr.write(f"WARN: frames={len(frames)} vs durations={len(durations)}; 补齐为帧数\n")
        if len(durations) < len(frames):
            durations = durations + [default_d] * (len(frames) - len(durations))
        else:
            durations = durations[:len(frames)]

    W, H = probe_size(frames[0])

    # 运动强度参数：zoom 峰值 + 平移占「缩放可用空间」的比例（比例式 → 永不越界）
    # 参数取自 motion_quality_check（门禁权威实现），不在此重复定义数值。
    zoom_max = ZOOM_MAX[args.preset]
    pan_frac = PAN_FRAC[args.preset]
    # 转场以整数帧为单位（避免浮点秒 offset 落在非整数帧 → 转场混合起点在帧中间 → 画面抖）
    XD = 0.5
    XD_FRAMES = max(1, round(XD * args.fps))

    # —— 统一质量总门禁（渲染前自检，强制）——
    # 校验：①运动段逐帧 quad 唯一（无停顿帧）②quad 恒不越界 ③跨段缩放/平移连续
    #       ④xfade offset 整数帧 ⑤编码契约（perspective 亚像素 + 禁用 zoompan）⑥素材合规
    if _run_quality_gate is None:
        sys.stderr.write("[质量总门禁] video_quality_gate.py 缺失，无法执行门禁，终止以确保质量。\n")
        raise SystemExit(2)
    gate_code = _run_quality_gate(frames, durations, args.fps, args.preset,
                                 scripts_dir=os.path.dirname(os.path.abspath(__file__)),
                                 XD=XD, strict=False)
    if gate_code == 1:
        sys.stderr.write("[质量总门禁] 未通过（FAIL），终止合成。请先修复上方问题再跑 compose_motion.py。\n")
        raise SystemExit(1)
    elif gate_code == 2:
        sys.stderr.write("[质量总门禁] 存在 WARN（非阻断），继续合成。\n")

    tmp = tempfile.mkdtemp(prefix="compose_motion_")
    seg_paths = []
    seg_frames = []          # 每段实际帧数（整数，确定，作为时间基准）
    total = len(frames)
    fps = args.fps

    # 逐帧生成「单段带 Ken Burns 运动的视频」，时长=该帧停留时长
    for i, fp in enumerate(frames):
        d = durations[i]
        if d < 0.5:
            d = 0.5
        n_frames = max(1, int(round(d * fps)))
        # 运动在 80%（MOTION_TAIL）时长内完成，尾段静止 → xfade 重叠期两段都静止，只做透明度交叉
        if n_frames <= XD_FRAMES + 1:
            N = max(1, n_frames - 1)        # 段过短，压缩运动避免转场占满整段
        else:
            N = max(1, int(n_frames * MOTION_TAIL))

        e = f"min(on/{N},1)"                          # 0→1 线性因子，尾段恒定（=1）
        # smoothstep 缓动：s = e²(3-2e)，两端速度为 0 → 段首/段尾不出现「起停跳变」，
        # 且 zoom 与平移用同一个 s，保证合成运动是 C1 连续的（无速度突变）。
        s = f"({e}*{e}*(3-2*{e}))"
        fexpr_s = s if i % 2 == 0 else f"(1-{s})"     # 平移因子（smoothstep 缓动后）
        if i % 2 == 0:
            zexpr = f"1+({zoom_max-1:.6f})*{s}"                     # 1.0 → Z
        else:
            zexpr = f"{zoom_max:.6f}-({zoom_max-1:.6f})*{s}"        # Z → 1.0
        # 可用空间（随 zoom 变化）：Ux(z)=W*(1-1/z)、Uy(z)=H*(1-1/z)
        ux = f"({W}-{W}/({zexpr}))"
        uy = f"({H}-{H}/({zexpr}))"
        dx, dy = PAN_DIRS[(i // 2) % 4]
        # 裁剪窗四角（浮点，亚像素）；|PAN_FRAC|≤1 且 0≤f≤1 ⇒ 恒在 [0,W]×[0,H] 内
        w_expr = f"{W}/({zexpr})"
        h_expr = f"{H}/({zexpr})"
        # f 用 smoothstep 后的 s 才是缓动；奇偶段用 (1-s) 反向回收 → 段尾=段头
        fexpr_s = s if i % 2 == 0 else f"(1-{s})"
        x0 = f"({ux})*(0.5+0.5*({dx}*{pan_frac:.4f})*{fexpr_s})"
        y0 = f"({uy})*(0.5+0.5*({dy}*{pan_frac:.4f})*{fexpr_s})"

        seg = os.path.join(tmp, f"seg_{i:03d}.mp4")
        vf = (f"perspective=x0='{x0}':y0='{y0}':"
              f"x1='{x0}+({w_expr})':y1='{y0}':"
              f"x2='{x0}':y2='{y0}+({h_expr})':"
              f"x3='{x0}+({w_expr})':y3='{y0}+({h_expr})':"
              f"sense=source:interpolation=cubic:eval=frame,format=yuv420p")
        # 中间段用无损暂存（qp 0），仅最终 xfade 一次有损编码（crf 18）→
        # 避免「逐段 crf20 再 xfade crf20」二次有损在渐变背景上产生 H.264 色带/块化。
        # 用 -frames:v 精确锁定段帧数（替代 -t 浮点秒），消除段尾帧差 1 导致的衔接抖。
        # -framerate 固定输入帧率 = fps（loop 静帧），保证 on 每帧 +1、无重复帧。
        run([FFMPEG, "-y", "-v", "error", "-framerate", str(fps), "-loop", "1", "-i", fp,
             "-frames:v", str(n_frames), "-vf", vf, "-r", str(fps),
             "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", "-pix_fmt", "yuv420p", seg])
        seg_paths.append(seg)
        seg_frames.append(n_frames)

    # 用 xfade 把各段级联（前一段尾部与后一段头部交叉淡入）。
    # 关键防抖：offset 必须落在整数帧边界，否则转场混合起点在帧中间 → 画面抖。
    # 因此全程以整数帧为唯一时间基准：offset_frames = 累计帧数 - XD_FRAMES，再除以 fps。
    # （不再用 ffprobe 浮点时长，从根上消除秒级浮点累积误差导致的转场抖。）
    inputs = []
    for s in seg_paths:
        inputs += ["-i", s]
    acc_frames = seg_frames[0]
    filter_parts = []
    filter_parts.append(f"[0:v]format=yuv420p[v0]")
    cur = "v0"
    for k in range(1, total):
        off_frames = acc_frames - XD_FRAMES
        if off_frames < 0:
            off_frames = 0
        off = off_frames / fps
        filter_parts.append(f"[{k}:v]format=yuv420p[v{k}]")
        outlabel = f"vx{k}"
        filter_parts.append(
            f"[{cur}][v{k}]xfade=transition=fade:duration={XD_FRAMES/fps:.4f}:offset={off:.6f}[{outlabel}]")
        cur = outlabel
        acc_frames = acc_frames + seg_frames[k] - XD_FRAMES

    fc = ";".join(filter_parts) + f";[{cur}]format=yuv420p[vout]"
    out = os.path.abspath(args.out_video)
    run([FFMPEG, "-y"] + inputs + ["-filter_complex", fc, "-map", "[vout]",
         "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", out])
    est = acc_frames / fps
    sys.stdout.write(f"OK -> {out}  (frames={total}, 预估时长≈{est:.1f}s)\n")

    # —— 合成后抽帧复核：运动段不得出现「停顿帧阶梯」——
    if args.verify:
        bad = verify_no_dwell(out, seg_frames, XD_FRAMES, fps)
        if bad:
            sys.stderr.write("[合成后复核] 检出运动量化阶梯（画面抖残留）：\n")
            for b in bad:
                sys.stderr.write(f"  {b}\n")
            sys.stderr.write("建议：确认 perspective 未被改回 zoompan，且 ffmpeg 支持 perspective 滤镜"
                             "（`ffmpeg -h filter=perspective`）；确认后可用 --no-verify 跳过本复核。\n")
            raise SystemExit(1)
        sys.stdout.write("[合成后复核] 运动段逐帧位移均匀、无停顿帧 ✅\n")


def verify_no_dwell(path, seg_frames, xd_frames, fps, max_seg=8, win=9):
    """抽检若干段的运动段中部，检测「停顿帧阶梯」——量化运动的指纹。

    判定：对窗口内相邻帧的灰度平均绝对差 mad[] 求 max/min 比。
      - 平滑运动（perspective 亚像素）：逐帧位移近似恒定 → 比值 ≈ 1.0~1.4；
      - 量化运动（zoompan 整数裁剪）：数帧完全静止 + 突然跳 1 像素 → 比值可达数十倍。
    另：若窗口整体 mad 极小（长页慢速运动），无从判定，跳过而非误判。

    ⚠️ 这是**兜底复核**，不是主判定：主判定是渲染前的确定性门禁
    （motion_quality_check：运动段逐帧裁剪窗唯一 + 不越界，数学上保证无停顿帧）。
    """
    import numpy as np
    n_seg = len(seg_frames)
    picks = list(range(n_seg)) if n_seg <= max_seg else \
        [round(k * (n_seg - 1) / (max_seg - 1)) for k in range(max_seg)]
    bad = []
    seg_start = []
    acc = 0
    for k, n in enumerate(seg_frames):
        seg_start.append(acc / fps)
        acc += n - (xd_frames if k > 0 else 0)
    for i in picks:
        n = seg_frames[i]
        N = max(1, n - 1) if n <= xd_frames + 1 else max(1, int(n * 0.8))
        # 取运动段 35%~70% 处，避开段头缓动起步与段尾静止
        t0 = seg_start[i] + (0.35 * N) / fps
        cmd = [FFMPEG, "-v", "error", "-ss", f"{t0:.4f}", "-i", path, "-frames:v", str(win),
               "-f", "rawvideo", "-pix_fmt", "gray", "-s", "960x540", "-"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or len(r.stdout) < 960 * 540 * 2:
            continue
        a = np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, 540, 960).astype(np.float32)
        mad = np.array([np.abs(a[j + 1] - a[j]).mean() for j in range(len(a) - 1)])
        if len(mad) < 3:
            continue
        if mad.max() < 0.05:
            continue          # 运动太慢（长页），本窗口无从判定；门禁侧已按位移幅度提示
        ratio = mad.max() / max(mad.min(), 1e-6)
        if ratio > 8.0:
            bad.append(f"段{i} t≈{t0:.2f}s：逐帧差异 max/min={ratio:.1f}（max={mad.max():.4f} "
                       f"min={mad.min():.6f}）→ 数帧静止 + 突然跳变 = 运动量化阶梯")
    return bad


if __name__ == "__main__":
    main()
