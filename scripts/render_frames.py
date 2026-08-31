# -*- coding: utf-8 -*-
"""
render_frames.py — PIL 渲染每页 1920x1080 帧（读书训练营·书墨棕主题）
读取 <build_dir>/pages_data.py 的 PAGES / DIAGRAMS / TITLE，
输出 <build_dir>/frames/page_NN.png（每页一帧，字幕另由 render_subs2 烧录）。

原创示意图：全部用 PIL 原语绘制（忠于原书概念，不复制书稿像素）。
用法: python3 render_frames.py <build_dir>
"""
import os, sys, glob
import importlib.util
from PIL import Image, ImageDraw, ImageFont

# ---- 书墨棕主题 ----
BG_TOP   = (58, 42, 34)    # 3A2A22
BG_BOT   = (43, 31, 24)    # 2B1F18
PANEL    = (78, 56, 44)    # 4E382C 半透明面板底
ACCENT   = (161, 136, 127) # A1887F 主色
HILITE   = (215, 204, 200) # D7CCC8 高亮
TEXT     = (239, 235, 230) # EFEBE6 正文
SUBTLE   = (176, 166, 158) # 次级文字
WHITE    = (255, 255, 255)

W, H = 1920, 1080
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"

def load_font(size, index=0, bold=False):
    try:
        return ImageFont.truetype(FONT_PATH, size, index=index)
    except Exception:
        return ImageFont.load_default()

F_TITLE = load_font(52)
F_BODY  = load_font(36)
F_DIAG  = load_font(30)
F_BIG   = load_font(72)
F_SMALL = load_font(26)
F_MONO  = load_font(28)


def get_text(draw, text, font, max_w):
    """按 max_w 折行（CJK 逐字，ASCII 按词），返回行列表。"""
    lines = []
    cur = ""
    for ch in text:
        test = cur + ch
        if draw.textlength(test, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def rr(draw, box, radius=18, fill=None, outline=None, width=3):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, x1, y1, x2, y2, color, width=4):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 14
    for da in (math.radians(150), math.radians(210)):
        draw.line([(x2, y2), (x2 + L * math.cos(ang + da), y2 + L * math.sin(ang + da))],
                  fill=color, width=width)


def box_text(draw, cx, cy, w, h, title, lines, fill=PANEL, tcolor=WHITE, lcolor=TEXT):
    x0, y0 = cx - w // 2, cy - h // 2
    rr(draw, [x0, y0, x0 + w, y0 + h], radius=14, fill=fill, outline=ACCENT, width=2)
    if title:
        tw = draw.textlength(title, font=F_DIAG)
        draw.text((cx - tw / 2, y0 + 12), title, font=F_DIAG, fill=tcolor)
    yy = y0 + (44 if title else 18)
    for ln in lines:
        lw = draw.textlength(ln, font=F_BODY)
        draw.text((cx - lw / 2, yy), ln, font=F_BODY, fill=lcolor)
        yy += 44


