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

---

## 2026-11-03 · 架构师训练营 · 期号 27《降本第一步不是砍机器》

### L025 [排版规则] 拼装模板时 head 出现两次 `</head>` → 覆盖 `<style>` 落到 body → 覆盖样式全部失效，P3 流程页布局崩 → **fixed / verified**

- **现象**：`export_frames` 出的 page_03 里，四张流程卡贴在画面最顶部、压住标题带，`legend` 紧跟其后；而 `.stage{position:absolute;top:250px;bottom:214px}` 明明已写进 HTML。
- **根因**：生成器用 `tpl.split("<body>")[0]` 取前缀——该前缀本身已含 `</head>`，再拼 `OVERRIDE + "</head>"` 就变成两个 `</head>`，覆盖用的 `<style>` 落在 body 之后，未生效（`.stage` 类不存在 → div 退回文档流）。
- **修复**：`tpl.split("<body>")[0].rsplit("</head>", 1)[0] + OVERRIDE + "</head>"`；改后重导帧，15 帧全部正常。
- **防复发点**：**凡「取模板前缀 + 追加样式」的生成器，必须先剥掉前缀里原有的 `</head>`**；生成后 `grep -c "</head>"` 必须等于 1，否则一定失效。另：`.stage` 这类自定义容器没生效时，画面特征就是「内容贴顶、被绝对定位元素压住」，先查样式是否真进了 head。
- **状态**：fixed / verified。

### L026 [排版规则] 模板 `.legend{margin-top:auto}` 在自定义 flex 容器里把正文顶到页头 → **fixed / verified**

- **现象**：P3/P14 的流程图与说明行分别贴住画面最上与最下，中间大片空白。
- **根因**：模板 `.legend` 用 `margin-top:auto` 在 `.diagram-stage`（flex column，内容独占）里把说明推到底部；搬到 `.stage`（同样是 flex column）后 auto 又把上方内容压到顶部。
- **修复**：覆盖 `.stage .legend{margin-top:0}`，内容随 `justify-content:center` 居中。
- **防复发点**：**复用模板组件到自定义容器时，`margin:auto` 类定位必须一并覆盖**；`grep "margin-top:auto" templates/slide-template.html` 可一次找全。
- **状态**：fixed / verified。

### L027 [排版规则] 终端块行数多时溢出，压住下方 `.code-note` 注释 → **fixed / verified**

- **现象**：P10 终端块第 12 行（高亮行）被 `code-note` 文本压住半行，实际视频 t≈200s 帧可见。
- **根因**：12 行 × 26px × line-height 1.58 ≈ 493px，加内边距与 code-file/code-note 共约 673px，超过可用高 598px（top:268 / bottom:214）。
- **修复**：该页 `.code-line{line-height:1.4}`（≈437px）+ `code-note` 压成单行，重导帧后 12 行完整可见。
- **防复发点**：**终端块按「行数 × 字号 × 行高 + 内边距 + 注释 ≈ 可用高」先算再排**；13 行以上一律先降行高到 1.4，或拆两页，不要靠目检才发现。
- **状态**：fixed / verified。

### L028 [门禁失效] `visual_presence_check` 不把 `.card-grid` 当载体 → 计划里写「指标卡」会被判 BLOCK → **fixed（口径纠正）**

- **现象**：P7（三张指标卡）、P13（三张边界卡）用 `.card-grid`，门禁判为「纯文字页」，声明 13 载体只落实 11 页 → BLOCK。
- **根因**：脚本只认 `code-block/terminal/diagram-grid/nodebox/flow/timeline/bars/cmp/stat/svg`，`card-grid` 不在其内；卡片页只算排版版式、不算视觉载体。
- **修复**：P7 改 `.bars`（P95 12% / 内存 35% / 45 台）、P13 改 `.diagram-stage + flow`（nodebox），复跑 13 载体页 87% PASS。
- **防复发点**：**计划表里「指标卡 / 卡片式」不能当载体写**——要么改 `stat`/`bars`/`table.cmp`，要么在 plan 里标「—」。Step 1 写 visual_plan 时就按脚本认的 9 类组件选，别等门禁打回。
- **状态**：fixed / verified（口径已纠正到计划侧）。

### L029 [排版规则] 发布封面按 `w*0.20` 定字号 → 4:3 竖排两行后副标题被裁 → **fixed / verified**

- **现象**：`封面_4x3.png` 副标题「云账单省钱，顺序错了白省」贴到画幅下沿被裁掉一截。
- **根因**：字号按宽度 20% 取（384px），两行主标题就吃掉 0.16h+2×1.24×384≈1126px，剩余高度不足。
- **修复**：字号改 `w*0.15`（4:3）/ `w*0.185`（3:4），主标题定锚 `y=0.16h`、行距 1.24、副标题 `0.042w`，两版均留足下边距。
- **防复发点**：**封面排版先算「行数 × 字号 × 行距 + 锚点 ≤ 0.86h」再定字号**；L022 的「定锚」原则保留，但字号必须与画幅高度联动，不能只按宽度。
- **状态**：fixed / verified。

### L030 [内容规则] 抖音合规自检按关键词命中绝对化用语，否定句里的「万能/最优/最X」照样 BLOCK → **fixed（话术口径）**

- **现象**：口播「Apache Doris … 透明改写算法自动挑最优视图」「物化视图不是万能药」均被 `douyin_compliance_check` 判 `[BLOCK][绝对化用语]`；后者是否定（"不是万能药"）仍被关键词命中。
- **根因**：自检脚本按关键词（万能/最优/最X 等绝对化词表）正则命中，不解析语义/否定；官方文档里的「最优」「万能」描述直接搬入口播即触发。
- **修复**：改写为「自动选择代价更低的视图」「物化视图并非处处适用」；重跑 exit 0。
- **防复发点**：写口播时凡引用官方功能描述里的「最X/万能/第一/唯一/极/全（量）」等绝对化词，一律换成可核验的比较/限定口径（"代价更低""并非处处适用""实测吞吐最高"），不要等自检 BLOCK 再返工；**否定句里的绝对化词同样要换**。
- **状态**：fixed / verified。

### 本轮其他（无需改规则，记备查）
- **合规命中属真命中非误报**：口播「那是理想情况的天花板」被 `天花板` 判绝对化 → 改「那是理论上限」；公众号文案「100% 基线」判 WARN → 改「全量基线」。两处均是话术问题，不是脚本误报。
- **改写单段后的最小返工链**：改稿 → `build_segments` → 重建 `segments_tts` → `rm seg_08.*` → `gen_sync_subs`（其余段复用缓存）→ restore → sub_clean → check_sync → compose_motion → burn。**只重配改动段，别整篇重跑**。

### L031 [脚本bug] `polyphone_check.py cmd_restore` 门控 `count` 漏还原已用代理字（给→己）致字幕残代理字、check_sync FAIL → **open（本地无条件还原兜底·待作者决策是否修脚本）**

- **现象**：本轮回填 `check_sync` 报 `[①字幕≠口播稿] 首差@62: script='今天把这股流式拆给你看…' subs='今天把这股流式拆己你看…'`——字幕里代理字 `己` 没还原成 `给`；`polyphone_check.py restore` 只报「已还原 11 处」，漏了 4 处 `己→给`。
- **根因**：`cmd_restore` 仅对 `v.get("count")` 非 0 的 map 条目做 `proxy→char` 还原（`if v.get("count"): srt=srt.replace(p, v["char"])`）。但 `polyphone_map.json` 里 `给→己` 的 `count` 被记为 0（scan 阶段未把「给」计入需代理命中，或 apply 实际替换集与 scan count 脱节），而口播稿确有 4 处「给」、且 `apply`/`make_segments` 实际把 给 替换成 己 进了 TTS 输入与字幕时间轴——restore 因 `count==0` 跳过该条目，字幕残留代理字。
- **修复（本轮本地兜底·未改脚本）**：用「不门控 count 的无条件 `proxy→char` 还原」重跑 restore（遍历 map 全部 16 个代理字→原字替换），得到 `subtitles_fixed.srt`；复跑 `check_sync` PASS（84 cues / 245.52s / 字幕==口播稿 / 偏差 0.07s）。原始口播稿经核验不含任何 16 个代理字，故无条件替换不会误伤真实文本。
- **防复发点**：根因是 `cmd_restore` 的 count 门控与「代理字实际被使用」脱节。建议二选一（待作者确认是否改脚本，保守偏好·改动前先问）：①`cmd_restore` 不论 count 均替换（与 apply 实际覆盖集对齐）；②map 生成时把「被 apply 实际替换」的条目 `count` 记为 ≥1。**本轮不擅自改脚本**，仅本地兜底；下个视频若再触发，按本条目复现。
- **状态**：open（本地兜底·待作者决策是否修脚本）。

---

## 2026-11-10 · 管理训练营 · 期号 32《1:1复盘表：事实和判断分开》

### L032 [脚本bug] 视频标题含 ASCII 冒号（如 `1:1`）致 ffmpeg 报 `Protocol not found`，烧字幕输出与输入解析双双失败 → **fixed（流程侧规避·可蒸馏为硬门禁）**

- **现象**：`burn_subtitles.py` 第一次把成片写到 `1:1复盘表：事实和判断分开_成片.mp4`，ffmpeg 退出码 1，编码日志 `Error opening output file 1:1复盘表：事实和判断分开_成片.mp4. Error opening output files: Protocol not found`；同轮用 `ffmpeg -i "1:1复盘表：事实和判断分开_成片.mp4"` 抽验证帧也因同一个冒号被解析成协议分隔符而失败。
- **根因**：ffmpeg 内部 URL 解析器把路径里的 ASCII 冒号 `:` 当成「协议://」分隔符；标题 `1:1复盘表…` 里的 `1:1` 被当成协议名 `1` 后接 `1复盘表…`，协议不存在 → `Protocol not found`。这与引号无关（路径已加引号，但解析发生在引号剥离之前）。**注意**：标题正文里的中文冒号 `：` 是 U+FF1A 全角，ffmpeg 不误判；**只有 ASCII 半角 `:`（U+003A）会触发**，典型来源是含 `1:1`、`A:B`、`HTTP` 等半角冒号的选题命名。
- **修复（流程侧规避·本轮已落地）**：烧字幕一律先输出到**无冒号的中间名** `build/成片.mp4`（step `burn_subtitles` 的 `--out` 用临时名），复跑 exit 0 后再 `mv build/成片.mp4 "<原标题>_成片.mp4"`（文件系统允许冒号，仅 ffmpeg 解析器不允许）；抽验证帧前先 `cp "<成片>.mp4" /tmp/chengpian.mp4`，对 /tmp 无冒号副本跑 `ffmpeg -i` 抽帧。本轮成片 `1:1复盘表：事实和判断分开_成片.mp4`（171.67s / 5.83MB）已按此法产出并 verify_burn PASS。
- **防复发点**：**SKILL.md Step 6 烧字幕 / 任何 ffmpeg `-i` 或 `-out` 涉及「视频标题」路径时，标题里若出现半角冒号 `:`，一律先落到无冒号临时名再 `mv`**（文件系统层重命名不受此限）。更稳的做法：给 `burn_subtitles.py` 加「输出路径含 ASCII `:` 即自动改 `build/` 临时名 + 返回最终名」的硬门禁，或在 `video_tool.py` 封装一层「冒号转义/临时名」wrapper——建议蒸馏为固定规范第 43 条 + `burn_subtitles.py` 内建规避（待作者确认是否固化脚本）。
- **状态**：fixed（流程侧规避·待作者决策是否蒸馏为硬门禁/改脚本）。

---

## 2026-11-16 · 大数据训练营 · 期号 37《窗口关了，迟到的数据去哪了》

### L033 [排版规则] 模板 `.code-src` 默认 `bottom:104px` 把来源标注推进字幕带 → 10/15 帧 FAIL → **fixed / verified**

- **现象**：`subtitle_band_check.py build/frames` 首跑 FAIL 10 帧（非白像素 2694~8128），OK 的 5 帧恰是封面 / 代码页（用 `.code-note`）/ 终端页（用块内 `.src`）/ 收尾页；凡带独立 `.code-src` 来源行的页全 FAIL。
- **根因**：`templates/slide-template.html` 定义 `.code-src{position:absolute;right:120px;bottom:104px}`——bottom 104px 对应 y≈976，正落在字幕带检测区 y[918,1001] 内。此前各期多在代码块内用 `.code-note`（随 code-wrap bottom≥196px 收住），本期把「来源：官方文档」大量作为独立 `.code-src` 行放在页面底部，才把这个默认定位缺陷暴露出来。属 L004 同类（字幕带侵入）的另一种触发路径。
- **修复**：生成脚本 OVERRIDE 覆写 `.code-src{position:absolute;right:120px;top:196px;bottom:auto;font-size:20px;text-align:right}`——把来源行锚到标题带（150px）下方、内容区（280px 起）上方的空白带；重导 15 帧复跑字幕带门禁 **15/15 OK、FAIL 0**，抽帧目检 t=1/150/295 三点确认来源行在右上、字幕带干净。
- **防复发点**：**凡套模板时用独立 `.code-src` 出处行，必须在 OVERRIDE 里覆写其定位，不能沿用模板的 bottom:104px**；更稳的做法是蒸馏进 `templates/slide-template.html` 把默认值直接改为 `top:196px;bottom:auto`（与 `.code-note`、`.card-grid` 的 bottom≥190px 口径一致）。此项为模板级缺陷、非单期排版失误，**待作者确认是否固化模板**（第 43 条⑤：不自动改模板）。
- **状态**：fixed / verified（本期已修并复检通过）；模板固化待作者拍板。

### L034 [门禁失效] 合规扫描把后台管理文档的「元描述列举」当发布内容命中 8 项 BLOCK → **open（口径问题·发布内容未动）**

