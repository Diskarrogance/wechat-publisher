#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
originality_rate.py — 原创率检测（多素材池覆盖度口径）

【与 originality_check.py 的分工 —— 不要混用】
    originality_check.py  单篇源文 · LCS / Dice 相似度 → 防「照抄那一篇」
    originality_rate.py   多篇素材池 · 覆盖度 → 算「原创率」这个百分比指标
    前者回答「像不像源文」，后者回答「有多少是自己的」。两个都跑。

【原创率怎么算】
    步长 K（默认 8）的滑窗扫全文，凡是「在素材池里出现过」的 K 连字窗口，
    其覆盖的字符全部标为重复；合并重叠区间后：
        原创率 = 1 - 被判重复的字符数 / 正文总字符数
    K=8 的取舍：短到能发现换词不换结构的改写，长到能放过「近年来/随着…」这类套话与
    通用搭配。数字、专有名词会被判重复 —— 这是**预期行为**：保留事实本就该占一部分，
    所以阈值定 80%（即允许 20% 是引用的事实/数据）。

【用法】
    python originality_rate.py <文章.html> --materials 素材1.txt 素材2.txt ...
    python originality_rate.py <文章.html> --materials-dir <素材目录>
    python originality_rate.py <文章.html> --materials-dir . --min 0.80

【退出码】
    0 = 通过（原创率 >= 阈值）
    1 = 未通过（原创率 < 阈值）→ 禁止建稿
    2 = 无法检测（素材池为空 / 素材全为英文 / 参数问题）——不算失败，但需人工确认
    3 = 脚本错误
