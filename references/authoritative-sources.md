# 权威来源清单与核验 SOP（固定规范第 7 条配套 · 强制）

> 定位：回答「内容凭什么这么讲」。国内与国外权威渠道**同等有效**，凡是能核到一手官方原文的主题，都必须核到一手——**语言与地域不构成取材边界**，英文一手官方内容优先于任何中文二手转述。**云厂商官方文档（阿里云 / 腾讯云 / 百度智能云 / 华为云 / 火山引擎 / AWS / Google Cloud / Azure）是 L1 一手来源、云与大数据类主题的取材主力。**
> 使用位置：Step 0 第 5 项「事实可核实性」判断、Step 1 第 1 条双重来源获取素材、Step 1 第 1.1 条国外权威来源、Quality Gates。
> 铁律不变：**正确性优先于完整性**，拿不准就删或留白，禁止"看起来合理"的推断性编写。

---

## 一、来源优先级（从高到低）

| 级别 | 来源类型 | 采信规则 |
|------|----------|----------|
| **L1 · 一手官方** | 项目/产品**官方网站与官方文档**（英文原版站与中文站同等，冲突以英文原版/最新版为准）、官方博客、Release Notes / CHANGELOG、官方 GitHub 仓库（README / `docs/` / releases / 官方 benchmark）、官方白皮书 PDF、官方大会 slides（KubeCon / re:Invent / SIGMOD 等）、**国内外云厂商官方文档与官方最佳实践（阿里云 / 腾讯云 / 百度智能云 / 华为云 / 火山引擎 / AWS / Google Cloud / Azure，见 §二「云厂商」）** | **可直接采信**，是数据与结论的第一依据 |
| **L2 · 标准规范机构** | IETF RFC、W3C / WHATWG、ECMA（如 ECMA-262）、ISO / IEEE SA / ANSI、NIST（含 NVD）、OWASP、Unicode Consortium、TPC / SPEC 官方榜单 | **可直接采信**（协议、标准、规范类结论的唯一权威） |
| **L3 · 学术论文** | 原论文优先：ACM DL、IEEE Xplore、Springer、ScienceDirect、**USENIX（ATC/FAST/OSDI/NSDI，官网开放 PDF）**、**VLDB Endowment（vldb.org/pvldb）**、CIDR、arXiv；检索用 DBLP / Google Scholar / Semantic Scholar | **可直接采信**，但须带实验条件（数据集、规模、硬件、版本） |
| **L4 · 权威技术媒体/机构观点** | ACM Queue、IEEE Spectrum、Communications of the ACM、The New Stack、InfoWorld、InfoQ 英文站、Ars Technica、Stack Overflow Blog、Red Hat Blog、ThoughtWorks Technology Radar、各大厂工程博客（Netflix / Cloudflare / Meta Engineering / Uber / Airbnb / Stripe / LinkedIn Engineering / AWS / GCP / Azure） | **只作线索与交叉验证**，单一 L4 来源不得单独支撑性能数字 |
| **L5 · 社区/聚合** | Hacker News、Reddit、知乎、公众号、CSDN、博客园、个人博客 | **只当线索，一律回溯 L1–L3 原文确认**；直接采信 = 违规 |

**判定口诀**：**能找到官方，就不用媒体；能找到论文原文，就不用解读稿；中文二手转述国外内容，必须回溯英文一手原文。**

---

## 二、权威来源速查（按主题对号入座，国内外同等）

> 清单是**思路提示，不是边界**（同「示例 ≠ 固定边界」原则）。拿得准的一手源都在允许范围内，未列出的按 §一 的级别判定即可。

**云厂商官方文档（L1 · 国内外同等 · 云/大数据/AI 主题的取材主力）**
- **国内云厂商**：
  - **阿里云**：阿里云文档 `help.aliyun.com`（产品文档 / API / 官方最佳实践），官方公告与官方技术博客；阿里云开发者社区的**官方账号**内容
  - **腾讯云**：腾讯云文档 `cloud.tencent.com/document`（产品文档 / API / 最佳实践），官方公告与技术实践文章（官方署名）
  - **百度智能云**：百度智能云文档 `cloud.baidu.com/doc`（含 AI / 大模型千帆相关官方文档）
  - **华为云**：华为云帮助中心 `support.huaweicloud.com`；**火山引擎**：`www.volcengine.com/docs`（含字节系大数据/AI 产品文档）
- **国外云厂商**：
  - **AWS**：AWS Documentation `docs.aws.amazon.com` + 官方博客 `aws.amazon.com/blogs`（含中文站 `/cn/blogs`）+ re:Invent 官方 slides/录播
  - **Google Cloud**：`cloud.google.com/docs` + 官方博客 `cloud.google.com/blog`
  - **Microsoft Azure**：Microsoft Learn `learn.microsoft.com/azure` + Azure 官方博客