- **现象**：`douyin_compliance_check.py` 全量复检（口播稿 + 标题 + 三平台文案 + `标题标签.md` + `抖音发布设置.md`）FAIL 8 BLOCK；命中全部集中在两份后台文档——「封面无绝对化与焦虑词」「归档网盘」「无微信/私域/二维码/站外链接」「未归档百度网盘」「期号 37 · 大数据训练营」。三份真正发布文案与口播稿零命中。
- **根因**：脚本按关键词正则扫描，不区分「发布内容」与「后台自检备注里的词表列举」；设置清单为说明自己合规而逐字列举红线词，反而被判违规。与 L024（期号误报）同属「不解析语境」，但触发词类与文件类型不同。
- **修复（本期口径纠正）**：改写两份后台文档的元描述措辞（网盘→云端归档、绝对化用语→违规话术、导流词列举→「已收敛到站内互动」、文件头去掉内部标识与编号），**发布内容一字未动**；复跑全量扫描 PASS（0 BLOCK / 0 WARN）。
- **防复发点**：**合规复检的扫描范围应限定为真正会发布的内容**（口播稿 / 字幕 / 标题 / 三平台文案 / 封面文字层），后台设置清单与目录索引的元描述行不进扫描；若坚持全量扫，后台文档写自检结论时**不要逐字列举红线词**。建议蒸馏为 `douyin_compliance_check.py` 的文件类型白名单或「元描述行跳过」规则——**待作者确认是否改脚本**（作者保守偏好：改脚本前先问；第 43 条⑤ 不自动改）。
- **状态**：open（本期措辞规避已验证；脚本口径待作者拍板）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中情况**：brief 列出 L005/L019/L024/L031 未闭环 + L032 待验证。本轮 ① 未用 `.card-grid` 与 `.diagram-row` 宽 nodebox → L005/L019 未复发；② 多音字 scan 需代理 0 处（仅 A 档抽检 11 处）→ **L031 的 restore count 门控 bug 天然未触发**；③ 标题不含 ASCII 半角冒号 → L032 未复发，但烧录仍按流程先落 `build/成片.mp4` 再 `mv`，流程侧规避生效；④ L024 同类误报在 L034 以新形态出现，已另行登记。
- **档位自主裁定**：口播稿 1686 字被 `content_depth_check` 按字数映射判为 L 档，按历史期号 35（1522 字记 M 档）先例与「讲透优先」自主裁定为 **M 档**；成片 300.63s ≈ 5 分 01 秒，贴合 M 档 3~5 分钟。
- **audit_recorded 遗留**：`--apply` 对账 16 个交付文件夹，漏登可补 0 条；1 条历史争议条目「迈向AGI时代：AI产品经理方法论」（文件夹标题与成片基名不一致）按规则未自动写入，留待人工确认，不视作已闭环。

### L035 [排版规则] 发布封面主标题与副标题重叠（固定比例累加 y 未按实测行高）→ **L029 同根因第 2 次复发 · fixed / verified · 蒸馏提议 pending_author**

- **现象**：本轮发布封面 `封面_4x3.png` 目检发现主标题「迟到数据去哪了」与副标题「窗口关了，算还是丢」压在一起（副标题落在主标题下沿内部）；`封面_3x4.png` / `封面_16x9.png` 同样受影响。自动门禁未拦（封面文案不进视频帧、不在 `subtitle_band_check` 范围），靠人眼目检才发现。
- **根因**：本轮自建的 `build/make_cover.py` 用**固定比例**累加纵向位置（`y = h*0.26`、`y2 = y + h*0.115`、`y3 = y2 + h*0.16`），而主标题字号按 `w*0.15` 取（4:3 上 288px，实测行高约 340px），固定偏移 166px 直接落进主标题内部 → 必重叠。与 **L029**（按宽度定字号致 4:3 副标题被裁）根因相同：**封面排版没有按实测文字高度累加行位**，本次是第 2 次复发。
- **修复**：新增 `draw_centered()` 以 `d.textbbox()` 实测高度顶部对齐并返回行高，后续每块 y = 上一块 y + 实测行高 + 间距；并加两条硬断言（相邻块不重叠、尾部文字不出画幅 `yf < 0.95h`）。重生成三张封面，4x3 / 3x4 目检四块文字互不重叠、无裁切、无溢出，断言全部通过。
- **防复发点**：**凡发布封面生成器，一律用实测 bbox 行高累加纵向位置，禁止用画幅比例固定偏移**；生成器内必须带「相邻文本块不重叠 + 末行不出画幅」断言，把人眼目检变成确定性门禁。按第 40 条④ 同根因 ≥2 次须蒸馏为技能内条款/脚本门禁，已生成 `distill` 提议（状态 `pending_author`）；**按第 43 条⑤ 不自动改技能规则，等作者拍板**。
- **状态**：fixed / verified（本轮脚本已修并复检）；蒸馏提议待作者确认。

---

## 2026-11-16 · AI 训练营 · 期号 38《模型换三版，效果全凭感觉》

### L036 [排版规则] 静态帧导出时 CSS 动画停在初始态 → 核心大数字 opacity≈0 几乎不可见 → **fixed / verified**

- **现象**：首版成片抽帧 t=145 / t=335，页面核心大数字「3 / 3 / 3」与「1 把尺子」呈极浅粉、几乎不可见；回查源帧 `page_07.png` / `page_14.png` 同样发虚。`bg_theme_check` / `subtitle_band_check` / `visual_presence_check` 三项确定性门禁均 PASS，靠人眼抽帧才发现。
- **根因**：本期 PPT 自定义 `.anim-pop{opacity:0;animation:pop .55s ... forwards}`，Chrome 静态截图在动画未推进到终点时取图，opacity 停在 0~0.2。SKILL.md Step 2 第 2 条「静态帧导出时动效终点态作为静态画面保证可读」只有文字要求、没有确定性门禁，也没有模板/导帧脚本兜底。受影响仅 3 处 `.anim-pop`（第 3 / 7 / 14 页大数字），其余页面正常。
- **修复（本轮已落地）**：PPT CSS 末尾追加静态导出覆写 `.anim-pop,.anim-fade-up{opacity:1;animation:none}`，用 `export_frames.py` 重导 14 帧；三项画面门禁复跑全 PASS；重跑 `compose_motion.py`（静态帧 + xfade）与 `burn_subtitles.py`（fast）重合成成片，`verify_burn` / `check_sync` 复跑 PASS，抽帧目检大数字为深酒红、清晰可读。
- **防复发点**：**凡 PPT 使用 `.anim-*` 类，静态帧导出必须先把动效终点态常显**（CSS 覆写或导帧脚本注入/等待动画结束），否则「数字聚焦」这类关键视觉会整段发虚。建议蒸馏为 `export_frames.py` 导出前自动注入 override 或模板层兜底 —— 按第 43 条⑤ **不自动改技能脚本/模板，待作者拍板**。
- **状态**：fixed / verified（本轮已修并复检）；脚本/模板固化待作者确认。

### L037 [流程缺口] `jobctl.py resume` 打印的 Step 3 命令与 `gen_sync_subs.py` 实际参数形态不符 → **open**

- **现象**：本轮续跑包给出的下一步命令为 `python3 scripts/gen_sync_subs.py --script build/script_tts.txt --out-dir build --voice zh-CN-YunxiNeural`；而当前脚本 `--help` 显示只接受 4 个**位置参数** `segments_txt out_dir voice [cover_min]`，照抄会直接 argparse 报错、无法开工。
- **根因**：续跑包里的命令文案未随脚本参数形态同步（疑似沿用旧版选项式写法），`resume` 不校验命令可执行性。
- **修复（本轮本地规避）**：按 `--help` 改回位置参数 `gen_sync_subs.py <script_tts.txt> <build> zh-CN-YunxiNeural`，14 段 TTS 一次成功（配音 339.31s / 115 cues / 14 页真实时长）。
- **防复发点**：`jobctl.py resume` 的 Step 3 命令应改为位置参数，或从目标脚本 `--help` 动态生成；**待作者确认是否改脚本**（作者保守偏好：改脚本前先问）。
- **状态**：open（本轮按 `--help` 规避；脚本文案待修）。

### L038 [门禁失效] REST API 推送 + `git update-ref` 掩盖历史分叉 → 下轮 `client_preflight.py gate` BLOCK → **fixed / verified**

- **现象**：本轮开工 gate 报「本地落后 origin/main 28 个提交，先 git pull origin main」；`git fetch` 显示 `+ 11ff653...c0316c8 main -> origin/main (forced update)`，`rev-list --left-right --count HEAD...origin/main` = `6 28`，但 `git diff --quiet HEAD origin/main` 为空（**两棵树内容完全相同**）。
- **根因**：第 41 条推送走 GitHub REST API（远端生成自己的提交链），本地另做 `git commit` + `git update-ref refs/remotes/origin/main HEAD`，把 tracking ref 指到本地提交以「保持一致」，只是掩盖而非消除历史分叉；下一次真正 `git fetch` 时暴露。gate 判定条件是 `HEAD == origin/main`（hash 相等），merge 也无法满足，只能对齐到远端。
- **修复（本轮已落地）**：先确认 `git diff --quiet HEAD origin/main`（树相同、零内容损失）且 `git status` 干净，再 `git reset --hard origin/main`；HEAD 变为 `c0316c8` 与远端一致，gate 复跑 `exit 0`（核心依赖齐 + WorkBuddy 已注册额度可用 + 台账已建立 + 技能版本最新）。
- **防复发点**：**推送收尾不要只做 `git update-ref`**；改为「REST API 推送 → `git fetch origin main` → `git reset --hard origin/main`」，让本地 HEAD 真正等于远端，下轮 gate 不再分叉。涉及第 41 条⑤ 流程文案，**待作者确认是否改 SKILL.md / 推送脚本**。
- **状态**：fixed / verified（本轮已对齐）；流程文案待作者拍板。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中情况**：brief 列出 L005/L019/L024/L031/L034 未闭环 + L032 待验证。本轮 ① 未用 `.card-grid` 与 `.diagram-row` 宽 nodebox → L005/L019 未复发；② 多音字 scan 需代理 6 处、restore 实还原 7 处且代理字零残留 → **L031 的 count 门控 bug 未触发**；③ 标题不含 ASCII 半角冒号 → L032 未复发，烧录仍按流程先落 `build/` 临时名再 `mv`；④ 后台文档措辞按 L034 口径收敛（不逐字列举红线词），全量合规复检 0 BLOCK / 0 WARN；⑤ L024 同类误报未复发。
- **提议 P001 状态**：本轮封面生成器沿用 L035 的 bbox 实测行高累加 + 两条硬断言，三张封面目检无重叠、无裁切；**提议仍为 `pending_author`，未 `approve`、未自动写入任何技能规则**，也未调用 `verify`（只适用于已批准提议）。
- **档位自主裁定**：主题池 AIX-07 建议 M 档、`content_depth_check` 按字数映射显示 L 档口径，按讲透优先与期号 37 先例自主裁定 **M 档**；成片 339.30s ≈ 5 分 39 秒。
- **返工计数**：本轮 1 次返工（L036 大数字发虚 → 改 PPT 覆写 → 重导帧 → 重合成 → 重烧录），门禁 FAIL 1 次（开工 gate 版本分叉 L038），作者打回 0 次。

---

## 2026-11-16 · 产品经理训练营 · 期号 39《访谈聚类完，需求反而错了》

### L039 [脚本bug] `make_ppt.py` 按标记取真代码上屏时抛 `StopIteration` → **fixed / verified**

- **现象**：首次运行 `build/make_ppt.py` 抛 `StopIteration`，16 页 PPT 未生成。
- **根因**：`hi_line=next(ln for ln,t in code_rows if ln and "log((1 + N)" in t)` 假定 TF-IDF 加权行必然落在取样窗口内；而 `code_rows = take("def bigrams(s):",4) + take("df = Counter()",6)` 的窗口只覆盖到 `df.update(...)`，不含 `v[idx[w]] = c * (log((1 + N)/(1 + df[w])) + 1)` 那一行；`next()` 未给默认值、也无存在性断言。
- **修复（本轮已落地）**：改为 `take("def bigrams(s):",4) + [(None,"")] + take("df = Counter()",3) + take("v[idx[w]] =",1)`，把高亮行显式纳入取样；重跑生成 16 页 PPT 成功，代码块仍为本机实跑脚本的真实行。
- **防复发点**：从真代码按标记取行上屏时，高亮目标行必须单独 `take` 或先做存在性断言；`next()` 不带默认值不得用于「应该存在」的匹配。
- **状态**：fixed / verified（本轮已修，PPT 生成并通过三项画面门禁）。

### L040 [排版规则] 纯 `.card-grid` 页面不被视觉载体门禁识别 → 3 页返工 → **fixed / verified**

- **现象**：`visual_presence_check.py` 首轮 FAIL——`visual_plan.md` 声明 15 段载体，PPT 只落实 12 页，纯文字页 `[1,2,10,14]`。
- **根因**：第 2/10/14 页用纯 `.card-grid` 承载「对比选型 / 数据处理 / 方法论落地」，但门禁只把 `flow` / `bars` / `table.cmp` / `code-block` / `terminal` / `stat` 等判为载体；写 visual_plan 时按「有卡片就算有画面」自判，未与门禁识别口径对齐。
- **修复（本轮已落地）**：第 2 页改 `flow` 三步骤（归堆 / 代表引语 / 误当结论，带角色说明）、第 10 页改 `bars` 柱状图（2 正面 / 3 套餐 / 1 结果 / 2 入口）、第 14 页改 `flow` 两步骤；同步更新 `visual_plan.md` 三行。复跑载体页 15/16（94%）、纯文字 1/16，PASS。
- **防复发点**：Step 1 写 `visual_plan.md` 时，载体类型必须是门禁识别集合内的具体类名；纯卡片页不计载体，凡有数据 / 流程 / 对比的段落一律上 `flow`、`bars` 或 `cmp` 表。
- **状态**：fixed / verified（本轮已改并复检）。

### L041 [流程缺口] 首版口播稿同时命中合规 BLOCK 与内容深度 WARN → 整稿重写一次 → **fixed / verified**