"""
import sys
import os
import re
import glob
import html as htmlmod
import argparse

# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

DEFAULT_K = 8             # 连续多少字算「一段重复」
DEFAULT_MIN = 0.80        # 原创率阈值
MIN_SOURCE_CHARS = 100    # 素材太短不参与
CN_RATIO_MIN = 0.20       # 素材中文占比低于此值 → 视为外文源，跳过


def strip_html(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', htmlmod.unescape(t)).strip()


def norm(s):
    """只保留中英文数字 —— 比对时忽略标点与空白，避免用标点刷原创率"""
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s)


def cn_ratio(s):
    han = len(re.findall(r'[\u4e00-\u9fff]', s))
    return han / max(1, len(s))


def load_text(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        raw = f.read()
    return strip_html(raw) if path.lower().endswith(('.html', '.htm')) else re.sub(r'\s+', ' ', raw).strip()


def collect_materials(args):
    """返回 [(路径, 文本)]，已剔除过短与非中文源"""
    paths = list(args.materials or [])
    if args.materials_dir:
        for ext in ('*.txt', '*.html', '*.htm', '*.md'):
            paths += sorted(glob.glob(os.path.join(args.materials_dir, ext)))
    seen, out, skipped = set(), [], []
    for p in paths:
        ap = os.path.abspath(p)
        if ap in seen or not os.path.isfile(ap):
            continue
        seen.add(ap)
        try:
            t = load_text(ap)
        except Exception as e:
            skipped.append((p, f'读取失败 {type(e).__name__}'))
            continue
        if len(t) < MIN_SOURCE_CHARS:
            skipped.append((p, f'过短 {len(t)} 字'))
            continue
        if cn_ratio(t) < CN_RATIO_MIN:
            skipped.append((p, '非中文源（n-gram 不可比，翻译场景请人工评估）'))
            continue
        out.append((p, t))
    return out, skipped


def build_source_grams(materials, k):
    """素材池的 K-gram 集合（合并全部素材）"""
    grams = set()
    for _, t in materials:
        s = norm(t)
        for i in range(len(s) - k + 1):
            grams.add(s[i:i + k])
    return grams


def mark_duplicate_ranges(article_norm, source_grams, k):
    """返回 (被标记的字符下标集合, 命中窗口列表[按长度降序])"""
    flagged = set()
    hits = []
    n = len(article_norm)
    i = 0
    while i <= n - k:
        w = article_norm[i:i + k]
        if w in source_grams:
            # 向后延伸，把连续命中合并成一整段
            j = i + k
            while j <= n - k and article_norm[j:j + k] in source_grams:
                j += 1
            flagged.update(range(i, j))
            hits.append({'start': i, 'len': j - i, 'text': article_norm[i:j]})
            i = j
        else:
            i += 1
    return flagged, hits


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('article', help='我们的文章（.html / .txt）')
    ap.add_argument('--materials', nargs='*', default=[], help='素材文件（可多个）')
    ap.add_argument('--materials-dir', default='', help='素材目录（扫描其中 .txt/.html/.md）')
    ap.add_argument('-k', '--window', type=int, default=DEFAULT_K,
                    help=f'连续多少字算一段重复（默认 {DEFAULT_K}；调小更严，调大更松）')
    ap.add_argument('--min', type=float, default=DEFAULT_MIN,
                    help=f'原创率阈值（默认 {DEFAULT_MIN}）')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--quiet', action='store_true', help='只输出结论')
    args = ap.parse_args()

    if not os.path.exists(args.article):
        print(f'[ERROR] 文章不存在: {args.article}', file=sys.stderr)
        return 3
    if args.window < 4:
        print('[ERROR] --window 过小（<4），会产生大量误报；建议 6~12', file=sys.stderr)
        return 2

    try:
        art = load_text(args.article)
    except Exception as e:
        print(f'[ERROR] 文章读取失败: {type(e).__name__}: {e}', file=sys.stderr)
        return 3

    materials, skipped = collect_materials(args)
    if not materials:
        print('[SKIP] 素材池为空 —— 无法计算原创率（请用 --materials 或 --materials-dir 提供素材）',
              file=sys.stderr)
        for p, why in skipped[:10]:
            print(f'       已跳过 {os.path.basename(p)}: {why}', file=sys.stderr)
        return 2

    art_norm = norm(art)
    if len(art_norm) < 200:
        print(f'[SKIP] 正文过短（{len(art_norm)} 字），原创率无统计意义', file=sys.stderr)
        return 2

    src_grams = build_source_grams(materials, args.window)
    flagged, hits = mark_duplicate_ranges(art_norm, src_grams, args.window)

    total = len(art_norm)
    dup = len(flagged)
    rate = 1 - dup / total

    # 素材贡献度：每篇素材单独比对，看谁贡献了多少重复字
    contrib = []
    for p, t in materials:
        g = build_source_grams([(p, t)], args.window)
        f, _ = mark_duplicate_ranges(art_norm, g, args.window)
        if f:
            contrib.append((os.path.basename(p), len(f)))
    contrib.sort(key=lambda x: -x[1])
    top_hits = sorted(hits, key=lambda h: -h['len'])[:8]

    result = {
        'article': os.path.basename(args.article),
        'article_chars': total,
        'materials': len(materials),
        'materials_chars': sum(len(norm(t)) for _, t in materials),
        'window': args.window,
        'dup_chars': dup,
        'dup_ratio': round(dup / total, 4),
        'originality': round(rate, 4),
        'threshold': args.min,
        'pass': rate >= args.min,
        'top_blocks': [{'len': h['len'], 'text': h['text'][:60]} for h in top_hits],
        'contrib': contrib[:8],
        'skipped': [{'file': os.path.basename(p), 'why': w} for p, w in skipped],
    }

    if args.json:
        import json
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['pass'] else 1

    if not args.quiet:
        print('=' * 78)
        print(f'原创率检测（覆盖度口径 · 连续 {args.window} 字为判定单元）')
        print('=' * 78)
        print(f'  文章      : {result["article"]}（{total} 字）')
        print(f'  素材池    : {len(materials)} 篇 / {result["materials_chars"]} 字')
        for p, _ in materials[:6]:
            print(f'              · {os.path.basename(p)}')
        if len(materials) > 6:
            print(f'              … 另有 {len(materials) - 6} 篇')
        print(f'  判定重复  : {dup} 字（{dup / total * 100:.1f}%）')
        print(f'  原 创 率  : {rate * 100:.1f}%   （阈值 {args.min * 100:.0f}%）'
              f'   {"✅ 通过" if result["pass"] else "❌ 未达标"}')
        if top_hits:
            print('  最长重复段:')
            for h in top_hits[:5]:
                print(f'     {h["len"]:3d} 字  {h["text"][:56]}')
        if contrib:
            print('  素材贡献  :')
            for name, n in contrib[:5]:
                print(f'     {n:4d} 字（{n / dup * 100:.0f}%）  {name}')
        if skipped:
            print(f'  已跳过    : {len(skipped)} 项（过短 / 外文源）')
        print()

    if result['pass']:
        print(f'裁定: PASS — 原创率 {rate * 100:.1f}% ≥ {args.min * 100:.0f}%')
        return 0
    print(f'裁定: BLOCK — 原创率 {rate * 100:.1f}% < {args.min * 100:.0f}%，禁止建稿')
    print('  处置: 上述「最长重复段」逐段重写 —— 事实数字可留，包着它的句子必须重构；')
    print('        若整段都靠素材支撑，说明该段还停留在「改写」而非「自己写」。')
    return 1


if __name__ == '__main__':
    sys.exit(main())
