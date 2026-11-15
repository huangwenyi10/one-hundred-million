# 双环自我进化机制（self-evolution）

> **固定规范第 43 条配套文档** · 2026-11-15 作者确认后落地
> 承接第 25 条「工匠级品控·持续进步」与第 40 条「自主学习与自主迭代」，**不替代任何既有硬门禁**。
> 执行靠 `scripts/evolution.py`（纯标准库、确定性、不联网、不删除文件）。

---

## 0. 定位与边界（先读这一节）

**一句话**：第 40 条解决「错了不再犯」，第 43 条补上「没错也要变得更好」。前者是**纠错环（A）**，后者是**提升环（B）**；两环共用一份跨轮事实，而不是各写一套日志。

| 维度 | A 环 · 纠错（已有，本机制加固） | B 环 · 提升（本机制新增） |
|---|---|---|
| 触发条件 | 门禁 FAIL / 返工 / 抽帧异常 / 作者打回 | **每轮都触发**，不依赖是否出错 |
| 覆盖对象 | 缺陷与复发 | **视频质量五维趋势** + **内容资料的跨期积累与时效** |
| 数据来源 | `assets/state/learnings.md` | `quality_scores.json` / `source_cards.json` / `evolution_proposals.json` |
| 输出 | 防复发清单、条款/脚本蒸馏 | 弱项定位、提档提议、资料复核清单、进化验证结论 |
| 是否自动改技能 | 第 40 条④ 允许蒸馏成条款/脚本 | **一律只提议，作者确认后才写入**（§5） |

**三条不能越过的边界**：

1. **不替代硬门禁**。`check_sync.py` / `subtitle_band_check.py` / `bg_theme_check.py` / `visual_presence_check.py` / `content_depth_check.py` / `video_quality_gate.py` / `douyin_compliance_check.py` 的地位不变；`evolution.py check` 只校验「进化动作有没有做」，**不是质量合格证**。
2. **不豁免取材纪律**。事实卡片命中 `valid` 只说明「历史上核实过」，**第 7 条双重来源核验、中英双语检索、性能数字带测试条件一律照跑**（见 §4.3）。
3. **不自动改规则**。脚本只写台账与提议；SKILL.md / scripts / references / templates 的任何条款或常量改动，必须经作者 `approve` 后由 AI 执行（§5）。

**关于评分的诚实说明**：五维评分卡是**结构化复盘工具**，不是客观画质测量仪。分数由当轮 AI 依据可核验的门禁输出与人审结论自评，**每一维都必须附证据**；它只用于同一技能内部的趋势定位与弱项发现，不做跨平台横向比较，也不作为发布/考核 KPI。没有证据就不录分（脚本会直接拒绝）。

---

## 1. 数据与文件

| 文件 | 层 | 内容 | 写入者 |
|---|---|---|---|
| `assets/state/learnings.md` | 技能内·共享 | 已有的问题登记簿（第 40 条） | AI 手工追加 |
| `assets/state/quality_scores.json` | 技能内·共享 | 每轮五维评分 + 逐维证据 + 返工/打回/门禁失败计数 | `evolution.py score` |
| `assets/state/source_cards.json` | 技能内·共享 | 跨期事实卡片库（结论 / 来源 / 版本 / 复核到期 / 状态） | `evolution.py source` |
| `assets/state/evolution_proposals.json` | 技能内·共享 | 提议状态机（机器可读，判定据此） | `evolution.py` |
| `assets/state/evolution_log.md` | 技能内·共享 | 人可读留痕，**只追加** | `evolution.py` |
| `<工作区>/.evolution_state.json` | 工作区·本轮 | 执行凭证：brief / score / check 的确定性凭据 | `evolution.py` |

前五份放技能内，是第 33 条「跨客户端共享真相源」的延续：WorkBuddy / Trae / Codex 读到同一份评分、同一批事实卡片、同一组待拍板提议。执行凭证放工作区，因为它是「本轮这一条视频」的状态，不是跨轮资产。

**防污染守卫**：`brief` / `score` / `check` 会写执行凭证，若 `--workspace` 指向技能仓库自身（目录含 `SKILL.md`）直接 `exit 1`。这是 `learnings.md` L009 教训的复用，别绕过。

