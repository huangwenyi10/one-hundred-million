# -*- coding: utf-8 -*-
"""
gen_ppt.py — 生成交付物 _PPT.html（读书训练营·书墨棕主题，16:9，键盘翻页）
直接嵌入 render_frames 产出的页面帧（base64），保证与视频画面一致；
每页附标题字幕。输出到标题文件夹（build 的上级目录）。
用法: python3 gen_ppt.py <build_dir>
"""
import os, sys, base64, importlib.util
from PIL import Image

ACCENT = "#A1887F"
HILITE = "#D7CCC8"
BG = "#2B1F18"


def main():
    build_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    build_dir = os.path.abspath(build_dir)
    spec = importlib.util.spec_from_file_location("pages_data", os.path.join(build_dir, "pages_data.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pages = mod.PAGES
    title = getattr(mod, "TITLE", "PPT")
    frames_dir = os.path.join(build_dir, "frames")
    frames = sorted(glob_safe(frames_dir))
    slides = []
    for i, p in enumerate(pages):
        fp = os.path.join(frames_dir, f"page_{i:02d}.png")
        if not os.path.exists(fp):
            continue
        with open(fp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        slides.append((p.get("title", ""), b64))
    slides_js = ",\n".join(f'{{"t":{title_json(t)!r},"img":{img!r}}}' for t, img in slides)
    html = TEMPLATE.replace("{{TITLE}}", title).replace("{{SLIDES}}", slides_js)
    out = os.path.join(os.path.dirname(build_dir), f"{title}_PPT.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: PPT -> {out} ({len(slides)} 页)")


def title_json(t):
    return t


def glob_safe(d):
    if not os.path.isdir(d):
        return []
    return sorted(os.listdir(d))


TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
  html,body{margin:0;background:""" + BG + """;font-family:"Hiragino Sans GB","PingFang SC",sans-serif;color:""" + HILITE + """;}
  #wrap{position:relative;width:100vw;height:100vh;display:flex;align-items:center;justify-content:center;background:#000;}
  #stage{position:relative;max-width:100vw;max-height:100vh;}
  #stage img{display:none;width:auto;height:auto;max-width:100vw;max-height:100vh;}
  #cap{position:absolute;left:0;right:0;bottom:18px;text-align:center;font-size:20px;color:""" + HILITE + """;text-shadow:0 2px 6px #000;padding:0 40px;}
  #bar{position:fixed;top:14px;right:18px;font-size:14px;color:""" + ACCENT + """;}
  #hint{position:fixed;bottom:14px;left:18px;font-size:13px;color:""" + ACCENT + """;opacity:.7;}
</style></head>
<body>
<div id="wrap"><div id="stage"><img id="img"></div></div>
<div id="cap"></div><div id="bar"></div><div id="hint">← → / 空格 翻页 · {{TITLE}}</div>
<script>
const SLIDES=[{{SLIDES}}];
let i=0;
const img=document.getElementById('img'),cap=document.getElementById('cap'),bar=document.getElementById('bar');
function show(n){i=(n+SLIDES.length)%SLIDES.length;img.src='data:image/png;base64,'+SLIDES[i].img;img.style.display='block';cap.textContent=SLIDES[i].t;bar.textContent=(i+1)+' / '+SLIDES.length;}
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' '||e.key==='PageDown')show(i+1);if(e.key==='ArrowLeft'||e.key==='PageUp')show(i-1);});
show(0);
</script></body></html>"""


if __name__ == "__main__":
    main()
