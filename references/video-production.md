# 视频制作规范（配音 / 水印 / 字幕 / 封面 / 合成 / 平台规格）

所有命令依赖 ffmpeg（`brew install ffmpeg`）与 Python3。封装脚本：`scripts/video_tool.py`。

## 1. 帧导出（HTML PPT → PNG）

用无头 Chrome 将每页幻灯片导出为 1920×1080 PNG：

```bash
# 每页一个 URL（PPT 支持 ?page=N 直达），逐页截图
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless --disable-gpu --window-size=1920,1080 --screenshot=frames/slide01.png \
  "file:///path/to/ppt.html?page=1"
```

若 PPT 无翻页 URL，可在 HTML 中加 `?page=N` 支持（读取 location.search 显示对应 section）。**导出前强制扫描 PPT.html 全文**：用 grep 命中"以上就是今天""下期再见"等固定收尾句、以及训练营名称/期号（见固定规范第 14 条），命中立即删除对应元素再导帧——幻灯片画面文字同样受禁句与禁标识约束。

## 2. 配音

- **音色唯一标准：项目资产 `We-Media/声音模版.mp3`**（作者指定）。配音前先从资产下载该模板并 `ffprobe` 核验，试听确定音色基线（性别/年龄感/语速/语调）。
- 据此选择匹配的 TTS 音色（例：edge-tts，`edge-tts --voice <音色> --file script.txt --write-media voiceover.mp3 --write-subtitles subs.vtt`），生成后**与模板并排试听对比**，听感不一致必须更换音色重跑。
- **音色匹配客观验证（不能只凭感觉）**：用 `scripts/analyze_voice.py` 并排分析模板与候选配音，对比性别、F0 中位（偏差 ≤ ±20Hz）、语速（偏差 ≤ ±10 字/分）：
  ```bash
  python3 scripts/analyze_voice.py "assets/We-Media/声音模版.mp3" build/voiceover.mp3
  ```
  客观指标通过 + 试听听感一致才算匹配。模板可能是带 BGM 的样音：F0 分析先排除音乐低频段（60-80Hz 大量帧），以语音段为准；转写可能混入音乐内容，语速对比以语音为主。
- 模板缺失/损坏时询问作者提供地址（本地路径/资产/下载链接）；**禁止自行随意选音色**。
- 语速基线 240–280 字/分钟；拿到配音后用 `ffprobe -show_entries format=duration voiceover.mp3` 取实际时长。

**环境坑（踩过，务必注意）：**

1. **本机代理会导致 huggingface 模型下载 502**（`faster-whisper`/`whisper` 首次下载模型时）。解决：临时 unset 代理 + 走 HF 镜像 + 禁用 Xet：
   ```bash
   unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
   export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1
   ```
   （新版 huggingface_hub 默认走 Xet 协议，镜像不兼容会 401；`HF_HUB_DISABLE_XET=1` 强制走普通 HTTP。）
2. **edge-tts 装在受控 venv 里**，用 `python -m edge_tts` 调用（无独立可执行文件的环境）：
   ```bash
   python3 -m venv <venv_dir> && <venv_dir>/bin/pip install edge-tts numpy faster-whisper
   <venv_dir>/bin/python -m edge_tts --voice zh-CN-YunyangNeural --rate=-10% --file script.txt \
     --write-media voiceover.mp3 --write-subtitles subs.vtt
   ```
3. **TTS 长文本**：`--file` 读脚本文件（首行若为标题则不朗读，需跳过）；`--write-subtitles` 与配音同步产出 VTT，是字幕逐字一致的唯一可靠来源。

**分段 + 真实时间轴（强制，Step 3/5）**：成片字幕与画面切换时间轴必须来自配音真实音频，不得按字数比例估算。用 `scripts/gen_sync_subs.py` 把口播稿按幻灯片切 N 段，逐段 edge-tts（开启词级 boundary）TTS 并拼接为 `voiceover.mp3`，同时产出真实时间轴字幕 SRT 与 `segments_durations.json`（每页真实时长）。`segments_durations.json` 是画面停留与字幕时间的唯一来源；render 时第 k 页只在第 k 段配音期间显示。真人配音用 faster-whisper 词级时间戳做同样对齐。

