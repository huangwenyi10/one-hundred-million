# 自主学习登记簿（learnings.md）

> 本文件是 one-hundred-million 技能「发现问题 → 自主迭代 → 作用于下个视频」的**跨轮唯一事实来源**（固定规范第 40 条）。
>
> - **追加式登记**：Step 8 收尾必写（只写 metrics.csv 备注或会话记忆不算登记）；
> - **开工必读**：Step 0 第一步先读本文件 open/fixed 未归档记录，生成本轮「防复发检查清单」；
> - **分类四类**：`脚本bug` / `排版规则` / `流程缺口` / `门禁失效`；
> - **五元组**：现象 → 根因 → 修复 → 防复发点 → 状态（open / fixed / verified / distilled / archived）；
> - **蒸馏纪律**：同一根因第 2 次出现 → 必须固化为 SKILL.md 固定规范条款或脚本硬门禁（能脚本化的优先脚本化），本条标注「已蒸馏 → 条款号」；已成规范的记录移入 `references/craft-quality.md` 归档，SKILL.md 只留指针。

---

## 2026-10-25 · 管理训练营 · 期号 17《技术债抢排期：把利息算给业务看》

### L001 [脚本bug] export_frames.py 导帧命名与流水线约定不符 → **fixed / verified**

- **现象**：P11 返工后重导帧，脚本报告成功，但 `page_11.png` 时间戳与内容均不变，下游 `compose_motion.py` 实际拿到的是旧帧。
- **根因**：脚本产出 `page_{i:03d}.png`（三位数 `page_011.png`），而流水线约定（SKILL.md、jobctl、历史 17 帧）全是两位数 `page_NN.png`——重导帧静默写出另一个文件名，消费方全部找不到。
- **修复**：`{i:03d}` → `{i:02d}`（技能仓库 commit `df46862`，已推送 GitHub）。
- **防复发点**：已修脚本；重导帧后与手动 Chrome 渲染产物 md5 逐字节一致，下游命名约定全链统一。
- **状态**：fixed / verified。

### L002 [脚本bug] gen_sync_subs 的 pad_audio 静默失败致封面段时长归零 → **fixed / verified**

- **现象**：`voiceover.mp3` 缺失、字幕时间轴整体前移约 3 秒。
- **根因**：`pad_audio` 用 `-af apad` + `-c:a copy`（音频滤镜与流复制冲突），ffmpeg 静默失败 → `seg_00_pad.mp3` 未生成 → `durations[0]=0.0` → concat 引用缺失文件失败（`capture_output=True` 吞掉错误）。
- **修复**：改 `-c:a libmp3lame -b:a 128k` 重编码；concat 加 returncode 检查 + 缺失文件显式 `exit 1`（commit `df46862`）。
- **防复发点**：已修脚本；`check_sync` PASS（102 cues / 偏差 0.08s）佐证时间轴正确。
- **状态**：fixed / verified。

### L003 [门禁失效] verify_burn 盲采样点踩 cue 边界误报 FAIL → **fixed / verified**

- **现象**：`verify_burn.py` 在 t=1.00 判字幕「大家好」FAIL，抽帧实画面是「我是Map」。
- **根因**：默认采样点 [1.0, 5.0, 12.5] 中的 1.010 恰在两条 cue 边界上；字幕母版按 30fps 整帧量化，切换点比 srt 边界早 ≤122ms（**有界不累积**，音频同步由 `check_sync.py` 权威把关，非缺陷）。默认采样无边界避让即盲踩。
- **修复**：默认采样改边界避让（±0.25s，自动选 cue 中部）；显式传入的采样点仍尊重但打边界提示；顺修 `__main__` 兜底预填 samples 致自动采样不生效的入口 bug（commit `df46862`）。
- **防复发点**：已修脚本；复跑 PASS（自动采样 23.6 / 147.6 / 271.6s）。
- **状态**：fixed / verified。

### L004 [排版规则] 封面 hero 文字侵入字幕带（违反固定规范第 15 条） → **fixed / verified（已一步到位配脚本门禁）**

