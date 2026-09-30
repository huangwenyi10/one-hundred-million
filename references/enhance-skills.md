# 视频质量增强技能清单与接入（enhance-skills）

> 本文档管理 `one-hundred-million` 短视频管线可接入的**质量增强技能**（封面 / 素材清晰度与去侵权 / 动效 / 画质）。
> **定位**：在既有 9 步管线与全部硬约束之上叠加的可选增强层——**不替代任何硬约束，不阻塞生产**；无依赖/无凭据时一律回退既有路径。

---

## 0. 接入原则

1. 只接入**可用**（无缺失依赖 / 凭据）且**安全**（已评估：无未授权网络外发 / 命令执行 / 凭据访问）的技能。
2. 每个增强都**有回落**：离线、失败、未授权时不阻塞主流程。
3. **不破坏**既有硬约束：左上角水印安全区（x 0~25% × y 0~15%）、底部字幕带（y 88%~95%）、训练营主题色、去侵权、画面无训练营标识 / 期号。

---

## 1. 已接入

### 1.1 `video-cover-designer`（封面方案生成）
- **能力**：封面文案提取、多种封面方案（文字型 / 人物型 / 对比型等）、爆款元素分析、多平台尺寸与风格建议（抖音 / 快手 / 视频号 / B站）。
- **安全评估**：纯本地 Python（仅 `import random` + 静态配置），**无网络、无命令执行、无凭据访问** → 安全。
- **调用**：`python3 ~/.workbuddy/skills/video-cover-designer/scripts/cover_designer.py`（用法见其 `SKILL.md`）。
- **接入点**：**Step 6 / 封面设计**（前 3 秒封面 + 平台封面图）。**必须叠加本技能硬约束**：封面主题色按「训练营主题色」表用同色系渐变；封面**不得出现训练营名称 / 期号 / 系列名**（固定规范第 14 条 + 封面图文字扫描）；CTA 站内收敛（第 30 条）。

### 1.2 `buddy-image-processing`（图片去水印 / 增强 / 修复）—— 内置，已可用
- **能力**：文字 / 水印去除、通用增强、人像美化、图像修复、抠图。
- **接入点**：**Step 2 第 5 条 素材去侵权**——当「裁切 / 覆盖 / PIL 修复」无法干净去除第三方水印、版权角标、无关 Logo、网址域名时，用本技能做 AI 文字 / 水印擦除或修复后再入画；也可用于提升官方架构图 / 截图的清晰度。
- **边界**：只处理素材图片，**不改变**「资产原图 > 官网官方图 > HTML/CSS 重绘」优先级链；处理结果仍须人工确认无残留标识。

### 1.3 `byted-mediakit-video`（火山引擎 MediaKit）—— CLI 已就绪 · AI 能力待 API Key

> **状态**：CLI 已安装并验证通过；**全部 AI 能力为 cloud-only，待 `MEDIAKIT_API_KEY`**。
>
> **决策（2026-09-30，作者确认）**：**暂不启用**——该服务为火山引擎付费云服务（需实名账号 + 预充值），
> 收益（AI 去水印 / 硬字幕擦除 / 画质评分）暂不足以覆盖开通成本与素材外发风险。
> **本条为已完结的评估结论；除非作者主动提出开通，否则不要再重复调研或安装。**
> 日常质量增强继续走 §1.1 `video-cover-designer` + §1.2 `buddy-image-processing`（零成本、零依赖、本地）。

**已完成安装（2026-09-30 实测）**

| 项 | 值 |
|---|---|
| CLI 包 | `@volcengine/mediakit-cli@0.2.1`（MIT，零传递依赖） |
| 安装位置 | `~/.workbuddy/binaries/node/workspace/node_modules/@volcengine/mediakit-cli` |
| 真实二进制 | `bin/mediakit-cli`（Go，darwin/amd64，3,081,431 B） |
| 校验 | SHA256 `ffda2579efa0133bc73fd662c944476546d2ac6bfa311b3b0c44bc6e3f854197` —— **与官方 `checksums.txt` 逐字节一致** |
| PATH | `~/.workbuddy/binaries/node/versions/22.22.2-3/bin/mediakit-cli`（软链到包内 `scripts/run.js`） |
| 验证 | `mediakit-cli --version` → `mediakit-cli version 0.2.1` |
| 技能包 | `~/.workbuddy/skills/byted-mediakit-video/`（`SKILL.md` + `reference/` 15 篇） |
| `doctor` 实况 | `cloud_ready: false`（无 Key）、`local_ready: true`、ffmpeg/ffprobe ok |