- **现象**：首版稿 `douyin_compliance_check.py` FAIL（BLOCK 1 项：「局部最优，高度依赖初始质心」被绝对化话术规则命中）；`content_depth_check.py` WARN「全文无一处机制解释（因为 / 之所以 / 原因是）——『为什么』段缺失」。
- **根因**：写稿时把官方术语「局部最优」原样搬进口播，未做话术改写；全稿偏现象罗列与步骤陈述，缺「为什么会这样」的机制句。两项门禁都在整稿写完才跑，导致重写后 TTS 输入与字幕基准要跟着换。
- **修复（本轮已落地）**：重写为 1943 字 / 16 段，「局部最优」改「局部极小值」保留机制含义；补多处机制句（「之所以会误判，是因为它压根不读句子的方向」「结果会飘，原因就是初始质心随机选的」「之所以反转，是因为簇数的是字面，不是诉求」）。复跑合规 0 BLOCK / 0 WARN、深度讲透闭环五项全齐 PASS。
- **防复发点**：Step 1 第一稿落盘后立刻跑合规 + 深度双门禁，通过再进 Step 2/3；官方术语入口播前先过话术改写，每段「是什么」后紧跟一句「之所以…是因为…」的机制句。
- **状态**：fixed / verified（本轮已改并复检）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中情况**：brief 列出 L005/L019/L024/L031/L034/L037 未闭环 + L032 待验证。本轮 ① 未用 `.card-grid` 宽 nodebox 叠图 → L005/L019 未复发（L040 为纯卡片不识别，属新形态）；② 多音字 apply 2 处（为→未 · 因为）、restore 实还原 2 处且代理字零残留 → L031 未触发；③ 标题不含 ASCII 半角冒号 → L032 未复发，烧录仍先落 `build/成片.mp4` 再 `mv`；④ 后台设置文档按 L034 口径不逐字列举红线词，全量合规 0 BLOCK / 0 WARN；⑤ 按 `--help` 用位置参数调 `gen_sync_subs.py` → L037 未复发；⑥ L024 同类误报未复发。
- **提议 P001 状态**：本轮封面生成器沿用 L035 的 bbox 实测行高累加 + 两条硬断言，并把「末块自身高度」纳入出画幅断言；三张封面目检无重叠、无裁切、无溢出。**提议仍为 `pending_author`，未 `approve`、未自动写入任何技能规则**，也未调用 `verify`（只适用于已批准提议）。
- **档位自主裁定**：主题池 PRD-09 建议 M 档，1943 字按讲透优先与期号 38 先例自主裁定 **M 档**；成片 401.97s ≈ 6 分 42 秒。
- **TTS 瞬时异常**：第 8 段 edge-tts 报 `NoAudioReceived`，脚本自动 retry（wait 2s）成功，16 段总配音 401.98s / 135 cues，非门禁问题，未改脚本。
- **audit_recorded 遗留**：`--apply` exit 3，1 条历史争议「迈向AGI时代：AI产品经理方法论」（文件夹标题与成片基名不一致）按规则未自动写入，非本轮产物，留待人工确认。
- **GitHub 通道事故（本轮新增 · L038 变体）**：REST API 6 个文件全部 `PUSH_OK` 后，按 L038 口径做 `git fetch origin main` 时被沙箱代理拒答（两次超时 / `Empty reply from server`）；紧接着 `git reset --hard origin/main` 因 tracking ref 仍指向旧提交 `5ffb567`，**把刚写回的 6 个资产文件全部回退**，本地与远端内容不一致。**修复（本轮已落地）**：改用 `api.github.com` 的 `/commits` + `/git/trees` + `/git/blobs` 逐对象重建远端提交链（先用本地已存在的 `5ffb567` 校验重建算法字节级一致，`hash-object` 结果完全相同），写回 blob / tree / commit 对象后 `git update-ref refs/remotes/origin/main <远端HEAD>` + `git reset --hard <远端HEAD>`；最终 `HEAD == origin/main == 3636ea5`，本地内容核验 L039 / SC009 / PRD-09 done / covered 全部回位，工作区干净。**防复发点**：`git fetch` 失败时**禁止**直接 `reset --hard origin/main`（tracking ref 是旧的，会静默丢弃本地已写回内容）；必须先确认 fetch 成功，或走「接口重建对象 → 对齐到远端真实 HEAD」。本次属环境网络限制，未改任何技能脚本 / 规则。
- **返工计数**：本轮 3 次返工（首版稿双门禁重写 / `make_ppt.py` StopIteration / 载体门禁 3 页改造）+ 1 次推送通道事故处置，门禁 FAIL 2 次（合规 BLOCK、visual_presence FAIL）+ 脚本异常 1 次，作者打回 0 次。



---

## 2026-11-18 · 前端训练营 · 期号 40《一个下拉框，为什么要写三遍》（跨客户端续跑）

### L042 [排版规则] `take()` 代码取样 marker 重叠致重复行 + 超长行被截断 → fixed / verified

- **现象**：P9 代码页首版抽帧，行号 52→57 后重复出现 54/55，且 `self.highlighted = min(... len(self.opt` 被右侧截断。
- **根因**：`take("def send...",4) + take('if key=="Down Arrow":',6)` 两段取样区间重叠（第二段从 54 行起，第一段已含 54/55）；`code-line{white-space:pre}` 下超长行（>64 字符）溢出代码块被裁。
- **修复**：改为不重叠切片 `take(def send,6) + (None,"") + take(Enter,4) + take(Escape,1)`，并核对每行长度（≤64 字符≈1000px 适配约 1100px 代码区）。
- **防复发点**：代码页 `take()` 多个 marker 的区间**不得重叠**；上屏前先打印每行长度，超 64 字符的行不取或换行。
- **状态**：fixed / verified（重导帧目检无重复、无截断）。

### L043 [排版规则] `cmp-wrap` / `src-note` 用正常流导致表头被标题带盖住、来源行浮到页顶 → fixed / verified

- **现象**：P4 表格首行「键位/行为」与标题带叠字看不清；P7 来源行「来源：github…」浮在页面最顶端压住橙色标题带。
- **根因**：模板 `.slide-head{position:absolute;top:0;height:150px}`，而 `.cmp-wrap` / `.src-note` 自定义类未定位，按正常流从 y=0 起排 → 钻到标题带下面。
- **修复**：交付覆写把 `.cmp-wrap` 改 `position:absolute;top:268px;bottom:288px`、`.src-note` 改 `position:absolute;top:168px`（锚在标题带下沿 150~268 空白带），`.kv-line` 也绝对定位到 `bottom:206px`。
- **防复发点**：凡在套模板 PPT 里新增内容块，若模板容器是绝对定位，新增块也**必须绝对定位并显式给 top/bottom**，不能依赖正常流；目检时专查表格页首行与来源行位置。
- **状态**：fixed / verified（重导 P4/P7/P12/P15 帧目检表头完整、来源行在带下、字幕带全净）。

### L044 [脚本bug] `code_html()` 改写时漏掉 `ln is None` 空行守卫 → 空行显示「None」→ fixed / verified

- **现象**：P9 代码页分隔符行号显示为「None」字样。
- **根因**：重写 `code_html()` 时删掉了 `if ln is None: 渲染「·」` 的守卫，`(None,"")` 空行直接 f-string 输出 `None`。
- **修复**：恢复 None 守卫，空行渲染「·」。
- **防复发点**：改脚本时勿删空行/占位分支；代码页上屏后目检空行行号。
- **状态**：fixed / verified（重导帧无 None 字样）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中情况**：brief 列出 L005/L019/L024/L031/L034/L037 未闭环 + L032 待验证。本轮 ① 未用宽 nodebox → L005/L019 未复发；② 多音字 apply 1 处（为→未·因为）、restore 实还原 1 处零残留 → L031 未触发；③ 标题无 ASCII 半角冒号 → L032 未复发，烧录按流程先落 `build/成片.mp4` 再 mv；④ 后台设置文档按 L034 口径不逐字列举红线词，全量合规 0/0；⑤ 按 `--help` 用位置参数调 `gen_sync_subs.py`（L037），未复发；⑥ L024 同类误报未复发。
- **档位自主裁定**：口播稿 1722 字被 `content_depth_check` 按字数映射判 L 档，按历史先例（期号 37/38/39 的 1600~1943 字均裁定 M）与讲透优先自主裁定 **M 档**；成片 321.03s ≈ 5 分 21 秒。
- **首版深度 WARN 修正**：首版中文数字表述被 `content_depth_check` 判量化密度 0.0/千字（WARN）→ 把关键量词改阿拉伯数字（14 类键位 / 4 框架 / 56 处 / 18 处 / 7 按键 / 5400 星）→ 复跑 5.68/千字 PASS。
- **跨客户端续跑**：本轮为 11-17 断稿任务续跑（实验脚本已在盘、口播稿未写），按「产物即进度」resume 未另起新视频；`jobctl done` 后 scan exit 3 干净。
- **audit_recorded 遗留**：exit 3，1 条历史争议「迈向AGI时代」非本轮产物，留人工确认。
- **提议 P001 状态**：封面生成器沿用 L035 的 bbox 实测行高累加 + 双断言，三张封面目检无重叠/裁切。**提议仍 `pending_author`，未 approve、未自动改技能规则**。
- **返工计数**：3 次返工（代码行切片 / 表格绝对定位 / 适配器 return 行）+ 1 次首版深度 WARN 修正，门禁 FAIL 0 次，作者打回 0 次。

---

## 2026-11-18 · 测试训练营 · 期号 41《AI生成的用例漏在哪》

### L045 [脚本bug] 自建 make_ppt.py 把自定义 CSS 追加在 `</style>` 之后 → 全部覆写不生效 → fixed / verified

- **现象**：导帧后字幕带门禁 8 帧 FAIL；以为是 `bottom` 覆写没生效，加 `!important` 后仍 FAIL，且整 14 帧全部变成同一数值——维基式把整段 CSS 当正文渲染。
- **根因**：脚本先切出含 `</style>` 的整段注入 `style` 变量，再 `style += 自定义CSS`，导致新增 CSS 落在 style 标签**外**、被浏览器当文本渲染进画面；此时 `:root` 变量与容器样式全失效。改 `!important` 无效正是"覆写不在 style 标签内"的特征信号。
- **修复**：改为切 `<style>` 与 `</style>` 之间的 body（不含闭合标签），在 `</style>` 前插入自定义 CSS，再在 HTML 拼接处补回 `<style>` 开标签。复导帧后 14/14 帧 PASS。
- **防复发点**：套模板生成 PPT 时，注入自定义 CSS 必须验证①`<style>`/`</style>` 各恰好一个；②**首帧目视确认没有 CSS 源码当正文出现**——"全帧同一 FAIL 数值"是 CSS 落标签外的强信号。
- **状态**：fixed / verified（重导帧 + 全门禁复跑 PASS）。

### L046 [排版规则] 模板 `.card-grid/.diagram-stage/.code-wrap` 默认 `bottom:150px` 底边压入字幕带 → fixed / verified

- **现象**：本轮表格页/代码页/图示页共 8 帧字幕带门禁 FAIL（非白像素 3000~134000）。
- **根因**：模板三个内容容器默认 `bottom:150px`（底边 y=930）与 `code-page` 覆写 `bottom:158px`（y=922）均进入字幕带 y∈[918,1001]；表格/卡片面板底色本身即被判为非白侵入。此与期号 12 的 `.card-grid bottom:150px` 踩坑（L 类同源）一致，属第二次复发。
- **修复**：交付覆写统一 `bottom:210px!important`（底边 y≈870），覆盖 card-grid/diagram-stage/code-wrap/code-page.code-wrap 四类容器。
- **防复发点**：按第 40 条④同类 2 次应蒸馏——**在 `slide-template.html` 的 `.card-grid/.diagram-stage/.code-wrap` 默认 bottom 改为 ≥196px**（待作者确认后改模板，本轮仅交付层覆写）。
- **状态**：fixed / verified（14 帧字幕带全净）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief L005/L019/L024/L031/L034/L037 + L032 待验证。本轮 ①未用宽 nodebox→L005/L019 未复发；②多音字 apply 4 处（为→未·因为 / 空→控×2 / 差→插）、restore 4 处零残留→L031 未触发；③标题无 ASCII 冒号→L032 未复发；④合规发布内容未逐字列红线词→L034 未复发；⑤`gen_sync_subs.py` 按位置参数调用（L037）未复发。
- **档位自主裁定**：口播稿约 1280 字，content_depth 判 M 档，成片 266.70s≈4分27秒（M 档偏上限·讲透优先）。
- **返工计数**：2 次返工（CSS 标签位置 / 容器字幕带侵入），门禁 FAIL 2 轮，作者打回 0。
- **提议 P001 状态**：沿用前例自绘封面，提议仍 `pending_author`，未 approve、未自动改技能规则。

---

## 2026-11-19 期号42 · 管理训练营《AI提效的账，为什么算不平》

### L047 [排版规则] 来源行 .src-note bottom:158px 底边落进字幕带 → 10 帧 FAIL → fixed（本期上移至 196px）
- **现象**：subtitle_band_check 首跑 10/15 帧 FAIL，字幕带 y[918,1001] 非白像素 9~15，全部落在页面底部来源标注行。
- **根因**：本页定制 `.src-note{bottom:158px}` → 文字底边 y≈922，正好压进字幕带上沿（y918）；内容块 bottom:196px 尚可，唯独来源行漏了同等避让。与 L046（容器默认 bottom:150px）同根因，但这次是**自定义来源行**而非模板容器。
- **修复**：内容块 bottom→230px、来源行 bottom→196px，重导 15 帧复跑 15/15 PASS。
- **防复发点**：凡在 PPT 页脚附近新增任何文字块（来源行/脚注/角标），bottom 一律 ≥196px；字幕带门禁导帧后必跑，人眼漏得过、脚本漏不掉。
- **状态**：fixed（本期验证通过；L046 同根因已 3 次——考虑蒸馏为模板级脚注定位变量）。

### L048 [门禁失效] verify_burn 对超长单行字幕 bbox 度量误报（x 跨度 809/1322px 超 6px 容差）→ 误报放行（抽帧目检）
- **现象**：verify_burn 三点采样中 t=24.93 与 t=80 报字幕 FAIL，x 跨度分别 809px / 1322px；短字幕行（178~615px）全 OK。
- **根因**：verify_burn 用 PIL 参考图 `textlength()` 算期望 bbox，与成片实际字幕渲染的字形度量存在累积误差；字幕越长误差越大，超 6px 固定容差即 FAIL。非烧录错误。
- **修复**：无需改成片。抽帧目检 t=24.93/80 确认字幕单行完整、无截断、无遮挡，按历史规程（10-12/10-18 同类误报）放行并记录。
- **防复发点**：verify_burn 报字幕 FAIL 时先看 x 跨度——超长行（>700px）优先抽帧目检再下结论，勿盲目重烧；可考虑给脚本加按字长放宽容差的逻辑（待作者决策）。
- **状态**：open（本期规避放行；脚本度量口径待作者拍板是否修）。

