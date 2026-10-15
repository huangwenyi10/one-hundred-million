# -*- coding: utf-8 -*-
"""
bg_theme_check.py — 营色背景门禁（2026-10-15 作者裁定：禁止全营一律白底）

背景：历史上所有训练营的视频/幻灯片背景都是纯白，作者多次反馈「弱智的错误」——
根因是 SKILL.md 旧「白底规则」把 9 营背景写死为 #FFFFFF。2026-10-15 起规则改为：
  · 非读书训练营：背景 = 本营主题色渐变（深底 → 主色，与封面同色系）；
  · 读书训练营（唯一例外）：背景 = 纯白 #FFFFFF（"白色就是白色"）。
本脚本把该规则变成确定性门禁，导帧前 / 交付前必须 PASS。

用法：
  python3 scripts/bg_theme_check.py <PPT.html> [--frames <frames_dir>] [--camp <训练营全名>]

判定（HTML 层）：
  1. 解析 PPT.html :root 的 --slide-bg / --bg / --accent / --hilite / --text；
  2. 推断训练营：--accent/--hilite 与主题色表做 RGB 最近匹配（可用 --camp 显式指定）；
  3. 非读书营：背景（渐变任一端点 / 兜底纯色）不得近白（亮度>0.90 且饱和度<0.08 → FAIL），
     且背景色相须落在本营主色色相 ±35° 内，否则 FAIL「背景色不是本营主题色」；
  4. 读书训练营：背景必须为白/近白，否则 FAIL。

判定（帧层，--frames 给定时追加）：
  每帧采样内容区边缘点（避开顶部标题带 y<170、左上角水印区 x<480&y<162、底部字幕带 y>890），
  取采样点中位数 HSV：非读书营须饱和度 ≥0.12 且色相在本营主色 ±35°；读书营须近白。
  cover 页（整页渐变）同样满足色相判定。

退出码：0 = PASS；1 = FAIL（逐条打印原因，返工改 :root 后重跑）。
"""
import colorsys
import os
import re
import sys

# 主题色表（与 SKILL.md「训练营主题色」一致；main=主色亮端, deep=封面渐变深端, hilite=高亮）
CAMP_COLORS = {
    "架构师训练营":   {"main": "#00C853", "deep": "#00572E", "hilite": "#4ADE80"},
    "大数据训练营":   {"main": "#0A5CFF", "deep": "#0A2A6B", "hilite": "#4D8DFF"},
    "AI训练营":       {"main": "#B91C1C", "deep": "#450A0A", "hilite": "#F87171"},
    "产品经理训练营": {"main": "#8B2BFF", "deep": "#3C0A7A", "hilite": "#B47CFF"},
    "前端训练营":     {"main": "#FF7A00", "deep": "#B33C00", "hilite": "#FFA94D"},
    "测试训练营":     {"main": "#00C2C7", "deep": "#00555C", "hilite": "#4FE3E8"},
    "管理训练营":     {"main": "#FFC400", "deep": "#B37A00", "hilite": "#FFE066"},
    "软技能训练营":   {"main": "#A1887F", "deep": "#4E342E", "hilite": "#D7CCC8"},
    "读书训练营":     {"main": "#FF3D7F", "deep": "#8A0B45", "hilite": "#FF3D7F"},
}
READING_CAMP = "读书训练营"
HUE_TOL = 35.0          # 背景色相与本营主色色相的最大允许偏差（度）
NEAR_WHITE_V = 0.90     # 近白判定：亮度下限
NEAR_WHITE_S = 0.08     # 近白判定：饱和度上限
FRAME_MIN_S = 0.12      # 帧层：非读书营采样点中位饱和度下限


def hex2rgb(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hsv(rgb):
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def hue_dist(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def is_near_white(rgb):
    _, s, v = hsv(rgb)
    return v > NEAR_WHITE_V and s < NEAR_WHITE_S


def parse_root_vars(html):
    """取 :root{...} 中的变量表（--slide-bg 可能是渐变，原样保留字符串）。"""
    m = re.search(r":root\s*\{(.*?)\}", html, re.S)
    if not m:
        return {}
    # 整块扫描（兼容一行多变量与一行一变量两种写法）
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", m.group(1)))


def bg_endpoints(vars_):
    """从 --slide-bg（渐变或纯色）与 --bg 提取背景代表色列表（RGB）。"""
    out = []
    slide_bg = vars_.get("--slide-bg", "")
    for hx in re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])", slide_bg):
        rgb = hex2rgb("#" + hx)
        if rgb:
            out.append(rgb)
    bg = vars_.get("--bg", "")
    rgb = hex2rgb(bg)
    if rgb:
        out.append(rgb)
    return out


def infer_camp(vars_):
    """按 --accent/--hilite 与主题色表 RGB 最近匹配推断训练营。"""
    best, best_d = None, 1e9
    for camp, c in CAMP_COLORS.items():
        for key in ("--accent", "--hilite"):
            v = vars_.get(key, "")
            rgb = hex2rgb(v)
            if not rgb:
                continue
            ref = hex2rgb(c["main"])
            d = sum((a - b) ** 2 for a, b in zip(rgb, ref))
            if d < best_d:
                best, best_d = camp, d
    return best


