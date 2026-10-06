#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cleanup_builds.py -- 视频临时产物清理器（one-hundred-million · 固定规范第 24 条配套）

把「成片交付后按可再生性分流清理 build 中间产物 / 根级孤儿构建目录」这件事工具化。
**默认 dry-run**：只打印清单与体积，不动任何文件；
加 `--apply` 才把目标**移入系统废纸篓**（不是 rm —— 可恢复）。

## 分流原则（2026-10-06 起 · 强制）

`build/` 内的东西按「能不能重造」分两类，处理方式不同：

  可再生（清掉）  媒体类中间产物，占 build 体积 99% 以上——
                  `frames/` `sub_frames/` `body.mp4` `body_motion.mp4` `final_silent.mp4`
                  `seg_*.mp3` `voiceover.mp3` `segments*.txt` `segs_concat.txt`
                  `subtitles*.srt` `pages_data.py` `seg_*.json` 渲染/合成 `*.py`
                  → 凭PPT.html + 口播稿可随时重建（重跑 TTS + 渲染即可）

  不可再生（保留） 溯源与复现台账，体积 <100 KB——
                  `sources.md` `book_source.md`
                  `segments_durations.json` `polyphone_map.json`
                  → 删了无法自证内容出处、无法二次重制对齐，故**迁入交付目录 `_archive/`**
                    随交付物一起走，而不是留在 build 里等下次连坐删除

判据（与 SKILL.md 固定规范第 24 条一致）：
  A 类  <交付目录>/build/             同目录存在 `<标题>_成片.mp4` → 可清
       （交付目录名自 2026-10-01 起带 `_<YYYYMMDD>-<NN>` 时间戳后缀；成片文件名仍为纯标题基准，
         即 `<标题>_成片.mp4` 或 `<标题>.mp4` —— 两种命名都已识别）
       （无成片 → 视为未完成任务，默认保留并单列，需 --include-incomplete 才清）
  B 类  工作区根级 `build*` 目录       孤儿构建目录（build / build_prev_* / build_<tag>_<ts>）→ 可清
       护栏：名称含 backup 跳过；mtime 距今 < --min-age-min 分钟跳过（防删正在跑的构建）
  C 类  <交付目录>/assets/ 空目录      空素材目录（素材已入PPT/成片后常见）→ 可清
       护栏：非空则跳过（可能仍有在用素材）

用法：
  python3 cleanup_builds.py --workspace <工作区>                 # 只看清单（默认）
  python3 cleanup_builds.py --workspace <工作区> --apply          # 移入废纸篓
  python3 cleanup_builds.py --workspace <工作区> --min-age-min 30
  python3 cleanup_builds.py --workspace <工作区> --include-incomplete   # 连无成片的 build/ 一起清（慎用）
  python3 cleanup_builds.py --workspace <工作区> --no-archive     # 连台账一起清（彻底档，丢失溯源链）
  python3 cleanup_builds.py --workspace <工作区> --json           # 机器可读输出

退出码：0 = 正常（dry-run 或 apply 全部成功）；1 = 参数/环境错误；2 = 有项目移动失败。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

# 绝不作为工作区处理的高危路径
FORBIDDEN = {
    "/", os.path.expanduser("~"), "/System", "/Library", "/Applications",
    os.path.expanduser("~/Desktop"), os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
}

# 顶层需跳过的非视频目录（工作区固定结构 / 保留项）
SKIP_TOP = {"scripts", "templates", "目录", "发布", "assets", "node_modules", "__pycache__"}

# 交付目录名的时间戳后缀（固定规范第 12 条：`<视频标题>_<YYYYMMDD>-<NN>`）
TS_SUFFIX_RE = re.compile(r"_\d{8}-\d{2,}$")

# 不可再生的溯源/ 复现台账 —— 清理时迁入<交付目录>/_archive/，不删
KEEP_FILES = ("sources.md", "book_source.md", "segments_durations.json", "polyphone_map.json")

# 保留台账的迁入目录名（放在交付目录内，随交付物走）
ARCHIVE_DIR = "_archive"


def dir_size(path):
    total = 0
    for dp, _dn, fn in os.walk(path):
        for f in fn:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def human(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.2f}T"


def has_final(dirpath):
    """目录内是否存在成片。

    兼容三种情况（固定规范第 12 条：交付目录名自 2026-10-01 起带时间戳后缀）：
      - `<任意>_成片.mp4`            （主判据，最常见）
      - `<目录名>.mp4`               （旧式：成片与目录同名）
      - `<目录名去时间戳>.mp4`       （新式：目录名 = `<标题>_<YYYYMMDD>-<NN>`，成片仍叫 `<标题>.mp4`）
    """
    base = os.path.basename(dirpath.rstrip(os.sep))
    stem = TS_SUFFIX_RE.sub("", base)  # 去掉 `_YYYYMMDD-NN` 后缀
    try:
        names = os.listdir(dirpath)
    except OSError:
        return False
    candidates = {base + ".mp4", stem + ".mp4"}
    for f in names:
        if not f.endswith(".mp4"):
            continue
        if "成片" in f or f in candidates:
            return True
    return False


