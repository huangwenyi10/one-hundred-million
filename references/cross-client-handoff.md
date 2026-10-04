# cross-client-handoff.md —— 跨客户端续跑 SOP（额度用完换台客户端接着干）

配套 SKILL.md「固定规范第 33 条」。解决一件事：**本技能会被 WorkBuddy / Trae / Codex /
Qoder / Kimi 等不同客户端加载执行，各客户端模型额度彼此独立；A 客户端额度用完时，
换到 B 客户端能把没做完的视频接着做完，且已完成的部分一步都不重做。**

---

## 1. 为什么需要（不解决会怎样）

纯靠对话记忆的流水线一旦换客户端就断：新产品会话里没有上一台机器的上下文，
模型不知道自己写过稿、渲过帧、配过音，只能从零重跑——作者的机时 wasted、额度二次消耗、
`build/` 还可能被两边同时写坏。

三个具体的失效点：

| 失效点 | 后果 | 本方案 |
|--------|------|--------|
| 进度只在对话里 | 换客户端 = 从零重跑 | 进度落磁盘：产物在 = 阶段已完成（`jobctl.py scan` 实物核对） |
| 额度是全局假设 | 以为「额度用完 = 全都做不了」 | 额度按客户端隔离（`pick_free_model.py --client`），换客户端即可继续 |
| 缺依赖时静默失败 | 换台机器才发现缺 ffmpeg/字体，白跑 | 开工前 preflight（`client_preflight.py probe`），缺什么当场报 |

**核心原则：产物即进度（artifacts are state）。** 只要文件在磁盘上，那一步就算完成，
不需要任何人记着。台账只是索引，**冲突时以磁盘实物为准**。

---

## 2. 三个脚本，各管一件事

| 脚本 | 回答什么问题 | 关键点 |
|------|--------------|--------|
| `scripts/jobctl.py` | **做到哪一步了？下一步做什么？** | 扫描磁盘实物判定阶段；生成续跑包 |
| `scripts/client_preflight.py` | **这台机器/这个客户端能不能干？** | 探测 ffmpeg/edge-tts/node/Chrome/字体/连接器；登记各客户端额度 |
| `scripts/pick_free_model.py` | **用哪个模型？额度还有没有？** | 已改造为按客户端命名空间隔离 + 跨客户端额度提示 |
| `scripts/pick_topic.py` | **这期选什么题？跟别的客户端撞了吗？** | 读**技能内**共享主题候选池，按 `covered` 去重 |

全部**只依赖 Python 标准库 + 通用可执行文件**，不调用任何客户端私有 API——
所以换到 Trae / Codex / Qoder / Kimi 上照样能跑。

### 2.1 共享资产 vs 工作区状态（两类东西，别搞混）

跨客户端协作时最容易踩的坑是**以为所有东西都跟着工作区走**。实际分两类：

| 类别 | 位置 | 换客户端后| 文件 |
|------|------|-----------|------|
| **共享资产**（选题候选 / 封面底图 / 体系进度） | **技能内 `assets/`** | **自动就在**（clone/拷贝技能即得，不依赖连接器） | `assets/topics/topic_pool.json`、`assets/covers/*.png`、`assets/state/syllabus.json` |
| **工作区状态**（任务台账 / 客户端额度 / 模型冷却） | 工作区根 | 跟着工作区目录走 | `one-hundred-million-jobs.json`、`-clients.json`、`-model-fallback.json` |

**共享资产为什么要放技能内**：放工作区则换机器就是空进度（重复选题）；放项目 Drive 则
Trae / Codex / Qoder / Kimi 没有该连接器、根本读不到。完整取用与维护见
`references/asset-index.md`。

> ⚠️ 共享资产里的**体系进度**要提交到技能仓库才有效——否则其他客户端 clone 到的进度偏旧、
> 会重复选题。`mark` / `add` 之后 `git add assets/ && git commit`。

---

## 3. 标准流程

### 3.1 开工（每个客户端每次必做，30 秒）

```bash
# ① 本机能力体检：缺什么当场报，别等渲完帧才发现没 ffmpeg
python3 scripts/client_preflight.py probe
python3 scripts/client_preflight.py register <客户端名> --probe

# ② 扫描工作区：有哪些没做完的视频、分别卡在哪
python3 scripts/jobctl.py scan --workspace <工作区>     # exit 4 = 有活可续

# ③ 有活 → 直接拿续跑包（自动认领 + 打印下一步精确命令）
python3 scripts/jobctl.py resume --workspace <工作区> --client <客户端名>

# ④ 没活要开新选题 → 先查共享候选池（别现造，会跟别的客户端撞车）
python3 scripts/pick_topic.py pick --camp <训练营> --uncovered-only -n 5
```

