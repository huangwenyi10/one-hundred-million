#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_syllabus_state.py — 把工作区里的旧进度文件迁到技能内共享真相源。

背景:
  旧设计把 covered 进度放在【工作区根】one-hundred-million-syllabus.json，
  工作区是本机本地的 —— 换到 Trae / Codex / Qoder / Kimi 就是另一份空进度，
  会重复选题。本技能自2026-10-04 起把进度改为【技能内】共享真相源：
  assets/state/syllabus.json（随技能仓库分发，各客户端 clone 即得）。

用法:
  # 迁移（默认只做预览，不写盘）
  python3 migrate_syllabus_state.py --workspace <工作区>

  # 确认无误后真正写入
  python3 migrate_syllabus_state.py --workspace <工作区> --apply

  # 导出技能内进度为工作区文件（旧客户端 / 旧脚本兼容用）
  python3 migrate_syllabus_state.py --export --workspace <工作区>

行为约定:
  - **合并而非覆盖**：已存在的 covered 关键词取并集，lastTopic 取较晚的。
  - 幂等：重复跑同一工作区不会产生重复条目。
  - 原子写：临时文件 + os.replace，避免另一客户端读到半截JSON。
  - 退出码：0=已同步 / 无需动，3=未找到旧文件（正常，非错误），1=出错。
"""
import argparse
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
STATE_PATH = os.path.join(SKILL_ROOT, "assets", "state", "syllabus.json")
LEGACY_NAME = "one-hundred-million-syllabus.json"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_atomic(path, obj):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"schema": "ohl-syllabus-state/1", "updated": "", "camps": {}}
    return load_json(STATE_PATH)


def find_legacy(workspace):
    """在工作区里找旧进度文件；找不到返回 None。"""
    p = os.path.join(workspace, LEGACY_NAME)
    return p if os.path.isfile(p) else None


def merge(legacy, state):
    """把旧文件的营数据并入技能内状态，返回变更说明列表。"""
    changes = []
    # 旧文件有两种可能结构：直接 {营名: {...}} 或 {"camps": {...}}
    src = legacy.get("camps") if isinstance(legacy.get("camps"), dict) else legacy
    camps = state.setdefault("camps", {})
    for camp, v in src.items():
        if camp in ("schema", "updated", "camps"):
            continue
        if not isinstance(v, dict):
            continue
        cur = camps.setdefault(camp, {"expertGoal": "", "lastTopic": "", "covered": []})
        if v.get("expertGoal") and not cur.get("expertGoal"):
            cur["expertGoal"] = v["expertGoal"]
        old_cov = v.get("covered") or []
        new_items = [x for x in old_cov if x not in cur["covered"]]
        if new_items:
            cur["covered"].extend(new_items)
            changes.append(f"  {camp}: covered +{len(new_items)} 条 -> {new_items}")
        if v.get("lastTopic"):
            cur["lastTopic"] = v["lastTopic"]
    return changes


def main():
    ap = argparse.ArgumentParser(description="迁移 syllabus 进度到技能内共享真相源")
    ap.add_argument("--workspace", required=True, help="工作区根目录")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认仅预览）")
    ap.add_argument("--export", action="store_true", help="反向导出到工作区（旧客户端兼容）")
    args = ap.parse_args()

    state = load_state()

    if args.export:
        dst = os.path.join(args.workspace, LEGACY_NAME)
        if not state.get("camps"):
            print(f"技能内进度为空，无可导出内容（{STATE_PATH}）")
            return 0
        save_atomic(dst, state["camps"])
        print(f"已导出 {len(state['camps'])} 个营的进度 -> {dst}")
        print("注意：技能内仍是唯一真相源，此文件仅供旧脚本/旧客户端读取，别回手改它。")
        return 0

    legacy_path = find_legacy(args.workspace)
    if not legacy_path:
        print(f"工作区未找到 {LEGACY_NAME}，无需迁移。")
        print(f"（若该工作区从未生产过，属正常；技能内进度位于 {STATE_PATH}）")
        return 3

    try:
        legacy = load_json(legacy_path)
    except json.JSONDecodeError as e:
        print(f"ERROR: 旧进度文件解析失败 {legacy_path}: {e}", file=sys.stderr)
        return 1

    # 注意：merge() 会就地改 state，所以「合并前」的营数必须在调用前取，
    # 否则打印出来的是合并后的数量，看起来像技能内本来就有这些记录（2026-10-04 实测踩到）。
    before_camps = len(state.get("camps", {}))
    changes = merge(legacy, state)
    print(f"旧文件: {legacy_path}")
    print(f"技能内: {STATE_PATH}")
    print(f"技能内合并前已记录: {before_camps} 个营 -> 合并后 {len(state.get('camps', {}))} 个营")
    if not changes:
        print("\n无需变更（旧文件内容已全部包含在技能内进度中）。")
        return 0
    print("\n将合并以下变更：")
    for c in changes:
        print(c)
    if not args.apply:
        print("\n这是预览。加 --apply 真正写入。")
        return 0

    state["updated"] = time.strftime("%Y-%m-%d")
    save_atomic(STATE_PATH, state)
    print(f"\n已写入，技能内进度现有 {len(state['camps'])} 个营。")
    print("后续各客户端读技能内进度即可跨客户端去重；旧工作区文件保留不动（只读参考）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