## 3. 水印（仅左上角，全片唯一）

```bash
ffmpeg -i in.mp4 -vf "\
drawtext=text='作者：@Map':fontfile=/System/Library/Fonts/PingFang.ttc:\
fontsize=28:fontcolor=white@0.85:box=1:boxcolor=black@0.35:boxborderw=8:\
x=36:y=28" -c:a copy out.mp4
```

要求：不遮挡画面主体；竖屏版 y 安全距离相同、x=36。**全片任何位置只允许左上角这一处作者标识**——封面、正文、片尾、角标不得再出现作者名/账号信息（封面设计元素也不例外），避免水印重复。

## 4. 字幕（与声音逐字一致、与内容对齐，按时间轴出现/消失）

**强制要求：字幕 = 声音 = 内容，三方逐字一致。** 完整链路是「口播稿内容 → 配音朗读 → 字幕文本」，三者必须对得上：字幕文本 = 配音实际朗读的逐字文本（不是口播稿的复制粘贴），配音不得擅自增删改口播稿内容；改稿后必须重配音并同步字幕。

- TTS 配音：用 `scripts/gen_sync_subs.py` 逐段 edge-tts（带词级 boundary）产出，天然逐字一致且时间轴来自真实音频（**不要**再拿口播稿单独按字数比例生成字幕时间轴——那是字幕与声音错位的头号根因）。
- 作者配音：用 whisper（`pip install openai-whisper; whisper voiceover.mp3 --language zh --initial_prompt "简体中文字幕"`）识别后**逐字校对**，以配音实际读出的内容为准。

```bash
# edge-tts：配音 + 逐字字幕一次性产出
edge-tts --voice <音色> --file script.txt \
  --write-media voiceover.mp3 --write-subtitles subs.vtt
```

**显示规则（时间轴同步）**：每条字幕有自己的 start/end，与音频 cue 严格对齐——到点显示、到点消失，跟随声音逐句切换；**禁止**把字幕固定在画面底部整帧常驻。

**位置与不遮挡（强制）**：字幕条带固定渲染在画面底部安全区（y ≈ 85%~95% 高度，单行），**字幕以下 / 字幕带之内不得放任何相关内容**——幻灯片标题/要点/图示主体、封面标题、卡片文字等都不得落入该区域，否则字幕出现即盖住内容。写幻灯片排版时就为底部预留字幕专用区（约纵向 12%~15%，内容主体收在画面顶部约 85% 以内，绝不延伸进字幕带，见 SKILL.md 固定规范第 15 条）；合成后抽帧校验字幕带区域无任何画面内容，发现内容侵入立即调整（内容上移/缩小），不得带遮挡交付。

**末尾句号去除**：每条字幕（cue）文本末尾的句号 `。` 必须去掉（行内句号保留；问号/感叹号等语气标点按配音保留）。TTS 产出的 VTT/SRT 先清洗再用：

```bash
python3 video_tool.py sub_clean --input subs.vtt --out subs_clean.vtt
```

（`sub_clean` 逐行去除 cue 文本末尾的 `。`；时间行、序号行不受影响。whisper 识别的人工字幕在校对时同步删除末尾句号。）

**烧录两种方式**：

1. ffmpeg 带 libass（`ffmpeg -filters | grep ass` 有输出）：`ffmpeg -i in.mp4 -vf "ass=subs.ass" -c:a copy out.mp4`（字幕文件路径写绝对路径）。
2. **无 libass 的兜底（PIL 逐帧绘制）**：按 cue 时间把字幕画到对应的帧上、过 cue 即擦除/换下一条——即"这一帧此刻在播什么，帧上就显示什么"，保证成片中字幕随时间出现/消失，而不是每帧固定一句。示例：把 VTT cue 的 start/end 映射到帧序号，只对时间落在 cue 区间内的帧绘制该句。