def move_to_trash(path):
    """优先系统废纸篓（可恢复）。返回 (ok, detail)"""
    # macOS: /usr/bin/trash。注意它**不认 `--` 分隔符**（传了会把 `--` 当文件名），
    # 且会把以 `-` 开头的路径当成自身参数，故这类路径直接走手动移动。
    base = os.path.basename(path.rstrip(os.sep))
    if not base.startswith("-") and shutil.which("trash"):
        r = subprocess.run(["trash", path], capture_output=True, text=True)
        if r.returncode == 0 and not os.path.exists(path):
            return True, "trash CLI"
    if shutil.which("gio"):
        r = subprocess.run(["gio", "trash", path], capture_output=True, text=True)
        if r.returncode == 0 and not os.path.exists(path):
            return True, "gio trash"
    trashdir = os.path.expanduser("~/.Trash")
    if os.path.isdir(trashdir):
        dst = os.path.join(trashdir, os.path.basename(path.rstrip(os.sep)))
        if os.path.exists(dst):
            dst = f"{dst}.{int(time.time())}"
        try:
            shutil.move(path, dst)
            return True, f"mv -> {dst}"
        except OSError as e:
            return False, str(e)
    return False, "无可用废纸篓（trash / gio / ~/.Trash 均不可用）"


def pick_keep(build_dir):
    """返回build_dir 内存在的台账文件列表（按 KEEP_FILES 顺序）。"""
    found = []
    for name in KEEP_FILES:
        p = os.path.join(build_dir, name)
        if os.path.isfile(p):
            found.append(p)
    return found


def archive_keep(delivery_dir, keep_paths):
    """把台账文件迁入<交付目录>/_archive/，返回 (迁入数, 失败列表)。"""
    if not keep_paths:
        return 0, []
    dest = os.path.join(delivery_dir, ARCHIVE_DIR)
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        return 0, [f"{p} -> {dest} ({e})"]
    ok = 0
    failed = []
    for src in keep_paths:
        dst = os.path.join(dest, os.path.basename(src))
        try:
            # 同名已存在时加时间戳后缀，不覆盖
            if os.path.exists(dst):
                dst = f"{os.path.splitext(dst)[0]}.{int(time.time())}{os.path.splitext(dst)[1]}"
            shutil.move(src, dst)
            ok += 1
        except OSError as e:
            failed.append(f"{src} ({e})")
    return ok, failed


def scan(workspace, min_age_min, include_incomplete, no_archive):
    now = time.time()
    age_cutoff = min_age_min * 60
    plan = []
    for name in sorted(os.listdir(workspace)):
        full = os.path.join(workspace, name)
        if not os.path.isdir(full) or name.startswith("."):
            continue

        # ---- A 类：<交付目录>/build/ ----
        if not name.startswith("build"):
            b = os.path.join(full, "build")
            if os.path.isdir(b):
                fin = has_final(full)
                keep = [] if no_archive else pick_keep(b)
                if fin:
                    plan.append({"kind": "A", "path": b, "title": name,
                                 "size": dir_size(b), "reason": "成片已存在",
                                 "keep": [os.path.basename(x) for x in keep],
                                 "archive_to": os.path.join(full, ARCHIVE_DIR),
                                 "clearable": True})
                else:
                    plan.append({"kind": "A", "path": b, "title": name,
                                 "size": dir_size(b), "reason": "无成片（未完成任务）",
                                 "keep": [os.path.basename(x) for x in keep],
                                 "archive_to": os.path.join(full, ARCHIVE_DIR),
                                 "clearable": bool(include_incomplete)})

            # ---- C 类：<交付目录>/assets/ 空目录 ----
            a = os.path.join(full, "assets")
            if os.path.isdir(a) and has_final(full):
                n = len(os.listdir(a))
                plan.append({"kind": "C", "path": a, "title": name, "size": dir_size(a),
                             "reason": "空素材目录（成片已存在）" if n == 0 else f"非空（{n} 项），跳过",
                             "clearable": n == 0})
            continue

        # ---- B 类：根级 build* 孤儿 ----
        if "backup" in name.lower():
            plan.append({"kind": "B", "path": full, "title": name,
                         "size": dir_size(full), "reason": "名称含 backup，跳过",
                         "clearable": False})
            continue
        age = now - os.path.getmtime(full)
        if age < age_cutoff:
            plan.append({"kind": "B", "path": full, "title": name,
                         "size": dir_size(full),
                         "reason": f"mtime 距今仅 {age/60:.0f} 分钟，疑似进行中，跳过",
                         "clearable": False})
            continue
        plan.append({"kind": "B", "path": full, "title": name, "size": dir_size(full),
                     "reason": f"根级孤儿构建目录（{age/3600:.0f} 小时未改动）",
                     "clearable": True})
    return plan