- **现象**：烧录后 verify_burn 字幕 bbox 异常宽（841px），抽帧发现封面说明文字落在 y≈930，与字幕「我是Map」重叠（7904px 侵入）。
- **根因**：封面 `.hero` 用 `flex-end + padding-bottom:120px` 把文字推至 y≈960。第 15 条禁「内容入字幕带」，但**封面 hero 版式的 flex 陷阱未被显式覆盖**，纯人眼排版检查漏过。
- **修复**：`padding-bottom` 120px → 260px（文字落位 y777-808），重导帧重烧录，字幕带清零。
- **防复发点**：**新增 `scripts/subtitle_band_check.py`**（Step 6 导帧后强制跑）——本轮为手动 python 扫描，已产品化为确定性像素门禁，人眼漏得掉、脚本漏不掉。
- **状态**：fixed / verified（本轮 17 帧复跑 PASS）。

### L005 [排版规则] P11 柱状图（`.bars`）色柱在 flex 布局不渲染 → **fixed（版式规避）/ open（组件缺陷待根治）**

- **现象**：P11 计划用 `.bars` 柱状图承载「7 天 → 3 天」对比，色柱像素扫描为 0——height 百分比与固定 px 两种写法均不显示。
- **根因**：`.col` 柱高在 flex 容器内被压缩/塌陷，`templates/slide-template.html` 的 bars 组件本身有健壮性缺陷。
- **修复（本轮）**：改用 `diagram-grid` 双 nodebox 对比（7 天 dim → 3 天 hot），`visual_plan.md` 同步声明。
- **防复发点**：暂以「关键数据不用 bars 承载」规避；**组件根治留待第 2 次撞上时按第 40 条④强制执行**（修模板 `.bars` 或给 `visual_presence_check.py` 加 bars 渲染探针）。
- **状态**：fixed（版式）/ open（组件）。

---

## 2026-10-25 · 软技能训练营 · 期号 18《被问期望薪资，区间别报死》

### L006 [门禁失效] visual_presence_check 误把 CSS 注释里的 section 示例文本解析成幻灯片页 → **fixed / verified（模板根因已修）**

- **现象**：visual_presence_check 报「幻灯片总数 17」（实际 16 页），页码整体错位——载体页列表 [4..15]、纯文字页 [1,2,3,16,17] 与真实页序不符。
- **根因**：`SLIDE_SPLIT_RE` 按 `<section[^>]*class="[^"]*\bslide\b` 匹配，而 `templates/slide-template.html` 头部使用注释里写着「每页一个 `<section class="slide">`，从下方『版式组件』选一个骨架」——每个套模板的 PPT 都会带这段注释，于是每期都会被误解析出 1 个「假页」排在真实页前面。
- **修复**：模板注释中的 `<section class="slide">` 字样改为「slide 章节块」（不触发正则）；本期 PPT 同步删除该字样。修复后复跑 16 页、页码归位 PASS。
- **防复发点**：模板根因已修（`templates/slide-template.html`），后续所有套模板产出的 PPT 不再带该误匹配源；`split_slides` 行为不变。
- **状态**：fixed / verified。

### L007 [流程缺口] visual_plan 载体列「—（说明）」带后缀被计入声明数致 BLOCK（期号12 同款复发） → **distilled（脚本门禁已加固）**

- **现象**：plan 有 4 个非载体段（封面/split/卡片/CTA），载体列写「—（封面 hero 版式页）」，visual_presence_check 报「声明载体 16 段 / 落实 12 页」BLOCK。
- **根因**：`read_plan` 对「未声明载体」的判定是**精确相等**（`cells[3] not in ("—","-","无")`），任何带后缀的说明文字都会逃过判定被计为声明。**期号12（2026-10-18）已踩过同款坑并记入 metrics 备注，但未沉淀为登记簿条目、未修脚本——本轮复发，属第 2 次同根因。**
- **修复**：① 本期 plan 四行改精确「—」；② **蒸馏**——`visual_presence_check.py` 的 `read_plan` 判定改为 `startswith(("—","-","无"))` 前缀判断，带后缀说明也不再误计（已复跑验证 PASS）。
- **防复发点**：脚本门禁已加固；SKILL.md 侧无需再文字提醒。
- **状态**：distilled → `scripts/visual_presence_check.py` read_plan。

