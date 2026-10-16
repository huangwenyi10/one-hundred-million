# -*- coding: utf-8 -*-
"""
bg_theme_check.py — 背景色门禁（2026-10-16 作者最终裁定：所有训练营视频背景=纯白 #FFFFFF）

规则（硬门禁）：
  全部 9 营（含读书营）的内容页 + 封面/第一页背景一律纯白 #FFFFFF（白底深字系）；
  本营主题色仅作前景（顶部 150px 主色渐变标题带 / kicker / em / 图表描边 / 强调数字）。
  标题带同时保证左上角白字「作者：@Map」水印在白底上始终有对比、可见。

用法：
  python3 scripts/bg_theme_check.py <PPT.html> [--frames <frames_dir>] [--camp <训练营全名>]

判定（HTML 层）：
  1. 解析 PPT.html :root 的 --slide-bg / --bg / --accent / --hilite / --text；
  2. 推断训练营（可用 --camp 显式指定）；
  3. 内容页背景（--slide-bg 渐变任一端点 / 兜底纯色）必须近白（亮度>0.90 且饱和度<0.08），
     否则 FAIL「背景非纯白」；
  4. 必须存在 .slide.cover{background:#FFFFFF…} 白封面规则（缺 → FAIL）。

判定（帧层，--frames 给定时追加）：
  每帧采样内容区边缘点（避开顶部标题带 y<170、左上角水印区、底部字幕带 y>890），
  取采样点中位数 HSV：所有帧（含封面与内容帧）必须近白，否则 FAIL。

退出码：0 = PASS；1 = FAIL。
"""
import colorsys
import os
import re
import sys

# 主题色表（与 SKILL.md「训练营主题色」一致；main=白底可读加深主色, hilite=标题带/柱状亮端）
CAMP_COLORS = {
    "架构师训练营":   {"main": "#00843D", "deep": "#00572E", "hilite": "#4ADE80"},
    "大数据训练营":   {"main": "#0A5CFF", "deep": "#0A2A6B", "hilite": "#4D8DFF"},
    "AI训练营":       {"main": "#B91C1C", "deep": "#450A0A", "hilite": "#F87171"},
    "产品经理训练营": {"main": "#8B2BFF", "deep": "#3C0A7A", "hilite": "#B47CFF"},
    "前端训练营":     {"main": "#FF7A00", "deep": "#B33C00", "hilite": "#FFA94D"},
    "测试训练营":     {"main": "#00A2A6", "deep": "#00555C", "hilite": "#4FE3E8"},
    "管理训练营":     {"main": "#B58600", "deep": "#B37A00", "hilite": "#FFE066"},
    "软技能训练营":   {"main": "#6D4C41", "deep": "#4E342E", "hilite": "#D7CCC8"},
    "读书训练营":     {"main": "#FF3D7F", "deep": "#8A0B45", "hilite": "#FF3D7F"},
}
READING_CAMP = "读书训练营"
NEAR_WHITE_V = 0.90     # 近白判定：亮度下限
NEAR_WHITE_S = 0.08     # 近白判定：饱和度上限


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
    """按 --accent 与主题色表 RGB 最近匹配推断训练营。"""
    best, best_d = None, 1e9
    for camp, c in CAMP_COLORS.items():
        v = vars_.get("--accent", "")
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
    ok = True
    # 硬规则（2026-10-16 作者最终裁定）：全部 9 营内容页背景一律纯白 #FFFFFF
    for rgb in bgs:
        if not is_near_white(rgb):
            h, s, v = hsv(rgb)
            ok = False
            msgs.append(
                f"内容页背景非纯白 #{'%02X%02X%02X' % rgb}（V={v:.2f},S={s:.2f}）——"
                f"所有训练营背景必须=纯白 #FFFFFF（2026-10-16 裁定）")
    if ok:
        hs = "/".join(f"#{'%02X%02X%02X' % rgb}" for rgb in bgs)
        msgs.append(f"内容页背景=纯白 {hs} ✓（全营白底硬规则）")
    # 封面/第一页必须纯白（.slide.cover 白底规则）
    cover = re.search(r"\.slide\.cover\s*\{[^}]*\}", html)
    cover_bg = cover.group(0) if cover else ""
    if not cover or not re.search(
            r"background\s*:\s*(#fff\b|#ffffff|white)\b", cover_bg, re.I):
        ok = False
        msgs.append("缺少「封面纯白」规则——必须有 .slide.cover{background:#FFFFFF}（白色就是白色）")
    elif ok:
        msgs.append("封面/第一页=纯白 ✓（第一页白硬规则）")
    return ok, camp, msgs


def check_frames(frames_dir, camp):
    """帧层像素抽检：返回 (ok, messages)。所有帧（含封面与内容帧）必须近白。"""
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
    bad = []
    checked = 0
    for idx, fn in enumerate(files):
        im = Image.open(os.path.join(frames_dir, fn)).convert("RGB")
        w, h = im.size
        vals = []
        for x, y in pts:
            px, py = int(x * w / 1920), int(y * h / 1080)
            vals.append(im.getpixel((px, py)))
        # 取中位数 RGB（逐通道）
        med = tuple(sorted(v[i] for v in vals)[len(vals) // 2] for i in range(3))
        checked += 1
        if not is_near_white(med):
            bad.append(f"{fn}: 背景采样 #{'%02X%02X%02X' % med} 非近白（V/S 不符纯白底）")
    if bad:
        return False, [f"帧层抽检 FAIL（{len(bad)}/{checked} 帧）："] + bad[:12] + (
            ["…"] if len(bad) > 12 else [])
    return True, [f"帧层抽检 PASS（{checked} 帧，背景均为纯白）"]


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
        print("  " + m)
    if ok and frames_dir:
        fok, fmsgs = check_frames(frames_dir, camp)
        ok = ok and fok
        for m in fmsgs:
            print("  " + m)
    print(("PASS" if ok else "FAIL") + f": bg_theme_check · {camp or '未知训练营'} · {os.path.basename(path)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