---

## 2. 每轮执行点（三条命令，不可跳过）

```
Step 0 第 0 条（开工最先）   python3 scripts/evolution.py --workspace <工作区> brief --episode <期号>
Step 1 取材前（按需）        python3 scripts/evolution.py source find --keyword <关键词>
Step 8 收尾（成对执行）      python3 scripts/evolution.py --workspace <工作区> score ...
                            python3 scripts/evolution.py --workspace <工作区> check
```

- `--workspace` 必须是本轮视频所在工作区，**不得省略到技能仓库根**。全局选项写在子命令前或后都能识别。
- `check` 的 `exit 0` 是本轮收尾完成的必要条件；`exit 1` 表示「进化动作没做完」，禁止结束本轮（与第 41 条推送并列为收尾项）。
- `brief` 会自动把已过复核期的 `valid` 事实卡片标记为 `stale`——这是确定性到期计算，**不改变任何结论文本、不改动任何规则**，只是提示本轮须回源复核。

**`check` 校验三项**（缺一即 FAIL）：

| 项 | 判据 |
|---|---|
| 开工回顾 | 本轮 `brief` 已跑（执行凭证存在；跨天长片日期不一致只 WARN） |
| 质量评分 | 评分库中存在本轮 `episode` 的条目，且五维与逐维证据齐全 |
| 问题登记 | `--learning-ids` 列出的每个 LID 确实存在于 `learnings.md`；或显式声明 `--no-issues`。**本轮若有维度退步却声明 `--no-issues` → FAIL** |

「既不给 LID 也不声明无问题」会被 `score` 直接拒绝 —— 把第 40 条①「禁止只写 metrics.csv 备注」从自觉变成必须显式表态。

---

## 3. B 环之一：视频质量评分卡

### 3.1 五维与证据锚点

| 维度 | 打分依据（**必须引用当轮真实产物，不能凭感觉**） |
|---|---|
| `content` 内容 | `content_depth_check.py` 的量化点密度 / 实战形态命中 / 讲透闭环五段覆盖；第 38 条废话门禁结果；权威来源核验结论 |
| `visual` 视觉 | `visual_presence_check.py` 载体页占比与 BLOCK/WARN；`subtitle_band_check.py` / `bg_theme_check.py` 结果；第 37 条图示人审闸门「3 秒能否看懂」 |
| `audio` 音频 | 响度归一 ≈ -14 LUFS、爆音/底噪抽听；`polyphone_check.py` 代理与 restore 结果；固定音色 `zh-CN-YunxiNeural` 核对 |
| `subtitle` 字幕 | `check_sync.py` 的偏差数值与 exit code；cue 停留时长、末尾标点、单行显示、不挡内容抽帧结论 |
| `delivery` 交付 | 本轮门禁 FAIL 次数 / 返工次数 / 作者打回次数 / 逐帧走查与三处精听结论 / 归档与推送是否完成 |

分值 0–10，**逐维 `--evidence` 必填**；同时录 `--rework` / `--rejections` / `--gate-failures` 三个计数。脚本不做任何自动打分，也不推算缺失值。

### 3.2 趋势判定（常量在 `evolution.py` 顶部，非拍脑袋）

| 判定 | 口径 | 后续动作 |
|---|---|---|
| **退步** | 某维 ≤ 近 10 期均值 − **1.5** 分（均值排除本轮） | 下轮 `brief` 列为「本轮重点改进项」；**本轮收尾必须登记一条 learnings「流程缺口」** |
| **提档候选** | 连续 **3** 期某维 ≥ **9.0** 分，且这 3 期均零返工 / 零作者打回 / 零门禁 FAIL | 生成 **1 条合并的 `threshold_raise` 提议**（不刷屏），状态 `pending_author` |
| 无历史 | 评分库为空或不足 | 明确输出「暂无数据，无法做趋势对比」，**不生成占位分数、不做推断** |

> 上述数值是**初始阈值**，不是永久标准。调整必须走 §5 的提议 → 作者确认 → 改脚本常量 → 下轮验证，禁止在对话里随口改。