# ---------- 示意图绘制 ----------
def draw_compare2(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("caption"):
        cw = draw.textlength(spec["caption"], font=F_DIAG)
        draw.text((x0 + w / 2 - cw / 2, y0 - 38), spec["caption"], font=F_DIAG, fill=HILITE)
    pw = w // 2 - 40
    ph = h - 10
    for side, pan in (("panel_left", spec["panel_left"]), ("panel_right", spec["panel_right"])):
        cx = x0 + (w * 0.25 if side == "panel_left" else w * 0.75)
        cy = y0 + h / 2
        rr(draw, [cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2], radius=16,
           fill=PANEL, outline=ACCENT, width=3)
        tw = draw.textlength(pan["title"], font=F_DIAG)
        draw.text((cx - tw / 2, cy - ph / 2 + 22), pan["title"], font=F_DIAG, fill=HILITE)
        bw = draw.textlength(pan["big"], font=F_BIG)
        draw.text((cx - bw / 2, cy - 30), pan["big"], font=F_BIG, fill=WHITE)
        sw = draw.textlength(pan["sub"], font=F_BODY)
        draw.text((cx - sw / 2, cy + 50), pan["sub"], font=F_BODY, fill=SUBTLE)


def draw_flow(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    steps = spec["steps"]
    n = len(steps)
    bw = (w - (n - 1) * 70) // n
    bh = 90
    cy = y0 + h / 2
    for i, s in enumerate(steps):
        cx = x0 + bw / 2 + i * (bw + 70)
        box_text(draw, cx, cy, bw, bh, None, [s])
        if i < n - 1:
            arrow(draw, cx + bw / 2 + 6, cy, cx + bw / 2 + 64, cy, ACCENT, 5)


def draw_flow2(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    cols = spec["cols"]
    cw = w // 2 - 40
    ch = h - 30
    for ci, col in enumerate(cols):
        cx = x0 + (w * 0.25 if ci == 0 else w * 0.75)
        cy0 = y0 + 30
        rr(draw, [cx - cw / 2, cy0, cx + cw / 2, cy0 + 46], radius=12, fill=ACCENT)
        lw = draw.textlength(col["label"], font=F_DIAG)
        draw.text((cx - lw / 2, cy0 + 9), col["label"], font=F_DIAG, fill=WHITE)
        steps = col["steps"]
        sh = (ch - 70) // len(steps)
        for si, st in enumerate(steps):
            sxc = cx
            syc = cy0 + 70 + sh / 2 + si * sh
            box_text(draw, sxc, syc, cw - 30, sh - 16, None, [st])
            if si < len(steps) - 1:
                arrow(draw, sxc, syc + sh / 2 - 8, sxc, syc + sh / 2 + 8 + (sh - 16) / 2, ACCENT, 4)


def draw_levels(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    rows = spec["rows"]
    n = len(rows)
    rh = (h - 30) // n
    for i, r in enumerate(rows):
        ry = y0 + 20 + i * rh
        shade = tuple(min(255, PANEL[j] + i * 10) for j in range(3))
        rr(draw, [x0 + 20, ry, x0 + w - 20, ry + rh - 14], radius=12, fill=shade, outline=ACCENT, width=2)
        rw = draw.textlength(r, font=F_BODY)
        draw.text((x0 + w / 2 - rw / 2, ry + rh / 2 - 22), r, font=F_BODY, fill=WHITE)
    if spec.get("note"):
        nw = draw.textlength(spec["note"], font=F_SMALL)
        draw.text((x0 + w / 2 - nw / 2, y0 + h - 4), spec["note"], font=F_SMALL, fill=HILITE)


def draw_tree(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    root_cx, root_cy = x0 + w / 2, y0 + 70
    mid_cy = y0 + h * 0.45
    leaf_cy = y0 + h - 70
    mids = spec.get("mid", [])
    leaves = spec.get("leaf", [])
    mw = (w - 40) // max(1, len(mids)) - 20
    lw = (w - 40) // max(1, len(leaves)) - 20
    mid_xs, leaf_xs = [], []
    for i, m in enumerate(mids):
        cx = x0 + 20 + mw / 2 + i * (mw + 20)
        mid_xs.append(cx)
        box_text(draw, cx, mid_cy, mw, 64, None, [m])
        arrow(draw, root_cx + (cx - root_cx) * 0.3, root_cy + 30, cx, mid_cy - 34, ACCENT, 3)
    for i, lf in enumerate(leaves):
        cx = x0 + 20 + lw / 2 + i * (lw + 20)
        leaf_xs.append(cx)
        box_text(draw, cx, leaf_cy, lw, 64, None, [lf], fill=(60, 44, 36))
        mi = min(len(mids) - 1, i * len(mids) // max(1, len(leaves)))
        arrow(draw, mid_xs[mi], mid_cy + 34, cx, leaf_cy - 34, ACCENT, 3)
    box_text(draw, root_cx, root_cy, 200, 64, None, [spec.get("root", "root")], fill=ACCENT)
    if spec.get("note"):
        nw = draw.textlength(spec["note"], font=F_SMALL)
        draw.text((x0 + w / 2 - nw / 2, y0 + h + 2), spec["note"], font=F_SMALL, fill=HILITE)


def draw_colstore(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    rows = spec["rows"]
    n = len(rows)
    cw = (w - 40) // n - 20
    hh = (h - 40) // (len(rows[0][1]) + 1)
    for i, (col, vals) in enumerate(rows):
        cx = x0 + 20 + cw / 2 + i * (cw + 20)
        rr(draw, [cx - cw / 2, y0 + 30, cx + cw / 2, y0 + 30 + hh], radius=10, fill=ACCENT)
        cw2 = draw.textlength(col, font=F_BODY)
        draw.text((cx - cw2 / 2, y0 + 30 + hh / 2 - 18), col, font=F_BODY, fill=WHITE)
        for j, v in enumerate(vals):
            ry = y0 + 30 + hh + j * hh + 6
            rr(draw, [cx - cw / 2, ry, cx + cw / 2, ry + hh - 12], radius=8, fill=PANEL, outline=ACCENT, width=1)
            vw = draw.textlength(v, font=F_SMALL)
            draw.text((cx - vw / 2, ry + hh / 2 - 16), v, font=F_SMALL, fill=TEXT)
    if spec.get("note"):
        nw = draw.textlength(spec["note"], font=F_SMALL)
        draw.text((x0 + w / 2 - nw / 2, y0 + h + 2), spec["note"], font=F_SMALL, fill=HILITE)


def draw_tag(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    fields = spec["fields"]
    n = len(fields)
    rh = (h - 30) // n
    for i, (tag, name, typ) in enumerate(fields):
        ry = y0 + 20 + i * rh
        rr(draw, [x0 + 20, ry, x0 + w - 20, ry + rh - 14], radius=10, fill=PANEL, outline=ACCENT, width=2)
        line = f"[{tag}]  {name} : {typ}"
        lw = draw.textlength(line, font=F_MONO)
        draw.text((x0 + w / 2 - lw / 2, ry + rh / 2 - 18), line, font=F_MONO, fill=WHITE)
    if spec.get("note"):
        nw = draw.textlength(spec["note"], font=F_SMALL)
        draw.text((x0 + w / 2 - nw / 2, y0 + h + 2), spec["note"], font=F_SMALL, fill=HILITE)


def draw_schemapair(draw, box, spec):
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    pw = w // 2 - 50
    ph = h - 30
    for side, key, label in (("writer", "writer", "写者 schema"), ("reader", "reader", "读者 schema")):
        cx = x0 + (w * 0.25 if side == "writer" else w * 0.75)
        cy = y0 + 30
        rr(draw, [cx - pw / 2, cy, cx + pw / 2, cy + ph], radius=14, fill=PANEL, outline=ACCENT, width=3)
        lw = draw.textlength(label, font=F_DIAG)
        draw.text((cx - lw / 2, cy + 14), label, font=F_DIAG, fill=HILITE)
        items = spec[key]
        ih = (ph - 40) // len(items)
        for j, it in enumerate(items):
            iy = cy + 40 + j * ih + ih / 2
            iw = draw.textlength(it, font=F_MONO)
            draw.text((cx - iw / 2, iy - 16), it, font=F_MONO, fill=WHITE)
    arrow(draw, x0 + w / 2 - 30, y0 + h / 2, x0 + w / 2 + 30, y0 + h / 2, HILITE, 5)
    if spec.get("note"):
        nw = draw.textlength(spec["note"], font=F_SMALL)
        draw.text((x0 + w / 2 - nw / 2, y0 + h + 2), spec["note"], font=F_SMALL, fill=HILITE)


def draw_topology(draw, box, spec):
    """节点拓扑图：nodes=[{id,x,y,label,sub?,accent?,r?}] (x,y 为 0~1 比例)，edges=[{from,to,label?}]"""
    import math
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    pos = {}
    for nd in spec["nodes"]:
        cx, cy = x0 + nd["x"] * w, y0 + nd["y"] * h
        pos[nd["id"]] = (cx, cy)
        r = nd.get("r", 50)
        col = ACCENT if nd.get("accent") else PANEL
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=HILITE, width=3)
        lw = draw.textlength(nd["label"], font=F_DIAG)
        draw.text((cx - lw / 2, cy - 18), nd["label"], font=F_DIAG, fill=WHITE)
        if nd.get("sub"):
            sw = draw.textlength(nd["sub"], font=F_SMALL)
            draw.text((cx - sw / 2, cy + 6), nd["sub"], font=F_SMALL, fill=SUBTLE)
    for e in spec.get("edges", []):
        ax, ay = pos[e["from"]]; bx, by = pos[e["to"]]
        ang = math.atan2(by - ay, bx - ax)
        sx, sy = ax + math.cos(ang) * 50, ay + math.sin(ang) * 50
        ex, ey = bx - math.cos(ang) * 50, by - math.sin(ang) * 50
        arrow(draw, sx, sy, ex, ey, ACCENT, 4)
        if e.get("label"):
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            mw = draw.textlength(e["label"], font=F_SMALL)
            draw.text((mx - mw / 2, my - 20), e["label"], font=F_SMALL, fill=HILITE)


def draw_steps(draw, box, spec):
    """竖向编号步骤：steps=[文本,...]"""
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    steps = spec["steps"]
    n = len(steps)
    gap = (h - 20) / n
    cx = x0 + 56
    for i, s in enumerate(steps):
        cy = y0 + 20 + gap / 2 + i * gap
        draw.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=ACCENT, outline=HILITE, width=3)
        dw = draw.textlength(str(i + 1), font=F_DIAG)
        draw.text((cx - dw / 2, cy - 16), str(i + 1), font=F_DIAG, fill=WHITE)
        lines = get_text(draw, s, F_BODY, w - 160)
        yy = cy - len(lines) * 22
        for ln in lines:
            draw.text((x0 + 110, yy), ln, font=F_BODY, fill=TEXT)
            yy += 44
        if i < n - 1:
            arrow(draw, cx, cy + 28, cx, cy + gap - 28, ACCENT, 3)


def draw_matrix(draw, box, spec):
    """表格矩阵：header=[列名], rows=[[单元格,...]]；首列左对齐强调，其余居中。"""
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    header = spec["header"]; rows = spec["rows"]
    cols = len(header)
    cw = w / cols
    rh = (h - 10) / (len(rows) + 1)
    for j, htxt in enumerate(header):
        cx = x0 + cw * j + cw / 2
        draw.rectangle([x0 + cw * j, y0, x0 + cw * (j + 1), y0 + rh], outline=ACCENT, width=2, fill=(60, 44, 36))
        tw = draw.textlength(htxt, font=F_SMALL)
        draw.text((cx - tw / 2, y0 + rh / 2 - 14), htxt, font=F_SMALL, fill=HILITE)
    for i, row in enumerate(rows):
        ry = y0 + (i + 1) * rh
        for j, cell in enumerate(row):
            cx = x0 + cw * j + cw / 2
            fill = (52, 38, 30) if j == 0 else PANEL
            draw.rectangle([x0 + cw * j, ry, x0 + cw * (j + 1), ry + rh], outline=ACCENT, width=1, fill=fill)
            cw2 = draw.textlength(cell, font=F_SMALL)
            draw.text((cx - cw2 / 2, ry + rh / 2 - 14), cell, font=F_SMALL, fill=TEXT)


def draw_spectrum(draw, box, spec):
    """一致性光谱：bands=[{label}] 从左到右 强->弱，颜色递减。"""
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    bands = spec["bands"]
    n = len(bands)
    bw = w / n
    bh = h - 64
    by = y0 + 28
    for i, b in enumerate(bands):
        bx = x0 + bw * i
        if n > 1:
            shade = tuple(int(PANEL[k] + (ACCENT[k] - PANEL[k]) * (1 - i / (n - 1))) for k in range(3))
        else:
            shade = ACCENT
        draw.rectangle([bx + 4, by, bx + bw - 4, by + bh], fill=shade, outline=HILITE, width=2)
        lw = draw.textlength(b["label"], font=F_DIAG)
        draw.text((bx + bw / 2 - lw / 2, by + bh / 2 - 16), b["label"], font=F_DIAG, fill=WHITE)
        if b.get("sub"):
            sw = draw.textlength(b["sub"], font=F_SMALL)
            draw.text((bx + bw / 2 - sw / 2, by + bh / 2 + 18), b["sub"], font=F_SMALL, fill=SUBTLE)
    dw = draw.textlength("强 ←—————————→ 弱", font=F_SMALL)
    draw.text((x0 + w / 2 - dw / 2, y0 + h - 22), "强 ←—————————→ 弱", font=F_SMALL, fill=SUBTLE)


def draw_triangle(draw, box, spec):
    """等价三角：corners=[3标签]，center 默认『三者等价』。"""
    import math
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    cx, cy = x0 + w / 2, y0 + h / 2 + 16
    R = min(w, h) / 2 - 46
    pts = [(cx, cy - R), (cx - R * 0.866, cy + R * 0.5), (cx + R * 0.866, cy + R * 0.5)]
    draw.polygon(pts, outline=HILITE, width=3)
    for p, lb in zip(pts, spec["corners"]):
        lw = draw.textlength(lb, font=F_DIAG)
        off = -34 if p[1] < cy else 12
        draw.text((p[0] - lw / 2, p[1] + off), lb, font=F_DIAG, fill=WHITE)
    mw = draw.textlength(spec.get("center", "三者等价"), font=F_DIAG)
    draw.text((cx - mw / 2, cy - 18), spec.get("center", "三者等价"), font=F_DIAG, fill=HILITE)


def draw_timeline(draw, box, spec):
    """横向时间轴：events=[{label}] 沿轴均匀分布，上下交错标注。"""
    x0, y0, w, h = box
    if spec.get("title"):
        tw = draw.textlength(spec["title"], font=F_DIAG)
        draw.text((x0 + w / 2 - tw / 2, y0 - 38), spec["title"], font=F_DIAG, fill=HILITE)
    events = spec["events"]
    n = len(events)
    y_axis = y0 + h / 2
    draw.line([(x0 + 40, y_axis), (x0 + w - 40, y_axis)], fill=ACCENT, width=3)
    for i, e in enumerate(events):
        tx = x0 + 60 + (w - 120) * i / max(1, n - 1)
        draw.ellipse([tx - 9, y_axis - 9, tx + 9, y_axis + 9], fill=HILITE)
        lw = draw.textlength(e["label"], font=F_SMALL)
        yy = y_axis - 54 if i % 2 == 0 else y_axis + 18
        draw.text((tx - lw / 2, yy), e["label"], font=F_SMALL, fill=TEXT)


DIAG_DISPATCH = {
    "compare2": draw_compare2, "flow": draw_flow, "flow2": draw_flow2,
    "levels": draw_levels, "tree": draw_tree, "colstore": draw_colstore,
    "tag": draw_tag, "schemapair": draw_schemapair,
    "topology": draw_topology, "steps": draw_steps, "matrix": draw_matrix,
    "spectrum": draw_spectrum, "triangle": draw_triangle, "timeline": draw_timeline,
}


def render_page(page, idx, out_path):
    img = Image.new("RGB", (W, H), BG_BOT)
    draw = ImageDraw.Draw(img)
    # 渐变背景
    for y in range(H):
        t = y / H
        c = tuple(int(BG_TOP[k] + (BG_BOT[k] - BG_TOP[k]) * t) for k in range(3))
        draw.line([(0, y), (W, y)], fill=c)
    # 顶部装饰条
    draw.rectangle([0, 0, W, 8], fill=ACCENT)
    # 标题（y≈96，避让左上角水印区）
    title = page["title"]
    tl = get_text(draw, title, F_TITLE, W - 240)
    ty = 96
    for ln in tl:
        lw = draw.textlength(ln, font=F_TITLE)
        draw.text((110, ty), ln, font=F_TITLE, fill=WHITE)
        ty += 62
    # 要点（收顶 85%，y 直到 ~430）
    py = ty + 26
    for pt in page.get("points", []):
        lines = get_text(draw, "· " + pt, F_BODY, W - 260)
        for ln in lines:
            draw.text((130, py), ln, font=F_BODY, fill=TEXT)
            py += 46
            if py > 430:
                break
        if py > 430:
            break
    # 示意图（y 470~870，避开底部字幕带 918+）
    spec = DIAGRAMS.get(idx)
    if spec:
        box = [100, 470, W - 200, 398]  # [x0, y0, 宽, 高]；高 398 → 底部 y≈868，给字幕带(918+)留白
        fn = DIAG_DISPATCH.get(spec["type"])
        if fn:
            fn(draw, box, spec)
    img.save(out_path)


def main():
    build_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    build_dir = os.path.abspath(build_dir)
    spec = importlib.util.spec_from_file_location("pages_data", os.path.join(build_dir, "pages_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    global DIAGRAMS
    DIAGRAMS = getattr(mod, "DIAGRAMS", {})
    pages = mod.PAGES
    frames_dir = os.path.join(build_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    for i, p in enumerate(pages):
        out = os.path.join(frames_dir, f"page_{i:02d}.png")
        render_page(p, i, out)
        print(f"  frame {i:02d}/{len(pages)-1}: {p['title']}")
    print(f"OK: {len(pages)} 帧 -> {frames_dir}")


if __name__ == "__main__":
    main()
