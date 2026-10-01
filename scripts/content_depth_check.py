#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""content_depth_check.py -- 口播稿内容深度自检（one-hundred-million · 固定规范第 31 条②配套）

把「讲透闭环」与「实战落地」从自觉遵守变成**确定性门禁**。
对**已定稿口播稿**做本地扫描，输出：讲透闭环五段覆盖 / 实战四形态命中 /
空转信号（蜻蜓点水反模式）/ 档位判定 / 修改建议。

判定阈值来自 47 份真实历史稿件的实测分布（2026-10-01 校准），非拍脑袋：
  量化数据点密度   p25=0.2  中位=0.8  p75=3.5   （个/千字）
  代码命令片段     中位=0    p75=0            （仅 6/47 份 ≥1）
  编号步骤         中位=0    p75=2
  最长无量化区间   中位=1453 p75=5265         （字）
  无原理结论句     中位=1    p75=2

用法：
  python3 content_depth_check.py <口播稿.txt> [--camp <训练营>] [--json] [--no-fail]
  --camp 读书训练营  读书营豁免「代码/命令」强制（按第 31 条②末段）
  --no-fail          只报告，不改退出码（自动化容错）
退出码：0 = PASS/WARN；1 = BLOCK；2 = 参数/文件错误
"""
import argparse
import json
import os
import re
import sys

# ---------- 信号词典（严格形态，避免泛动词误报） ----------

NUM = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|％|倍|毫秒|ms|秒|分钟|小时|天|周|个月|月|年|"
    r"GB|TB|MB|KB|QPS|TPS|IOPS|元|美元|美金|块|人|条|次|台|核|行|个))"
    r"|百分之[一二三四五六七八九十百零几多]+"
    r"|(?:翻了?|降了?|省了?|涨了?)\d+"
)

CODE = re.compile(
    r"--[a-zA-Z][\w-]{1,}"                      # 命令行参数
    r"|`[^`\n]{2,}`"                            # 行内代码
    r"|[A-Za-z_][\w-]*\.(?:py|json|sh|sql|ya?ml|js|ts|conf|ini|log|html|md|csv|parquet)\b"
    r"|\b(?:SELECT|CREATE\s+TABLE|INSERT\s+INTO|EXPLAIN|ALTER\s+TABLE)\b"
    r"|\b(?:docker|kubectl|git|npm|pnpm|pip|curl|ssh|grep|awk|sed|systemctl|psql|redis-cli)\s+\w+"
    r"|\b\w+\s*[:=]\s*[\w.\-]+"                 # 配置项 key: value
    r"|\b\w+\.\w+\(\)"                          # 函数调用
    r"|\{\s*\w+\s*\}"                           # 模板占位
    r"|[A-Za-z_][\w-]*\s*=\s*[\w'\"]"           # 赋值
)

STEP = re.compile(r"第[一二三四五六七八九十\d]+步|\d[.、]\s?")

REASON = re.compile(r"因为|之所以|原因是|本质原因|机制是|原理是|根源|代价|导致|为什么会")

DEFINE = re.compile(r"说白了|指的是|意思是|本质是|可以理解为|全称|叫作|也就是说")

CONCLUDE = re.compile(r"建议|最佳实践|应该|一定要|记住|核心思路是|原则是|关键在|诀窍是")

PITFALL = re.compile(r"坑|翻车|踩雷|踩过|事故|故障|不适用|边界|副作用|误区|反例|例外|注意了|别急着")

TOOL_OPS = re.compile(r"控制台|控制面板|配置页|命令行|终端|截图|benchmark|dashboard", re.I)

FUZZY = re.compile(r"某大厂|某公司|某电商|某互联网公司|某头部|某知名企业|某平台|某团队")

ABSTRACT = re.compile(r"能力|体系|机制|维度|方法论|思维|范式|闭环|抓手|赋能|对齐|沉淀|拉通|"
                      r"性(?=[，。、的地])|化(?=[，。、的地])")

ENTITIES = [
    # 大厂 / 互联网
    "阿里", "腾讯", "字节", "抖音", "美团", "百度", "京东", "拼多多", "网易", "快手",
    "滴滴", "携程", "小红书", "B站", "哔哩哔哩", "华为", "小米", "OPPO", "vivo",
    "Google", "谷歌", "Meta", "Facebook", "Amazon", "亚马逊", "微软", "Microsoft",
    "Apple", "Netflix", "Uber", "Airbnb", "Twitter", "Cloudflare", "GitHub",
    "OpenAI", "Anthropic", "NVIDIA", "英伟达", "Intel", "AMD", "AWS", "Azure",
    # 基础设施 / 中间件 / 数据库
    "MySQL", "PostgreSQL", "Redis", "Kafka", "RocketMQ", "RabbitMQ", "Elasticsearch",
    "ClickHouse", "Doris", "StarRocks", "Hive", "Spark", "Flink", "Presto", "Trino",
    "Hadoop", "HBase", "MongoDB", "TiDB", "OceanBase", "Nginx", "Kubernetes", "K8s",
    "Docker", "Linux", "Chrome", "Firefox", "Safari", "V8", "JVM", "Spring",
    "React", "Vue", "Node.js", "Webpack", "Vite", "Python", "Java", "Golang", "Rust",
    "WASM", "WebAssembly", "gRPC", "GraphQL", "Prometheus", "Grafana", "Jaeger",
    "LangChain", "LlamaIndex", "Milvus", "FAISS", "Qdrant", "Pinecone",
    # 非技术行业（软技能 / 产品 / 管理类常引用的具名案例）
    "星巴克", "宜家", "IKEA", "优衣库", "麦当劳", "肯德基", "可口可乐", "百事",
    "耐克", "Nike", "沃尔玛", "Costco", "好市多", "宝洁", "欧莱雅", "海尔",
    "比亚迪", "蔚来", "理想", "小鹏", "特斯拉", "Tesla", "SpaceX", "波音",
    "麦肯锡", "波士顿咨询", "贝恩", "德勤", "普华永道", "安永", "毕马威",
    "海底捞", "胖东来", "名创优品", "瑞幸", "蜜雪冰城", "农夫山泉", "元气森林",
]
VERSION = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")

BUCKETS = [
    ("S 档", 0, 450, 800),
    ("M 档", 450, 1500, 1500),
    ("L 档", 1500, 9000, 3000),
    ("读书长篇", 9000, 10 ** 9, 3500),
]


def read_script(path):
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def split_sents(text):
    return [s.strip() for s in re.split(r"[。！？!?\n]", text) if len(s.strip()) > 3]


def analyze(text, camp):
    n = len(text)
    per_k = max(n, 1) / 1000.0
    sents = split_sents(text)

    nums = NUM.findall(text)
    codes = CODE.findall(text)
    steps = STEP.findall(text)
    reasons = REASON.findall(text)
    defines = DEFINE.findall(text)
    pitfalls = PITFALL.findall(text)
    tools = TOOL_OPS.findall(text)
    fuzzy = FUZZY.findall(text)
    ents = [e for e in ENTITIES if e in text]
    vers = VERSION.findall(text)

    # 最长无量化区间（空讲段）
    longest = cur = 0
    longest_at = 0
    for i, s in enumerate(sents):
        if NUM.search(s):
            cur = 0
        else:
            cur += len(s)
        if cur > longest:
            longest, longest_at = cur, i

    # 无原理结论句：给结论但前后无原因解释
    bare = []
    for i, s in enumerate(sents):
        if CONCLUDE.search(s):
            ctx = "".join(sents[max(0, i - 2):i + 3])
            if not REASON.search(ctx):
                bare.append(s[:40])

    # 档位
    tier, lo, hi, gap_limit = "M 档", 450, 1500, 1500
    for name, a, b, gl in BUCKETS:
        if a <= n < b:
            tier, lo, hi, gap_limit = name, a, b, gl
            break

    is_book = any(k in (camp or "") for k in ("读书", "读书训练营"))

    forms = {
        "代码/命令/配置片段": len(codes) > 0,
        "工具/平台操作演示": len(tools) > 0,
        "真实案例拆解（具名实体）": len(ents) > 0 and (len(nums) > 0 or len(vers) > 0),
        "真实踩坑与复盘": len(pitfalls) >= 2,
    }
    forms_hit = [k for k, v in forms.items() if v]

    # ---- 判定 ----
    blocks, warns = [], []
    num_density = len(nums) / per_k
    op_signal = len(codes) + len(steps)

    if is_book:
        if len(nums) == 0 and not ents:
            blocks.append("读书营稿：全文无任何量化数据点、也无具名实体/案例——不符「替读者把书读透」要求")
    else:
        if len(nums) == 0 and op_signal == 0:
            blocks.append("三无稿：无量化数据点、无可操作形态（代码/命令/配置/编号步骤）——纯理论空转")
        if not forms_hit and num_density < 1.0:
            blocks.append("实战四形态（第 31 条②）一个都未满足，且量化密度 <1.0 ——证据不足，须改回带实战的选题")
        elif not forms_hit:
            warns.append("未命中实战四形态，但量化密度充足——人工确认本期「怎么做」是否讲到可复现颗粒度")

    if longest > gap_limit:
        warns.append(f"最长无量化区间 {longest} 字 > 阈值 {gap_limit} 字（{tier}）——该段在空讲概念，补 1 个数据/案例拆解")
    if len(bare) >= 3:
        warns.append(f"无原理结论句 {len(bare)} 处（阈值 ≥3）——给了结论没讲机制，逐条补「因为/之所以」")
    if fuzzy:
        warns.append(f"模糊主体 {len(fuzzy)} 处（{'、'.join(set(fuzzy))}）——违反第 25 条「有名有姓」，换成真实公司/产品/版本")
    if num_density < 0.5:
        warns.append(f"量化密度 {num_density:.1f}/千字 < 0.5（历史中位 0.8）——数据支撑偏薄")
    if len(reasons) == 0 and not is_book:
        warns.append("全文无一处机制解释（因为/之所以/原因是）——「为什么」段缺失，读者只知其然")

    verdict = "BLOCK" if blocks else ("WARN" if warns else "PASS")
    return {
        "chars": n, "tier": tier, "per_k": round(per_k, 2),
        "closure": {
            "是什么(定义句)": len(defines), "为什么(机制句)": len(reasons),
            "怎么做(可操作形态)": op_signal,
            "数据/案例(量化点)": len(nums),
            "坑/边界": len(pitfalls),
        },
        "signals": {"定义": len(defines), "代码命令": len(codes), "编号步骤": len(steps),
                    "原因": len(reasons), "坑边界": len(pitfalls), "工具操作": len(tools),
                    "具名实体": len(ents), "版本号": len(vers)},
        "num_density": round(num_density, 2),
        "longest_gap": longest, "gap_limit": gap_limit, "gap_at": longest_at,
        "bare_conclusions": bare, "fuzzy": sorted(set(fuzzy)),
        "abstract_density": round(len(ABSTRACT.findall(text)) / per_k, 1),
        "forms": forms, "forms_hit": forms_hit, "is_book": is_book,
        "blocks": blocks, "warns": warns, "verdict": verdict,
    }


def report(path, r):
    print(f"内容深度自检 · {os.path.basename(path)}")
    print(f"字数 {r['chars']} → 判定档位 {r['tier']}"
          f"{'（读书营 · 豁免代码强制）' if r['is_book'] else ''}\n")

    c = r["closure"]
    print("【讲透闭环覆盖】")
    print(f"  {'✓' if c['是什么(定义句)'] else '⚠'} 是什么        "
          f"{c['是什么(定义句)']} 处定义句（说白了/指的是/本质是…）")
    print(f"  {'✓' if c['为什么(机制句)'] else '⚠'} 为什么        {c['为什么(机制句)']} 处原因/机制句")
    print(f"  {'✓' if c['怎么做(可操作形态)'] else '⚠'} 怎么做        "
          f"{c['怎么做(可操作形态)']} 处可操作形态（代码/命令/配置/编号步骤）")
    print(f"  {'✓' if c['数据/案例(量化点)'] else '⚠'} 数据/案例     "
          f"{c['数据/案例(量化点)']} 个量化点（{r['num_density']}/千字，历史中位 0.8）")
    print(f"  {'✓' if c['坑/边界'] else '⚠'} 坑/边界       {c['坑/边界']} 处\n")

    print("【实战形态 · 第 31 条② · 至少满足其一】")
    for k, v in r["forms"].items():
        print(f"  {'✓' if v else '✗'} {k}")
    print()

    print("【空转信号（蜻蜓点水反模式）】")
    print(f"  最长无量化区间  {r['longest_gap']} 字（{r['tier']} 阈值 {r['gap_limit']} 字）")
    print(f"  无原理结论句    {len(r['bare_conclusions'])} 处（阈值 ≥3）")
    print(f"  抽象行话密度    {r['abstract_density']}/千字（历史中位 1.6，仅参考）")
    if r["fuzzy"]:
        print(f"  模糊主体        {'、'.join(r['fuzzy'])}")
    print()

    if r["blocks"]:
        print("【BLOCK · 必须改后再进 Step 2】")
        for b in r["blocks"]:
            print(f"  ✗ {b}")
    if r["warns"]:
        print("【WARN · 建议改】")
        for w in r["warns"]:
            print(f"  ! {w}")
    if r["bare_conclusions"]:
        print("\n【无原理结论句样本】")
        for s in r["bare_conclusions"][:5]:
            print(f"  · {s}")
    print(f"\n【结论】{r['verdict']}")


def main():
    ap = argparse.ArgumentParser(description="口播稿内容深度自检（讲透闭环 + 实战落地）")
    ap.add_argument("script", help="口播稿 .txt 路径")
    ap.add_argument("--camp", default="", help="训练营名（读书训练营豁免代码强制）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-fail", action="store_true", help="只报告，不改退出码")
    a = ap.parse_args()

    if not os.path.isfile(a.script):
        print(f"ERROR: 文件不存在: {a.script}", file=sys.stderr)
        return 2
    text = read_script(a.script)
    if len(text) < 150:
        print(f"ERROR: 稿件过短（{len(text)} 字），疑似空文件", file=sys.stderr)
        return 2

    r = analyze(text, a.camp)
    if a.json:
        print(json.dumps({"script": a.script, **r}, ensure_ascii=False, indent=2))
    else:
        report(a.script, r)

    if a.no_fail:
        return 0
    return 1 if r["verdict"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