### L049 [流程缺口] 抖音合规脚本需同时扫口播稿与 PPT 画面文字——画面独立绝对化用语易漏 → fixed（本期手动扫描）
- **现象**：口播稿合规 PASS，但 PPT 封面副标题含「最严格」绝对化用语，脚本默认只扫口播稿/标题/文案文件，不扫 HTML 画面文字。
- **根因**：合规门禁的扫描对象限于文本文件；画面文字（PPT.html 内的可见文本）需单独扫描。第 14/30 条红线覆盖画面，但脚本未覆盖 HTML。
- **修复**：本期增加一步「PPT 可见文字绝对化用语扫描」（去 style/script/注释后 grep 绝对化词表），抓出「最严格」→改「很有分量」，重导帧重烧。
- **防复发点**：每期 Step 7 除口播稿合规外，必跑 PPT.html 可见文字绝对化扫描；可将该扫描并入 douyin_compliance_check.py 支持 HTML 输入（待作者决策）。
- **状态**：fixed（本期验证通过；脚本能力扩展待作者拍板）。

### L050 [脚本bug] PIL 封面字体 Hiragino Sans GB 缺 U+2212 减号字形 → 方框 → fixed（封面改 ASCII 减号）
- **现象**：封面 stat 行「−19%」的减号渲染成方框（缺字）。
- **根因**：`/System/Library/Fonts/Hiragino Sans GB.ttc` 不含 U+2212（数学减号）字形；PPT 用 PingFang 正常，封面脚本用 Hiragino 故缺字。
- **修复**：封面文案改用 ASCII 连字符 `-19%`，重生成两张封面。
- **防复发点**：封面/字幕等 PIL 出图的文案避免 U+2212、特殊数学符号；非 ASCII 标点上屏前目检。
- **状态**：fixed（本期验证通过）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief L005/L019/L024/L031/L034/L037 + L032 待验证。本轮 ①未用宽 nodebox→L005/L019 未复发；②多音字 apply 3 处（行→航/为→未/差→插）、restore 3 处零残留→L031 未触发；③标题无 ASCII 冒号→L032 未复发（烧录直接输出目标名）；④发布文案未逐字列红线词→L034 未复发；⑤gen_sync_subs 按位置参数调用→L037 未复发；⑥合规无期号误报→L024 未复发。
- **返工计数**：3 次返工（字幕带来源行侵入 / 合规顶级用词 / 画面绝对化+减号缺字），门禁 FAIL 3 轮，作者打回 0。
- **verify_burn 误报**：2 处长字幕 bbox 误报，抽帧目检放行（L048）。
- **提议 P001 状态**：仍 `pending_author`，未 approve、未自动改技能规则。

---

## 2026-11-20 期号43 · 软技能训练营《技术分享：讲得越全，记得越少》

### L051 [脚本bug] sub_clean 吞掉行末《英文书名》的内容 → 口播改写规避（open·待脚本修复）
- **现象**：`sub_clean` 后字幕 `写了本书叫《Resonate》` → `写了本书叫`，英文书名整块消失；`check_sync` FAIL（script 991 / subs 983，首差@701）。
- **根因**：sub_clean 的行末书名号清洗把「《》连同其中实词」一并删掉（规范要求删行末书名号符号，实现未区分「纯标点」与「书名号包裹的实词」）——英文书名无中文字符，被当标点整体吞掉。
- **修复**：口播稿改为 `写了本 Resonate 的书`，`make_segments.py` 第 11 段同步，删 `seg_11.*` 重配该段 TTS → check_sync PASS（79 cues / 220.82s）。
- **防复发点**：上屏/上字幕的英文书名、专名不要用《》包裹在行末，改 `写了本 X 的书` 句式；脚本侧应加「书名号内实词保留」逻辑（第 43 条⑤：改脚本须作者确认，本轮不自动改）。
- **状态**：open（本期规避放行；脚本修复待作者拍板）。

### L052 [脚本bug] burn_subtitles.py 对 voiceover.mp3 的 probe_duration 返回空串 → 复制为无扩展名文件规避（open·根因待查）
- **现象**：`burn_fast` 抛 `ValueError: could not convert string to float: ''`，定位 `audio_dur = probe_duration(audio)`。
- **根因**：直接跑 `ffprobe` 对同一文件返回 `220.824` 正常；直接 import 模块调用 `probe_duration("build/voiceover.mp3")` 也正常；换 `/tmp` ASCII 路径仍失败；把 audio 复制为无扩展名文件 `vox` 后烧录成功。疑与 `.mp3` 扩展名 + 脚本内 ffprobe 参数组合有关，根因未最终定位。
- **修复**：`cp voiceover.mp3 vox`，以 `vox` 作 audio 入参烧录成功（body=220.83s / audio=220.82s / 79 cues）。
- **防复发点**：burn 报 audio 时长空串时先复制为无扩展名文件重试；脚本侧 `probe_duration` 应加空值兜底与更明确报错（第 43 条⑤：改脚本须作者确认，本轮不自动改）。
- **状态**：open（本期规避成功；根因与脚本修复待作者拍板）。

### L053 [门禁失效] 合规元描述行 BLOCK 第 2 次复发（L034 同根因）→ 改写措辞放行 · 触发蒸馏（open）
- **现象**：发布包合规全量复检 FAIL 6 BLOCK，全部落在两份后台文档（`抖音发布设置.md` / `标题标签.md`）的元描述行——字面写了「绝对化用语」「站外链接」「网盘」「软技能训练营主题色」等红线词；三份真正发布文案 + 口播稿零命中。
- **根因**：照抄历史期号模板，模板元描述行本身就逐字列举了红线词；L034 已登记同类问题并给出「后台文档不要逐字列举红线词」的防复发点，本轮未落实 → 同根因第 2 次复发（第 40 条④触发蒸馏）。
- **修复**：把元描述行改为具体描述（「绝对化用语」→「夸大用语」、「站外链接」→「联系方式」、「网盘」删除、「训练营」→「营名」），发布内容一字未动；复跑全量扫描 PASS（0 BLOCK / 0 WARN）。
- **防复发点**：写后台设置/标题标签文件时**不逐字列举红线词**，只写「已通过自检」；应蒸馏为 `douyin_compliance_check.py` 的元描述行跳过或文件类型白名单（第 43 条⑤须作者确认，本轮只生成提议不自动改脚本）。
- **状态**：open（同根因第 2 次 → 已生成蒸馏提议 pending_author；本期改写放行）。

### L054 [流程缺口] 抽帧 t=120 出现单字「三」字幕（转场瞬间）→ 目检放行（open·待更多样本）
- **现象**：成片抽帧 t=120 处字幕带仅显示单字「三」。
- **根因**：段切换/转场瞬间抽帧恰好落在两 cue 之间的单字尾帧；`check_sync` PASS（79 cues 无重叠、间隙 ≤0.35s）、`verify_burn` PASS，其余抽帧正常。
- **修复**：无需改成片；判为转场瞬时现象，不作阻塞，记录备查。
- **防复发点**：单字字幕抽帧先看 check_sync 的 cue 边界；非持续单字不返工；若持续出现再查 gen_sync_subs 句内拆字逻辑。
- **状态**：open（本期目检放行；待更多样本确认是否需改拆句逻辑）。

### L055 [流程缺口] content_depth 初检 WARN（缺机制句）→ 补 2 处「之所以…是因为…」后 PASS（fixed）
- **现象**：首版口播稿 M 档 `content_depth_check` WARN「无原理结论句」「全文无一处机制解释」。
- **根因**：初稿以事实罗列 + 方法给出为主，缺因果机制句。
- **修复**：结论先行段补「之所以要先给结论，是因为听众得先有个筐…」、三块段补「之所以砍成三块，是因为工作记忆就装 3 到 4 个…」，复跑 PASS。
- **防复发点**：写稿时每个核心方法后主动加一句「之所以…是因为…」机制句，不等门禁 WARN 再补。
- **状态**：fixed（本期验证通过）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列出 7 个 open 项 + 4 个待验证 + P001。本轮 ①L050 非 ASCII 减号未复发（封面无减号）；②L034 元描述行**复发**（L053，已蒸馏）；③L049 画面绝对化扫描本轮画面干净；④L048 verify_burn 误报未复发。
- **返工计数**：4 次返工（sub_clean 吞 Resonate 重配第 11 段 / content_depth 补机制句 / 合规元描述行 6 项改写 / burn audio 无扩展名规避），门禁 FAIL 3 轮，作者打回 0。
- **提议 P001 状态**：仍 `pending_author`，未 approve、未自动改技能规则。

---

## 2026-11-20 · 架构师训练营 · 期号 44《AI懂架构，但拍板还得人》

### L056 [门禁失效] 合规元描述行 BLOCK 第 3 次复发（L034→L053→本轮）→ 改写措辞放行 · 已蒸馏（open）
- **现象**：发布包全量合规复检 FAIL 5 BLOCK，全部落在两份后台文档（`抖音发布设置.md` / `标题标签.md`）的元描述行——字面写了「绝对化」「站外链接」「网盘」等红线词；三份真正发布文案 + 口播稿零命中。
- **根因**：照抄历史期号模板，模板元描述行本身逐字列举红线词。L034（首次）、L053（第2次·已蒸馏生成提议）之后本轮第 3 次照抄复发——防复发点「后台文档不逐字列举红线词」连续两轮未落实，说明仅靠文字约定不够，需脚本侧文件类型白名单。
- **修复**：元描述行改为「文字符合平台规范」「不提供任何联系方式」「归档交付物」等具体描述，发布内容一字未动；复跑全量扫描 PASS（0 BLOCK / 0 WARN）。
- **防复发点**：后台设置/标题标签文件不逐字列举红线词，只写「已通过自检」；已按第 40 条④第 2 次复发规则蒸馏为 `douyin_compliance_check.py` 的元描述行跳过/后台文件白名单提议（第 43 条⑤须作者确认，本轮只生成提议 pending_author 不自动改脚本）。
- **状态**：open（同根因第 3 次 → 蒸馏提议 pending_author；本期改写放行）。

### L057 [排版规则] visual_presence 不识别自定义 class（statx/bars2/hbar）→ 改用脚本白名单 class 后 PASS（fixed）
- **现象**：首版 PPT `visual_presence_check.py` 只识别 9/16 载体页、7 页纯文字 FAIL（>40%）；plan 声明 16 段有载体但 PPT 只落实 9 段。
- **根因**：画面用了自定义 class `.statx`/`.bars2`/`.hbar`，脚本只认模板白名单 class（`metric`/`bar-chart`/`cmp`/`stat`/`code-block`/`flow` 等），自定义 class 一律当纯文字。
- **修复**：数字元素加 `metric`、柱状组加 `bar-chart`，visual_plan 第 16 段 CTA 载体改 `-`（纯文字 CTA 合规）；15/16 载体页 PASS。
- **防复发点**：Step 2 排版数字/柱状时直接用模板白名单 class，不自造 class；写 visual_plan 时 CTA 段载体记 `-`。
- **状态**：fixed（本期验证 PASS）。

### L058 [排版规则] 代码页 code-wrap 侵入字幕带（page12）→ 通用 bottom 覆写后 16/16 PASS（fixed）
- **现象**：`subtitle_band_check.py` page_12 FAIL，字幕带非白像素 1120；定位为绿色 `.code-note` 行 y≈900–925 侵入字幕带 y[918,1001]。
- **根因**：模板 `.code-wrap` 默认 `bottom:150px`，代码页内容块底边过高；首次改 `.slide.code-page .code-wrap` 无效——section 根本没有 `code-page` class。
- **修复**：改为通用覆写 `.code-wrap{bottom:268px!important}` + `.code-src{bottom:250px!important}`，重导帧 16/16 PASS。
- **防复发点**：代码页覆写不要用假设的 section class 前缀，直接用通用 `.code-wrap`/`.code-src`；导帧后必跑 `subtitle_band_check.py`（与 L046 测试营代码页字幕带侵入同根因第 2 次，但锚点不同，暂不蒸馏、续观察）。
- **状态**：fixed（本期验证 16/16 PASS）。

### 本轮其他（无需改规则，记备查）
- **返工计数**：4 次（中文数字改阿拉伯数字满足量化识别 / 合规 BLOCK+WARN 重配音 / visual_presence 自定义 class 改白名单 / 画面绝对化「第一/100%」+page12 字幕带侵入重导帧），门禁 FAIL 4 轮，作者打回 0。
- **字幕维度改进**：上轮 43 字幕维度退步（8.0 vs 近10期均值 9.57），本轮 check_sync PASS（113 cues / 321.24s / 字幕==口播稿 / restore 零残留）、verify_burn PASS、抽帧 t=1/240/319 单行不遮挡，字幕评分回升至 9。
- **提议状态**：P001（元描述行脚本白名单）、P002 仍 `pending_author`，未 approve、未自动改技能规则。

---

## 2026-11-21 · 大数据训练营 · 期号 45《一个报表数错了，怎么追到源头那张表》

### L059 [流程缺口] 改 PPT 页顺序后忘重导帧 → 画面与口播段错位（抽帧目检发现，已返工重导帧重烧）
- **现象**：成片 t=250 抽帧，画面显示旧顺序的「从报表逆流而上 4 层」反查链图，而字幕在讲「它列出三个：清洗层净金额、汇总层营收」（影响分析段）——画面与声音错页。
- **根因**：本轮为让「页面在播什么=口播讲什么」严格同帧，重写了 PPT 27 页顺序（slides_body.html 重排 G1–G27 与口播句群对齐），但重新生成 PPT.html 后**漏了重新导帧**——`build/frames/` 仍是旧顺序帧，compose_motion 用旧帧合成，导致画面顺序与新的口播段错位。check_sync/verify_burn 只校验字幕文本与烧录，不校验画面页序与口播段对应，故均 PASS，靠抽帧目检 t=250 才发现。
- **修复**：清空 `build/frames/page_*.png` → 用新 PPT.html 重导 27 帧 → subtitle_band 27 帧全净 → 重跑 compose_motion + burn_subtitles + verify_burn → 重抽帧 t=1/150/250/400 目检，t=250 已变为「改一个字段，影响谁」影响分析代码页、与字幕同主题。
- **防复发点**：**凡改动 PPT.html 的页顺序或内容，必须清空并重导 `build/frames/`，再重跑 compose+burn**；导帧后抽帧核对「画面页序 ↔ 口播段序号」至少 2 点（不只查字幕/水印）。建议在 Quality Gates 加一条「frames 与 PPT 页序一致性」提示（脚本难判定，靠流程纪律）。
- **状态**：fixed（本期返工验证画面声音对齐）。