**安装踩坑（本环境网络策略，可复用）**

`github.com/.../releases/download/...` **直连被阻断**（`http=000` 且挂起）。可用通道是
**GitHub API 资产端点**（302 跳转 `release-assets.githubusercontent.com`，实测可通）：

```bash
AID=$(curl -s "https://api.github.com/repos/volcengine/mediakit-cli/releases/tags/v0.2.1" \
  | python3 -c "import sys,json;[print(a['id']) for a in json.load(sys.stdin)['assets'] if a['name']=='mediakit-cli_0.2.1_darwin_amd64.tar.gz']")
curl -sL -H "Accept: application/octet-stream" -o mk.tar.gz \
  "https://api.github.com/repos/volcengine/mediakit-cli/releases/assets/$AID"
shasum -a 256 mk.tar.gz   # 必须等于官方 checksums.txt 的值
```

> 资产文件名用**裸版本号** `0.2.1`，**tag 才带 `v`**（`.../download/v0.2.1/mediakit-cli_0.2.1_...`）——写错会 404。
> npm 包本体只是启动器：`postinstall` 会去 GitHub Releases 拉二进制，`scripts/run.js` 在缺 `bin/` 时自动补拉。

**能力矩阵（2026-09-30 实测 CLI「支持模式」字段，非文档推测）**

| 能力 | 域 | 支持模式 | 对本管线价值 |
|---|---|---|---|
| `image erase-image` | image | **Cloud** | AI 擦除水印 / 角标 / Logo —— 处理的**最强手段** |
| `image enhance-image` | image | **Cloud** | 素材清晰度提升 |
| `image evaluate-image-quality` | image | **Cloud** | 15 维画质评分（vqscore/noise/blur/blockiness…）→ 可做**素材门禁** |
| `video erase-video-subtitle` / `-pro` | video | **Cloud** | 硬字幕无痕擦除 |
| `video enhance-video` / `-fast` / `-generative` | video | **Cloud** | 画质增强 / 超分 / 扩散修复 |
| `video assess-video-quality` | video | **Cloud** | VQScore 画质评分 → 可做**成片门禁** |
| `video extract-frames` / `probe-video-metadata` / `segment-scenes` / `asr-subtitles` / `video-ocr` / 抠像 | video | **Cloud** | 拆帧 / 元数据 / 场景切分 / 字幕 / OCR / 抠像 |
| `editing` 域（23 项：裁剪 / 拼接 / 合成…） | editing | **Local（FFmpeg）** | **与既有 `scripts/video_tool.py` 重叠，无增量** |

> **反误导要点**：全部 AI 能力均为 **cloud-only** —— **不存在「离线跑 `erase-image`」这条路径**。
> `doctor` 的 `local_ready: true` 只覆盖 FFmpeg 剪辑，**不覆盖任何 AI 增强**。
> 另：实际能力数远超技能文档列的 14 项（`video` 域 30 项 / `image` 域 21 项）。

**唯一剩余阻塞：`MEDIAKIT_API_KEY`**

- 获取：火山引擎控制台 → <https://console.volcengine.com/imp/ai-mediakit/settings>（单一 API Key，无需 OAuth / STS / IAM）
- 计费：火山引擎「智能处理 IMP」为**充值 / 按量计费**的付费云服务（需实名账号 + 预充值）——**不对免费额度作任何承诺**
- 启用（拿到 Key 后两条命令）：

```bash
MEDIAKIT_SURFACE=skill MEDIAKIT_RUNTIME=workbuddy \
  mediakit-cli init --mode cloud-first --api-key <your-api-key> --yes
mediakit-cli doctor          # 期望 cloud_ready: true
```

**调用形态（cloud 异步 + 轮询）**

```bash
MEDIAKIT_SURFACE=skill mediakit-cli video enhance-video \
  --video-url ./in.mp4 --scene ugc --tool-version standard --resolution 1080p
mediakit-cli shared query-task --task-id <task_id>     # 轮询取终态
```