**单行显示 + 位置固定（强制）**：每条字幕必须是一行，**禁止折行成多行**；字幕条带固定渲染在画面底部安全区（y ≈ 88%~95%，不超出该区域），**不遮挡任何画面内容**（见上"位置与不遮挡"）。普通句白色 `&H00FFFFFF`、字号 52；重点句（数据/结论/术语）品牌色 `&H00A5C8FF`、加粗、字号 62，可加轻微描边。单行放不下时：先按比例缩小字号适配单行（下限 40，保证可读）；缩到下限仍放不下，则将该 cue 按配音实际停顿拆成两条相邻 cue 分时显示（拆 cue 不改变逐字一致，只让显示时间片变短）。PIL 逐帧绘制用单行不折行模式；ASS 用 `{\q2}`（不自动换行），禁止依赖自动换行把一条字幕拆成多行。ASS 模板片段：

```ass
Style: Normal,PingFang SC,52,&H00FFFFFF,&H000000FF,&H40000000,&H40000000,0,0,0,0,100,100,0,0,1,2,0,2,30,30,40,1
Style: Key,   PingFang SC,62,&H00A5C8FF,&H000000FF,&H40000000,&H40000000,0,0,0,0,100,100,0,0,1,3,0,2,30,30,40,1
```

## 5. 封面（前 3 秒，可直接使用）

封面是一帧独立画面，配色按训练营类型取色（完整主题色表见 SKILL.md「训练营主题色」章节），规则：

- 背景：该训练营的同色系渐变（深底 → 主色），如架构师训练营 `#00572E → #00C853`。
- 大标题：纯白（黄/橙系训练营必须深底白字，保证对比度），≤20 字，占画面 1/3。
- 数字/关键句/装饰元素：用该训练营高亮色，如大数据训练营 `#4D8DFF`。
- 同一支视频内不得混入其他训练营主色。

封面必须包含：大标题（≤20 字，占画面 1/3）、一句副标题钩子。**封面不得出现训练营名称/期号等标识（强制）**——如"架构师训练营""第 1 期"等字样/徽章一律不出现（见 SKILL.md 固定规范第 14 条）；**封面不单独放 `作者：@Map`**——作者标识由左上角水印统一承担（见 §3，全片只此一处）。导出 PNG 后拼在片头 3 秒：

```bash
ffmpeg -loop 1 -t 3 -i cover.png -i body.mp4 -filter_complex \
"[0:v]scale=1920:1080,format=yuv420p[c];[c][1:v]concat=n=2:v=1:a=0" \
-c:v libx264 -r 30 out.mp4
```

## 6. 合成（帧 + 配音）

```bash
# 帧目录 → 视频，每帧停留时长按配音段落分配，总时长 = 配音时长
ffmpeg -framerate 1/8 -i frames/slide%02d.png -i voiceover.mp3 \
  -c:v libx264 -pix_fmt yuv420p -tune stillimage -c:a aac -shortest body.mp4
```

帧停留不均等时，先为每帧生成各自时长的单段视频再 concat；每帧时长取自 `segments_durations.json`（分段真实配音时长，与字幕同一时间轴）。最终顺序：封面段 + 正文 + 配音 + 字幕 + 水印。

## 7. 平台输出规格速查

**一律默认输出 16:9 横屏母版（1920×1080），不因目标平台自动改变画幅**；下表仅为各平台的发布规格参考，仅当作者明确指定其他格式（如明确要求 9:16 竖屏）时才从母版派生对应版本。

| 平台 | 画幅 | 分辨率 | 时长 | 备注 |
|------|------|--------|------|------|
| 抖音 | 9:16 竖屏 | 1080×1920 | ≤15min | 前3s决定完播，封面必须有标题 |
| 快手 | 9:16 竖屏 | 1080×1920 | ≤15min | 同抖音 |
| 小红书 | 3:4 或 9:16 | 1080×1440/1920 | ≤30min | 封面图单独可发布 |
| 微信公众号（视频号） | 9:16 或 16:9 | 1080×1920/1080P | ≤60min | 横竖屏均支持 |
| YouTube | 16:9 横屏 | 1920×1080 | 不限 | 建议横屏，章节时间轴 |

竖屏转换：16:9 帧居中 + 上下深色延展，或重排 HTML 为竖屏版重新导出（优先后者，字号需放大 1.5×）。转换命令：

```bash
ffmpeg -i landscape.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=decrease,\
pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x0B1026" -c:a copy portrait.mp4
```

同一素材多平台发布时：默认只做 16:9 横屏母版；作者明确要求竖屏时，才在母版基础上派生竖屏版，字幕与水印在两版中各自校准位置。