### L060 [门禁失效] content_depth 扩容写后量化密度降至 0.5/千字 WARN（概念解析型取舍，放行记日志）
- **现象**：为消除 G6/G9/G26 短段（15/28/29 字易闪页）扩写正文 3 处后，content_depth 由 PASS 变 WARN（量化密度 0.5/千字，阈值 0.5 边缘）。
- **根因**：扩写的是机制/过渡句（无新增带单位数字），分母增大而分子未增，密度被稀释到阈值线上。
- **修复**：判定为本期是概念解析型（字段级血缘），量化点集中在实跑脚本（3 模型/10 边/4 层反查/3 下游列）与双源 L1（dbt/OpenLineage 规范），已在画面与实跑脚本充分呈现，口播以讲透机制为主——按规范 WARN 非 BLOCK，记日志说明取舍，不改稿。
- **防复发点**：扩写短段时尽量保留/补入一个量化点（带单位数字），避免密度被稀释触发 WARN；概念型选题提前预判密度边缘。
- **状态**：open（本期取舍放行；非脚本问题）。

### L061 [门禁失效] 抖音合规 BLOCK：口播「一劳永逸」命中教培虚拟内容禁语 → 改稿重配音（fixed）
- **现象**：合规自检 BLOCK 1 项——「血缘不是建完就一劳永逸的」被正则命中教培「有效期宣传」禁语（虽为普通语义、非课程有效期宣传）。
- **根因**：脚本正则对「一劳永逸」无技术语境白名单，属误报型 BLOCK，但按第 30 条 BLOCK 必须清零。
- **修复**：口播改为「血缘不是建完就不用再管了」→ 重跑 polyphone apply / build_segments（拼接校验 PASS）/ 分段 TTS（缓存复用）/ restore / sub_clean / check_sync（132cues/403.51s/偏差0.04s）/ compose / burn / verify_burn → 合规复跑 0 BLOCK / 0 WARN。
- **防复发点**：写稿避开「一劳永逸/永久有效」等有效期宣传词；可考虑给 douyin_compliance_check.py 加普通语义白名单（待作者拍板，第 43 条⑤不自动改脚本）。
- **状态**：fixed（本期改稿验证 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列出 12 open + 7 待验证 + P001/P002/P003。本轮 ①L057 白名单 class：E8 用 card-grid/metric/bar-chart/cmp/flow 白名单，visual_presence 26/27 PASS 未复发；②L058/L047 底部避让：自定义 CSS 统一 bottom≥196（code-wrap 210），subtitle_band 27 帧全净未复发；③L049 画面绝对化扫描：仅「第一条路/第一件事」序数词（非广告绝对化），放行；④L053/L056 后台文档不逐字列红线词：发布设置/标题标签写「已通过自检」，合规全量 0 BLOCK；⑤L050 封面避免 U+2212：用 ASCII「·」，封面双断言通过；⑥L037 gen_sync_subs 位置参数：未复发；⑦L048 verify_burn 误报：未复发（三点全 PASS）。
- **返工计数**：3 次（短段扩写致 check_sync 重跑 / 合规「一劳永逸」改稿重配音 / PPT 顺序改动后漏重导帧致画面错位返工），门禁 FAIL 3 轮，作者打回 0。
- **时长**：成片 403.5s≈6.7 分钟（L 档·讲透优先）；content_depth 判 L 档。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。

---

## 2026-11-21 · AI 训练营 · 期号 46《温度调到零，模型就更准了吗》

### L062 [排版规则] 用 re.S 跨行删 /*...*/ 注释时误吃 :root 变量块 → bg_theme FAIL（已修）
- **现象**：make_ppt.py 里为删「训练营」字样写了 `re.sub(r"/\*.*?训练营.*?\*/", "", head, flags=re.S)`，结果从 :root 前的注释 `/*` 一直吃到后面某个 `*/`，把整个 `:root{...}` 配色变量块删掉 → bg_theme_check 报「未解析到 :root 变量块」FAIL。
- **根因**：`re.S` 让 `.` 跨行、非贪婪 `.*?` 从第一个 `/*` 匹配到**第一个**含「训练营」的 `*/`，但中间跨越了 :root 定义——CSS 注释与变量块在同一段文本里，删注释不能跨行一刀切。
- **修复**：改成逐行过滤——只删「单行且以 /* 开头、含训练营、以 */ 结尾」的行；跨行 :root 内的注释改用精确字符串替换（把「训练营主题色」换成中性词）保留结构。重导帧复检 bg_theme PASS。
- **防复发点**：**任何删 CSS/HTML 注释的操作都不得用 re.S 跨行 `/*...*/` 通配**——模板 :root 与注释交错，跨行删必误伤变量。用逐行状态机或精确字符串替换。本期新增口诀：删注释不跨行。
- **状态**：fixed（本期返工验证 PASS）。

### L063 [排版规则] visual_presence 声明载体数 > PPT 落实数 → 把纯文字页升级为真载体（已修）
- **现象**：首版 visual_plan 声明 15 段载体，PPT 只落实 9 页（bars/stat/diagram-grid/code-page），visual_presence BLOCK「用文字描述代码/流程头号反模式」。
- **根因**：P7「三种温度对照」、P12「top-p 候选集」用 `.split`/`.card-grid` 版式，脚本载体正则只认 cmp/stat/bars/diagram 等 class，未识别为对比表载体；visual_plan 却按语义声明了载体。
- **修复**：P7、P12 改用 `<table class="cmp">` 真对比表（脚本识别 cmp），载体页升到 11；visual_plan 把 3 个确为纯文字的页（P1 封面/P11/P14/P15）载体列改「—」，声明数=落实数=11 → PASS（载体 73%、纯文字 20%）。
- **防复发点**：写 visual_plan 时，凡声明「对比表/柱状/流程」的页，PPT 必须用脚本识别的 class（cmp/stat/bars/diagram-grid/code-page），不能只用 card-grid/split；且声明数必须与 CSV 载体识别结果对齐，多的标「—」。
- **状态**：fixed（本期返工验证 PASS）。

### L064 [排版规则] bars 柱状图 .lab 标签压入字幕带（FAIL 3 帧）→ 限高柱高并上移（已修）
- **现象**：subtitle_band 首检 P4/P5/P6 FAIL（字幕带非白像素 9330/6530/12152）——柱状图页的柱体+标签落到 y 900~993 字幕带。
- **根因**：`.bars{height:100%}` 让容器撑满 stat，柱高按 `v*3.6`（100%→360px），最高柱 99.75%→359px 把标签推到字幕带。
- **修复**：柱高系数改 `v*2.2`（100%→220px），`.bars` 固定 height:560px 并上移，stat 内 margin-top:10px → 重导 15 帧 subtitle_band 全净。
- **防复发点**：bars 页柱高上限按「内容底边 ≤ y870」反推，100% 柱高不超过 220px；凡用 bars 的期次导帧后必跑 subtitle_band（本期第 3 次踩同类底部避让，L047/L058 同源——同类已 3 次，建议蒸馏为模板级 bars 高度变量，待作者拍板）。
- **状态**：fixed（本期返工验证 PASS）。

### L065 [脚本bug] 本机实跑采样脚本 T=0 分支 one-hot 被二次 softmax 稀释（已修）
- **现象**：sampling_experiment.py 首跑 T=0 贪心输出 A=47.54% 而非 100%，与「贪心=必选第一名」矛盾。
- **根因**：`scale(logits, 0)` 返回 one-hot [1,0,0,0] 后又过了一次 `softmax()`，把 1 稀释成 e^1/(e^1+3)=47.54%。
- **修复**：T=0 分支直接返回 one-hot，不再二次 softmax → A=100.00%。重跑留存 experiment_output.txt。
- **防复发点**：贪心解码=argmax one-hot，不能对已归一化分布再 softmax；写采样/解码演示脚本时，T=0 特判必须直接 one-hot。此类「教学演示脚本自身正确性」也受第 7 条正确性红线约束——上屏数字必须自洽。
- **状态**：fixed（本期修复并验证 PASS；属本机实跑脚本，非技能脚本）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列出 13 open + 9 待验证 + P001/P002/P003。本轮 ①L007 visual_plan 精确「—」：本期按前缀判定落实，未复发；②L045 自定义 CSS 注入：在 `</style>` 前插入，未复发；③L048 verify_burn 误报：未复发（三点全 PASS）；④L053/L056 后台文档不逐字列红线词：发布设置/标题标签写「已通过自检」，合规全量 0 BLOCK；⑤L050 封面避免 U+2212：用 ASCII「·」，双断言通过；⑥L037 gen_sync_subs 位置参数：未复发。
- **返工计数**：3 次（visual_presence 声明数 / CSS 注释误吃 root / 字幕带柱状侵入），门禁 FAIL 3 轮，作者打回 0。实验脚本自纠 1 处（L065，未影响成片）。
- **时长**：成片 330.9s≈5.5 分钟（M 档偏上·讲透优先）；content_depth 判 L 档但按一个核心概念自主定 M。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。L064 同类底部避让第 3 次，建议蒸馏模板级 bars 高度变量（待作者拍板）。

---

## 2026-11-22 · 产品经理训练营 · 期号 47《Roadmap 怎么排才不被打乱》

### L066 [流程缺口] make_ppt.py 生成器把 <style> 放进 <body> → export_frames 只保留 head，导出帧全无 CSS（抽帧目检发现，已修）
- **现象**：自动门禁全过（bg_theme PASS、visual_presence PASS、subtitle_band PASS、verify_burn PASS），但抽帧 t=1 目检发现封面文字全挤在左上角成小字、画面无紫色标题带——导出的 14 帧完全没有应用 CSS。
- **根因**：本轮用自建 make_ppt.py 生成 PPT，把 `<style>...</style>` 拼在 `<body>` 之后（模板原本在 `<head>`）。`scripts/export_frames.py` 的 split_pages 只取 `head = html[:html.index('<body>')]` 部分重组每页，body 内的 style 被丢弃 → Chrome 渲染的是无样式裸文本。bg_theme_check 直接解析 :root 变量、visual_presence 只解析 class 字符串、subtitle_band 在无内容帧上天然全净、verify_burn 只看水印与字幕——四个门禁都看不到「渲染层没样式」。
- **修复**：生成器改为把 `full_css` 拼进 `</head>` 之前，重生成 PPT → 清空 frames 重导 14 帧 → 像素抽检确认标题带 (158,81,255) 且封面纯白 → 重跑 compose+burn+verify → 重抽帧目检全过。
- **防复发点**：**自建 PPT 生成器必须把 `<style>` 放在 `<head>`**，且导帧后必须做一次「渲染层 sanity check」——像素抽检标题带区域非白（内容页）与封面纯白，不能只信文本层门禁。自动门禁 PASS ≠ 画面正常，抽帧目检不可省（与 L059 同属「门禁测不到画面层」类）。是否给 export_frames 加「head 内无 style 则 FAIL」硬门禁待作者拍板（第 43 条⑤不自动改脚本）。
- **状态**：fixed（本期修正生成器并重导帧验证 PASS）。

### L067 [排版规则] 静态帧导出把 anim-pop 抓在半透明态 → 公式文字几乎不可读（已修）
- **现象**：page_03 的公式「分数 = 触达 × 影响 × 信心 ÷ 投入」渲染成极淡的浅紫，肉眼几乎看不清；数字页 `.num.anim-pop` 也有类似风险。
- **根因**：模板 CSS 动画 `.anim-pop{opacity:0;animation:pop .55s forwards}`，`export_frames.py` 用 `--virtual-time-budget=3000` 导帧，但 xfade 静态合成管线不需要动画，动画起始帧被抓到 opacity 很低的状态。`animation-fill-mode:forwards` 只保证动画结束后态，不保证截图落在结束后。
- **修复**：从生成器里移除所有内容承载元素的 `anim-pop` class（公式与 3 个数字页），静态帧直接渲染终态；重导帧后公式恢复实色可读。
- **防复发点**：**静态帧 + xfade 合成（默认管线，不加 --motion）时，关键内容（公式/数字/结论）一律不挂 anim-* class**——静态帧必须终态可读，动画只在走 render_animated.js 逐帧捕获时才用。是否内置「静态导帧自动去动画 class」开关待作者拍板（第 43 条⑤）。
- **状态**：fixed（本期去动画重导帧验证 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列出 13 open + 9 待验证 + P001/P002/P003。本轮 ①L007 精确「—」：visual_plan CTA 段记「—」，未复发；②L046/L058/L064 底部避让：卡片/表格/柱状统一 bottom:210、bars 限高 250，subtitle_band 14 帧全净未复发；③L063 声明数=落实数：P2/P4 由 split 改真 cmp 表，声明 12=落实 12，未复发；④L053/L056 后台文档元描述行：发布设置里「网盘」被合规脚本判 BLOCK → 改「云端归档」措辞，发布内容未动，复检 0 BLOCK（同根因又1次，P002/P003 仍 pending_author）；⑤L050 封面避免 U+2212：用 ASCII「·」，双断言通过；⑥L037 gen_sync_subs 位置参数：未复发；⑦L019 diagram-row nodebox 等分：P3 四节点等宽显示正常，未复发。
- **返工计数**：4 次（P2/P4 cmp 声明数 / style 误置 body 全无 CSS / anim-pop 半透明 / 合规元描述行 BLOCK），门禁 FAIL 4 轮，作者打回 0。其中两次靠抽帧目检才发现（L066/L067），自动门禁全 PASS。
- **时长**：成片 259.5s≈4.3 分钟（M 档·一个核心概念 RICE 讲透）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。L066 建议 export_frames 加 head-style 硬门禁、L067 建议静态导帧自动去动画 class，均待作者拍板。

---

## 2026-11-22 · 前端训练营 · 期号 48《框架自动转义了为什么还有XSS》