> `MEDIAKIT_SURFACE=skill` 是技能调用时的**强制要求**（见其 `reference/shared.md`），不得依赖用户既有环境变量。

**无 Key 时的行为（硬约束）**：**一律回退**既有路径（`buddy-image-processing` 去水印 / `PIL` 修复 / 裁切覆盖），
**不在缺凭据时发起云端调用** —— 避免挂起、误报与无谓外发。

---

## 2. 候选清单（需前置条件 · 暂不默认接入）

| 技能 | 能力 | 前置条件 | 评估 |
|---|---|---|---|
| `byted-mediakit-video` | 画质增强 / 硬字幕擦除 / 抠像 / 画质评分 / OCR 等（`video` 30 项 + `image` 21 项） | **CLI 已装好并验证**；仅差 `MEDIAKIT_API_KEY` | **见上文 §1.3**（安装、能力矩阵、启用命令、回退规则均已实测固化） |
| `xeon-smartupscale` | 本地 CPU 视频超分（Lanczos 预缩放 + ETDS 2x OpenVINO 模型，任意目标分辨率） | 需下载 OpenVINO 模型（`install.sh`，CPU 推理） | 本管线原生 1080p 矢量渲染，超分价值有限；仅对外部低清素材增强有意义 |
| `video-deconstruct`（叙事式拆解，dl≈2414） / `lingyi-wx-video-decomposer-plus`（付费） | 爆款拆解（十章节叙事式 / 六维评分），反哺选题、钩子与节奏 | `video-deconstruct` 需 `STEP_API_KEY`（StepFun 云，付费）；另一款本身付费 | 服务于**内容质量**反哺（对应 `craft-quality.md` §8「定期拆解头部账号爆款手法」）；需凭据，登记备用 |
| `video-auto-editor-skill`（dl≈15882） / `doorstep-video-editor` / `ai-video-clipper` 等剪辑类 | 剪辑 / 字幕 / 拼接 / 变速 / 水印 / 音频 | 多数零依赖但功能与现有管线重叠 | 现有 `scripts/video_tool.py` + `scripts/compose_motion.py` + `scripts/gen_sync_subs.py` 已覆盖，**不重复接入** |
| `remotion-video-toolkit`（**本地已可用**） | 程序化视频 / 动效（React + Remotion） | 无 | 可作为**关键页动效**的高质量替代，与 `scripts/render_animated.js`（CSS 动画逐帧）**二选一**；需重建渲染管线，工作量中等 |
| `3D模型与视频特效`（**本地已可用**） | 3D 模型 / 模板视频特效（部分需云积分） | 无 | 视觉特效增强；须遵守「克制」动效纪律（单页 ≤2 处、不抢讲解） |

---

## 3. 选用决策树

- 要**封面方案 / 爆款元素分析** → `video-cover-designer`（已接入）。
- 要**去除素材水印 / 角标 / 增强清晰度**（图片） → `buddy-image-processing`（已可用）。
- 要**源视频画质增强 / 硬字幕擦除 / 素材 AI 去水印 / 画质评分** → `byted-mediakit-video`（**CLI 已就绪**，仅差 `MEDIAKIT_API_KEY`；无 Key 一律回退 §1.2 与既有路径）。
- 要**内容选题 / 钩子反哺** → 爆款拆解类（需凭据）。
- 要**更高质量的动效** → `remotion-video-toolkit`（或既有 `render_animated.js`）。

---

## 4. 边界与自检

- 增强技能一律**不接触**既有硬约束（水印区 / 字幕带 / 主题色 / 去侵权 / 去训练营标识）。
- 需要外部凭据 / CLI 的技能**未就绪即回退**既有路径。
- `byted-mediakit-video` 的 AI 能力**全部 cloud-only**：**无 `MEDIAKIT_API_KEY` 时不发起调用**，直接回退（§1.3）。
- 云端处理会把**素材本身**上传至火山引擎 —— 涉及**书本原图 / 未公开素材**时，先确认能否外发，否则走本地路径。
- 启用时机由 **Step 2（素材）** 与 **Step 6（封面 / 合成）** 按需判断，**不默认全量启用**（避免动效过载与无谓外发）。
- 合成前自检：封面无训练营标识、素材无残留第三方水印、动效未侵入水印区 / 字幕带。