### L008 [流程缺口] segments 段过短致闪页（期号17 同款复发） → **distilled（脚本提示已加固）**

- **现象**：本期 segments 段7「具体怎么落地？记住三步。」仅 12 字，配音约 3 秒，对应页会闪页。
- **根因**：按页切分时为对齐 PPT 页留了过渡段，未校验段长下限；M 档单页停留 10-15 秒，<10s 即闪。**期号17（2026-10-25 管理营）踩过同款（段仅 26 字），当时只在本期 metrics 备注记录、未固化——本轮复发，属第 2 次同根因。**
- **修复**：① 本期口播稿/segments 同步扩充段7 至 40 字（≈10s），重新校验「拼接==原文」；② **蒸馏**——`gen_sync_subs.py` 读取 segments 后增加短段 WARN（<40 字列出段号与字数，提示平衡切分点）。
- **防复发点**：脚本提示已加固；切分 segments 后跑 gen_sync_subs 即会暴露短段。
- **状态**：distilled → `scripts/gen_sync_subs.py` 短段 WARN。

---

## 观察项（未构成问题，登记备查）

- O1（2026-10-25）：字幕母版 30fps 整帧量化与 srt 边界存在 ≤122ms 有界漂移（不累积、音频由 check_sync 权威把关）——**已知公差，不是缺陷**；若未来漂移越过 ±0.5s 或开始累积，升级为 `脚本bug` 类登记并修烧录引擎。

---

## 2026-10-25 · 读书训练营 · 停工待料轮（#2《迈向AGI时代》原书文件未提供）

### L010 [流程缺口] 10-15 的 capture_book_figs.py 修复版遗漏推送，远端长期持旧版（gate 联网时才暴露） → **fixed / verified（已补推 + 本地远端对齐）**

- **现象**：本轮 gate 的 `git fetch` 联网成功，报「本地落后 origin/main 59 个提交」；排查发现远端 `scripts/capture_book_figs.py` 是 10-13 旧版（364 行，无 `get_image_info` 图区判定修复），本地却是 10-15 晚 `66efb02` 修复版（523 行，含三类排除 + 文字密度门禁）。
- **根因**：①10-15 晚轮次自报「已推送」（远端 5870132），但该文件实际未落远端（疑当轮 `FILES_JSON` 未含它，或后续某客户端以旧版覆盖）；②API 推送按文件逐个生成新 commit，本地 commit 对象永远不在远端 → 慢性分叉；③此前各轮 gate 的 fetch 均超时走离线 WARN 通道，分叉一直不暴露，本轮联网才炸。
- **修复**：① API 补推修复版（PUSH_OK，commit 300979c）；② `git merge origin/main` 解 add/add 冲突取本地修复版；③ `git reset --hard origin/main` 对齐（reset 前已验证 `git diff HEAD origin/main` 为空，两树内容一致，不丢任何内容）；④ gate 复跑 PASS。
- **防复发点**：gate 在线时分叉必现（已有兜底）；**新增纪律（替代「PUSH_OK 即完事」）：每轮 API 推送后 `git fetch` + `git diff HEAD origin/main` 必须为空，非空即当轮 merge/reset 处理**。
- **状态**：fixed / verified。

### L009 [流程缺口] update_catalog.py 在技能仓库根执行会把「目录/」误写进技能仓库 → gate FAIL → **fixed / verified（已加脚本守卫）**

