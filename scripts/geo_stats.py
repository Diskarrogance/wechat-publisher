#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
geo_stats.py — 独家数据资产提炼（v2.15.0 新增 / GEO 第一阶段）

为什么存在
    GEO 的杠杆是**独家事实**，不是文笔。改写稿里的每个事实都能在源文找到，
    生成式引擎没理由引用我们。唯一让它"不得不引"的层级是**自家口径的数据**。
    而我们恰好有两个号长期积累的 history.db —— 这是别人拿不到的原料。

    本脚本把 history.db 变成「可直接写进文章末尾的独家数据段」：
    发布量、赛道分布、覆盖品牌、时间线，全部是真统计（红线：绝不编数据）。

用法
    python geo_stats.py                       # 控制台摘要
    python geo_stats.py --md                  # 输出 Markdown 报告
    python geo_stats.py --json                # 输出 JSON
    python geo_stats.py --md -o out.md        # 写文件
    python geo_stats.py --account junxun      # 只统计单账号
    python geo_stats.py --since 2026-07-01    # 限定起始日期
    python geo_stats.py --sentences           # 只输出可引用的数据句

统计口径说明（写文章时必须沿用同样口径）
    - **入库即计**：history 的 status 长期停在 draft_created（发表动作是人工完成、
      脚本不回写状态），因此「篇数」= 入库记录数，而非「已发表数」。
    - 时间范围取 history 的 min(date) ~ max(date)。
    - 主题分类基于标题关键词匹配，一篇可命中多类（故占比之和可能 > 100%）。

