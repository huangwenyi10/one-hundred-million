#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
douyin_compliance_check.py — 抖音发布前合规自检（本地确定性扫描 · 零外部依赖）

配套：references/douyin-compliance.md（固定规范第 30 条）
作用：对口播稿 / 标题 / 发布文案 做发布前的红线扫描，命中 BLOCK 即 exit 1、禁止进入 Step 7 作者审核。

设计原则：
  1) 只做高置信、可正则化的红线（站外引流 / 绝对化用语 / 效果收益承诺 / 焦虑对立 /
     教培虚拟内容禁语 / 固定收尾句 / 训练营标识与期号），不做语义判断——语义问题由人看。
  2) 技术语境词白名单（唯一索引 / 第一范式 / 最佳实践 …）避免误报，误报会让人放弃用这个门禁。
  3) 输出 BLOCK（必须改）/ WARN（疑似，人工确认）两级；exit 0 才视为通过。

用法：
  python3 douyin_compliance_check.py <口播稿.txt> [更多文件...] [--title "标题"] [--json]
  例：python3 douyin_compliance_check.py "标题/xxx_口播稿.txt" --title "Doris读写分离" --copy 发布/抖音.md

退出码：0 通过（无 BLOCK）｜1 命中 BLOCK｜2 用法或文件错误
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# 词表：(正则, 级别, 类别, 建议)
#   级别 BLOCK = 红线，必须改写；WARN = 疑似，人工确认
#   白名单 allow：命中该正则的上下文视为技术术语，不报
# ---------------------------------------------------------------------------