- **取材边界（防坑，强制）**：①**官方产品文档 / 技术规格 / API 文档 / 官方署名的最佳实践 = L1 可采信**；②**产品营销页上的性能对比数字（自家 vs 竞品）≠ L1**——属厂商宣传，按 L4 处理：口播须表述「据 XX 官方公布的测试…」并带测试条件，最好再找一个独立来源交叉；③**云厂商开发者社区的第三方作者投稿 ≠ 官方内容**（阿里云开发者社区 / 腾讯云开发者社区大量是个人投稿）——按 L4/L5 处理，须回溯官方文档确认；④跨厂商选型对比类结论，不得只引单一厂商一方的 benchmark。

**基础设施 / 数据库 / 大数据**
- Apache 各项目官方站（`*.apache.org`，含 Doris / Flink / Spark / Kafka / Hadoop / Iceberg / Paimon）
- CNCF 项目官方站（Kubernetes / Prometheus / etcd / Envoy / TiKV 等，含 `cncf.io` 官方博客与 landscape）
- 数据库官方 docs：PostgreSQL、MySQL、Oracle、SQL Server、MongoDB、Redis、ClickHouse、StarRocks、Elasticsearch、Snowflake、Databricks
- 论文/会议：SIGMOD、VLDB、ICDE、CIDR、USENIX FAST/ATC/OSDI（系统/存储/数据库类硬结论的第一手出处）

**云原生 / 架构 / 运维**
- 云厂商官方 docs 与博客：AWS（docs + `aws.amazon.com/blogs`）、Google Cloud（cloud.google.com/blog）、Azure（Microsoft Learn / Azure Blog）
- 标准与规范：CNCF 官方规范、OpenTelemetry 官方 spec、IETF RFC、OpenAPI/Swagger 官方规范
- 厂商工程博客：Netflix TechBlog、Cloudflare Blog、Meta Engineering、Uber Engineering、LinkedIn Engineering、Stripe Blog、Airbnb Engineering

**AI / 机器学习**
- 官方：OpenAI、Anthropic、Google DeepMind、Meta AI、Hugging Face（docs + blog）、PyTorch、TensorFlow、NVIDIA（docs + developer blog）
- 论文：arXiv、NeurIPS / ICML / ICLR / ACL / CVPR 官方论文集（Proceedings 页）
- 评测基准：官方 leaderboard 页面（须注明版本与评测日期）

**前端 / 语言 / 框架**
- 官方 docs：MDN（Web 标准的权威）、WHATWG / W3C 规范、TC39（ECMAScript 提案与规范）、React、Vue、Angular、Svelte、Node.js、Deno、TypeScript
- 语言官方：Python、Go、Rust、Java（OpenJDK / JEP）、Kotlin、Swift
- 规范：ECMA-262、W3C CSS/WAI 规范

**安全**
- OWASP（Top 10 / ASVS / Cheat Sheet）、NIST（SP 800 系列）、CVE/NVD、CWE、各大厂 Security Blog

**产品 / 管理 / 软技能**
- 一手研究：Harvard Business Review、MIT Sloan Management Review、McKinsey / BCG / Bain 官方洞察（机构观点须注明出处）
- 经典原著与作者官方站点（读书训练营直接以书为一手源）
- 企业官方公布的复盘/工程文化文档（如 Google re:Work、Amazon Leadership Principles 官方页）

**性能与基准数据（特殊：必须带条件）**
- 官方 benchmark 仓库与官方公布的测试报告；标准化榜单 TPC（`tpc.org`）、SPEC（`spec.org`）
- **禁止脱离测试条件报数字**：引用时必须带上「版本 + 规模 + 硬件/节点 + 数据集 + 日期」。

---

## 三、检索与获取方式

1. **中英双语检索（强制）**：中文关键词 + 英文原名并行，否则大量一手资料搜不到。
   - 例：`Doris 读写分离` → 同时搜 `Apache Doris compute-storage separation`
   - 例：`布隆过滤器 误判率` → 同时搜 `bloom filter false positive rate`
   - 例：`缓存雪崩` → 同时搜 `cache stampede thundering herd`
