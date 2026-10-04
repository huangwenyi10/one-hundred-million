# asset-index.md —— 跨客户端共享资产索引（主题候选池 / 封面底图 / 体系进度）

配套 SKILL.md「固定规范第 33 条」与 `references/cross-client-handoff.md`。
解决一件事：**本技能会被 WorkBuddy / Trae / Codex / Qoder / Kimi 等不同客户端加载执行，
选题候选、封面底图、体系进度这三类「资产」必须各客户端读到同一份，否则会重复劳动、
配色不一致、重复选题。**

---

## 1. 为什么资产必须放技能内（不放在工作区 / 项目 Drive）

| 放哪 | WorkBuddy | Trae / Codex / Qoder / Kimi | 结论 |
|------|-----------|------------------------------|------|
| 工作区根目录 | 能读 | **换机器就是空进度** → 重复选题 | ❌ |
| 项目 Drive（tdrive） | 能读（连接器已接入） | **无此连接器，读不到** | ❌ |
| **技能内 `assets/`** | 能读 | clone/拷贝技能即可读 | ✅ |

**核心原则：技能内 = 唯一事实来源（single source of truth）。**
资产随技能仓库分发，任何客户端只要拿到技能目录就拿到全部资产，**不依赖任何连接器、
不依赖任何客户端私有 API**。

---

## 2. 三类资产与取用方式

| 资产 | 路径 | 维护者 | 取用命令 |
|------|------|--------|----------|
| 主题候选池 | `assets/topics/topic_pool.json` | `pick_topic.py` | `python3 scripts/pick_topic.py pick --camp<训练营> -n 5` |
| 体系进度（covered） | `assets/state/syllabus.json` | `pick_topic.py mark` | 同上，加 `--uncovered-only` 只看未覆盖维度 |
| 训练营合集封面 | `assets/covers/*.png` | 手工（作者提供新图时） | 直接取`assets/covers/<训练营>_合集封面.png` |

路径一律相对**技能根目录**（即 `SKILL.md` 所在目录）。脚本内部用
`os.path.dirname(os.path.abspath(__file__))` 逐级定位，**不依赖 cwd、不依赖环境变量**，
所以在任何客户端、任何目录下执行都指向同一份资产。

---

## 3. 主题候选池（`assets/topics/topic_pool.json`）

### 3.1 定位

Step 0 选题引擎的**第一来源**。旧设计是「每次现造 3-5 个候选」，候选只活在当次对话上下文里，
换客户端就断、且各客户端各造各的、极易撞车。现在改为**先查池、再定选题**。

**取用顺序（Step 0 强制遵循）**：

1. `pick_topic.py pick --camp <训练营> -n 5` 取候选——**池内有条目时优先从池里挑**；
2. 池内该营 `unused` 条目不足、或需追当期热点 → 技能自主生成新候选；
3. 自主生成的候选**必须用 `pick_topic.py add` 回写池**（否则下次又现造，池永远不增长）；
4. 选题定稿、进入生产 → 出片后`mark <id> --status done`，写池状态 + 同步 covered。

### 3.2 条目字段

| 字段 | 含义 | 取值约束 |
|------|------|----------|
| `id` | 稳定标识，格式 `<营缩写>-<序号>`（如 `ARC-01`） | **一经发布不得复用给别的选题**（历史产物按 id 回溯） |
| `title` | 标题锚点，作者给初始标题时的对齐基准 | ≤20 字 |
| `dimension` | 所属能力维度 | 须能在 `references/syllabus.md` 该营能力地图中对上 |
| `angle` | 一句话切入角度 | 须具体到「能照着做」，不是空泛方向 |
| `tier` | 建议档位 | `S` / `M` / `L` |
| `reach` | 预估传播力 | `高` / `中` / `低`（`pick` 按此降序） |
| `hook` | 建议钩子类型 | 反直觉 /踩坑 / 数字对比 / 身份共鸣 / 实测拆解 |
| `aiAngle` | 可挂的 AI 视角 | **挂不上留空字符串，不强拧**（SKILL.md 固定规范第 31 条①） |
| `handsOn` | 是否动手型 | 布尔；用于「每 4 期≥1 期动手型」配比门禁 |
| `risk` | 风险点 | 无则空字符串；涉合规/安全/数据的**必填** |
| `status` | 状态 | `unused` / `done` / `dropped`（弃用须写 `reason`） |