### L068 [排版规则] 模板顶部 HTML 注释未整段删除 → 残留文本把整页下推 150px、字幕带 FAIL 12 帧（fixed）
- **现象**：subtitle_band_check 12/16 帧 FAIL（字幕带非白像素 139440≈整带）；抽帧显示标题带出现在画面中部、表格下缘压进字幕带。
- **根因**：自建 make_ppt.py 只删了以 `<!--` 开头的单行，模板顶部多行 HTML 注释的正文行残留为可见文本，在 head 中被浏览器当作正文渲染，把 `.slide` 整体下推约 150px。L062 的「删注释不跨行」教训被误用成「只删首行」。
- **修复**：改为截取 `<head>` 后到第一个 `<meta>` 之前整段丢弃（只处理 head 已知注释块，不碰 CSS 的 /*...*/），重导 16 帧 → subtitle_band 全净、bg_theme 帧层 PASS。
- **防复发点**：自建 PPT 生成器必须整段删掉模板顶部 HTML 注释（`<head>`→首个 `<meta>`）；不要逐行删 `<!--`。**导帧后必做渲染层 sanity check**（抽帧看标题带位置），自动文本层门禁看不到「整页下推」。
- **状态**：fixed（本期重导帧验证 PASS）。

### L069 [排版规则] .src-note 来源行未绝对定位 → 浮到标题带压住 kicker/title（fixed）
- **现象**：抽帧 page_02 见「来源：OWASP…」出现在橙色标题带内、与「反直觉」kicker 重叠；自动门禁全 PASS（文本层脚本不判位置）。
- **根因**：`.src-note` 只写了 `margin-top`，无 `position`；在 `.diagram-stage` 等绝对定位兄弟节点后，它按正常流落在 slide 顶部（标题带区）。
- **修复**：改为 `position:absolute;left:120px;bottom:182px;z-index:3`，落在内容区下方、字幕带上方；重导帧抽帧确认来源行在表格下方、标题完整可读。
- **防复发点**：凡新增内容块（来源行/脚注/标签）一律显式绝对定位并给 bottom 值（承接 L043）；来源行 bottom 取 182px，位于内容块（bottom:214px）下沿与字幕带（y918）之间。
- **状态**：fixed（本期重导帧验证 PASS）。

### L070 [门禁失效] 合规后台设置文档「绝对化用语」元描述行 BLOCK 第 4 次复发（L034→L053→L056→本轮）→ 改写放行（open）
- **现象**：发布包全量合规复检 1 BLOCK，落在 `抖音发布设置.md` 第 7 行——字面写「封面…与绝对化用语」，被正则命中；三份发布文案与口播稿零命中。
- **根因**：同根因第 4 次。P002/P003 蒸馏提议仍 pending_author，脚本侧后台文件白名单未落地，靠文字约定连续四轮未根治。
- **修复**：改为「封面文字已通过平台规范自检，无系列标识与作者名」，发布内容未动；复检 0 BLOCK / 0 WARN。
- **防复发点**：后台设置/标题标签文件不逐字列举任何红线词；**P002/P003 已第 4 次复发，强烈建议下轮交互式会话批准作者拍板后改脚本白名单**（第 43 条⑤不自动改）。
- **状态**：open（同根因第 4 次 → 提议 pending_author 已升级；本期改写放行）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 13 open + 15 待验证 + P001/P002/P003；本轮 ①L066 `<style>` 在 head：本期生成器遵循，未复发；②L067 静态帧无动画 class：内容页无 anim-*，公式/代码终态可读，未复发；③L047/L058/L064 底部避让：所有内容块 bottom:214px，subtitle_band 16 帧全净；④L063 声明数=落实数：visual_plan 14 声明=PPT 14 落实（首版因表格缺行首 `|` 被解析 0 段，已补，未复发）；⑤L062 删注释：改 head 整段删，未复发；⑥L037 gen_sync_subs 位置参数：遵循；⑦多音字：apply 3 处（更→耕×2/因未×1）restore 零残留；「载荷」代理字冲突→改写为「恶意输入」绕开，属正确性优先。
- **返工计数**：3 次（HTML 注释残留字幕带 FAIL / src-note 浮顶 / 合规元描述行 BLOCK），门禁 FAIL 3 轮，作者打回 0。
- **时长**：成片 315.8s≈5.3 分钟（M 档·一个核心概念三层防线讲透）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。L068/L069 的「导帧后渲染层 sanity check」与 L066 同属「门禁测不到画面层」，第 3 次出现，建议蒸馏为导帧后像素抽检硬门禁（待作者拍板）。

### L071 [排版规则] 自建 make_ppt.py 封面页漏加 `cover` class → 顶部出现青色标题带、封面白字强调压同色带不可读（fixed）
- **现象**：抽帧封面 t1 见顶部青色渐变标题带（本应纯白封面），且"拐点"二字用 accent 青色压在青带上几乎看不清；自动门禁 bg_theme/visual_presence/subtitle_band 全 PASS（它们不检查 cover class 是否存在）。
- **根因**：self-built `slide()` 生成器对所有页统一输出 `<section class="slide">`，第一页未加 `cover active`，导致 `.slide.cover{background:#FFFFFF}` 与 `.slide.cover::before{display:none}` 两条封面规则均未生效。
- **修复**：`slide()` 加 `cover` 参数，第一页输出 `<section class="slide cover active">`；重导帧目检确认封面纯白、深字标题+青色强调清晰。
- **防复发点**：自建 PPT 生成器必须给封面页显式 `cover active` class；导帧后抽帧目检第 1 页（自动门禁测不到 class 缺失导致的封面错误）。与 L066/L067/L068 同属"渲染层抽帧目检不可省"。
- **状态**：fixed（本期重导帧验证 PASS）。

### L072 [排版规则] 代码页独立 `.src-note` 与 `.code-wrap` 底边几乎重叠 → 来源行被代码块遮住、起始文字被裁切（fixed）
- **现象**：抽帧 P6 见左下角来源行"本机实跑 knee_experiment.py…"起始文字被代码块盖住裁切；单独把它下移 44px 后又与 code-note 挤在同一行重叠。
- **根因**：`.src-note{bottom:216px}` 与 code-wrap 底边（代码页模板 bottom:158px）间距不足，且 code-block 层叠在上；简单下调 bottom 会与 code-note（在 code-wrap 内）冲突。
- **修复**：代码页取消独立 src-note，把来源并入 `.code-note` 文本末尾（"｜来源：…"），代码块内安全区一行显示；重导帧 P6/P13 确认来源单行完整不重叠。
- **防复发点**：代码页来源标注一律并入 code-note，不另起独立 src-note；非代码页 src-note 保持 bottom:216px。
- **状态**：fixed（本期重导帧验证 PASS）。

### L073 [门禁失效] 口播正文"吞吐量天花板"中"天花板"命中抖音绝对化 BLOCK（fixed）
- **现象**：抖音合规全量自检 2 BLOCK，落在口播稿第 3 段与公众号文案第 5 行的"吞吐量天花板"——"天花板"被正则判绝对化用语。
- **根因**：口播正文真实使用了绝对化表述（非 L070 那种元描述行误报），脚本正确命中。
- **修复**：口播稿与公众号文案同步改为"吞吐量的峰值数字"；因口播稿改动重跑 apply→分段 TTS（删 seg_01 缓存强制重渲）→restore→sub_clean→check_sync→重合成 body→重烧；合规复检 0 BLOCK / 0 WARN。
- **防复发点**：写稿避免"天花板/顶级/最好"等绝对化比喻词；合规门禁前于写稿阶段自查。口播稿一旦改动必须整条 TTS 链重跑（四方同频硬规则）。
- **状态**：fixed（本期重配音重烧验证 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 17 待验证 + P001/P002/P003；本轮 ①L066 `<style>` 在 head：本期生成器遵循未复发；②L067 静态帧无半透明动画：内容页无 anim-class，终态清晰未复发；③L047/L058/L064 底部避让：所有内容块 bottom:210px、subtitle_band 14 帧全净未复发；④L063 声明数=落实数：visual_plan 首版声明 14>落实 12（P1封面/P2split 未识别）→ P2 改 cmp 表+plan 声明 13 → PASS；⑤L037 位置参数遵循；⑥多音字 apply 2（因为→因未）restore 零残留。
- **返工计数**：4 次（封面 cover class / 代码页来源行 / 载体声明数 / 合规天花板重配音），门禁 FAIL 4 轮，作者打回 0。
- **时长**：成片 240.9s≈4 分钟（M 档·拐点一个核心概念讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。L071/L072 再次印证"导帧后渲染层抽帧目检不可省"（与 L066/L068 同根因第 3 次），建议蒸馏为导帧后像素抽检硬门禁（待作者拍板）。

---

## 2026-11-24 · 管理训练营 · 期号50《改流程之前，先量这三个数》

### L074 [流程缺口] visual_plan 封面/CTA 段载体列写描述而非精确「—」→ 声明数>落实数 BLOCK（fixed）
- **现象**：visual_presence_check FAIL——声明 14 段载体、PPT 只落实 13 页。
- **根因**：visual_plan 第 1 段（封面）与第 14 段（CTA）的「画面载体」列写了「hero 大字 + 三数小标」「stat 三数回顾 + 自然 CTA」等描述而非精确「—」；脚本对「—」精确相等判定，带描述即计入声明数（L007 同根因复发）。
- **修复**：把这两段的画面载体列改为精确「—」，描述并入「口播要点」列；复跑声明 12 ≤ 落实 13 → PASS（WARN 正常）。
- **防复发点**：visual_plan 封面段与纯 CTA 段的画面载体列必须精确写「—」，任何描述文字都会导致声明数虚高。
- **状态**：fixed（本期复检 PASS）。

### L075 [门禁失效] 模板 CSS 注释含营名/期号字样 → PPT 全文禁句扫描命中（fixed）
- **现象**：PPT 生成后全文 grep「训练营/架构师/期号」命中 6 处，全部位于模板 head 的 CSS 注释（如「--accent 如架构师 #00843D」「完整配值见 SKILL.md 训练营主题色表」）。
- **根因**：模板注释属说明文字、不进画面，但「PPT 画面禁句/禁标识扫描」是全文 grep，注释同样命中；首版尝试逐行过滤删注释，误删了含「架构师」说明的 `--accent` 定义行，导致 bg_theme 推断不出训练营 FAIL。
- **修复**：改严格的 CSS 注释块非贪婪匹配 `r"/\*.*?\*/"` + re.S 整块删除（注释块配对完整，不会误吃 `:root`），再做颜色替换；重新生成后 grep 干净、bg_theme PASS。
- **防复发点**：自建 PPT 生成器删 CSS 注释须整块非贪婪删，禁止逐行关键字过滤（会误删属性定义行）；L062 的坑是正则写错吃 `:root`，本次用配对块删除规避。
- **状态**：fixed（本期复检 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 20 待验证 + P001/P002/P003。①L066 style 在 head：遵循未复发；②L067 静态帧无 anim class：覆写 `animation:none` 未复发；③L068 head 整段删 HTML 注释：遵循；④L069 src-note 绝对定位：来源行并入 diagram legend / code-note，L072 遵循；⑤L071 封面 cover active class：遵循未复发；⑥L046/L047 底部避让 196px：subtitle_band 14 帧全净；⑦L037 位置参数：sub_clean 用 `--input/--out` 未复发；⑧L070 合规元描述行：发布设置不逐字列红线词，全量 0 BLOCK（未复发）；⑨多音字代理 3 处 restore 零残留。
- **返工计数**：2 次（visual_plan 声明数 / CSS 注释禁标识），门禁 FAIL 2 轮，作者打回 0。
- **时长**：成片 375.8s≈6.3 分钟（M 档·一个核心概念「先量三数再改」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。

---

## 2026-11-24 · 软技能训练营 · 期号51《收藏了那么多，为什么都没学会》

### L076 [排版规则] bars 容器 height:100% + 下方 legend 叠加 → 图例文字侵入字幕带 P2 FAIL（fixed）
- **现象**：subtitle_band_check P2 FAIL，字幕带非白像素 918——图例行「177名大学生…来源…」被推到字幕带。
- **根因**：模板 `.bars{height:100%}` 撑满 bars-wrap，图例 legend 在其后追加即溢出容器底边（bottom:210px）。
- **修复**：P2 的 `.bars` 改 `style="height:80%"`，图例回到安全区内；重导帧 subtitle_band 12/12 全净。
- **防复发点**：bars 页若有容器外图例/来源行，柱区高度须显式留白（≤82%），不得让 height:100% 撑满后再追加元素。
- **状态**：fixed（本期重导帧验证 PASS）。

### L077 [排版规则] terminal 页来源行未绝对定位 → 浮到顶部标题带压字；深色底灰字不可读（fixed）
- **现象**：P9 抽帧目检见来源行「来源：Dunlosky 2013…」出现在顶部棕色标题带、与主标题「先答后翻，分散日子」重叠；自动门禁（bg_theme/subtitle_band）全 PASS 未能发现。
- **根因**：来源行 `.kv-note` 是普通流内元素，terminal 为绝对定位，来源行落到页面顶部；改绝对定位后文字用 `--muted` 灰、落在深色 terminal 上对比度不足。
- **修复**：来源行改 `position:absolute;bottom:232px;left:188px;color:#9fb0c8`（浅色），移入深色框底部；重导帧目检清晰无重叠。
- **防复发点**：terminal/深色代码块页的来源行一律绝对定位 + 浅色文字，且导帧后必须抽帧目检（自动门禁测不到「浮顶压字/深色底灰字」）。与 L066/L068/L069/L071 同属「渲染层抽帧目检不可省」。
- **状态**：fixed（本期重导帧验证 PASS）。

### L078 [门禁失效] 抖音发布设置.md 元描述行逐字列举红线词 → 全量合规 5 BLOCK 误报（fixed）
- **现象**：全量合规复检 5 BLOCK，全部落在后台「抖音发布设置.md」的说明文字（逐字写了「网盘/绝对化用语/微信加V/私域/站外链接」等词），发布内容本身 0 BLOCK。
- **根因**：脚本正则不区分「发布正文」与「后台设置说明文档」，元描述行逐字列举红线词即命中——L034→L053→L056→L070 同根因**第 5 次复发**。
- **修复**：改「封面文字已通过平台规范自检，无系列标识与作者名」「CTA 仅用评论区提问与关注，符合平台站内互动规范」；复检 0 BLOCK / 0 WARN。
- **防复发点**：P002/P003 提议已第 5 次复发，强烈建议交互式会话批准作者拍板后改脚本白名单（第 43 条⑤不自动改）。后台文档禁止逐字列举任何红线词。
- **状态**：fixed（同根因第 5 次 → 提议 pending_author 已升级；本期改写放行）。