RULES = [
    # ---------------- 1. 站外引流（最高危） ----------------
    (r"微信号|加微信|加个微信|vx|VX|Vx|薇信|徽信|weixin|wechat|WeChat|企微|企业微信",
     "BLOCK", "站外引流", "删除；改为站内引导（关注/评论/站内私信）"),
    (r"加我|扣我|私聊我|私我|加个好友|扫码|二维码|扫一扫|站外|私域|引流",
     "BLOCK", "站外引流", "删除；抖音 AI 会识别导流关键词，首次即限流"),
    (r"私信领资料|私信领取|评论区领|扣【?[^】]{0,6}】?领|扣1领|留邮箱|留联系方式",
     "BLOCK", "站外引流", "删除；'私信领资料' 式导流已被平台列为高危"),
    (r"(?<![0-9])1[3-9]\d{9}(?![0-9])", "BLOCK", "隐私安全", "删除手机号"),
    (r"[Qq][Qq]\s*[:：]?\s*\d{5,}", "BLOCK", "隐私安全", "删除 QQ 号"),
    (r"https?://|www\.[a-zA-Z0-9-]+\.", "BLOCK", "站外引流", "删除网址；站外链接不可出现"),
    (r"网盘|百度网盘|夸克|蓝奏|提取码", "BLOCK", "站外引流", "删除网盘信息"),

    # ---------------- 2. 绝对化用语 ----------------
    (r"最好|最强|最优|最快|最牛|最先进|最便宜|最专业|最高级|最高效|最低价", "BLOCK", "绝对化用语",
     "改为可核验的比较口径（如「实测 3 个版本里吞吐最高」）；说不出范围就删"),
    (r"全网最|史上最|全世界最", "BLOCK", "绝对化用语", "删除"),
    (r"唯一", "WARN", "绝对化用语", "确认非技术术语「唯一索引/唯一键/唯一性」；营销语境请改"),
    (r"顶级|极致|绝对|万能|无敌|天花板|绝无仅有|独一无二|无与伦比", "BLOCK", "绝对化用语", "删除或改为具体描述"),
    (r"(?<![0-9.])100%(?![\d.])", "WARN", "绝对化用语", "确认是技术指标（带测试条件）还是营销话术；后者改写"),
    (r"国家级|世界级|国际级|行业第一|唯一指定", "BLOCK", "绝对化用语", "删除；无法考证的权威背书"),
    (r"永久|终身|无限次|一劳永逸|永久有效|终身有效", "BLOCK", "教培虚拟内容禁语",
     "官方明确禁止（有效期宣传不得超过 5 年）；删除或改为「随课程版本更新」"),
    (r"最佳实践", "ALLOW", "", ""),

    # ---------------- 3. 效果与收益承诺（本项目最高危） ----------------
    (r"保证学会|包教包会|包过|保过|必过|包就业|包分配|包涨薪|保证涨薪|保证提薪", "BLOCK", "效果收益承诺",
     "官方明文禁止；改为「讲解方法/机制」，不给结果承诺"),
    (r"月入过万|月入十万|月入百万|年入百万|轻松过万|躺着赚钱|躺赚|稳赚|稳赚不赔|包赚|保证回本|肯定回本|一定回本|稳回本",
     "BLOCK", "效果收益承诺", "官方公告原文禁止（「普通人也能月入过万」即违规示例）；删除"),
    (r"一夜暴富|快速暴富|快速致富|日入过千|日赚|暴利", "BLOCK", "效果收益承诺", "删除"),
    (r"零基础速成|速成|秒会|三天学会|七天精通|一个月精通", "BLOCK", "效果收益承诺", "改为「入门路径/学习周期参考」，不给速成承诺"),
    (r"学完就能|学会就能赚|保证你|包你", "BLOCK", "效果收益承诺", "改为客观描述，不做结果担保"),
    (r"年薪百万|财务自由|财富自由", "WARN", "效果收益承诺", "确认是「客观描述市场行情」还是承诺收益；后者改写"),

    # ---------------- 4. 焦虑 / 对立 / 贬低 ----------------
    (r"35\s*岁.{0,4}危机|中年危机|被淘汰|淘汰你|再不学就|再不.{0,4}就晚了|等着被优化|被裁员", "BLOCK", "焦虑对立",
     "禁贩卖职业焦虑；改为客观描述能力缺口"),
    (r"割韭菜|智商税|穷人思维|韭菜", "BLOCK", "焦虑对立", "删除"),
    (r"垃圾语言|垃圾技术|一文不值|毫无价值|烂代码|智商堪忧", "WARN", "贬低同行/贬低技术",
     "确认是否贬低他人/同行（踩一捧一被禁）；技术对比请给客观数据"),

    # ---------------- 5. 教培虚拟内容专项 ----------------
    (r"密押|押题|押中原题|内部资料|内部消息|小道消息|命题组|命题老师|阅卷专家|考纲内幕", "BLOCK",
     "教培虚拟内容禁语", "官方明文禁止；删除"),
    (r"专家推荐|名师推荐|官方认证", "WARN", "虚假资质", "确认有无资质；无资质不得以专家/名师名义推荐"),

    # ---------------- 6. 固定收尾句（既有固定规范第 2 条） ----------------
    (r"以上就是今天(所有)?内容|下期再见|我们下期再见|感谢(大家|各位)?观看|感谢收看|喜欢请点赞关注", "BLOCK",
     "固定收尾句", "改为自然收尾 + 站内 CTA"),

    # ---------------- 7. 训练营标识与期号（既有固定规范第 14 条） ----------------
    (r"架构师训练营|大数据训练营|AI训练营|产品经理训练营|前端训练营|测试训练营|管理训练营|软技能训练营|读书训练营",
     "BLOCK", "训练营标识", "画面/口播不得出现训练营名称（固定规范第 14 条）"),
    (r"第\s*[0-9一二三四五六七八九十]{1,3}\s*期", "BLOCK", "期号标识", "画面/口播不得出现期号（固定规范第 14 条）"),

    # ---------------- 8. 其它内容红线（关键词兜底） ----------------
    (r"邪教|封建迷信|赌博|毒品|色情|低俗", "BLOCK", "内容红线", "社区自律公约明令禁止"),
]

