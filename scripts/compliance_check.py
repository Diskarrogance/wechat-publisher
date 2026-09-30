#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
compliance_check.py — 内容合规硬化检查（v2.15.0 新增 / GEO 第一阶段）

为什么存在
    两个号已有「内容违规 → 删文/警告」的先例，且定下的 GEO 第一阶段验收标准是
    「能过原创 + 不触发限流」。原有 validate_title.py 只查「情绪对立词」一类，
    金融类（融资额/估值/股价）与绝对化表述（最/第一/唯一）完全没覆盖，
    而这两类恰好是「科技资讯 + 品牌嵌入」最高频的踩坑点。

与 validate_title.py 的分工
    validate_title.py  = 老关卡，保持向后兼容（标题禁词 + 长度）
    compliance_check.py = 新关卡，做**更宽**的扫描：金融、绝对化、医疗宣称、投资诱导
    两者都跑，任何一个 exit≠0 都禁止建稿。

用法
    python compliance_check.py <article.html> [--title "<标题>"] [--json] [--quiet]
    python compliance_check.py @json:<draft.json>            # 直接从 draft.json 读 title+content
    python compliance_check.py <article.html> --title "..." --strict

退出码
    0 = 通过（可能带 WARN，可建稿）
    1 = FAIL，禁止建稿，必须改写命中处
    2 = 参数 / 文件错误
    3 = 脚本内部错误

级别约定
    FAIL = 硬拦截（标题限词、投资诱导、涉外词堆叠）
    WARN = 列出上下文，交改写者判断（正文极限词、金融数字缺出处、医疗宣称）