---

## 2026-11-25 · 架构师训练营 · 期号52《服务拆得越细，为什么越容易崩》

### L079 [排版规则] 来源行 bottom:232px 与 diagram-stage bottom:240px 几乎同位 → 来源行压在底层节点上（fixed）
- **现象**：P10 抽帧见来源行「来源：AWS Well-Architected…」横穿「照片 / 评论」两个底层节点；自动门禁 bg_theme / subtitle_band / visual_presence 全 PASS，目检才发现。
- **根因**：`.src-note{bottom:232px}` 与 `.diagram-stage{bottom:240px}` 底边几乎重合，来源行落在图示容器下沿内部而非下方。
- **修复**：来源行统一改 `bottom:196px`；重导 14 帧并复跑 subtitle_band 全净，P10 目检来源行移至节点下方且不入字幕带。
- **防复发点**：来源行 bottom 数值须比内容容器 bottom 至少低 40px（图示/表格/卡片页同理）；导帧后必须抽帧目检来源行位置，自动门禁测不到此类重叠。
- **状态**：fixed（本期重导帧验证 PASS）。

### L080 [排版规则] diagram-stage 内 `.legend{margin-top:auto}` 在容器高度不足时被 overflow:hidden 裁成半行（fixed）
- **现象**：P10 第一次修正后，图示容器下沿的「结论：区分必选与可选…」只露出上半截，被容器边界切掉。
- **根因**：`.diagram-stage{overflow:hidden}` + 三层 diagram-row + 两条 link-band 已占满容器，legend 再 `margin-top:auto` 只能挤在下沿被裁切。
- **修复**：删除该页 legend，信息已由两条 link-band 标签（必选调用 / 可选调用·失败即省略）承载；重导帧确认无残留半行文字。
- **防复发点**：图示页若已有带标签连线，不再追加 legend；确需 legend 时为容器预留 ≥40px 余量，导帧后抽帧确认完整。
- **状态**：fixed（本期重导帧验证 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 22 待验证 + P001/P002/P003；①L066 style 在 head：遵循未复发；②L067 静态帧无 anim-class：内容页无 anim，终态清晰；③L046/L047/L064 底部避让：除 P2 图例溢出（L076）外全净；④L074 visual_plan 声明数：10 声明 = 10 落实，封面/CTA 精确「—」，未复发；⑤L075 CSS 注释整块删：遵循未复发；⑥L071 封面 cover active：遵循未复发；⑦L037 位置参数：sub_clean 用 --input/--out 未复发；⑧多音字 apply 3（因为→未 / 间隔→见×2）restore 零残留；「卡壳」改「想提取却提不出的费劲过程」规避读音风险。
- **返工计数**：3 次（P2 字幕带 / P9 来源行浮顶 / 合规元描述行），门禁 FAIL 3 轮，作者打回 0。
- **时长**：成片 272.8s≈4.5 分钟（M 档·一个核心概念「主动检索优于重读」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。SC031 事实卡片入库。

---

## 2026-11-25 · 大数据训练营 · 期号53《大模型写的SQL，错在哪》

### L081 [流程缺口] 本机实验案例初版两组 SQL 输出相同，演示不出错误（fixed）
- **现象**：text2sql_experiment.py 案例 3 初版「朴素」与「修正」SQL 都返回 430.0，无法支持口播中「漏掉下午那笔 60 元」的结论。
- **根因**：初版把朴素条件写成 `paid_at LIKE '2026-10%'`，与 `>= 10-01 AND < 11-01` 在数据上等价；没有真正制造闭区间上界截断。
- **修复**：新增 2026-10-31 15:20 的 PAID 订单（60 元），朴素条件改 `BETWEEN '2026-10-01' AND '2026-10-31'`，重跑得到 430.0 vs 490.0，与口播逐字一致。
- **防复发点**：写「错误 vs 正确」对照实验时，必须先跑一遍确认两组输出**不同**；实验输出与口播数字必须逐项核对后才写稿。
- **状态**：fixed（本期重跑验证 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 27 待验证 + P001/P002/P003；①L066 style 在 head：自建生成器未另写 style，模板 head 完整；②L068 head 注释整段删：用非贪婪正则整段删 CSS/HTML 注释，未复发；③L071 cover active class：封面 `cover active` 显式写；④L046/L047/L079 底部避让：src-note bottom:196，subtitle_band 15/15 全净；⑤L074 visual_plan 声明数：声明 13 = 落实 13，封面/CTA 精确「—」；⑥L078 合规元描述行：发布设置用「已过规范自检」，全量 0 BLOCK/0 WARN；⑦多音字 apply 10 处 restore 零残留；⑧P003 合规第5次复发仍未自动改脚本（pending_author 保留）。
- **返工计数**：1 次（实验案例初版无差异，改稿重跑，未返工重配音）；门禁 FAIL 0 轮；作者打回 0。
- **时长**：成片 264.80s≈4.4 分钟（M 档·一个核心概念「先用数据画像约束生成，比结果集」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。SC034/SC035/SC036 事实卡片入库。

---

## 2026-11-26 · AI训练营 · 期号54《榜单第一的模型，为什么不好用》

### L082 [脚本bug] 自建 make_ppt.py 切页方向写反，模板示例 slides 残留致 20+ 页（fixed）
- **现象**：首版生成 PPT 后 visual_presence_check 报「幻灯片总数 22（应 16）」，且声明/落实载体数严重失配。
- **根因**：用 `html[:script_i] + 占位 + html[script_i:]` 替换，保留了 `<body>` 开标签到 `<script>` 之间的模板示例 slides，把新增 16 页加在了模板 4 页示例之后。
- **修复**：改为按 `<body>` 开标签定位——`html[:body_tag_i+len('<body>')] + 占位 + html[script_i:]`，丢掉 body 内模板示例、保留 script；重生成后 section=16。
- **防复发点**：自建 PPT 生成器若有「删模板示例」步骤，必须用 `<body>` 开标签定位保留前缀，不可用 `<script>` 位置反推；生成后立刻 `grep -c '<section class="slide'` 核对页数==计划页数。
- **状态**：fixed（本期重导帧验证 PASS）。

### L083 [排版规则] visual_plan 把 split/card-grid/hero 声明为载体，声明 16 > 落实 10 BLOCK（fixed）
- **现象**：visual_presence_check BLOCK「声明 16 段载体，PPT 只落实 10 页」。
- **根因**：脚本 CARRIER_RES 只认 code/diagram/bars/cmp/stat/flow/svg，不认 split/card-grid/hero；我在 plan 里把这些也填了载体描述。
- **修复**：按实际 PPT 载体页回填 plan，非识别类一律填精确「—」，声明 10 = 落实 10 → PASS（WARN 非阻塞）。
- **防复发点**：写 visual_plan 时，载体列只填脚本可识别的 class 名（diagram/flow/bars/cmp/stat/code/svg），split/card/hero/纯文字一律「—」；L007 同类口径第 2 次。
- **状态**：fixed（本期复跑 PASS）。

### L084 [排版规则] stat 大数字用模板 .num 渐变填充，中文串在白底变浅粉不可读（fixed）
- **现象**：抽帧 t=200 发现「自己的任务数据」大字是浅粉色，白底上几乎看不清；t=1/t=10 的 0.6%/<1% 同样偏浅。
- **根因**：模板 `.stat .num` 带 `-webkit-text-fill-color:transparent` + 渐变填充（为数字大字号设计），中文串渐变落在浅端，且自动门禁（bg_theme/visual_presence/subtitle_band/verify_burn）全 PASS，属渲染层目检盲区。
- **修复**：三处 num span 显式加 `color:var(--accent);-webkit-text-fill-color:var(--accent)` 覆盖渐变；重导 8/10/15 帧 → 重合成 → 重烧 → 目检深红可读。
- **防复发点**：stat 页若放非数字大字（中文/百分号），必须显式覆盖 text-fill-color；抽帧目检不可省——自动门禁测不到「渐变色在白底不可读」。此为本期第 2 次印证「渲染层目检盲区」（L082 亦靠目检发现）。
- **状态**：fixed（本期重导帧复检 PASS）。

### L085 [门禁失效] 抖音合规 BLOCK「成绩最好的那个」绝对化用语（fixed）
- **现象**：合规自检 BLOCK 1 项——「只公布成绩最好的那个」命中绝对化用语「最好」。
- **根因**：转述论文 "selective disclosure of best score" 时直译成「最好」，触犯第 30 条。
- **修复**：改「只挑成绩靠前的那个」，四方同频（口播稿/segments/PPT/script_tts/make_ppt/sources 六处）改写 → 删 seg_10 缓存重配音 → restore/clean → check_sync PASS → 重导 11 页 → 重合成重烧 → 全量合规 0 BLOCK/0 WARN。
- **防复发点**：转述论文/外文中含 best/top 的表述时避免直译「最好/第一」，用「成绩靠前/排名靠前」等可核验比较口径；改稿必须删对应 seg 缓存重配音（否则字幕与稿不一致，check_sync 会 FAIL）。
- **状态**：fixed（本期复检 PASS）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 28 待验证 + P001/P002/P003；①L066 style 在 head：模板完整未另写 style；②L068 head 注释整段删：非贪婪正则删 HTML 注释块 + 逐行删 CSS 含营名注释，禁句扫描 CLEAN；③L071 cover active class：封面显式 cover active；④L046/L047/L079 底部避让：card-grid/split/code-wrap bottom:196、src-note bottom:210，subtitle_band 16/16 全净；⑤L074 visual_plan 声明数：见 L083；⑥L078 合规元描述行：发布设置用「已过规范自检」，全量 0 BLOCK/0 WARN；⑦多音字 apply 3 处 restore 零残留；⑧L081「对照实验先跑出差异」：实验首版 0.6% 未翻转榜首，如实呈现为「分差 0.078→0.004 未易主」未编造，与论文结论分开陈述。
- **返工计数**：4 次（切页方向 / plan 声明 / 大字色 / 合规改写），门禁 FAIL 2 轮（visual_presence BLOCK + 合规 BLOCK），作者打回 0。
- **时长**：成片 217.83s≈3.6 分钟（M 档·一个核心概念「榜单分≠场景分」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。事实卡片本轮新增（见 evolution source add）。

---

## 2026-11-27 · 产品经理训练营 · 期号55《研发说做不了，需求这样改》

### L086 [脚本bug] 自建实验脚本 f-string 内嵌转义引号 + 元组扩位不一致（fixed）
- **现象**：`moscow_experiment.py` 首跑 `SyntaxError: unexpected character after line continuation character`（`f"...{effort[\"Won't\"]}"`），改 Tuple 为 4 元后 `ValueError: too many values to unpack (expected 3)`。
- **根因**：① f-string 表达式内不能直接写反斜杠转义的引号（Python <3.12 口径）；② `REQUIREMENTS` 由 3 元组改为 4 元组后，`tally()` 仍按 3 元解包。
- **修复**：把带撇号的字典值先取局部变量（`wont_effort = effort["Won't"]`）再进 f-string；`tally()` 改为 `for (_, days, _, _), lv in zip(...)`；两轮版本同法修 `wont2`。
- **防复发点**：写本机实验脚本时，含撇号的分类名（如 `Won't`）一律先取变量再格式化；改元组结构必须全局 grep unpack 处。实验脚本先空跑到输出全通再写口播稿。
- **状态**：fixed（本期两轮实验实跑通过，输出已留档 `发布/moscow_experiment_output.txt`）。

### L087 [流程缺口] 单轮实验只得到「Must 61.5% FAIL」，撑不起「需求拆解后排得下」的结论（fixed）
- **现象**：首版把 47 人天需求一次性分类，Must 24 人天=61.5% 超 DSDM 60% 上限，结论是「排不下」，但口播要讲「研发说做不了时先动范围」的可操作解法。
- **根因**：实验只模拟一次归类，没有还原真实排期会上「对 Must 再追问有无临时人工绕过」这一步；把 DSDM 的取消测试用成了「谁喊得响谁就是 Must」。
- **修复**：改为两轮对照——第二轮对 Must 逐条追问能否人工绕过（支付回调对账保留 Must、订单导出/消息推送降 Should），Must 18 人天=46.2% PASS，Could 8 人天=20.5%，本期排入 39/容量 40。
- **防复发点**：L081 同口径——实验必须先跑出**方向不同的两种结果**再写稿；讲「先拆解」类方法论时，实验设计须包含拆解前/后两轮，且每轮判定规则可复述。
- **状态**：fixed（本期重跑验证 PASS，口播数字逐项核对一致）。

### L088 [排版规则] cmp 对照表同时输出 legend 来源行与 code-src 来源行，页内重复（fixed）
- **现象**：目检 page_06 见两行「来源：本机实跑 · 2026-11-27」上下相邻。
- **根因**：`cmp_table()` 原本既渲染 `legend` 文本行，又在 `.code-src` 固定输出来源，两处同源。
- **修复**：删除 `cmp_table()` 中的 legend 来源行，只保留 `.code-src`；重导帧目检单来源。
- **防复发点**：同一表格组件只允许一个来源输出点；导帧后目检同类表格页，自动门禁测不到来源行重复。
- **状态**：fixed（本期重导帧目检 PASS）。

### L089 [排版规则] 误差区间用双柱 + 两个「±50%」标签，柱高与标签语义对不上（fixed）
- **现象**：page_12 初版柱状图用两根等高柱各标「±50%」，读者会误读成两个不同场景的柱高差异。
- **根因**：把「同一诊断在三种场景下的偏差口径」画成柱状对比，图表类型与语义不匹配。
- **修复**：slide 12 改为 `cmp` 三场景对照表，同步把 `build/visual_plan.md` 的载体声明从 `bars` 改为 `cmp`，重导帧。
- **防复发点**：画误差/偏差区间优先用对照表或区间示意，不用等高柱配相同百分比标签；改载体类型必须同步 visual_plan，否则 visual_presence 会 BLOCK（L083 同口径）。
- **状态**：fixed（本期重导帧复检 PASS）。