`resume` 输出的续跑包含：目录路径、**上一客户端在哪个阶段因什么中断**、
已完成阶段清单（磁盘实物核对）、下一步该做什么（含可直接复制的命令）。

### 3.2 干活中（正常推进）

每完成一个阶段显式记一笔，便于别的客户端/人接手时一眼看清：

```bash
python3 scripts/jobctl.py done "<标题>" --stage frames --client <客户端名>
```

注意：`done` 不盲信自报——它会**重新扫描磁盘**，产物不存在就返回 `exit 1` 并告诉你缺什么。

### 3.3 撞上限额（关键动作，不能只是停下）

```bash
python3 scripts/pick_free_model.py exhausted <模型id> \
        --reason "credit 额度已用完" --client <客户端名> --workspace <工作区>
python3 scripts/pick_free_model.py register exhausted \
        --reason "credit 额度已用完" --client <客户端名> --workspace <工作区>
python3 scripts/jobctl.py block "<标题>" \
        --reason "credit 额度已用完" --client <客户端名> --workspace <工作区>
```

三条命令的分工：`pick_free_model` 记模型冷却、`register` 记客户端额度、
`jobctl block` 记**任务卡在哪个阶段**——最后这条是换客户端能续上的关键。

然后**先把能做的做完再停**：确定性步骤（ffmpeg 合成、字幕烧录、`check_sync` 校验、
像素扫描）**不耗额度、不需要模型**，照跑不误，能省下一台客户端的活。

### 3.4 换客户端接手

在**新客户端**里打开同一个工作区，然后：

```bash
python3 scripts/client_preflight.py probe                     # 先看这台机器有没有依赖
python3 scripts/jobctl.py clients --workspace <工作区>        # 看哪些客户端还有额度
python3 scripts/jobctl.py resume --workspace <工作区> --client <新客户端名>
```

`resume` 会打印上一客户端的中断原因与精确续跑命令，**不需要作者复述任何上下文**。

---

## 4. 阶段与实物对照表（`jobctl.py` 的判定依据）

| 阶段 key | 对应 Step | 磁盘实物（任一命中即算完成） |
|----------|-----------|------------------------------|
| `script` | Step 1 | `<目录>/*_口播稿.txt` |
| `ppt` | Step 2 | `<目录>/*_PPT.html` |
| `frames` | Step 2 | `build/frames/page_*.png` |
| `tts` | Step 3 | `build/voiceover.mp3` |
| `segments` | Step 5 | `build/segments_durations.json` |
| `subs` | Step 5 | `build/subtitles.srt` / `subtitles_fixed.srt` |
| `body` | Step 6 | `build/body.mp4` |
| `final` | Step 6 | `<目录>/*_成片.mp4` |
| `publish` | Step 8 | `发布/*` |

**「已出片」即视为流水线完工**：成片存在就说明 Step 1-6 全部跑完，
Step 7（作者审核）/ Step 8（发布归档）属人工环节，不算「未完成的活」。
—— 否则历史交付目录一旦按固定规范第 24 条清理掉 `build/` 与口播稿，
每次 `scan` 都会把它们误报成可续跑任务。

---

## 5. 能力降级矩阵（缺依赖时怎么办）

`client_preflight.py probe` 的输出直接对应这张表。**核心依赖缺失 = 无法出片，必须换机器或装齐**。

| 依赖 | 等级 | 缺失后果 | 处置 |
|------|------|---------|------|
| `python3` | 核心 | 所有技能脚本跑不了 | 装 Python 3.9+ |
| `ffmpeg` / `ffprobe` | 核心 | 合成/字幕/水印全废；读不了真实时长 → 时间轴退化成估算（**硬违规**） | `brew install ffmpeg` |
| `edge-tts` | 流水线 | 做不了配音与逐字字幕 | `pip install edge-tts` |
| 中文字体 | 流水线 | 字幕渲染成方框 | 装 PingFang / Noto Sans CJK / 思源黑体 |
| `PIL` | 流水线 | 字幕/水印 alpha 叠加层做不出来 | `pip install pillow` |
| `node` ≥22 | 可选 | `render_animated.js` 动画增强不可用 | 回退静态帧导出（Step 6 第 2 条），出片不受影响 |
| `chrome` | 可选 | 同上 | 同上 |
| 百度网盘 / tdrive 连接器 | 可选 | Step 8 归档 / 项目资产同步做不了 | 降级为交付「发布就绪包」到本地 `发布/`，日志标注待归档 |