"""

import sys
import os
import io
import re
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 命中金融数字时，向两侧各看多少字找「出处词」
ATTR_WINDOW = 80


def strip_html(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', t).strip()


def has_attribution(text, lo, hi, attr_words):
    """[lo, hi) 区间（前后各扩 ATTR_WINDOW 字）内是否出现出处词"""
    seg = text[max(0, lo - ATTR_WINDOW): min(len(text), hi + ATTR_WINDOW)]
    return any(w in seg for w in attr_words)


def check(title, content):
    """返回 (fails: list[str], warns: list[str], stats: dict)

    词表从 _rules.py（唯一真源）延迟导入 —— 这样本模块既能当脚本跑、
    也能被 create_draft.py 当库导入，词表缺失时由调用方决定如何处理。
    """
    from _rules import (
        BANNED_WORDS, POLITICAL_WORDS, ALARMIST_WORDS, INVEST_INDUCE_WORDS,
        ABSOLUTE_WORDS, MEDICAL_CLAIM_WORDS,
        FINANCE_SUBJECT_WORDS, SOURCE_ATTRIBUTION_WORDS, MONEY_PATTERNS,
        find_hits, find_hits_with_context,
    )
    fails, warns = [], []
    body = strip_html(content or '')
    title = title or ''

    # ── F1 硬禁词 ──
    t_hits = find_hits(title, BANNED_WORDS)
    if t_hits:
        fails.append(f'F1 标题含硬禁词 {t_hits}（曾致删文，必须改写）')
    b_hits = find_hits(body, BANNED_WORDS + ALARMIST_WORDS)
    if b_hits:
        warns.append(f'W1 正文含高危情绪词 {b_hits}（若非"我们反对××"语境，建议改写）')

    # ── F2 涉外/政治词堆叠 ──
    p_hits = find_hits(title + body, POLITICAL_WORDS)
    if len(p_hits) >= 2:
        fails.append(f'F2 涉政/涉外词出现 {len(p_hits)} 个 {p_hits}（科技资讯勿作时政评论）')

    # ── F3 投资诱导 ──
    i_hits = find_hits(title + body, INVEST_INDUCE_WORDS)
    if i_hits:
        fails.append(f'F3 出现投资诱导/荐股类词 {i_hits}（金融信息合规红线）')

    # ── F4 标题绝对化（标题无法自证，一律拦）──
    ta_hits = find_hits(title, ABSOLUTE_WORDS)
    if ta_hits:
        fails.append(f'F4 标题含绝对化/极限词 {ta_hits}（广告法风险；若为可举证事实，'
                     f'改写为"据《××报告》× 项指标居首"这类带出处的表述）')

    # ── W2 正文绝对化（列出上下文，逐条判断）──
    a_ctx = find_hits_with_context(body, ABSOLUTE_WORDS, window=16, limit=10)
    if a_ctx:
        warns.append(f'W2 正文含绝对化表述 {len(a_ctx)} 处（有出处可留，无出处必改）：')
        for w, ctx in a_ctx:
            warns.append(f'      [{w}] {ctx}')

    # ── W3 医疗/疗愈宣称 ──
    m_ctx = find_hits_with_context(body, MEDICAL_CLAIM_WORDS, window=16, limit=6)
    if m_ctx:
        warns.append(f'W3 涉及医疗/疗效宣称 {len(m_ctx)} 处（无资质不得宣称疗效）：')
        for w, ctx in m_ctx:
            warns.append(f'      [{w}] {ctx}')

    # ── W4 金融数字缺出处 ──
    # 多组正则可能匹配到同一位置，按 (start,end) 去重，避免同一数字报两遍
    seen_spans, money_hits = set(), []
    for pat in MONEY_PATTERNS:
        for m in re.finditer(pat, body):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            money_hits.append((m.start(), m.end(), m.group(0)))
    missing = [(s, e, g) for (s, e, g) in money_hits
               if not has_attribution(body, s, e, SOURCE_ATTRIBUTION_WORDS)]
    fin_words = find_hits(body, FINANCE_SUBJECT_WORDS)
    if missing and fin_words:
        warns.append(f'W4 金融类数字缺出处 {len(missing)} 处（正文提到 {fin_words}；'
                     f'补"据××报告/公告"后保留，否则删除）：')
        for s, e, g in missing[:6]:
            a = max(0, s - 20)
            b = min(len(body), e + 20)
            warns.append(f'      {g}  ←  …{body[a:b]}…')

    # ── W5 品牌嵌入频率（GEO 红线：一篇 1~2 次，硬塞判软文）──
    # 统计前先剔除二维码引导文案（「扫码加入君寻粉丝群」是固定模板，不算品牌嵌入）。
    _body_nb = re.sub(r'[^。！？\n]*(?:扫码|粉丝群|二维码)[^。！？\n]*', '', body)
    brand_stats = {}
    for name in ('君寻智能', '岚牧哒', '君寻'):
        n = len(re.findall(re.escape(name), _body_nb))
        if n:
            brand_stats[name] = n
    if brand_stats.get('君寻智能', 0) > 0 and brand_stats.get('君寻', 0) > brand_stats.get('君寻智能', 0):
        warns.append(f'W5 品牌实体口径不统一：出现"君寻智能"{brand_stats.get("君寻智能")} 次、'
                     f'"君寻"单独使用 {brand_stats.get("君寻")} 次（GEO 口径应统一为"君寻智能"）')
    for name, n in brand_stats.items():
        if n > 3:
            warns.append(f'W5 品牌"{name}"出现 {n} 次（>3 次易被判软文降权，建议压到 1~2 次）')

    stats = {
        'title_len': len(title),
        'body_chars': len(body),
        'money_mentions': len(money_hits),
        'money_missing_attr': len(missing),
        'brand_mentions': brand_stats,
    }
    return fails, warns, stats


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('article', help='正文 HTML 文件，或 @json:<draft.json>')
    ap.add_argument('--title', default='', help='标题（HTML 模式下必填）')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--quiet', action='store_true', help='只输出结论')
    args = ap.parse_args()

    title, content = args.title, ''

    if args.article.startswith('@json:'):
        p = args.article[6:]
        if not os.path.exists(p):
            print(f'[ERROR] 文件不存在: {p}', file=sys.stderr)
            return 2
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
        title = title or data.get('title', '')
        content = data.get('content', '')
    else:
        if not os.path.exists(args.article):
            print(f'[ERROR] 文件不存在: {args.article}', file=sys.stderr)
            return 2
        with open(args.article, encoding='utf-8') as f:
            content = f.read()

    if not content:
        print('[ERROR] 正文为空', file=sys.stderr)
        return 2

    try:
        fails, warns, stats = check(title, content)
    except ImportError as e:
        print(f'[FATAL] 无法导入 _rules.py（词表真源，须与本脚本同目录）：{e}', file=sys.stderr)
        return 3
    except Exception as e:
        print(f'[ERROR] 检查异常: {type(e).__name__}: {e}', file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps({'title': title, 'fails': fails, 'warns': warns,
                          'stats': stats,
                          'verdict': 'FAIL' if fails else ('WARN' if warns else 'PASS')},
                         ensure_ascii=False, indent=2))
        return 1 if fails else 0

    if not args.quiet:
        print('=' * 78)
        print('合规检查 compliance_check')
        print('=' * 78)
        print(f'  标题：{title[:50]}（{stats["title_len"]} 字）')
        print(f'  正文：{stats["body_chars"]} 字')

    for w in warns:
        print(w)

    if fails:
        print('裁定: FAIL — 存在硬拦项，禁止建稿')
        for x in fails:
            print(f'  ✗ {x}')
        return 1

    print('裁定: PASS' + ('（含 WARN，逐条确认后再建稿）' if warns else ' — 无风险项'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