### 3.3 提档不是「把阈值调高」这么简单

作者批准提档后，AI 才执行：①确定要上调的**具体硬指标与目标值**（例如「量化点密度 2.0 → 2.5 个/千字」或「载体页占比 25% → 30%」），②改对应脚本常量或 Quality Gates 条款，③按第 41 条提交并推送 GitHub，④在 `evolution_log.md` 留痕，**⑤下一轮 `verify` 验证是否真的生效且没有引发 BLOCK 雪崩**。

提档失败（新阈值导致连续 BLOCK、产量下降）→ `verify --result recurred`，把该提议标 `failed`，回滚到旧阈值并登记 learnings。**收紧标准若以出不了片为代价，就是退步不是进步。**

---

## 4. B 环之二：内容资料进化

### 4.1 事实卡片字段

| 字段 | 含义 | 纪律 |
|---|---|---|
| `id` | `SC###`，脚本自增 | 不手工编号 |
| `claim` | 一句可核验的结论（含具体数字/版本/主体） | 禁止「性能大幅提升」式模糊表述（第 7/25 条） |
| `source` | 官方 URL / 原书页码章节 / 官方仓库路径 | 与第 7 条来源分级一致，`L5` 只当线索 |
| `level` | `L1`–`L5` | 见 `references/authoritative-sources.md` |
| `version` | 产品版本 / 论文版本 / 文档发布日期 | **版本变了就必须复核**，不是等 180 天 |
| `conditions` | 性能数字的测试条件（版本/规模/硬件/数据集/日期） | 缺条件不入库（第 7、27 条） |
| `verified_at` / `review_due` | 核实日 / 复核到期（默认 **180 天**） | 到期自动转 `stale` |
| `status` | `valid` / `stale` / `retired` | 见下表 |
| `used_in` / `review_history` | 用过哪些期次 / 每次复核的前后版本 | 便于结论失效时反查受影响视频 |

### 4.2 生命周期

```
source add  →  valid  ──(到期 / 版本变化)──→  stale  ──source verify（回源确认）──→  valid
                             │
                             └──source retire --reason "官方修订/结论作废"──→  retired（禁止复用）
```

- `stale` **不是结论错误**，只是「需要重新核实」；`retired` 才是「这条结论不能再用」。
- `source find` 命中 `retired` 会打印停用原因；命中 `stale` 要求先 `verify`；命中 `valid` 仍要求「回源确认版本未变」——**复用不豁免第 7 条双源核验**。
- 官方发布新版本 / 数据被修订时，即使没到期也应主动 `retire` 或 `verify`，并反查 `used_in` 里已用过该结论的视频是否需要更正。

### 4.3 与 `build/sources.md` 的关系（别搞混）

| | `build/sources.md` | 事实卡片库 |
|---|---|---|
| 范围 | **本条视频**的结论→来源台账 | **跨期**可复用事实 |
| 生命周期 | 每期生成，`cleanup_builds.py` 迁 `_archive/` 留档 | 长期留在 `assets/state/`，随技能推 GitHub |
| 作用 | 作者抽查「这句出自哪里」的审计证据 | 下轮取材时先查「这个结论是不是已经核过」 |

**两者不互相替代**：`sources.md` 仍按第 7 条每期必写；事实卡片库是从中挑出「值得跨期复用且带版本/条件」的结论，由 Step 8 `source add` 入库。临时性、一次性、无法带测试条件的数字不入库。

### 4.4 每轮动作

1. **Step 1 取材前**：`source find --keyword <主题词>`；`brief` 里列出的 `stale` 卡片若与本期主题相关，**先回源复核再写稿**。
2. **写稿时**：命中 `valid` 也只是线索，仍须按第 7 / 42 条跑公网权威双源核验、中英双语检索、GitHub 官方仓库核对。
3. **Step 8 收尾**：把本期新核实、值得复用的结论逐条 `source add`（带 `version` + `conditions` + `used-in`）。
4. **版本变更**：发现官方改版 → `source verify --id SC001 --version <新版本>` 或 `source retire --id SC001 --reason "..."`。

---

## 5. 提议状态机与自治权限（作者 2026-11-15 拍板）