### L090 [门禁失效] 抖音发布设置.md 元描述行再触 BLOCK「绝对化词」「网盘」（fixed）
- **现象**：全量合规 2 BLOCK，均在后台设置说明行（「封面无训练营名/期号/绝对化词/作者名」「按规范归档网盘」），发布正文 0 BLOCK。
- **根因**：L034→L053→L056→L070→L078 同根因**第 6 次复发**：脚本正则不区分发布正文与后台元描述行，逐字列举红线词即命中。
- **修复**：改「封面已过规范自检与 bbox 双断言」「按规范做云端归档」；复检 0 BLOCK / 0 WARN。
- **防复发点**：P002/P003 已第 6 次复发，须作者拍板后改脚本白名单（第 43 条⑤不自动改）；后台文档禁止逐字列举任何红线词。
- **状态**：fixed（同根因第 6 次 → 提议 pending_author 已升级；本期改写放行）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 32 待验证 + P001/P002/P003；①L066 style 在 head：模板 head 完整未另写 style；②L068 head 注释整段删 + L075 CSS 注释删：HTML/CSS 注释用正则整段清，禁句扫描 CLEAN；③L071 cover active：封面显式 cover active；④L046/L047/L079 底部避让：card-grid/split 270–196、diagram-stage 250–196、code-src bottom:210，subtitle_band 14/14 全净；⑤L074 visual_plan 声明数：声明 13 = 落实 13，封面/CTA 精确「—」（L083 口径未复发）；⑥L078 合规元描述行：本期复发见 L090；⑦L081「对照实验先跑出差异」：两轮 61.5% FAIL→46.2% PASS 后才写稿（L087）；⑧L084 stat 大字显式 `var(--accent)` 覆盖渐变，未复发；⑨多音字 apply 2 处（因为→未、误差→插）restore 零残留，「载」因误伤风险跳过。
- **返工计数**：1 次（page_12 载体语义改表 + 同步 plan 重导帧）；门禁 FAIL 1 轮（全量合规 BLOCK，见 L090）；作者打回 0。
- **时长**：成片 271.80s≈4.5 分钟（M 档·一个核心概念「排期谈不拢先动范围，用取消测试重划 Must」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。事实卡片 SC039/SC040 入库（DSDM 官方 L1）。

---

## 2026-11-27 · 前端训练营 · 期号56《AI写的代码，靠类型兜底》

### L091 [流程缺口] export_frames.py 位置参数不被接受（fixed）
- **现象**：按历史口径 `python3 scripts/export_frames.py <ppt> <out>` 报错 `the following arguments are required: --ppt, --out`。
- **根因**：脚本只支持具名参数 `--ppt / --out`（与 video_tool.py sub_clean 同类的 CLI 收紧）。
- **修复**：改 `python3 scripts/export_frames.py --ppt <PPT.html> --out <frames_dir>`，14/14 帧导出成功。
- **防复发点**：导帧前先跑 `export_frames.py --help` 确认参数形态；与 L037（sub_clean 具名参数）同属「脚本 CLI 以当轮 --help 为准」。
- **状态**：fixed（本期验证 PASS）。

### L092 [门禁失效] 抖音合规脚本是纯文本扫描器，不可喂 PNG（fixed）
- **现象**：把 `封面_4x3.png / 封面_3x4.png` 当参数传给 `douyin_compliance_check.py`，输出 15 项 BLOCK，全是二进制乱码匹配「站外引流」词表。
- **根因**：该脚本按文本逐行读文件；PNG 二进制被解码成乱码后正则误命中，与封面实际文字无关。
- **修复**：封面图改用人工逐字目检（画面文字扫描口径），脚本只扫口播稿/标题/三平台文案/标题标签/发布设置等文本文件，全量复检 0 BLOCK/0 WARN。
- **防复发点**：合规脚本入参只给 .txt/.md 文本；封面图的文字合规走 `present_files`/ViewImage 目检，不喂脚本。此为本期工具误用，非脚本缺陷。
- **状态**：fixed（本期验证 PASS）。

### L093 [门禁失效] 发布设置.md 元描述行逐字列红线词触发 BLOCK 第 7 次复发（fixed）
- **现象**：全量合规 1 BLOCK——发布设置清单第⑤项写「画面无训练营名/期号/作者名/招募词/绝对化用语」，命中绝对化词表。
- **根因**：L034→L053→L056→L070→L078→L090 同根因**第 7 次复发**：后台元描述行逐字列举红线词被正则误报，发布正文 0 BLOCK。
- **修复**：改「已过 bbox 双断言与画面文字逐字目检、合规自检」「已过画面标识与话术规范自检」；复检 0 BLOCK / 0 WARN。
- **防复发点**：P002/P003 待拍板脚本白名单（第 43 条⑤不自动改脚本）；后台文档禁止逐字列举任何红线词，一律写「已过规范自检」。
- **状态**：fixed（同根因第 7 次 → 提议 pending_author 已升级；本期改写放行）。

### 本轮其他（无需改规则，记备查）
- **防复发清单命中**：brief 列 14 open + 37 待验证 + P001/P002/P003；①L066 style 在 head：模板 head 完整，覆写在 `</style>` 前注入；②L068 head 注释整段删 + CSS 注释删：禁句扫描 CLEAN；③L071 cover active：封面显式 `slide cover active`；④L046/L047/L079 底部避让：code-wrap/cmp-wrap/terminal bottom 196~204、src-note top:196 绝对定位，subtitle_band 14/14 全净；⑤L083 visual_plan 声明 12 = 落实 12，封面/CTA 精确「—」；⑥L084 stat 大字显式 --accent（本期无 stat 页）；⑦L081 对照实验：先跑出 exit0面积0 / exit2 TS2322 / exit0面积8 三种方向不同结果再写稿；⑧L090 合规元描述行本期第 7 次复发（L093）；⑨多音字 apply 3 处（因为→未）restore 零残留。
- **返工计数**：1 次（L093 合规元描述行改写）；门禁 FAIL 2 轮（L091 CLI 参数 + L093 合规 BLOCK），均非渲染层问题；作者打回 0。
- **抽帧目检**：t=1/30/70/150/190/258 六点全过（白底橙带·代码与终端深底浅字清晰·对照表与流程图节点可读·水印左上不压字·单行字幕不遮挡·无营标识期号·CTA 站内收敛）。
- **时长**：成片 261.07s≈4.35 分钟（M 档·一个核心概念「可辨识联合 + never 穷尽检查把漏分支挡在编译期」讲透闭环）。
- **提议状态**：P001/P002/P003 仍 pending_author，未 approve、未自动改技能规则。事实卡片 SC041 入库（TS 官方 Handbook L1 + 本机实跑）。

---

## 期号57（2026-11-28）测试训练营《大模型应用怎么测，对错怎么判》

### L094 [排版规则] visual_plan 表格缺行首竖线导致 read_plan 声明 0 段 BLOCK（fixed）
- **现象**：visual_presence_check 报「visual_plan.md 里没有任何一段声明了画面载体」，实测 15 段载体全写在无前导 `|` 的表格里。
- **根因**：`read_plan()` 只认 `line.startswith("|")` 的行；表头/数据行无行首竖线时整表被跳过。与 L007 同源（该次是「—（说明）」后缀）。
- **修复**：表格每行改为 `| ... |` 标准写法，声明 15 段。
- **防复发点**：写 visual_plan 一律带行首 `|`；封面/非强载体页精确写「—」前缀。
- **状态**：fixed（本期复跑 PASS，声明 14 = 落实 14）。

### L095 [排版规则] diagram-stage 灰底铺满字幕带，5 帧 FAIL（fixed）
- **现象**：page_03/06/09/10/13 字幕带非白像素 139440（=1680×83，整条带宽），改 CSS bottom/height 多次无效。
- **根因**：模板 `.diagram-stage{position:absolute;top:250;bottom:170;background:var(--panel)}` 相对 slide 定位，灰底块一直铺到画面底部；export_frames 的 head 截取与层叠让自定义覆盖未生效。
- **修复**：在 make_ppt.py 里给 diagram-stage inline `style="background:transparent!important;border:none!important;height:600px!important;..."`（inline!important 优先级最高），灰底消除。
- **防复发点**：图示页灰底块若 FAIL，优先 inline!important 去掉背景，而非反复调 bottom 百分比；导帧后必跑 subtitle_band_check。
- **状态**：fixed（本期 15/15 帧全净）。

### L096 [排版规则] bars 柱底压字幕带（fixed）
- **现象**：P9/P10 柱图底部青色像素侵入 y918~980（6784/10074 像素）。
- **根因**：`.bars{height:100%}` + 柱子 `align-items:flex-end`，降柱高百分比无效，柱底仍落在字幕带起点。
- **修复**：给 bars 容器 inline `padding-bottom:70px!important` 整体上移；重导帧后 subtitle_band 15/15 全净。
- **防复发点**：柱状图页导帧后必跑字幕带门禁；柱底侵入优先加容器 padding-bottom，不动柱高比例。
- **状态**：fixed（本期验证 PASS）。

### L097 [脚本bug] 自定义 CSS 注释内字面量 `</style>` 导致 CSS 泄漏到画面（fixed）
- **现象**：成片封面帧顶部出现整屏 CSS 源码文字，字幕仅显示「我是Map」，水印被压。
- **根因**：make_ppt.py 用 `html.replace('</style>', extra_css+'</style>', 1)` 注入；extra_css 的注释里写了字面量 `</style>`，被浏览器当成第二个闭合标签，后续 CSS 全部作为 body 文本渲染。属 L045（style 误置 body）的变体。
- **修复**：注释改为「注入在样式闭合标签前」，避免字面量；重生成后 `<style>` 开/闭各 1，封面帧目检干净。
- **防复发点**：注入 CSS 时，任何注释/字符串都不得含字面量 `</style>`；生成后校验 `<style>` 与 `</style>` 计数均为 1。
- **状态**：fixed（本期重烧成片目检 PASS）。

### 本轮其他（备查）
- **返工 4 处**（L094~L097），门禁 FAIL 4 轮，作者打回 0；合规元描述行误报第 8 次（改写放行，同根因 L093）。
- **防复发清单命中**：L046/L079 底部避让（L095/L096 再现）；L068 head 注释（本期无残留）；L071 cover active（封面显式）；L083 visual_plan 声明口径（L094）。
- **抽帧目检**：t=1/55/130/210/283 五点全过（封面纯白青带无 CSS 泄漏、终端步骤块深底浅字清晰、来源行归位、水印左上、单行字幕不遮挡、无营标识期号、CTA 站内收敛）。
- **提议状态**：P001/P002/P003 仍 pending_author，未自动改技能规则。事实卡片 SC042/SC043 入库。


### L098 [排版规则] .note 与 .src 底部叠字，自动字幕带门禁未发现（fixed）
- **现象**：成片抽帧 t=40/100/160/280 底部注释行与来源行叠在一起（P3/P4/P6/P11 等含 .note 页），肉眼不可读；但 subtitle_band_check 14/14 全 PASS，自动门禁未发现。
- **根因**：make_ppt.py 中 `.note{bottom:170px}` 与 `.src{bottom:178px}` 仅差 8px，文字行高约 25px，必然重叠；自动字幕带门禁只查 y[918,1001] 净空，不检查底部两个文本行之间的互相重叠。
- **修复**：`.note` 改为 `bottom:212px`，重新生成 PPT → 重导 14 帧 → 三门禁 PASS → 重合成 body → 重烧录成片 → verify_burn PASS → 抽帧目检确认两行分离（y≈455 vs y≈472）。
- **防复发点**：底部有多个文本行时 bottom 间距须 ≥ 字高 + 8px；每轮成片抽帧目检必须逐项看「注释行/来源行/页码」三者互不重叠，不能只信自动门禁。
- **状态**：verified（本期重烧成片抽帧 PASS）。

### L099 [脚本bug] burn_subtitles.py 相对路径致 probe_duration 返回空、烧录中断（fixed）
- **现象**：`python3 burn_subtitles.py --engine fast build/body.mp4 build/subtitles_clean.srt build/voiceover.mp4 成片.mp4` 报 `ValueError: could not convert string to float: ''`（line 229 audio_dur）；手动 ffprobe 同一文件正常返回 386.232。
- **根因**：脚本 `probe_duration()` 对相对路径解析失败、stdout 为空（硬编码 `/usr/local/bin/ffprobe` 本身正常）；改用绝对路径传参即恢复。
- **修复**：烧录命令 body/srt/audio/out 全部改绝对路径，重跑 `cues=122` PASS。
- **防复发点**：burn_subtitles.py / verify_burn.py 等涉及 ffprobe 的脚本一律传绝对路径；遇 `probe_duration` 空输出先切绝对路径，再排查 ffprobe 本身。
- **状态**：fixed（本期绝对路径重烧成片 PASS）。

### L100 [流程缺口] visual_plan 声明载体 13 > PPT 实际 10，门禁 FAIL（fixed·同根因第 3 次）
- **现象**：visual_presence_check.py FAIL：plan 声明载体 13 段，PPT 实际落实 10 页（cover/split/card-grid 被误计为强载体）。
- **根因**：visual_plan 把非门禁识别载体（cover/split/card-grid）计入强载体数；与 L083/L094 同根因第 3 次复发。
- **修复**：将 P1/P2/P13/P14 标为 `—（轻视觉）`，声明强载体 10 段，复检 PASS。
- **防复发点**：visual_plan 只计 `diagram-stage/diagram-grid/flow/bars/cmp/stat` 等脚本识别载体，其余一律精确写「—」；生成后立即跑 visual_presence_check 双向核对。
- **状态**：fixed（本期 PASS，已触发蒸馏提议待作者拍板）。

### 本轮其他（备查·期号58）
- **返工 2 处**（L098/L100），另脚本坑 1 处（L099），门禁 FAIL 1 轮（visual_presence），作者打回 0；合规 0 BLOCK / 0 WARN（元描述行误报未复发）。
- **防复发清单命中**：L083/L094 载体声明口径（L100 第 3 次复发）；L068 head 注释（本期主动删除模板注释，无残留）；L097 CSS 注释泄漏（本期无）。
- **抽帧目检**：t=40/100/160/280/384 五点全过（note/src 分离、字幕净空带不遮挡、水印左上、无营标识期号、CTA 站内收敛）。
- **提议状态**：P001/P002/P003 仍 pending_author，未自动改技能规则。事实卡片本轮 source add 入库。
