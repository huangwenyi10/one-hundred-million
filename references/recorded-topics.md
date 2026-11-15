# 已录制主题 · 多源去重 SOP（2026-11-15 新增 · 强制）

> **一句话口径**：判断「这个主题录过没有」，**任一来源命中即判已录制**；
> 判断「目录写全了没有」，只认主工作区 `目录/`（唯一写入源）。
> 两者不是一回事：判定要宽（多源聚合），写回要严（单一事实来源 + 客观证据）。

作者指令（2026-11-15）：「已经录制过的主题，不要再录制了，可以从资产里面读取录制过的主题或者其他地方」。

---

## 1. 为什么必须多源（两次实测根因）

| 时间 | 旧口径 | 实测漏洞 | 后果 |
|---|---|---|---|
| 2026-10-31 | 只查 `topic_pool.json` 的 `status` / `syllabus.json` 的 `covered` | 本地 `目录/` 只记 19 条，网盘 `/自媒体` 实际 153 条归档 | CAP、2PC、Raft、缓存三连击、熔断、限流等老主题从不出现在「已录制」清单，被反复选中 |
| 2026-11-15 | 只查本地 `目录/*.md` | 主工作区 21 个交付文件夹里 **5 个未入目录**（约 24%）：`Agent 为什么会死循环`、`Agentic设计模式：A2A到安全护栏`、`loss曲线决定微调去留`、`大模型写SQL先测它错在哪`、`迈向AGI时代：AI产品经理方法论` | 门禁对这 5 条全部返回「未录制」，可以再录一遍 |

共同根因：**单一真相源 + 手工写回**。`update_catalog.py` 靠 Step 8 人工调用，某轮中断、定时任务跳过、或本地交付目录被归档清理，就永久漏登；而判定又只认这份目录。
2026-11-15 修复 = 判定侧改多源聚合 + 写回侧改确定性对账（`audit_recorded.py --apply`）+ 门禁前置到选题脚本。

---

## 2. 八类来源（任一命中即拦）

`scripts/recorded_index.py` 是唯一判定底座，`check_recorded.py` / `pick_topic.py` 都调它。

| # | 来源标识 | 读什么 | 特点 / 边界 |
|---|---|---|---|
| 1 | `catalog` | 主工作区 `目录/01~09_*.md` 的标题列 | 原权威源，含期序 / 档位 / 维度元数据；仍是**唯一写入源** |
| 2 | `delivery_dir` | 各工作区顶层 `<标题>_<YYYYMMDD>-<NN>/` | **只认有交付物**（`*_成片.mp4` / `*_PPT.html` / `*_口播稿.txt` 任一）的目录；空文件夹、仅建目录的废弃任务不算已录 |
| 3 | `metrics` | 各工作区 `metrics.csv` 的「标题」列 | 出片台账，含训练营 / 档位，可用于补录元数据 |
| 4 | `jobs` | `one-hundred-million-jobs.json` 中 `done_stages` 含 `final`/`publish` 的 `title` | 跨客户端续跑台账；本地交付目录被清理后仍能证明录过 |
| 5 | `netdisk` | `assets/state/recorded_netdisk.json` 快照 = 百度网盘 `/自媒体/<营>/` 归档目录名 | 离线快照，跨工作区 / 跨客户端兜底；2026-11-15 首次导入 163 条 |
| 6 | `tdrive_catalog` | `assets/state/tdrive_catalog/*.md` 快照 = 项目资产 `短视频目录/` 副本 | 跨会话兜底；副本由 `catalog-sync.md` SOP 从本地目录同步，天然是本地的子集且常滞后 |
| 7 | `topic_pool_done` | 技能内 `assets/topics/topic_pool.json` 中 `status=done` 的标题锚点 | 跨客户端共享；锚点可能与最终出片标题不同，故只作补充 |
| 8 | `syllabus_topic` | 技能内 `assets/state/syllabus.json` 各营 `lastTopic` | 实测补上了目录中漏登的 `Agent 为什么会死循环` |

### 明确**不纳入标题级判定**的两类（防误杀，正确性优先）

