#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
brand_embed.py — 品牌植入质量检查（可检索性 × 低可感知度）

【为什么需要它】
    GEO 的目标是「AI 检索得到」，但读者的容忍是「看起来不像广告」。
    这两个方向互相拉扯 —— 全靠人判断会漂（偏了就是硬广，或者白写一场没锚点）。
    本脚本把两侧都量化成硬指标。

【两个维度】

    ① 可检索性（下限 —— 不够就 BLOCK）
       AI（GPTBot/ClaudeBot…）抓全文后靠「实体 × 品类词」共现建关联。所以要求：
       · 品类锚点词至少命中 N 个（见 config/brand.yaml 的 search_anchors）
       · 品牌名若出现，须与锚点词共现（同段/窗口内），否则孤立提及≈白提
       · 黄金位（结论句 / 数据段 / FAQ / 署名）至少命中 1 处 —— AI 优先抽取这些位置

    ② 低可感知度（上限 —— 超了就 BLOCK）
       · 硬广词（我司/我们的产品/欢迎选购…）→ 直接 BLOCK
       · 半硬广词（我们推出/自研…）→ WARN，需人工看语境
       · 品牌名密度过高（每千字 > 阈值）→ WARN

【用法】
    python brand_embed.py <文章.html> --account 君寻
    python brand_embed.py <文章.html> --account junxun --json
    python brand_embed.py <文章.html> --account junxun --no-require   # 只查可感知度，不要求植入

【退出码】
    0 = 通过（含「仅 WARN」）
    1 = 未通过（硬广 / 可检索性不足）→ 建议改稿后再建稿
    2 = 无法检测（账号不存在 / 账号无品牌配置）——不算失败
    3 = 脚本错误