2. **site 限定提精度**：`site:help.aliyun.com ...`、`site:cloud.tencent.com ...`、`site:cloud.baidu.com ...`、`site:docs.aws.amazon.com ...`、`site:apache.org doris ...`、`site:kubernetes.io ...`、`site:arxiv.org ...`。
3. **云产品主题优先打官方文档**：凡主题落在某云厂商产品上（RDS / 数据库 / 大数据 / AI / 云原生托管服务…），先查该厂商官方文档的产品页 + 最佳实践页，再补社区与论文——不要反过来从博客倒推官方参数。
3. **定位 → 抓原文**：WebSearch 定位到权威页面 → WebFetch 抓正文；抓不到就用官方仓库原始文档（`raw.githubusercontent.com/<org>/<repo>/<branch>/docs/...`）或官方 PDF/白皮书。
4. **官方中文站 vs 英文站**：二者都是 L1。中英**冲突时以英文原版/最新版本为准**（中文翻译常滞后），并在产物日志中记一笔差异。
5. **版本意识**：所有结论须锁定版本（如 "Kubernetes 1.30 起 …"、"Doris 2.1 官方文档"），跨版本结论不得混用。

---

## 四、不可访问时的降级链（不阻塞、不降标准）

国外站点偶发超时/不可达时，按序降级，**不得因此编造或跳过核验**：

```
1. 官方站点 / 官方文档（英文原版优先）
      ↓ 不可达
2. 官方 GitHub 仓库的 docs / raw 原始文档 / releases notes
      ↓ 不可达
3. 官方 PDF 白皮书 / 官方大会 slides / 官方录播
      ↓ 不可达
4. 官方镜像或官方在国内可访问的同源内容（须确认是官方发布）
      ↓ 不可达
5. 权威二手（L4，如 ACM Queue / IEEE Spectrum / InfoWorld / 大厂工程博客）
      —— 必须标注来源，且需第二个独立来源交叉确认
      ↓ 仍拿不到
6. 留白 / 删除该结论（正确性优先于完整性）
```

- **超时/不可达 ≠ 模型限流**，不切模型、不算 bug。最多重试 2 次，仍失败就走下一级。
- 走到第 5 级时，口播表述改为「**据 X 官方博客/某机构**的说法……」，不作普适断言。

---

## 五、采信与表述纪律

1. **多源交叉**：关键数据/性能倍数/结论，**至少两个独立权威来源一致**才作为普适结论；只有单一来源时，表述为「某官方/某论文指出……」并标注出处性质。
2. **数据带条件**：性能数字必须带「版本 + 规模 + 硬件/节点 + 数据集 + 时间」，缺条件即放弃该数字。
3. **英文素材的处理**：
   - 最终表达仍是**中文口语**（面向中文读者），不做翻译腔直译。
   - 专有名词、缩写保留英文原文，首次出现给中文 —— 与固定规范第 28 条「简写备注」联动（`缩写 = 英文全称 · 中文释义`）。
   - 示例：「TPC-H，也就是 TPC 组织定的一套决策支持类基准测试，说白了就是拿固定的 22 条分析型 SQL 跑分。」
4. **画面/口播不堆来源**：口播稿不念 URL；来源记录进 `build/sources.md`（一行一条：`结论 → 来源名 + URL + 版本/日期 + 级别 L1–L5`），供复盘与作者抽查。画面上只在需要时给一行极简出处（如「来源：Apache Doris 2.1 官方文档」）。
5. **禁止行为**：照抄中文二手稿的国外数据；只引数字不引条件；把社区讨论当官方结论；把厂商宣传稿当权威数据（宣传稿属 L4，需第三方或官方 benchmark 佐证）；**把云厂商开发者社区的第三方投稿当官方内容**（须认准官方署名/官方文档域名，否则回溯 L1 确认）。

---

## 六、自检清单（Step 1 交稿前）

- [ ] 每个关键数据/结论都能追到一个 L1–L3 的一手来源（名称 + URL + 版本/日期写在 `build/sources.md`）
- [ ] 中英文双语都检索过，英文一手原文已核（不是只看中文解读）
- [ ] **云产品主题已查过对应云厂商官方文档**（阿里云/腾讯云/百度智能云/华为云/火山引擎/AWS/GCP/Azure 的产品文档与最佳实践），不是只看个人博客
- [ ] 云厂商营销页性能对比数字未当 L1 使用（按 L4 处理且带测试条件、口播改「据 XX 官方公布的测试…」）
- [ ] 官方中文站与英文站冲突处，已按英文原版/最新版为准并记录
- [ ] 性能类数字全部带测试条件，缺条件的已删除
- [ ] 只有 L4 单一来源处，口播措辞已改为「据…指出」，未作普适断言
- [ ] 英文专有名词/缩写首次出现已配「全称 + 大白话」（第 28 条）
- [ ] 无任何仅凭社区/个人博客/记忆得出的结论
