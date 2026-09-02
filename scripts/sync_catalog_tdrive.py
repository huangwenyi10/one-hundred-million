#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_catalog_tdrive.py — 短视频目录 → tdrive 项目资产 同步辅助器

本脚本是 `references/catalog-sync.md` SOP 的「配置持有者 + 校验/清单器」，
**不直接执行 tdrive 写入**（Project Drive 的 mutating 操作由 AI 按 SOP §3
用 tdrive MCP 工具按序执行，受 project-file-rules 约束）。本脚本提供：
  1. 读取 tdrive 目标目录 id（TDRIVE_DIR_ID 常量或环境变量 ONE_HUNDRED_MILLION_CATALOG_DIR_ID）
  2. --check    检查配置 + 列本地 10 个待同步 md
  3. --list     列出待同步文件（路径 / 字节数 / sha1）
  4. --sync     打印 SOP §3 步骤与 AI 应调用的 tdrive MCP 工具序列，不直接上传

用法：
  python3 scripts/sync_catalog_tdrive.py --check           # 校验 + 列待同步文件
  python3 scripts/sync_catalog_tdrive.py --list            # 仅列待同步文件（含 hash）
  python3 scripts/sync_catalog_tdrive.py --sync            # 打印 AI 应执行的同步步骤
  python3 scripts/sync_catalog_tdrive.py --set-dir-id <id>  # 把 dir_id 写到 .tdrive_dir_id 配置（首次启用）

首次启用：
  1. 在 tdrive 项目资产根目录（cmUdIiamIZso）下建子目录 `短视频目录/`
     （属 Project Drive mutating，须经作者确认；用 mcp__netdrive__tdrive.dir_create）
  2. 把返回的 dir_id 写到本脚本顶部 TDRIVE_DIR_ID 常量，或环境变量
     ONE_HUNDRED_MILLION_CATALOG_DIR_ID，或运行 `python3 sync_catalog_tdrive.py --set-dir-id <id>`
"""
import argparse, datetime, hashlib, os, sys

# === tdrive 短视频目录 dir_id 配置（首次启用后填入，留 None 表示未配置） ===
TDRIVE_DIR_ID = None  # 例：'cXXXXXXXXXXXXXXXX'；留 None 则脚本以"未配置"状态运行
ENV_KEY = "ONE_HUNDRED_MILLION_CATALOG_DIR_ID"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tdrive_dir_id")

INDEX_FILENAME = "00_总览.md"
CATEGORY_FILENAMES = [
    "01_架构师训练营.md", "02_大数据训练营.md", "03_AI_训练营.md",
    "04_产品经理训练营.md", "05_前端训练营.md", "06_测试训练营.md",
    "07_管理训练营.md", "08_软技能训练营.md", "09_读书训练营.md",
]


def resolve_dir_id():
    """解析 dir_id：常量 → 环境变量 → 配置文件（优先级递减）。"""
    if TDRIVE_DIR_ID:
        return TDRIVE_DIR_ID, "脚本常量"
    env = os.environ.get(ENV_KEY)
    if env:
        return env, f"环境变量 {ENV_KEY}"
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v, f"配置文件 {CONFIG_FILE}"
    return None, "未配置"


def set_dir_id(value):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(value.strip())
    os.chmod(CONFIG_FILE, 0o600)


def catalog_files(workspace):
    cat_dir = os.path.join(workspace, "目录")
    files = []
    for name in [INDEX_FILENAME] + CATEGORY_FILENAMES:
        p = os.path.join(cat_dir, name)
        if os.path.exists(p):
            with open(p, "rb") as f:
                data = f.read()
            files.append({"name": name, "path": p, "size": len(data), "sha1": hashlib.sha1(data).hexdigest()[:12]})
        else:
            files.append({"name": name, "path": p, "size": 0, "sha1": None, "missing": True})
    return files


def cmd_check(args):
    did, src = resolve_dir_id()
    print(f"[配置] dir_id={did or '⚠️ 未配置'}  来源={src}")
    if not did:
        print("  请先在 tdrive 建 `短视频目录/`，把 dir_id 写入脚本常量或运行 --set-dir-id")
    files = catalog_files(args.workspace)
    print(f"[本地] 目录={os.path.join(args.workspace, '目录')}")
    print(f"[本地] 待同步 {len([f for f in files if not f.get('missing')])} / {len(files)} 个文件")
    for f in files:
        flag = "✗ 缺失" if f.get("missing") else f"{f['size']:>6}B  {f['sha1']}"
        print(f"  - {f['name']:24s}  {flag}")


def cmd_list(args):
    files = catalog_files(args.workspace)
    for f in files:
        if f.get("missing"):
            print(f"MISSING  {f['name']}  {f['path']}")
        else:
            print(f"{f['size']:>8}  {f['sha1']}  {f['path']}")


def cmd_sync(args):
    did, src = resolve_dir_id()
    if not did:
        sys.stderr.write("未配置 dir_id；请先 --set-dir-id 或填脚本常量\n")
        sys.exit(2)
    files = [f for f in catalog_files(args.workspace) if not f.get("missing")]
    print(f"[sync] dir_id={did}（{src}） 共 {len(files)} 个文件")
    print("按 references/catalog-sync.md §3 SOP 用 tdrive MCP 工具执行：")
    for f in files:
        print(f"  · {f['name']:24s}  {f['size']:>6}B  sha1={f['sha1']}")
    print("\n每个文件的步骤：")
    print("  1) mcp__netdrive__tdrive.search_file(dir_id=<dir_id>, keywords=[<name 前缀或关键词>]) → 拿 file_id")
    print("  2) 若存在：mcp__netdrive__tdrive.file_download(file_id) → curl 下载 → diff 本地；相同则 skip")
    print("  3) 若不同/不存在：mcp__netdrive__tdrive.file_upload(dir_id=<dir_id>, file_name=<name>, file_size=<bytes>, conflict_strategy='overwrite')")
    print("     → curl -sSL -X PUT -H '<返回的 headers>' -T <abs path> 'https://<domain><path>'")
    print("     → mcp__netdrive__tdrive.file_upload_complete(dir_id=<dir_id>, file_name=<name>, file_size=<bytes>, confirm_key, task_id)")
    print("  4) 全部完成后回报作者：「项目资产 `短视频目录/` 已同步（uploaded=N / skipped=M）」")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=os.getcwd(), help="工作区根目录（含 `目录/` 子目录）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="校验配置 + 列待同步文件").set_defaults(func=cmd_check)
    sub.add_parser("list", help="列待同步文件（路径/size/sha1）").set_defaults(func=cmd_list)
    sub.add_parser("sync", help="打印 SOP §3 同步步骤（AI 用 tdrive MCP 工具执行）").set_defaults(func=cmd_sync)
    s = sub.add_parser("set-dir-id", help="把 dir_id 写到本地配置文件")
    s.add_argument("value")
    args = ap.parse_args()
    if args.cmd == "set-dir-id":
        set_dir_id(args.value)
        print(f"已写入 {CONFIG_FILE}（{args.value}）")
        return
    args.func(args)


if __name__ == "__main__":
    main()