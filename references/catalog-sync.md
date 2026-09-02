# 项目资产目录同步 SOP（tdrive · 短视频目录位）

> **目的**：把本地工作区 `目录/*.md` 同步到 **tdrive 项目资产（Project Drive）** 的固定目录位
> `短视频目录/`，让每个训练营的「已生成短视频标题目录」在项目资产里长期留存、跨会话可查。
>
> 与百度网盘归档（SKILL.md 固定规范第 19 条）的区别：百度网盘归档的是**完整视频工程**
> （成片 / PPT / 配音 / 字幕 / 发布物料），走 `/自媒体/<训练营>/<视频标题>/`；
> 本 SOP 归档的是**目录索引**（9 大类 + 总览的 md），走项目资产根级 `短视频目录/`，是
> 「按大类查阅已产出过哪些视频」的目录资产位。

---

## 1. 资产位与目录结构

**tdrive 目标位**：项目资产根目录下 `短视频目录/`（与 `We-Media`、`InfoQ`、`极客时间`、
`个人出版书籍`、`系统文件` 平级）。

```
短视频目录/                          ← 项目资产（tdrive），跨会话稳定留存
├── 00_总览.md                       ← 9 大类入口 + 累计条数 + 最新一条
├── 01_架构师训练营.md                ← 单类索引
├── 02_大数据训练营.md
├── 03_AI_训练营.md
├── 04_产品经理训练营.md
├── 05_前端训练营.md
├── 06_测试训练营.md
├── 07_管理训练营.md
├── 08_软技能训练营.md
└── 09_读书训练营.md
```

**首次启用**：在项目资产根目录（`dir_id=cmUdIiamIZso`）下 `dir_create` 一个名为 `短视频目录`
的子目录，拿到 `dir_id` 后写入 `scripts/sync_catalog_tdrive.py` 顶部常量 `TDRIVE_DIR_ID`
（或环境变量 `ONE_HUNDRED_MILLION_CATALOG_DIR_ID`）。建目录是 Project Drive 的 mutating
操作，**首次执行前须经作者确认**（见 project-file-rules）。

---

## 2. 同步触发点

- **手动场景（作者在场）**：作者在 Step 8 产出后说「同步到项目资产」/「更新一下目录资产位」
  / 或由 AI 在 Step 8.2.2 询问「是否同步到项目资产」经作者确认后执行。
- **自动场景（定时轮转 / cron）**：默认**跳过 tdrive 同步**——tdrive 的 mutating 在
  自动化场景下需要逐次授权，与 cron 批量产出冲突；本地 `目录/*.md` 仍是事实来源，下次
  交互式会话里 AI 一次性补同步即可。日志标注「项目资产同步待手动触发」。
- **补同步**：作者随时可说「把当前目录同步到项目资产」/「补同步 tdrive」一次性完成。

---

## 3. 同步 SOP（幂等 · AI 用 tdrive MCP 工具按序执行）

对**工作区根目录 `目录/`** 下的 10 个 md（`00_总览.md` + `01_~09_<大类>.md`）各做一次：

### 3.1 检查目标目录是否已配置

读 `scripts/sync_catalog_tdrive.py` 顶部常量 `TDRIVE_DIR_ID`（或环境变量
`ONE_HUNDRED_MILLION_CATALOG_DIR_ID`）——若未配置，提示作者先按 §1 建好 `短视频目录/` 并
填入 dir_id。

### 3.2 对每个 md（10 个文件循环）

按工作区 `目录/<file>.md` → tdrive `短视频目录/<file>.md`：

1. **查同名**：`tdrive.search_file(dir_id=TDRIVE_DIR_ID, keywords=[<file_basename>])`
   看目标目录是否已有同名 md。**记录目标 file_id**（若存在）。
2. **对比内容**（若存在）：
   - `tdrive.file_download(file_id=<existing>)` 拿 `download_url`
   - `curl -sSL <download_url>` 下载旧内容到 `/tmp/catalog_compare_<file>.md`
   - `diff` 工作区 `目录/<file>.md` 与下载的旧内容
   - **完全相同** → 打印 `[skip] <file>.md 内容未变` 并跳到下一个文件
3. **上传新版本**（不存在 或 内容不同）：
   - `tdrive.file_upload(dir_id=TDRIVE_DIR_ID, file_name=<file>.md,
     file_size=<bytes>, conflict_strategy=overwrite)`
     → 返回 `domain/path/headers/confirm_key/task_id`
   - `curl -sSL -X PUT -H "K1: V1" ... -T "<abs path to 目录/<file>.md>"
     "https://<domain><path>"`（`-T` 流式上传，**严禁 `--data-binary` 不带 `@`**）
   - `tdrive.file_upload_complete(dir_id=TDRIVE_DIR_ID, file_name=<file>.md,
     file_size=<bytes>, confirm_key, task_id)` 落库
   - 打印 `[uploaded] <file>.md`

### 3.3 完成后回报

输出：「项目资产 `短视频目录/` 已同步（10 个 md，其中 uploaded=N / skipped=M）」。

---

## 4. 边界与坑（踩过/验证过）

- **Project Drive mutating 必须经作者确认**（project-file-rules）——首次建 `短视频目录/`
  与每次覆盖写入均属 mutating；首次建目录明确告知作者并取得 dir_id；后续覆盖在「经作者
  批准的 Step 8 流程内」或「作者明确说『同步到项目资产』」时执行，不在 cron 自动化里自动跑。
- **tdrive.search_file 关键词 ≤20 字符**：文件名如 `02_大数据训练营.md` 超过 20 字符
  （`.md` 算上），按 basename 搜可能截断；建议搜 `keywords=["<类前缀编号>"]`（如 `["02_"]`）
  或拆词（如 `["大数据"]`）。
- **file_upload 必须用 `-T`（curl）**：`--data-binary` 不带 `@` 会把路径字符串当 body 上传，
  网盘里存的是路径文本。
- **content_type 与 confirm_key 来自 file_upload 返回**：返回 headers 的每对 key/value 都
  用一个 `-H` 原样传，勿省略改写。
- **幂等保证**：本地 `目录/<file>.md` 内容不变时跳过上传，避免每次都触发 mutating 写、
  减少覆盖冲突与日志噪音；首次全量上传，之后只上传有变化的文件。

---

## 5. 与 update_catalog.py 的关系

`scripts/update_catalog.py` 仍然是**事实来源的写入器**：每次 Step 8 产出后调用它，把视频
追加进**本地** `目录/<大类>.md` + `目录/00_总览.md`（幂等）。本 SOP 是**同步器**：把本地
目录**异步**推送到 tdrive 项目资产，让目录在项目资产里也有一份权威副本。两者解耦：

| 写入器 | 同步器 |
|---|---|
| `update_catalog.py` | 本 SOP（AI 调 tdrive MCP 工具） |
| 写本地 `目录/`（工作区） | 读本地 → 上传/覆盖 tdrive `短视频目录/` |
| 每次 Step 8 自动调用 | 手动场景自动询问 / 定时场景默认跳过 |
| 幂等：标题已存在只刷新 | 幂等：内容相同则跳过上传 |