# 技术语境白名单：出现在命中位置左右 N 字内则忽略
ALLOW_CONTEXT = {
    "唯一": [r"唯一索引", r"唯一键", r"唯一性", r"唯一标识", r"唯一 ID", r"唯一 id", r"唯一约束"],
    "第一": [r"第一范式", r"第一性原理", r"第一次", r"第一步", r"第一层", r"第一代", r"第一版",
             r"第一章", r"第一节", r"第一部分", r"第一类", r"第一阶段", r"第一时间", r"第一行", r"第一位"],
    "最佳实践": [r"最佳实践"],
    "100%": [r"命中率\s*100%", r"可用性\s*100%", r"覆盖\s*100%", r"100%\s*的?测试"],
}
WINDOW = 8  # 上下文窗口（字符）

SEV_ORDER = {"BLOCK": 0, "WARN": 1}


def _allowed(term, text, start, end):
    """命中位置附近是否命中技术语境白名单"""
    for t, pats in ALLOW_CONTEXT.items():
        if t in term:
            seg = text[max(0, start - WINDOW): end + WINDOW]
            for p in pats:
                if re.search(p, seg):
                    return True
    return False


def scan_text(text, source):
    hits = []
    for pattern, level, category, advice in RULES:
        if level == "ALLOW":
            continue
        for m in re.finditer(pattern, text):
            term = m.group(0)
            if _allowed(term, text, m.start(), m.end()):
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            # 上下文摘要（去掉换行，便于单行展示）
            ctx = text[max(0, m.start() - 18): m.end() + 18].replace("\n", " ")
            hits.append({
                "level": level, "category": category, "term": term,
                "source": source, "line": line_no, "context": ctx.strip(),
                "advice": advice,
            })
    return hits


def main():
    ap = argparse.ArgumentParser(description="抖音发布前合规自检（本地确定性扫描）")
    ap.add_argument("files", nargs="*", help="口播稿 / 发布文案等文本文件")
    ap.add_argument("--title", default=None, help="视频标题（单独扫描）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if not args.files and not args.title:
        print("用法：python3 douyin_compliance_check.py <口播稿.txt> [更多文件...] [--title 标题] [--json]",
              file=sys.stderr)
        return 2

    hits, missing = [], []
    for f in args.files:
        if not os.path.isfile(f):
            missing.append(f)
            continue
        with open(f, "r", encoding="utf-8", errors="ignore") as fh:
            hits += scan_text(fh.read(), os.path.basename(f))
    if args.title:
        hits += scan_text(args.title, "<标题>")

    if missing:
        for f in missing:
            print("文件不存在：%s" % f, file=sys.stderr)
        return 2

    # 去重（同一条命中可能在多规则重复）
    seen, uniq = set(), []
    for h in hits:
        key = (h["level"], h["category"], h["term"], h["source"], h["line"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    uniq.sort(key=lambda h: (SEV_ORDER[h["level"]], h["source"], h["line"]))

    block = [h for h in uniq if h["level"] == "BLOCK"]
    warn = [h for h in uniq if h["level"] == "WARN"]

    if args.json:
        print(json.dumps({
            "verdict": "FAIL" if block else "PASS",
            "block": len(block), "warn": len(warn), "hits": uniq,
        }, ensure_ascii=False, indent=2))
        return 1 if block else 0

    print("=== 抖音合规自检（douyin-compliance 固定规范第 30 条）===")
    if not uniq:
        print("[通过] 未发现 BLOCK / WARN 命中——可进入 Step 7 作者审核。")
    for h in uniq:
        print("[%s][%s] %s:%d  «%s»  → %s" % (h["level"], h["category"], h["source"], h["line"], h["context"], h["advice"]))
    print("---")
    print("汇总：BLOCK %d 项 / WARN %d 项" % (len(block), len(warn)))
    if block:
        print("结论：FAIL —— 必须改写全部 BLOCK 项 → 重新生成配音与字幕 → 重跑本脚本（exit 0 才可交付）。")
        return 1
    print("结论：PASS（WARN 项请人工确认）—— 可进入 Step 7 作者审核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
