# 架构图生成技能接入（diagram-generation）

> 本文档是 `one-hundred-million` 与 **`contextweave-interactive-architecture`（架构图一键生成，SkillHub 最热 dl≈279982）** 技能的对接规范。
> **作用**：用专门的架构图技能产出**高质量、可编辑**的架构 / 流程 / 拓扑 / 思维导图（SVG / HTML），嵌入视频图示页，替代或增强原本手写 SVG 与纯 HTML/CSS 重绘。
> **定位**：**可选增强路径**，不替代既有硬约束（左上水印安全区 / 底部字幕带 / 训练营主题色 / 去侵权 / 无训练营标识期号），也不推翻 SKILL.md Step 2.4 的图示来源优先级链。

---

## 0. 与既有流程的关系

SKILL.md Step 2.4 图示来源优先级链：**资产原图 > 官网/官方文档官方图 > HTML/CSS 重绘**。
本技能生成的图属于「**HTML/CSS 重绘**」档（原创、去侵权安全）：当资产原图与官方图都不可得、或你要更高质感 / 可编辑的原创架构图时启用。

- **离线 / 作者拒绝外发授权 / 云端失败 → 回退**到 `slide-template.html` 内置 `.diagram-grid/.nodebox/.flow`（见 `visual-design.md` §8.1），**不阻塞生产**。

---

## 1. 何时启用

- 该页需要**架构 / 流程 / 拓扑 / 思维导图**，且内容较复杂（多组件、跨层、带流向），手写 SVG 易溢出 / 错位、质感不足时。
- 读书训练营：原书关键图示需「忠于原书概念、自绘原创示意图」——可用本技能生成原创示意图骨架，再按读书营规则标注「示意图，基于《书名》第 N 章」（**不得复制原书像素**）。
- 简单单屏小图（≤6 节点、≤3 层）直接用模板组件，不必调用本技能。

---

## 2. 调用接口（来自 `contextweave-interactive-architecture` 技能）

1. **写请求文件**（工作区绝对路径，如 `<视频标题文件夹>/.cw_skill/requests/request_<timestamp>.md`）：

   ````
   # Request
   [展示重点、绘图意图、必要背景、明确关系与已确认的展示要求，50-5000 字符。
    把"参考某文件 / 某术语"解引用为自包含纯文本（先读文件拍平、补全术语的角色/层级/动作/上下游）]

   # CW
   （首次生成留空；修改已有图时放当前 CW 全文）
   ````

2. **执行脚本**（需 `node` ≥22；数据发往云端 `https://pptx.chenxitech.site`）：

   ```bash
   node ~/.workbuddy/skills/contextweave-interactive-architecture/scripts/generate_contextweave.cjs \
     --input_file "<请求文件绝对路径>" \
     --output_name "<语义化英文名, 如 order_payment_flow>" \
     --output_dir "<视频标题文件夹>/build/diagrams" \
     --diagram_style topology|logic|hybrid|mindmap \
     --morphology container|flow|editorial \
     --base_palette '{"primary":"<训练营主色 hex>","style_preset":"tech_blue"}' \
     --accent_targets '[{"name":"支付网关","color":"暖橙"}]'
   ```

   - `--diagram_style`：组件关系 = `topology`、步骤/因果/时序 = `logic`、流程 + 归属 = `hybrid`、中心展开 = `mindmap`。
   - `--morphology`：强调模块归属 = `container`、强调流向 = `flow`、强调说明 = `editorial`。
   - `--base_palette`：主色传**当前训练营主色**（保主题色一致）；`style_preset` 可选 `tech_blue` / `corporate_blue` / `corporate_red`。
   - 脚本产出 `<output_name>.cw` 并下载 **SVG/HTML** 到 `output_dir`（需原生可编辑 PPTX/VSDX 时再取 `session_id` 调 `export_session_asset.cjs --format pptx|vsdx`）。
   - 详细协议与反模式见该技能 `SKILL.md` 与 `references/`。

3. **外发授权（强制 · 一次性）**：首次联网前，向作者简要说明「本任务将把绘图意图文本发送到云端 `pptx.chenxitech.site` 用于生成图表」，取得一次明确同意；同一任务内不重复询问。作者拒绝 → 回退模板组件路径。

---

## 3. 映射进视频图示页（关键 · 不破坏硬约束）

1. 把生成的 **SVG** 内联进 `slide-template.html` 的 `.diagram-stage` 容器（或 `<img src="build/diagrams/xxx.svg">`）；HTML 版则整体嵌入。
2. **套用 `visual-design.md` 约束**：
   - §1.4 图示页：图占版面 55%~75%、四周留白；**图示底部必须收在底部字幕带（y 88%~95%）以上**。
   - §2.6 架构/流程图：层与层用分区底色分隔、数据流方向统一（左→右 或 上→下），不来回绕。
   - §8 健壮性：一屏节点总数 ≤6、流程步骤 ≤5；超过则拆「总览 → 分层」两页，不要硬塞。
   - 节点文字超长：生成图虽已自动处理，但最好在 `# Request` 阶段就约束「节点文字 ≤8 字、超长拆子节点」。
3. **去侵权**：本技能产出为原创 SVG，**本身无第三方水印 / Logo**，安全；但若混合使用 Step 2.4 链里的「官网官方图」，那些仍需裁切去水印（不变）。
4. **主题色**：通过 `--base_palette` 主色对齐训练营主色，避免杂色；图内高亮用 `--accent_targets`。
5. 静态帧导出（`?page=N`）后，按 `visual-design.md` §6 / §8.3 逐页检查图示：节点、箭头、图例完整、无重叠、无溢出、不侵入水印安全区 / 字幕带。

---

## 4. 边界与反模式（来自该技能 + 本技能约束）

- 不承诺像素级布局 / 精确样式（该技能不支持绝对坐标）——只传语义级意图，布局交后端。
- 一张图只回答一个核心问题；复杂时拆多视图（该技能会触发确认门，先给拆分方案等作者确认，不擅自拆）。
- 不得把「参考某文件」悬空写进 `# Request`——先读文件拍平为纯文本。
- 禁用：`zoompan`、手写绝对定位 + 硬编码 SVG（已有模板组件即用模板）；**生成的图也不得出现训练营标识 / 期号**（固定规范第 14 条）。
- 云端失败 / 超时：按该技能 `references/error-recovery.md` 处理，或回退模板组件，不阻塞交付。

---

## 5. 合成前自检

- [ ] 已按需取得外发授权（或已回退模板组件路径）。
- [ ] 生成的图已按 `visual-design.md` §1.4 / §2.6 / §8 放入 `.diagram-stage`，底部收在字幕带以上。
- [ ] 主色对齐训练营主题色；无杂色、无第三方水印 / Logo。
- [ ] 一屏节点 ≤6、步骤 ≤5；超则已拆页。
- [ ] 静态帧导出后图示无溢出 / 重叠 / 侵入安全区。