- **现象**：2026-10-25 23:01 定时轮转开工，`client_preflight.py gate` 报 FAIL「技能目录有未提交改动（1 项）」——技能仓库根出现未跟踪的 `目录/`（00_总览.md + 09_读书训练营.md，mtime 2026-10-22 23:50）。
- **根因**：`update_catalog.py` 的 `--workspace` 缺省值 = `os.getcwd()`。此前某次交互会话在技能仓库根目录（`cd ~/.workbuddy/skills/one-hundred-million`）直接跑了 `python3 scripts/update_catalog.py ...`，目录索引被写进技能仓库。内容经 diff 确认是 10-22 过期残留（工作区 `目录/` 为权威且更新更全：软技能 10-25 21:46、读书 #10 10-24 已入）。
- **修复**：① 残留 `目录/` 移出技能仓库至 `/tmp/skill_repo_stray_catalog_20261025`（可恢复，未硬删）；② **当轮自主修复脚本**——`update_catalog.py` 加防复发守卫：`--workspace` 解析到含 `SKILL.md` 的目录（= 技能仓库自身）即报错 exit 1 并提示显式传 `--workspace`。修完即验：cwd=技能仓库跑 → exit 1 报错；临时空目录跑 → exit 0 正常写入（最小复现双向验证）。
- **防复发点**：脚本守卫已生效；`client_preflight gate` 的「技能版本最新」检查仍是兜底（能发现、不静默）。
- **状态**：fixed / verified（脚本守卫已随本轮 commit 推送）。

---

## 2026-11-01 · 前端训练营 · 期号 23《点完卡半秒：主线程里谁在堵路》

### L011 [脚本bug] 自写 PPT 拼装脚本漏拼 override CSS → 缺 `</head>` → export_frames 直接崩 → **fixed / verified**

- **现象**：`export_frames.py` 报 `ValueError: substring not found`（`html.index("</head>")`），零帧导出。
- **根因**：用 Python 拼装 PPT 时 `head` 取自模板 `src.split('</head>')[0]`（已剥掉闭合标签），而补救用的 `override` 变量定义了却**没参与拼接**（`out = head + body`），导致 `<head>` 永不闭合。
- **修复**：把 override 样式块拼回 `<body>` 之前，并断言 `'</head>' not in s` 后再插入。
- **防复发点**：自写生成器时用断言校验 HTML 结构（`</head>` 计数 == 1、`<section class="slide"` 计数 == 页数）再交导帧脚本。
- **状态**：fixed / verified（补后 15 帧正常导出）。

### L012 [排版规则] `templates/slide-template.html` 的代码页把标题推到白底上 → 白字白底不可见 → **fixed（本期规避）/ open（模板缺陷）**

- **现象**：代码页（`.slide.code-page`）标题只剩上半截可见，下半截"消失"。抽帧才看清：不是裁切，是**白色标题落到白底区域看不见**。
- **根因**：模板为给代码区腾位置写了 `.slide.code-page .slide-head{top:64px}`，而标题带 `.slide::before` 只有 150px 高、标题色为白 —— 头部下移 64px 后标题越过 150px 边界，白字压在白底上。
- **修复（本期）**：PPT 内覆盖 `.slide.code-page .slide-head{top:0}`（标题回到带内）。
- **防复发点**：**属模板级缺陷，建议把模板该条改为 `top:0`**（本期未改模板，避免影响其他期次已有版式）；后续任何用模板做代码页的期次都要加这条覆盖，第二次再撞即按第 40 条④ 直接修模板。
- **状态**：distilled（2026-11-01 期号24 二次复发 → 模板已改 `.slide.code-page .slide-head{top:0}`，模板级根治）。

### L013 [排版规则] 代码页右侧三张 `.side-card` 溢出压入字幕带（3 帧 FAIL） → **fixed / verified**

- **现象**：`subtitle_band_check` 报 page 11/12/13 FAIL，非白像素 746~762，bbox x[1400,1870] y[900,1038]。
- **根因**：`.code-side` 三卡 + 默认 `padding:30px 28px`、`h4 26px`/`p 24px` 时总高超出可用区（1080−268−200=612px），flex 容器默认 `overflow:visible` 于是向下溢出到字幕带。
- **修复**：`.code-side{gap:16px;overflow:hidden}` + `.side-card{padding:20px 24px}` + `h4 24px` / `p 21px`；重导帧后 15 帧全 PASS。
- **防复发点**：**代码页侧栏卡片内容量天然偏大**，排版时按 612px 可用高预估（3 卡 ≈ 每卡 ≤180px）；`subtitle_band_check` 已能确定性兜住。
- **状态**：fixed / verified。

### L014 [排版规则] 强调色在「同色标题带」与「白底封面」上两处都不可见 → **fixed / verified**