**核心红线：`evolution.py` 绝不自动修改 SKILL.md / scripts / references / templates 中的任何条款或常量。** 脚本能自动做的只有：写台账、算到期、算趋势、生成提议、校验收尾。

```
                  ┌──────────────────── 作者 reject ──→ rejected（规则原样）
生成提议 ─→ pending_author
                  └──────────────────── 作者 approve ──→ approved ──→ AI 执行固化 ──→ 下轮 verify
                                                                              ├─ no-recurrence / improved → 闭环生效
                                                                              ├─ recurred → failed（提级重新蒸馏）
                                                                              └─ no-data → 继续列待验证
```

| 提议类型 | 由谁生成 | 典型内容 |
|---|---|---|
| `threshold_raise` | `score` 检测到连续 3 期达标 | 上调某项硬指标一档（§3.3） |
| `distill` | `distill --lids ...`（AI 显式判定同根因第 2 次） | 把复发问题固化为条款/脚本（第 40 条④） |
| `rule_change` | 预留，由 AI 显式登记 | 其他规则变更建议 |

**为什么蒸馏不自动判定**：「同根因」是语义判断，靠关键词匹配会误判（作者硬规则：拿不准的不写、不推断）。所以 `distill` 由 AI 显式给出 LID 列表与证据，脚本只负责校验编号存在、去重、记录状态——**确定性归脚本，判断归人/AI 并留证据**。

**作者拍板命令**：

```
python3 scripts/evolution.py proposals --status pending_author
python3 scripts/evolution.py approve P001 --note "同意，按脚本门禁固化"
python3 scripts/evolution.py reject  P001 --note "暂不动模板，继续规避"
python3 scripts/evolution.py verify  P001 --result no-recurrence --evidence "本轮未复发，复跑 exit 0"
```

`approve` 之后 AI 才执行固化，并按第 41 条提交推送 GitHub；`verify` 必须带证据，不接受「感觉好多了」。

**无人值守（cron / 定时轮转）特例**：定时任务只跑 `brief` / `score` / `check` / `source add`，**不得调用 `approve`，也不得执行任何规则固化**。`pending_author` 提议写进日志，等下一轮交互式会话由作者拍板；否则「自动提议、作者确认」会在无人值守时悄悄退化成「自动生效」，直接违反本节红线。

---

## 6. 命令速查

> 全局选项 `--assets-dir` / `--workspace` / `--date` 可写在子命令前或后。`--assets-dir` **仅供测试隔离**，生产一律用默认（技能内 `assets/state`）。

| 命令 | 作用 | 退出码 |
|---|---|---|
| `brief --episode <期号>` | 开工清单：未闭环 LID / 退步维度 / 到期资料 / 待拍板 / 待验证 | 0 |
| `score --episode ... --title ... --camp ... --tier ... --scores ... --evidence ... [--learning-ids \| --no-issues]` | 录五维评分（每维必带证据） | 0 / 1 参数不合格 |
| `check` | 收尾三项门禁 | 0 通过 / 1 BLOCK |
| `source add --claim ... --source ... --level L1 [--version] [--conditions] [--used-in] [--review-days 180]` | 事实卡片入库 | 0 / 1 |
| `source find --keyword <词>` 或 `source find <词>` | 查已核实结论及状态 | 0 / 3 未命中 |
| `source list --status valid\|stale\|retired\|all` | 列卡片 | 0 / 3 空 |
| `source verify --id SC001 [--version] [--note]` | 回源复核通过 → valid | 0 / 1 |
| `source retire --id SC001 --reason <原因>` | 结论作废 → retired | 0 / 1 |
| `source expire` / `source stats` | 到期标记 / 状态统计 | 0 |
| `distill --lids L001,L002 --clause <条款> [--evidence]` | 生成蒸馏提议 | 0 / 1 |
| `proposals [--status ...] [--json]` | 列提议 | 0 / 3 空 |
| `approve <id> --note ...` / `reject <id> --note ...` | 作者拍板 | 0 / 1 |
| `verify <id> --result no-recurrence\|improved\|recurred\|no-data --evidence ...` | 下轮验证进化是否生效 | 0 / 1 |
| `status` | 全量状态总览（只读） | 0 |
| `--help` / `<cmd> --help` | 参数说明 | 0 |