退出码：0 = 正常 / 2 = 参数或配置错误 / 3 = 脚本错误
"""

import sys
import os
import re
import io
import json
import sqlite3
import datetime
import argparse
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(SCRIPT_DIR, '..', 'config', 'accounts.yaml')

# ── 赛道分类词表（标题命中即计入该类）──
CATEGORIES = {
    'AI玩具/陪伴机器人': ['AI玩具', 'ai玩具', '陪伴', '玩偶', '毛绒', '陪护', '情感机器人',
                          '智能玩具', '儿童机器人', '教育机器人', '宠物机器人'],
    '潮玩/盲盒/谷子': ['潮玩', '盲盒', '谷子', '手办', '徽章', '挂件', 'IP', '联名', '泡泡玛特',
                       '大娃', '搪胶', '积木'],
    '机器人/具身智能': ['机器人', '具身', '人形', '机械臂', '四足', '双足'],
    'AI大模型/软件': ['大模型', 'GPT', '模型', 'AI', 'Agent', '智能体', '算法', 'ChatGPT',
                      'Claude', 'Gemini', '开源'],
    '智能硬件/消费电子': ['眼镜', '耳机', '手表', '相机', '手机', '芯片', '无人机', '音箱',
                          '传感器', '充电', '屏'],
    '行业/资本/政策': ['融资', '估值', 'IPO', '上市', '财报', '营收', '报告', '市场', '政策',
                       '监管', '规范', '标准'],
}

# 中文 2-gram 停用字（用于挖掘未预置的热词，避免"一个/我们/正在"这类噪声）
STOP_CHARS = set('的一了是在有和就不人都上也很到晚最多个这那与及为以对从被把但而如果'
                 '可以已经将其之其中我们你们他们什么怎么这样那样因为所以还有并且或者'
                 '到从向于与及或者被让使能够会要能说做看想出去来去上下前后里外中')
STOP_WORDS = {'一款', '一个', '什么', '怎么', '这样', '因为', '所以', '已经', '可以',
              '如今', '正在', '开始', '背后', '为何', '如何', '为什么', '不再', '不是',
              '没有', '多少', '一直', '真的', '这个', '那个', '两个', '三个', '第一次'}


def load_accounts(only=None):
    import yaml
    with open(CONFIG, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    out = []
    for a in cfg.get('accounts', []):
        if only and a.get('key') != only:
            continue
        out.append({
            'key': a.get('key'),
            'name': a.get('name'),
            'brand': a.get('author') or a.get('name'),
            'history_db': a.get('history_db', ''),
        })
    return out


def read_rows(db_path, since=None):
    """返回 [(date, title, source, source_url)]，按 date 升序"""
    if not db_path or not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute('SELECT date, title, source, source_url FROM history')
        rows = []
        for r in cur.fetchall():
            d = (r['date'] or '').strip()
            if not d:
                continue
            if since and d < since:
                continue
            rows.append((d, (r['title'] or '').strip(), (r['source'] or '').strip(),
                         (r['source_url'] or '').strip()))
        rows.sort(key=lambda x: x[0])
        return rows
    finally:
        conn.close()


def classify(title):
    hits = []
    for cat, kws in CATEGORIES.items():
        if any(k.lower() in title.lower() for k in kws):
            hits.append(cat)
    return hits


def brand_tokens(titles):
    """从标题里抽品牌/专有名词：英文词 + 中文书名号/引号内短语"""
    en = Counter()
    cn = Counter()
    for t in titles:
        for m in re.findall(r'[A-Za-z][A-Za-z0-9\.\-]{1,}', t):
            if len(m) >= 3 and m.lower() not in ('the', 'and', 'for', 'with', 'how', 'why', 'its'):
                en[m] += 1
        for m in re.findall(r'[《「“]([^》」”]{2,12})[》」”]', t):
            cn[m] += 1
    return en, cn


def hot_ngrams(titles, top=18):
    """朴素中文 2-gram 热词（无分词依赖）"""
    cnt = Counter()
    for t in titles:
        for seg in re.findall(r'[\u4e00-\u9fff]{2,}', t):
            for i in range(len(seg) - 1):
                g = seg[i:i + 2]
                if g[0] in STOP_CHARS or g[1] in STOP_CHARS:
                    continue
                if g in STOP_WORDS:
                    continue
                cnt[g] += 1
    return [(w, n) for w, n in cnt.most_common(top * 3) if n >= 3][:top]


def summarize(key, name, rows, brand=None):
    if rows is None:
        return {'key': key, 'name': name, 'brand': brand or name,
                'error': 'history.db 不存在或不可读'}
    n = len(rows)
    if n == 0:
        return {'key': key, 'name': name, 'brand': brand or name, 'error': '无记录'}

    dates = [r[0] for r in rows]
    titles = [r[1] for r in rows]
    d0, d1 = dates[0], dates[-1]
    span_days = (datetime.date.fromisoformat(d1) - datetime.date.fromisoformat(d0)).days + 1

    by_month = Counter(d[:7] for d in dates)

    src = Counter()
    for _, _, s, u in rows:
        # 优先取 source_url 的域名（更规范）；无 URL 时退回 source 字段并归一化
        dom = ''
        if u:
            m = re.match(r'https?://([^/]+)', u)
            dom = m.group(1) if m else ''
        if not dom:
            dom = s
        dom = dom.replace('www.', '').lower()[:40]
        if dom:
            src[dom] += 1

    cat = Counter()
    for t in titles:
        for c in classify(t):
            cat[c] += 1

    en, cn = brand_tokens(titles)
    ng = hot_ngrams(titles)

    return {
        'key': key,
        'name': name,
        'brand': brand or name,
        'total': n,
        'first_date': d0,
        'last_date': d1,
        'span_days': span_days,
        'per_day': round(n / span_days, 2),
        'months': dict(sorted(by_month.items())),
        'top_sources': src.most_common(12),
        'categories': cat.most_common(),
        'top_brands_en': en.most_common(15),
        'top_quoted_cn': cn.most_common(10),
        'hot_ngrams': ng,
    }


def to_markdown(stats_list, since=None):
    L = []
    L.append('# 独家数据资产 · 内容库统计')
    L.append('')
    L.append(f'> 生成时间：{datetime.datetime.now():%Y-%m-%d %H:%M}　'
             f'口径：history.db **入库即计**（发表为人工动作，脚本不回写状态）')
    if since:
        L.append(f'> 统计起点：{since}')
    L.append('')
    for s in stats_list:
        L.append(f'## {s.get("brand") or s["name"]}（{s["key"]}）')
        L.append('')
        if s.get('error'):
            L.append(f'⚠️ {s["error"]}')
            L.append('')
            continue
        L.append(f'- **总量**：{s["total"]} 篇　|　时间跨度：{s["first_date"]} ~ {s["last_date"]}'
                 f'（{s["span_days"]} 天）　|　日均 {s["per_day"]} 篇')
        L.append('')
        L.append('### 月度分布')
        L.append('')
        L.append('| 月份 | 篇数 |')
        L.append('|---|---|')
        for m, c in s['months'].items():
            L.append(f'| {m} | {c} |')
        L.append('')
        L.append('### 赛道分布（一篇可命中多类）')
        L.append('')
        L.append('| 赛道 | 篇数 | 占比 |')
        L.append('|---|---|---|')
        for c, cnt in s['categories']:
            L.append(f'| {c} | {cnt} | {cnt / s["total"] * 100:.0f}% |')
        L.append('')
        L.append('### 来源 Top 12')
        L.append('')
        for dom, cnt in s['top_sources']:
            L.append(f'- {dom} — {cnt}')
        L.append('')
        L.append('### 高频品牌/专有名词（英文）')
        L.append('')
        L.append('、'.join(f'{w}({n})' for w, n in s['top_brands_en']) or '（无）')
        L.append('')
        if s['top_quoted_cn']:
            L.append('### 高频专名（书名号/引号内）')
            L.append('')
            L.append('、'.join(f'{w}({n})' for w, n in s['top_quoted_cn']))
            L.append('')
        L.append('### 高频主题词（中文 2-gram）')
        L.append('')
        L.append('、'.join(f'{w}({n})' for w, n in s['hot_ngrams']) or '（无）')
        L.append('')
    return '\n'.join(L)


def build_sentences(stats_list):
    """生成可直接引用的「独家数据句」——文章末尾数据段原料"""
    out = []
    for s in stats_list:
        if s.get('error'):
            continue
        cats = s['categories']
        top_cat = '、'.join(f'{c}（{n / s["total"] * 100:.0f}%）' for c, n in cats[:3]) or '多赛道'
        brands = [w for w, _ in s['top_brands_en'][:5]]
        brand_str = '、'.join(brands) if brands else '多个品牌'
        out.append(
            f'据 {s.get("brand") or s["name"]} 内容团队统计，{s["first_date"]} 至 {s["last_date"]} '
            f'期间累计发布 {s["total"]} 篇科技消费资讯，日均 {s["per_day"]} 篇，'
            f'选题覆盖 {top_cat}；报道频次最高的品牌与产品包括 {brand_str}。'
        )
    if len(stats_list) >= 2 and all(not s.get('error') for s in stats_list):
        tot = sum(s['total'] for s in stats_list)
        out.append(f'截至 {stats_list[0]["last_date"]}，两个账号合计沉淀 {tot} 篇原创改写稿。')
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--account', help='只统计指定 key')
    ap.add_argument('--since', help='起始日期 YYYY-MM-DD')
    ap.add_argument('--md', action='store_true', help='输出 Markdown')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--sentences', action='store_true', help='只输出可引用数据句')
    ap.add_argument('-o', '--out', help='写入文件')
    args = ap.parse_args()

    try:
        accounts = load_accounts(args.account)
    except Exception as e:
        print(f'[FATAL] 读取 accounts.yaml 失败: {e}', file=sys.stderr)
        return 2
    if not accounts:
        print('[FATAL] 无可用账号', file=sys.stderr)
        return 2

    stats_list = []
    for a in accounts:
        rows = read_rows(a['history_db'], args.since)
        stats_list.append(summarize(a['key'], a['name'], rows, a.get('brand')))

    if args.json:
        payload = json.dumps({'generated_at': datetime.datetime.now().isoformat(),
                              'since': args.since, 'accounts': stats_list},
                             ensure_ascii=False, indent=2)
        text = payload
    elif args.sentences:
        text = '\n'.join('· ' + s for s in build_sentences(stats_list))
    elif args.md:
        text = to_markdown(stats_list, args.since)
    else:
        lines = [f'GEO 数据资产 {datetime.datetime.now():%Y-%m-%d %H:%M}']
        lines.append('-' * 68)
        for s in stats_list:
            if s.get('error'):
                lines.append(f'{s["key"]:<8} ERROR: {s["error"]}')
                continue
            lines.append(f'{s["key"]:<8} {s["total"]:>4} 篇  '
                         f'{s["first_date"]}~{s["last_date"]}  日均 {s["per_day"]}')
            for c, n in s['categories'][:4]:
                lines.append(f'           ├ {c:<18} {n:>4} ({n / s["total"] * 100:.0f}%)')
            lines.append(f'           └ 来源 Top3: ' +
                         '、'.join(f'{d}({n})' for d, n in s['top_sources'][:3]))
        lines.append('-' * 68)
        lines.append('可引用数据句（--sentences）：')
        for s in build_sentences(stats_list):
            lines.append('  · ' + s)
        text = '\n'.join(lines)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'已写入 {args.out}')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