- **现象**：①正文页标题里 `color:var(--accent)` 的强调词在 `accent→hilite` 渐变带上几乎看不见；②封面标题强调词改成白字后压在白底封面上完全消失。
- **根因**：`--accent` 是为**白底**挑的加深主色（前端 `#FF7A00`），而标题带背景本身是 accent 渐变 —— 同色叠同色；反过来封面是白底，白字同样不可见。**同一个强调词在两种底色上不能用同一个颜色**。
- **修复**：标题带内强调词改 `#FFFFFF` + 白色下边框（下划线强调）；封面标题强调词保留 `var(--accent)`。
- **防复发点**：强调色必须**按所在底色分别选**——白底用 `--accent`，主题色渐变带内用 `#FFF`（配下划线/加粗），二者不可混用。
- **状态**：fixed / verified。

### L015 [流程缺口] 发布「内部设置文档」不能当 `--copy` 输入 → 误报 3 个 BLOCK → **distilled（口径固化）**

- **现象**：把 `发布/抖音发布设置.md` 一起传给 `douyin_compliance_check.py --copy`，报 3 个 BLOCK（「绝对化」(出现在"无绝对化与焦虑词"的说明句) / 「网盘」/「站外」），但该文件是**给自己看的清单**，不会被发布。
- **根因**：扫描器是关键词确定性匹配，无法区分"要上传的文案"与"描述合规要求的内部文档"。
- **修复**：`--copy` 只传真正会被粘贴到平台的文案（抖音/公众号/小红书/标题标签四份），设置清单不参与扫描；四份文案复扫 0 BLOCK / 0 WARN。
- **防复发点**：**`--copy` 输入白名单 = 平台文案 + 标题标签**；发布设置/合规声明类内部文档一律不进扫描。
- **状态**：distilled（口径已在 metrics 备注与本节固化）。

### L016 [脚本] 发布封面大数字按固定字号渲染 → 横向溢出画幅 → **fixed / verified**

- **现象**：`封面_3x4.png` 第一版主数字「130.3ms → 2.7ms」左右两段被画幅裁掉。
- **根因**：渲染脚本对所有画幅用同一个字号系数（`w*0.135`/`w*0.16`），竖版画幅窄、长数字串直接超宽。
- **修复**：加 `fit()`——按 `maxw = w*0.86` 逐 2px 收缩字号直到放得下；并把「标题/数字/说明」整块按总高垂直居中。
- **防复发点**：**所有封面/图片文字一律走"按可用宽度收缩字号"的 fit 逻辑**，禁止固定字号直接 `draw.text`。
- **状态**：fixed / verified（横竖两版均目检通过）。

### L017 [流程缺口] `cleanup_builds.py` 台账白名单不含 `visual_plan.md` → 载体计划随 build 一起进废纸篓 → **open（待改脚本）**

- **现象**：收尾清理后 `_archive/` 只有 `sources.md` / `segments_durations.json` / `polyphone_map.json`，`visual_plan.md`（固定规范第 34 条要求的载体台账）被一并清掉。
- **根因**：脚本的不可再生台账白名单写死为 4 个文件，`visual_plan.md` 不在其中；但它同样是「页面为什么这样排」的审计证据。
- **修复（本期）**：按交付时内容重建一份存入 `_archive/visual_plan.md` 并在文件头注明来源。
- **防复发点**：**建议把 `visual_plan.md` 加入 `cleanup_builds.py` 的归档白名单**（与 sources.md 同级），否则每期都要手工找回。
- **状态**：distilled（2026-11-01 期号24 二次复发 → `cleanup_builds.py` 的 `KEEP_FILES` 已加入 `visual_plan.md`，此后自动迁 `_archive/`）。


---

## 2026-11-01 · 测试训练营 · 期号 24《拦不住历史bug的用例，错在哪》

### L018 [脚本bug] 字幕把英文文献标题硬断成碎片 → 观众看到「ange-Detector Tests Considered H」 → **fixed / verified**