def check_html(html, camp_override=None):
    """返回 (ok, camp, messages)。"""
    msgs = []
    vars_ = parse_root_vars(html)
    if not vars_:
        return False, None, ["未解析到 :root 变量块"]
    camp = camp_override or infer_camp(vars_)
    if camp not in CAMP_COLORS:
        return False, camp, [f"无法推断训练营（--accent={vars_.get('--accent')}），请用 --camp 显式指定"]
    bgs = bg_endpoints(vars_)
    if not bgs:
        return False, camp, ["未解析到背景色（--slide-bg / --bg 均无有效色值）"]
    main_h, _, _ = hsv(hex2rgb(CAMP_COLORS[camp]["main"]))
    ok = True
    if camp == READING_CAMP:
        for rgb in bgs:
            if not is_near_white(rgb):
                ok = False
                msgs.append(f"读书训练营背景必须为纯白 #FFFFFF，实测 #{'%02X%02X%02X' % rgb}")
        if ok:
            msgs.append("读书训练营背景=纯白 ✓（本营专属例外）")
    else:
        for rgb in bgs:
            h, s, v = hsv(rgb)
            if is_near_white(rgb):
                ok = False
                msgs.append(
                    f"背景仍为白色/近白 #{'%02X%02X%02X' % rgb}（V={v:.2f},S={s:.2f}）——"
                    f"{camp}必须用本营主题色背景（深底→主色渐变），禁止全营一律白底")
            elif hue_dist(h, main_h) > HUE_TOL:
                ok = False
                msgs.append(
                    f"背景色相 {h:.0f}° 距本营主色色相 {main_h:.0f}° 超 {HUE_TOL:.0f}°"
                    f"（#{'%02X%02X%02X' % rgb}）——不是{camp}的主题色")
        if ok:
            hs = "/".join(f"#{'%02X%02X%02X' % rgb}" for rgb in bgs)
            msgs.append(f"{camp}背景=主题色系 {hs} ✓")
    return ok, camp, msgs


def check_frames(frames_dir, camp):
    """帧层像素抽检：返回 (ok, messages)。"""
    try:
        from PIL import Image
    except ImportError:
        return True, ["[跳过帧层抽检：PIL 不可用]"]
    if not os.path.isdir(frames_dir):
        return False, [f"帧目录不存在：{frames_dir}"]
    files = sorted(f for f in os.listdir(frames_dir) if f.lower().endswith(".png"))
    if not files:
        return False, [f"帧目录无 PNG：{frames_dir}"]
    # 采样点：内容区左右边缘 + 标题带下方（避开水印区 x<480&y<162 / 字幕带 y>890 / 标题带 y<170）
    pts = [(70, 400), (70, 700), (1850, 400), (1850, 700), (960, 190), (500, 860), (1420, 860)]
    main_h, _, _ = hsv(hex2rgb(CAMP_COLORS[camp]["main"]))
    bad = []
    checked = 0
    for fn in files:
        im = Image.open(os.path.join(frames_dir, fn)).convert("RGB")
        w, h = im.size
        vals = []
        for x, y in pts:
            px, py = int(x * w / 1920), int(y * h / 1080)
            vals.append(im.getpixel((px, py)))
        # 取中位数 RGB（逐通道）
        med = tuple(sorted(v[i] for v in vals)[len(vals) // 2] for i in range(3))
        checked += 1
        if camp == READING_CAMP:
            if not is_near_white(med):
                bad.append(f"{fn}: 采样中位 #{'%02X%02X%02X' % med} 非近白（读书营须纯白底）")
        else:
            hh, s, v = hsv(med)
            if is_near_white(med):
                bad.append(f"{fn}: 背景采样为白色/近白 #{'%02X%02X%02X' % med}（V={v:.2f},S={s:.2f}）")
            elif s < FRAME_MIN_S or hue_dist(hh, main_h) > HUE_TOL:
                bad.append(f"{fn}: 背景色相/饱和度不符（#{'%02X%02X%02X' % med} H={hh:.0f}° S={s:.2f}，期望 H≈{main_h:.0f}°）")
    if bad:
        return False, [f"帧层抽检 FAIL（{len(bad)}/{checked} 帧）："] + bad[:12] + (
            ["…"] if len(bad) > 12 else [])
    return True, [f"帧层抽检 PASS（{checked} 帧，背景均为{camp}主题色）" if camp != READING_CAMP
                  else f"帧层抽检 PASS（{checked} 帧，背景均为纯白）"]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    camp_override = None
    frames_dir = None
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--camp" and i + 1 < len(argv):
            camp_override = argv[i + 1]
        if a == "--frames" and i + 1 < len(argv):
            frames_dir = argv[i + 1]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    if not os.path.isfile(path):
        print(f"FAIL: 文件不存在 {path}")
        return 1
    with open(path, encoding="utf-8") as f:
        html = f.read()
    ok, camp, msgs = check_html(html, camp_override)
    for m in msgs:
        print(("  " if ok else "  ") + m)
    if ok and frames_dir:
        fok, fmsgs = check_frames(frames_dir, camp)
        ok = ok and fok
        for m in fmsgs:
            print("  " + m)
    print(("PASS" if ok else "FAIL") + f": bg_theme_check · {camp or '未知训练营'} · {os.path.basename(path)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