- `syllabus.json` 的 `covered`：是**能力维度词**（「高并发」「数据架构」），不是视频标题。拿它做子串 / 模糊匹配，会把同维度下的所有新主题误判为已录 → 只用于 Step 0 体系定位。
- `reading_camp_progress.json` 的书目状态：含「作废·待重录」记录，把书名当已录标题会挡住作者明确要重录的书 → 读书营仍走 `reading_progress_scan.py` 的原有门禁。

### 判定层级（与旧版完全一致，保证兼容）

`exact`（规范化后相等）→ `substr`（互为子串）→ `fuzzy`（字符 2-gram Jaccard ≥ 0.55）。
规范化 = 去 `_YYYYMMDD-NN` 后缀 + 全角标点转半角 + 去空白 + 小写。退出码：`0` 未录 / `3` 已录。

---

## 3. 三层门禁（绕过人工检查也拦得住）

| 环节 | 命令 / 机制 | 命中动作 |
|---|---|---|
| Step 0 第 5.5 条（最终定稿） | `python3 scripts/check_recorded.py "<标题>"` | `exit 3` → 立即弃题重选，不得强行录制 |
| 选题取候选 / 新增候选（前置） | `pick_topic.py pick` 自动过滤；`pick_topic.py add` 命中即 `exit 3` | 门禁脚本不可用时**报错不放行**；调试用 `--include-recorded` |
| Step 8 2.2（写回闭环） | `python3 scripts/audit_recorded.py --apply` | 对账后幂等补录漏登；`exit 3` = 仍有争议条目待人工确认 |

`pick_topic.py` 的前置过滤让「不记得跑 Step 0」不再成为漏洞；Step 0 的显式调用则是对最终定稿的二次确认。

---

## 4. 离线快照刷新 SOP

脚本**不联网、不调 MCP**（纯标准库，任何客户端可跑）。快照由 AI 在会话里用 MCP 只读拉取后导入；缺失 / 陈旧不阻塞判定，其余 6 类本地来源照常生效。

### 4.1 百度网盘 `/自媒体`

1. 对 9 个训练营目录逐个 `mcp__baidu-netdisk__file_list`：
   - `dir` 传**百分号编码**（中文与 `/` 都要编码，`/` → `%2F`）；
   - **每页 10 条**，从 `page=1` 翻到返回不足 10 条 / 空列表为止；
   - 只保留 `category=6` 且 `size=0` 的**目录项**；`.mp4` / `.mov` / `.MP3` / `.png` / `.zip` / `.txt` 是散文件，**不是归档视频目录**，不得混入。
2. 汇总成紧凑 JSON：`{"<训练营名>": ["<归档目录名>", ...], ...}`。
3. `python3 scripts/recorded_index.py import-netdisk <json>` → 原子写入 `assets/state/recorded_netdisk.json`（带 `updated` 日期）。
4. `python3 scripts/recorded_index.py snapshot-status` 复核条数与日期。

> 2026-11-15 首次全量导入 163 条（9 个营）。实测相对其它 7 类来源**独有标题 0 条**——本地目录 / 台账已覆盖网盘历史归档；快照价值在「工作区目录丢失或换客户端」时的兜底，不是日常增量。

### 4.2 项目资产 `短视频目录/`

1. `tdrive.dir_list(dir_id="cDDhGWjfNMso")` 列 10 个 md → 逐个 `tdrive.file_download` 取临时 URL → `curl -sSL -o <本地md> "<URL>"`（URL 原样使用，勿拆分改写）。
2. `python3 scripts/recorded_index.py import-tdrive <md所在目录>` → 复制到 `assets/state/tdrive_catalog/`。
3. **本轮未生成该快照**：`dir_list` 显示副本文件全面小于本地（如 `01_架构师训练营` 本地 3629 B / 副本 3193 B），是本地目录的**陈旧子集**，导入不带来任何新增覆盖；脚本读取能力与导入命令已备好，需要时按上述两步执行即可。项目资产的 mutating 操作仍受 `catalog-sync.md` / project-file-rules 约束，本 SOP 全程只读。

---

## 5. 自动补录的准入条件（`audit_recorded.py --apply`）

对账 = 扫全部工作区「有交付物」的视频文件夹，与 `目录/*.md` 逐条比对。

**全部满足才自动写**（写入只落主工作区 `目录/`，幂等）：