- **现象**：成片 t≈116s 字幕显示 `ange-Detector Tests Considered H`，前后 cue 各截一段，英文单词被切断、整句读不通。
- **根因**：`gen_sync_subs.py` 的 `split_lines()` 只在中文标点处断句，超长就直接按 `max_chars=32` 硬断——遇到长英文标题（《Change-Detector Tests Considered Harmful》）必然把单词切成两半。
- **修复**：①脚本加 `_safe_cut()`——切点落在 ASCII 单词内部时回退到最近空格（回退距离 ≤ max_chars/2），切分只改位置不增删字符，`sum(片段)==原文` 与 `pos_map` 连续性不变；②本期口播把英文标题改为中文译名（「变更检测型用例有害」），双保险。
- **防复发点**：口播避免念长英文标题（用中文译名，画面上再标英文原名）；脚本层面的回退已固化，任何含英文/版本号的长句都不再断词。
- **状态**：fixed / verified（单测：切分后拼接与原句完全一致，单词完整）。

### L019 [排版规则] `.diagram-grid` 三个宽 nodebox 挤在一行 → 折行塌陷成竖排文字 → **fixed（本期改版式）/ open（组件待根治）**

- **现象**：P13 用 `diagram-grid` 放三个节点（单元层/集成层/端到端层），导出帧里三个节点竖着堆成一段文字，箭头也串成纵向，整页不可读。
- **根因**：`.diagram-row` 是 `flex-wrap:wrap`，三个节点各约 520px + 两个 `spacer` 60px 超过可用宽 1600px → 每个节点独占一行；`.nodebox` 没有 `flex`，宽度按内容塌缩。
- **修复（本期）**：改用 `.flow + .stepcard`（与 P2/P12 同款，横向三等分稳定）。`visual_plan.md` 同步改载体名。
- **防复发点**：**横排三节点以上一律优先 `.flow + .stepcard`**；确需 `diagram-grid` 时给 `.nodebox` 加 `flex:1` 或把节点压到 2 个以内。第二次再撞即按第 40 条④ 直接改模板。
- **状态**：fixed（本期）/ open（组件）。

---

## 2026-11-02 · 管理训练营 · 期号 25《OKR打满分，说明目标定低了》

### L020 [排版规则] 代码页 `.code-src` 绝对定位落入字幕带（subtitle_band_check FAIL 3318px） → **fixed / verified**

- **现象**：`subtitle_band_check` 报 page_07 FAIL，字幕带非白像素 3318。目检确认「来源：Google re:Work…」整行压在 y≈950 的字幕带里。
- **根因**：模板 `.code-src{position:absolute;right:120px;bottom:104px}`——`bottom:104px` 意味着元素底边在 y=976，**深在字幕带（y 918~1001）内部**；且 `.slide.code-page .code-wrap{bottom:158px}` 让代码区底边落在 y=922，也只剩 4px 余量。
- **修复（本期）**：删掉独立 `.code-src` 元素，把来源并入 `.code-note`（随文档流），并把该页 `code-wrap` 内联 `bottom:196px`；重导帧后 14 帧全 PASS。
- **防复发点**：**凡绝对定位的右下角标注元素（`.code-src` / `.srcline` / `.legend` 之类），`bottom` 必须 ≥ 170px**（字幕带上沿 918 → bottom ≤162 才安全，留 8px 余量取 170）。第二次再撞即按第 40 条④ 直接改模板 `.code-src{bottom:180px}`。
- **状态**：fixed / verified。

### L021 [排版规则] SVG 图内标签宽度超过色块宽度 → 文字压住矩形边框 → **fixed / verified**

- **现象**：P3 甜蜜区区间条里，色块只占坐标轴宽度 10%，居中标签「平均 0.6 – 0.7」（34px）比色块还宽，左右两端横穿矩形描边，第一版目检即发现。
- **根因**：标签字号按「页面宏观可读」定，没按「所在图元宽度」定——`text-anchor:middle` 只保证居中，不保证不超出。
- **修复**：把内层标签删除，内容并进上方主标题「甜蜜区 60%–70%　平均 0.6–0.7」（无边框约束）。
- **防复发点**：**SVG 内嵌文字宽度必须 ≤ 其依附图元的宽度**；色块窄于文字时，标签一律移到块外或合并到标题，禁止 text-anchor 居中后压边框。可在导帧前的帧层目检里专门看「小色块上的长标签」。
- **状态**：fixed / verified。