### 3.3 常用命令

```bash
python3 scripts/pick_topic.py list                # 各营候选数 / 可用数
python3 scripts/pick_topic.py pick --camp 架构师- n 5        # 挑候选（支持简称）
python3 scripts/pick_topic.py pick --camp 架构师 --hands-on # 只要动手型
python3 scripts/pick_topic.py pick --camp 架构师 --uncovered-only  # 只看未覆盖维度
python3 scripts/pick_topic.py mark ARC-01 --status done      # 出片后回写
python3 scripts/pick_topic.py mark ARC-02 --status dropped --reason "热点已过时"
python3 scripts/pick_topic.py add --camp 架构师训练营 --title "..." --dimension "..." \\
        --angle "..." --tier M --reach 高 --ai-angle "..." --hands-on   # 回写新候选
python3 scripts/pick_topic.py verify                          # 校验池与进度一致性
```

`pick` 退出码：`0` 有候选 / `4` 池已耗尽（此时按 3.1 第2 步自主生成并 add）。
`verify` 退出码：`0` 通过 / `1` 有错（id 重复、必填缺失、状态非法等）。

### 3.4 维护约定

- **池是共享的，改动即影响所有客户端**：手工编辑 JSON 也认（脚本每次读盘重新解析，无内存缓存）。
- **并发安全**：`mark` / `add` 用「临时文件 + `os.replace`」原子替换，避免写到一半被另一客户端读到。
- **别硬编码营名**：脚本接受简称（「架构师」「大数据」「AI」均可），内部去掉「训练营」后缀做匹配。
- **定期`verify`**：改动池结构后跑一次，防止 id 重复 / 状态写错。
- **池不是待办清单**：条目是**候选**，不是必须做完的章节。池里某条不合适就`dropped` + 写原因。

---

## 4. 体系进度（`assets/state/syllabus.json`）

### 4.1 为什么从工作区搬到技能内

旧设计：进度写**工作区根** `one-hundred-million-syllabus.json`。工作区是本机本地的——
换到 Trae / Codex 打开同一工作区时若进度没同步（或换机器），就是一份空进度，
**会重复讲已讲过的维度**。现在改为技能内共享真相源，各客户端 clone 同一技能即接着走。

### 4.2 结构

```json
{
  "schema": "ohl-syllabus-state/1",
  "updated": "2026-10-04",
  "camps": {
    "架构师训练营": {
      "expertGoal": "能独立承担系统架构设计…",
      "lastTopic": "缓存雪崩的真正解法",
      "covered": ["高可用与稳定性"]
    }
  }
}
```

`covered` 是**开放关键词列表**（非固定编号），记录已覆盖的能力维度 / 主题节点，用于
**去重 + 决定下一期往哪个维度延展**。读书训练营不走本文件，按书中章节走
`reading_camp_progress.json`（选书事实来源见 `references/author-book-list.md`）。

### 4.3 与工作区旧文件的关系

- **技能内是唯一真相源**。工作区若已有旧 `one-hundred-million-syllabus.json`，
  用迁移脚本并入技能内（**合并、不覆盖**，幂等）：

```bash
python3 scripts/migrate_syllabus_state.py --workspace <工作区>            # 预览（默认不写盘）
python3 scripts/migrate_syllabus_state.py --workspace <工作区> --apply    # 确认后写入
python3 scripts/migrate_syllabus_state.py --export --workspace <工作区>   # 反向导出（旧客户端兼容）
```

- 迁移脚本退出码：`0` 已同步 / 无需动，`3` 未找到旧文件（**正常**，多数工作区从未生产过其余 8 类），`1` 出错。
- 旧工作区文件**保留不动**（只读参考），别回手改——改了对技能内无效。

---

## 5. 训练营合集封面（`assets/covers/`）

### 5.1 来源与现状

