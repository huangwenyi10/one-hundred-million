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

## 观察项（未构成问题，登记备查）

- O1（2026-10-25）：字幕母版 30fps 整帧量化与 srt 边界存在 ≤122ms 有界漂移（不累积、音频由 check_sync 权威把关）——**已知公差，不是缺陷**；若未来漂移越过 ±0.5s 或开始累积，升级为 `脚本bug` 类登记并修烧录引擎。