**换机器的额外风险**：不同机器的 ffmpeg / 浏览器版本不同，**渲染结果可能有细微差异**。
跨机器续跑时，`frames` 与 `body` 之间不要在两台机器上来回切——
要么全在一台机器渲完，要么渲完把 `build/frames/` 整体拷过去。

---

## 6. 状态文件（工作区根，唯一事实来源）

| 文件 | 维护者 | 内容 |
|------|--------|------|
| `one-hundred-million-jobs.json` | `jobctl.py` | 任务台账：目录、已完成阶段（实物核对）、认领方、中断原因、历史 |
| `one-hundred-million-clients.json` | `client_preflight.py` / `pick_free_model.py register` | 各客户端名称、额度状态、能力（ffmpeg/edge-tts） |
| `one-hundred-million-model-fallback.json` | `pick_free_model.py` | 各客户端的模型冷却记录（**已改为按客户端命名空间**） |

**手工改动以文件为准**；三者都在工作区根，跟着目录走，换客户端不会丢。

**另有一组「共享资产」在技能内**（不在工作区）：`assets/topics/topic_pool.json`（主题候选池）、
`assets/covers/*.png`（合集封面底图）、`assets/state/syllabus.json`（体系进度 covered）——
随技能仓库分发，各客户端 clone 即得，详见 §2.1 与 `references/asset-index.md`。

---

## 7. 避坑（已踩）

- **不要在两台客户端上并行做同一条视频**：`build/` 会互相覆盖。`claim` 有租约机制，
  但**租约只是提醒，不是锁**——接手前先确认上一客户端确实停手了。
- **不要为了「换客户端」重跑已完成阶段**：配音重跑会让时间轴全变、字幕错位、
  `check_sync.py` 直接挂。已完成的产物**一律复用**。
- **不要因为读不到模型配置就停工**：非 WorkBuddy 客户端读不到产品配置是**正常**的
  （`pick_free_model.py` 返回 `exit 3`），直接用该客户端自带模型继续。
- **不要把「客户端额度用完」当成全局停工**：额度按客户端独立，
  WorkBuddy 没了 Trae / Codex 往往还有。
- **不要在 Step 7 发布关卡换客户端重生成**：成片已进审核，换客户端重跑会破坏已审成品；
  发布动作永远等作者批准（与第 23 条同一边界）。
- **不要信自报的进度**：`jobctl.py done` 会重新扫磁盘，产物不在就是没完成——
  这正是它能跨客户端可靠续跑的原因。
- **不要在新客户端里"重新想一个选题"**：选题候选在**技能内共享池**，换个客户端现造会跟上一个客户端撞车。
  先 `pick_topic.py pick --uncovered-only`。
- **不要把 `assets/covers/*_合集封面.png` 当单条视频封面用**：图中训练营名是烧录文字层，
  用作视频封面/前 3 秒画面会命中固定规范第 14 条与抖音「不当宣传/招募（画面）」限流规则
  （2026-09-13 SRE 上篇实测）。它的用途是**合集/专辑入口封面**——详见 `references/asset-index.md` §5.2。
- **清理工作区时别删台账**：`one-hundred-million-*.json` 是跨客户端续跑的唯一依据，
  不属于固定规范第 24 条可清理的 build 中间产物。**但也别删技能内 `assets/`**——
  那是共享资产本体（候选池 / 封面 / 进度），删了下个客户端就取不到。

---

## 8. 自检清单（换客户端后对照）

- [ ] 跑过 `client_preflight.py probe`，核心 + 流水线依赖齐全（exit 0）
- [ ] 跑过 `jobctl.py scan`，知道有哪些未完成任务（exit 4 = 有活）
- [ ] `jobctl.py resume` 已看过：上一客户端的中断原因与下一步命令明确
- [ ] 已 `claim` 认领，确认上一客户端已停手（不并行写 `build/`）
- [ ] 选题走的是**共享候选池**（`pick_topic.py pick --uncovered-only`），不是现造——否则会跟别的客户端撞选题
- [ ] 上一客户端的 `mark` / `add` 改动**已提交到技能仓库**（否则读到的进度偏旧）
- [ ] 已完成阶段**一个都没重跑**（配音/时间轴/字幕尤其不能重生成）
- [ ] 质量门禁一条没少跑：`check_sync.py` exit 0、禁句禁标识扫描、
      字幕带与水印区像素扫描、素材双源核验（换客户端不豁免）
- [ ] 中断时已跑 `jobctl.py block` + `pick_free_model.py register exhausted`，
      下一个客户端才接得上