### L022 [脚本bug] `make_cover.py` 垂直居中算法受字体 bbox 行高影响 → 文字块整体偏高，主标题两行贴死 → **fixed / verified**

- **现象**：封面文字块落在画幅上部 12%~45%，下方大片空白；「OKR 打满分」与「说明目标定低了」两行几乎贴着。
- **根因**：①`total` 由 `textbbox` 高度累加估得，Hiragino ttc 的 bbox 含行高，估算值远大于实际绘制高度，`(h-total)//2` 把起点算得偏高；②两行主标题之间只累加 `h1`、没有额外行距。
- **修复**：起点改为定锚 `y = int(h*0.26)`（不再依赖 bbox 估算）；两行间加 `int(w*0.032)` 行距。
- **防复发点**：**封面/图片排版一律用「定锚 + 按可用宽度收缩字号」，不要用 bbox 累加做居中**；主标题多行之间必须显式加行距。
- **状态**：fixed / verified（4x3 / 3x4 两版均目检通过）。

---

## 2026-11-02 · 软技能训练营 · 期号 26《先说结论：汇报别从过程讲起》

### L023 [排版规则] `.diagram-row .nodebox` 按内容塌缩 → 双节点对比页视觉偏窄（L019 同根因二次出现，已蒸馏） → **distilled**
- **现象**：P3 双节点对比（过程先行 / 结论先行）、P10 四段话术卡，`diagram-grid > diagram-row > nodebox` 里的节点宽度塌缩到文字宽度，在 1680px 宽的 stage 里只占中间一小块，页内留白过大、观感局促。
- **根因**：`.nodebox` 没有 `flex`，在 `flex-wrap:wrap` 的 `.diagram-row` 里宽度按内容（max-content）决定；**与 L019「三个宽 nodebox 折行塌陷」是同一根因的另一种表现**（一个溢成竖排、一个缩成小块）。
- **本期修复**：P3 两个节点加内联 `min-width:560px`；P10 话术卡改 `width:100%;max-width:1440px`。
- **防复发点（已按第 40 条④ 蒸馏进模板）**：`templates/slide-template.html` 新增 `.diagram-row .nodebox{flex:1;min-width:0}` —— 同一行内节点自动等分可用宽度、且允许收缩不溢出。**此后不再需要逐页写内联 min-width**；新建 deck 直接套模板即生效。
- **状态**：distilled（模板已改，L019 一并关闭）。

### L024 [门禁失效] `douyin_compliance_check.py` 把期刊期号「2019 年第 2 期」误判为训练营期号 → BLOCK 误报 → **fixed / verified（规避+待脚本优化）**
- **现象**：公众号文案「参考来源」里写「《Army Lawyer》2019 年第 2 期」，合规扫描报 `[BLOCK][期号标识]`，导致整篇文案复检 FAIL。
- **根因**：期号正则匹配「第 N 期」，不区分「训练营期号」（画面禁令对象）与「期刊/杂志期号」（正当引文）。
- **修复（本期）**：文案改写为「《Army Lawyer》2019 年刊载文章」，复检 0 BLOCK / 0 WARN。
- **防复发点**：①**引用期刊/杂志时一律不写「第 N 期」**，改「某年刊载」「某年某月」；②脚本侧待优化——期号匹配前先排除被书名号/期刊名上下文包住的情形（同一误报第 2 次出现时必须改脚本，不再靠文案绕）。
- **状态**：fixed / verified（文案层）；脚本优化 open。

### 本轮其他（无需改规则，记备查）
- **水印与页头间距实测**：水印胶囊右缘约 x=228，模板 `.slide-head{left:260px}` 的 kicker 起点 x=260，余量约 32px——**刚好不压字但余量偏小**。若后续把页头左缘再往左调，必须同步检查水印胶囊（作者：@Map，6 字 × 30px）。
- **合规脚本无 `--copy` 参数**（本机版本），文案复检一律用位置参数多文件 + `--title`，与既有记忆一致。