1. 文件夹里确有交付物（成片 / PPT / 口播稿任一）；
2. 文件夹标题与成片文件基名一致（规范化后相等或互为子串）；
3. 训练营大类可**客观**判定：交付目录内 `<营名>-<标题>_口播稿.txt` 前缀，或工作区顶层同名散稿前缀，或 `metrics.csv` 同标题行的「训练营」列。

元数据口径：档位取 `metrics.csv` 同标题行（取不到写 `–`）；**能力维度一律 `–`**（无可靠来源，禁止编造）；日期取文件夹后缀 `_YYYYMMDD-NN`（不取「今天」，避免补录日期失真）。
不满足的条目只列「需人工确认」，不自动写、不猜大类、不臆造元数据。

**2026-11-15 首次执行结果**：目录 182 → 186 条，补录 4 条
（`Agent 为什么会死循环` / `Agentic设计模式：A2A到安全护栏` / `loss曲线决定微调去留` / `Agentic智能体设计模式：提示链到多智能体协作`）；
1 条 `迈向AGI时代：AI产品经理方法论` 因「文件夹标题 ≠ 成片基名（实际为『AI产品经理方法论精读（上）…』）」且读书进度台账标注该书「作废·待重录」，列为需人工确认，**未自动写入**。
二次运行 `applied=0`，幂等验证通过；补录前目录已备份至 `/tmp/ohl_catalog_backup_*`。

---

## 6. 命令速查

```bash
# 判定（Step 0 第 5.5 条）
python3 scripts/check_recorded.py "候选标题"                 # exit 0 可录 / 3 已录
python3 scripts/check_recorded.py "候选标题" --json
python3 scripts/check_recorded.py --batch candidates.txt
python3 scripts/check_recorded.py --list --sources           # 多源已录总表
python3 scripts/check_recorded.py "标题" --catalog-only      # 调试：退回旧单源

# 索引与快照
python3 scripts/recorded_index.py stats
python3 scripts/recorded_index.py snapshot-status
python3 scripts/recorded_index.py import-netdisk <mcp.json>
python3 scripts/recorded_index.py import-tdrive <md目录>

# 写回闭环（Step 8 2.2 强制）
python3 scripts/audit_recorded.py                           # 只读对账
python3 scripts/audit_recorded.py --apply                   # 幂等自动补录
python3 scripts/audit_recorded.py --apply --json

# 选题（已内置前置门禁）
python3 scripts/pick_topic.py pick --camp 架构师训练营 -n 5
python3 scripts/pick_topic.py add --camp ... --title ... --dimension ... --angle ...
```

---

## 7. 回归自检清单（每次改去重逻辑必跑）

- [ ] `python3 -m py_compile scripts/recorded_index.py scripts/audit_recorded.py scripts/check_recorded.py scripts/pick_topic.py` 全过；
- [ ] 历史候选批量判定：已产出主题 **100% 判已录**（2026-11-15 基线：21/21）；
- [ ] 全新主题（如「用 eBPF 定位内核态长尾延迟」）判**未录**，不得被模糊匹配误杀；
- [ ] `audit_recorded.py --apply` 二次运行 `applied=0`（幂等）；
- [ ] `pick_topic.py verify` 通过；`pick_topic.py add` 对已录标题 `exit 3`；
- [ ] `recorded_index.py stats` 八类来源均有条数（快照缺失允许 0，但须在日志标注）；
- [ ] 目录文件改动已随技能仓库 / 工作区留存，补录前先备份。

## 8. 已知边界

- 模糊阈值 `0.55` 是经验值，`--threshold` 可调；短标题（如「Spring AI」）与包含它的长标题会互为子串命中，属**有意的宁拦勿漏**口径。
- 快照是**静态快照**，不会随网盘 / 项目资产自动更新；新增归档后需按 §4 重新导入，或依赖本地 `catalog` / `metrics` / `jobs` 自动生效。
- `delivery_dir` 只扫 `ONE_HUNDRED_MILLION_WORKSPACE_GLOB`（默认 `/Users/ay/WorkBuddy/*`）下的工作区；工作区放在别处时用环境变量或 `--workspace` 指定。
- 判定「已录」不等于「已发布」：本 SOP 只管**不再重复录制**，发布仍受 Step 7 作者审核关卡约束。