退出码统一：`0` 成功 / `1` 校验失败或门禁 BLOCK / `2` 参数错或台账损坏（**不静默重建**，先人工检查）/ `3` 查询无数据。

---

## 7. 与既有条款的关系

| 条款 | 关系 |
|---|---|
| 第 7 条 忠于权威来源 | 事实卡片库的**上位规则**；复用 `valid` 卡片仍须双源核验，版本变更触发复核 |
| 第 25 条 工匠级品控 | 五维评分卡的锚点来自该条的七维度；§8「持续进步」由本机制变成可执行动作 |
| 第 31 / 34 / 38 条 内容门禁 | `content` / `visual` 维度的证据来源，评分不替代它们 |
| 第 40 条 自主学习与自主迭代 | A 环本体；`brief` 加固②、`check` 加固①、`distill` + 状态机加固④ |
| 第 41 条 必推 GitHub | 所有台账写回与规则固化**当轮必推**；台账滞留本地 = 其他客户端读不到进化结果 |
| 第 33 条 跨客户端续跑 | 台账放技能内共享；执行凭证放工作区；换客户端 `brief` 能读到同一份历史 |
| 第 42 条 GitHub 高赞项目 | 官方仓库版本变更是事实卡片复核的重要触发源 |
| 第 16 条 自主决策 | **不适用**：阈值提档 / 蒸馏固化属于「改技能自己」，明确等作者批准 |

---

## 8. 反模式（明令禁止）

1. **把评分当 KPI 刷分**：为让曲线好看而给无证据的高分 → 直接违反「正确性优先于完整性」；脚本拒收无证据评分，但人仍可编造证据，故此项靠自律 + 作者抽查。
2. **把提议当已生效**：`pending_author` 状态下对外说「规则已改」= 虚假陈述；只有 `approve` + 固化 + 推送 + 下轮 `verify` 才算闭环。
3. **用脚本自动改自己**：任何时候都不得让 `evolution.py`（或任何脚本）自动写入 SKILL.md / scripts 常量；这会让作者失去对规则的最终控制权。
4. **绕过第 7 条**：拿 `valid` 卡片直接写稿、不回源确认版本、性能数字不带测试条件。
5. **只写 metrics.csv 不登记**：第 40 条① 的老坑，`check` 会用 LID 存在性校验拦下。
6. **收紧阈值导致出不了片**：提档后连续 BLOCK 不回滚，把「标准提高」误当「质量提高」。
7. **回填历史数据**：不得凭印象给过往期次补评分、补事实卡片；台账从空开始，只用当轮真实产物。
8. **在技能仓库根跑 brief/score/check**：会把执行凭证写进技能仓库（L009 同款坑），守卫会直接拒绝。

---

## 9. 自检清单

**Step 0 开工**
- [ ] `client_preflight.py gate` 通过后，已跑 `evolution.py brief --episode <期号>`（**必须显式传 `--workspace`**）
- [ ] 未闭环 LID 已逐条标注「已修复且已验证 / 需本轮规避 / 需本轮跟进」
- [ ] 上轮退步维度已定本轮具体改进动作；待拍板提议已提请作者

**Step 1 取材**
- [ ] `source find` 已查本期主题；命中的 `stale` 卡片已回源复核、`retired` 结论未复用
- [ ] 复用的 `valid` 结论仍按第 7 条做了双源核验与版本确认

**Step 8 收尾**
- [ ] `score` 五维齐全、逐维有当轮真实证据、三个计数如实填写
- [ ] 本轮问题已登记 `learnings.md`，LID 已传 `--learning-ids`；确无问题才用 `--no-issues`
- [ ] 本期新核实的可复用结论已 `source add`（带版本与测试条件）
- [ ] `check` exit 0
- [ ] 台账与日志改动已按第 41 条 commit + 推送 GitHub

**作者拍板时**
- [ ] `proposals --status pending_author` 逐条看过证据，`approve` / `reject` 带 `--note`
- [ ] `approve` 后 AI 才固化规则 + 推送；下一轮 `verify` 已带证据回填结果