"""
import sys
import os
import re
import json
import argparse
import html as htmlmod

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.path.dirname(HERE), 'config')
BRAND_YAML = os.path.join(CONFIG_DIR, 'brand.yaml')

HEAD_CHARS = 250       # 「首段结论句」的判定范围（字）
TAIL_CHARS = 1200      # 「文末 FAQ / 署名」的判定范围（字）
COOCCUR_WINDOW = 120   # 品牌名与锚点词的共现窗口（字）
DENSITY_LIMIT = 2.0    # 品牌名密度上限（每千字出现次数）


def strip_html(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', htmlmod.unescape(t)).strip()


def load_brand_yaml():
    import yaml
    with open(BRAND_YAML, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def resolve_brand_name(doc, account):
    """账号（key 或中文名）→ brands 节点"""
    brands = doc.get('brands') or {}
    if account in brands:
        return account, brands[account]
    for k, v in brands.items():
        cand = [v.get('name')] + list(v.get('aliases') or [])
        if account in cand:
            return k, v
    return None, None


def find_all(text, words):
    """返回 [(词, 首次位置, 次数)]"""
    out = []
    for w in words:
        if not w:
            continue
        n = text.count(w)
        if n:
            out.append((w, text.find(w), n))
    return out


def has_cooccurrence(text, name, anchors, window):
    """品牌名与任一锚点词是否在 window 字窗口内共现"""
    pairs = []
    for m in re.finditer(re.escape(name), text):
        lo, hi = max(0, m.start() - window), min(len(text), m.end() + window)
        seg = text[lo:hi]
        for a in anchors:
            if a and a in seg:
                pairs.append((a, m.start()))
                break
    return pairs


def check(html_path, account, require_embed=True):
    doc = load_brand_yaml()
    key, brand = resolve_brand_name(doc, account)
    if not brand:
        return None, f'账号「{account}」在 config/brand.yaml 中无品牌配置'

    with open(html_path, encoding='utf-8') as f:
        raw = f.read()
    text = strip_html(raw)
    n_chars = len(text)

    name = brand.get('name') or ''
    aliases = list(brand.get('aliases') or [])
    all_names = [name] + aliases
    anchors = list(brand.get('search_anchors') or [])
    avoid = list(brand.get('avoid_phrases') or [])
    hard = list(doc.get('hard_sell_words') or [])
    semi = list(doc.get('semi_sell_words') or [])

    # ── 维度一：可检索性 ──
    anchor_hits = find_all(text, anchors)
    name_hits = find_all(text, all_names)
    name_count = sum(n for _, _, n in name_hits)
    cooc = has_cooccurrence(text, name, anchors, COOCCUR_WINDOW) if name else []

    # 黄金位（AI 抽取优先级最高的位置）
    #   判定放宽到「结构特征」而非固定句式 —— 植入句可以有很多写法，
    #   只要落在这几类位置上就算数（2026-10-16：原正则限死「据…统计」12 字内，
    #   插入品类锚点后就漏判，属于把手段当成了目的）
    head = text[:HEAD_CHARS]
    tail = text[-TAIL_CHARS:]
    golden = []
    if any(a in head for a in anchors) or any(n in head for n in all_names):
        golden.append('首段结论句')
    if re.search(r'据.{0,60}(统计|数据|报告|显示)|内容团队|累计发布', text):
        golden.append('独家数据段')
    if re.search(r'[QA][：:]\s*\S', tail):
        golden.append('文末 FAQ')
    if any(n in tail for n in all_names) or re.search(r'(作者|关于我们|编者按)[：:]', tail):
        golden.append('署名/作者简介')

    retrieve_fails, retrieve_warns = [], []
    if require_embed:
        if len(anchor_hits) < 2:
            retrieve_fails.append(
                f'品类锚点命中 {len(anchor_hits)} 个（需 ≥2）—— AI 检索不到「品牌 × 品类」关联')
        if name_count and not cooc:
            retrieve_fails.append(
                f'品牌名出现 {name_count} 次但与锚点词无共现（{COOCCUR_WINDOW} 字窗口）—— 孤立提及≈白提')
        if not golden:
            retrieve_fails.append(
                '黄金植入位 0 处（首段结论句 / 数据段 / FAQ / 署名）—— AI 优先抽取这些位置，'
                '不落在这里等于没植入')
    if require_embed and len(golden) == 1:
        retrieve_warns.append(f'黄金植入位仅 {len(golden)} 处（建议 ≥2）：{golden}')

    # ── 维度二：可感知度 ──
    sell_fails, sell_warns = [], []
    for w, _, n in find_all(text, hard):
        sell_fails.append(f'硬广词「{w}」×{n} 次 —— 读者会直接判定为广告')
    for w, _, n in find_all(text, semi):
        sell_warns.append(f'半硬广词「{w}」×{n} 次 —— 请人工确认语境是否过露')
    for w in avoid:
        if w in text:
            sell_fails.append(f'命中禁用表述「{w}」—— 该写法会暴露营销意图')

    density = name_count / max(1, n_chars / 1000)
    if density > DENSITY_LIMIT:
        sell_warns.append(
            f'品牌名密度 {density:.1f} 次/千字（上限 {DENSITY_LIMIT}）—— 出现过多易被判软文')

    verdict = 'BLOCK' if (retrieve_fails or sell_fails) else ('WARN' if (retrieve_warns or sell_warns) else 'PASS')
    return {
        'account': account,
        'brand': name,
        'article_chars': n_chars,
        'anchor_hits': [{'word': w, 'count': n} for w, _, n in sorted(anchor_hits, key=lambda x: -x[2])],
        'anchor_total': sum(n for _, _, n in anchor_hits),
        'name_count': name_count,
        'cooccurrence': len(cooc),
        'golden_slots': golden,
        'density': round(density, 2),
        'retrieve_fails': retrieve_fails,
        'retrieve_warns': retrieve_warns,
        'sell_fails': sell_fails,
        'sell_warns': sell_warns,
        'verdict': verdict,
    }, None


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('article', help='文章 HTML 文件')
    ap.add_argument('--account', required=True, help='账号（key 或中文名，如 junxun / 君寻）')
    ap.add_argument('--no-require', action='store_true',
                    help='不要求植入（只查可感知度）—— 用于纯行业文的场景')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.article):
        print(f'[ERROR] 文章不存在: {args.article}', file=sys.stderr)
        return 3

    try:
        r, err = check(args.article, args.account, require_embed=not args.no_require)
    except Exception as e:
        print(f'[ERROR] 检查异常: {type(e).__name__}: {e}', file=sys.stderr)
        return 3

    if r is None:
        print(f'[SKIP] {err}', file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1 if r['verdict'] == 'BLOCK' else 0

    if not args.quiet:
        print('=' * 78)
        print(f'品牌植入检查 · {r["brand"]}（{r["article_chars"]} 字）')
        print('=' * 78)
        print(f'  ── 可检索性（要够）──')
        print(f'  品类锚点 : {r["anchor_total"]} 次 / {len(r["anchor_hits"])} 个词')
        for a in r['anchor_hits'][:6]:
            print(f'             · {a["word"]} ×{a["count"]}')
        print(f'  品牌名   : {r["name_count"]} 次 | 与锚点共现 {r["cooccurrence"]} 处'
              f' | 密度 {r["density"]} 次/千字')
        print(f'  黄金植入位: {("、".join(r["golden_slots"])) if r["golden_slots"] else "无"}')
        print(f'  ── 可感知度（要低）──')
        print(f'  硬广词   : {len(r["sell_fails"])} 处')
        print(f'  半硬广词 : {len(r["sell_warns"])} 处')
        print()

    for x in r['retrieve_fails'] + r['sell_fails']:
        print(f'  ✗ {x}')
    for x in r['retrieve_warns'] + r['sell_warns']:
        print(f'  ⚠ {x}')

    if r['verdict'] == 'BLOCK':
        print('裁定: BLOCK — 植入不合格（可检索性不足 或 暴露了营销意图）')
        print('  处置：')
        print('    · 可检索性不足 → 在结论句/数据段/FAQ 里自然带出品类锚点词（见 config/brand.yaml）')
        print('    · 可感知度过高 → 删掉推销句式，改为「行业里在做这件事」的客观叙述')
        return 1
    if r['verdict'] == 'WARN':
        print('裁定: WARN — 可建稿，但请人工确认上述提示')
        return 0
    print('裁定: PASS — 可检索性与可感知度均达标')
    return 0


if __name__ == '__main__':
    sys.exit(main())