def main():
    ap = argparse.ArgumentParser(description="视频临时产物清理器（默认 dry-run）")
    ap.add_argument("--workspace", required=True, help="视频工作区路径")
    ap.add_argument("--apply", action="store_true", help="实际移入废纸篓（默认只打印）")
    ap.add_argument("--include-incomplete", action="store_true",
                    help="连「无成片」的 build/ 也清（危险，未完成任务将需重跑）")
    ap.add_argument("--no-archive", action="store_true",
                    help="连不可再生台账（sources.md 等）一起清，彻底档，丢失溯源链")
    ap.add_argument("--min-age-min", type=float, default=60,
                    help="跳过最近 N 分钟内改动过的根级构建目录（默认 60，防删进行中）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    ws = os.path.abspath(os.path.expanduser(args.workspace))
    if not os.path.isdir(ws):
        print(f"ERROR: 工作区不存在: {ws}", file=sys.stderr)
        return 1
    if ws in FORBIDDEN:
        print(f"ERROR: 拒绝在高危路径上运行: {ws}", file=sys.stderr)
        return 1

    plan = scan(ws, args.min_age_min, args.include_incomplete, args.no_archive)
    todo = [x for x in plan if x["clearable"]]
    held = [x for x in plan if not x["clearable"]]
    kept_total = sum(len(x.get("keep", [])) for x in todo)

    if args.json:
        print(json.dumps({"workspace": ws, "apply": args.apply,
                          "todo": todo, "held": held}, ensure_ascii=False, indent=2))
    else:
        print(f"工作区: {ws}")
        print(f"临时产物清理清单（{'APPLY · 移入废纸篓' if args.apply else 'DRY-RUN · 不动文件'}）\n")
        for tag, items in (("可清", todo), ("保留", held)):
            print(f"--- {tag}（{len(items)} 项，{human(sum(i['size'] for i in items))}）---")
            for x in items:
                print(f"  [{x['kind']}] {human(x['size']):>8}  {x['path']}")
                print(f"        理由: {x['reason']}")
                if x.get("keep"):
                    print(f"        保留台账: {', '.join(x['keep'])}  ->  {x['archive_to']}")
            print()
        print(f"合计可清: {len(todo)} 项 / {human(sum(i['size'] for i in todo))}")
        print(f"保留:     {len(held)} 项 / {human(sum(i['size'] for i in held))}")
        if kept_total:
            print(f"台账迁移: {kept_total} 个文件将迁入各交付目录的 {ARCHIVE_DIR}/（不删除）")

    if not args.apply:
        # --json 模式下不得再追加任何非 JSON 文本，否则下游解析器会报 "Extra data"
        if not args.json:
            print("\n（DRY-RUN 结束。确认清单无误后加 --apply 执行）")
        return 0

    failures = []
    freed = 0
    archived = 0
    for x in todo:
        if not os.path.exists(x["path"]):
            continue
        size = dir_size(x["path"])
        # 先迁台账，再清 build —— 顺序不能反，反了台账就随 build 一起进废纸篓
        if x["kind"] == "A" and x.get("keep"):
            keep_paths = [os.path.join(x["path"], k) for k in x["keep"]]
            ok_n, failed = archive_keep(os.path.dirname(x["path"].rstrip(os.sep)), keep_paths)
            archived += ok_n
            failures.extend(failed)
            if failed:
                # 台账没安全落地就不动 build，避免连带丢失
                print(f"  SKIP {x['path']}  (台账迁移失败，保住 build 不删)")
                continue
        ok, detail = move_to_trash(x["path"])
        if ok and not os.path.exists(x["path"]):
            print(f"  OK   {human(size):>8}  {x['path']}  ({detail})")
            freed += size
        else:
            failures.append(x["path"])
            print(f"  FAIL {x['path']}  ({detail})")

    print(f"\n已移入废纸篓: {human(freed)}")
    if archived:
        print(f"台账已归档: {archived} 个文件 -> 各交付目录 {ARCHIVE_DIR}/")
    print("注意：废纸篓不释放磁盘空间，确认无误后需清空废纸篓才真正回收。")
    if failures:
        print(f"失败 {len(failures)} 项: {failures}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())