8 张 `xx训练营_合集封面.png`（读书 / 架构师 / 大数据 / AI / 产品 / 前端 / 测试 / 管理），
原存项目 Drive `项目资产/We-Media/`，2026-10-04 归集进技能内，共约 5.4MB。
`assets/covers/MANIFEST.json` 记录每张图的 camp / 尺寸 / 字节数 / sha256 / 来源 Drive file_id。

### 5.2 ⚠️ 使用边界（硬约束，务必先读）

图中**训练营名称是烧录进画面的文字层**，不是透明背景。因此：

| 场景 | 能否用这张图 | 依据 |
|------|-------------|------|
| 抖音 / 快手**「合集 · 专辑」入口封面**、训练营主页横图、课件 PPT 首屏 | ✅ 可以 | 合集封面本就该展示训练营名|
| **单条视频的封面图**、视频**前 3 秒画面** | ❌ **禁止** | 命中固定规范第 14 条（成片画面禁训练营标识/期号）+ `douyin-compliance.md` §6「不当宣传/招募（画面）」；**2026-09-13 SRE 上篇已实测被限流** |

单条视频封面须另出**无标识版**（见固定规范第 14 条与读书训练营专项「`封面_16x9` / `封面_9x16`」规则）。
读到本文件的使用边界就不要再拿合集封面当视频封面。

### 5.3 命名差异（脚本已处理，人工注意）

规范营名是「**AI 训练营**」（带空格，SKILL.md / camp_switch.py 口径），
而封面文件名是「**AI训练营**」（无空格，来自 Drive 原名）。`pick_topic.py` 内部按去空格匹配，
人工查找时注意两种写法都指同一个营。

### 5.4 配色参考

- 各营主题色见 SKILL.md「训练营主题色」表（架构师=绿、大数据=蓝、产品=紫、AI=深酒红…）。
- **读书训练营合集封面底图为纯白 `(255,255,255)`、标题玫红**——与用户 2026-09-26 决策一致：
  **禁止用主题色重铺背景**，「白色就是白色」；合成后角点/空白区须实测为精确 `(255,255,255)`。
  脚本见 `读书训练营合集封面/render_cover_white.py`。

---

## 6. 换客户端时怎么就位（30 秒）

各客户端拿到技能目录后，资产即就位，**不需要额外配置、不需要连任何连接器**。
唯一要注意的是**进度要在git 仓库层面同步**（否则另一台机器 clone 到的进度偏旧）：

```bash
# 1) 拿到技能（含 assets/ 全部资产）
git clone <repo> skills/one-hundred-million     # 或直接拷贝技能目录

# 2) 体检+ 看有没有别人的活没干完
python3 scripts/client_preflight.py probe
python3 scripts/jobctl.py scan --workspace <工作区>

# 3) 选题：先查共享池，不要现造
python3 scripts/pick_topic.py list
python3 scripts/pick_topic.py pick --camp <训练营> --uncovered-only -n 5
```

提交进度变更回仓库，让其他客户端下次clone 拿到最新状态（**否则各客户端会重复选题**）：

```bash
#改了 topic_pool.json / syllabus.json 后
cd skills/one-hundred-million
git add assets/ && git commit -m "chore(sync): 回写选题状态与体系进度"
```

> 各客户端的模型额度彼此独立，但**资产是共享的**：额度用完时按
> `references/cross-client-handoff.md` §3.3 记 `jobctl block` + `pick_free_model register exhausted`，
> 换台客户端跑`jobctl resume` 即可接着干——**已讲过的选题、已出片的阶段一步都不重做**。

---

## 7. 自检清单（改动资产后对照）

- [ ] `python3 scripts/pick_topic.py verify` exit 0（无 id 重复 / 状态非法 / 必填缺失）
- [ ] `list` 显示的各营可用数与预期一致（没有误标`done`）
- [ ] `pick --uncovered-only` 能正确读出 `camps` 下的 `covered`（不是读顶层——那是曾经的 bug）
- [ ] 封面改动后 `MANIFEST.json` 的 sha256/尺寸已同步
- [ ] 读合集封面用途时确认走的是「合集入口」而非「单条视频封面」
- [ ] 进度与池状态的改动已提交到仓库（否则其他客户端读到旧值会重复选题）
