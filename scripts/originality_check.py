#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
originality_check.py — 改写稿原创度检测（对标微信原创校验 / 查重算法）

用途
    在 create_draft 之前，把「我们的改写稿」与「源文」做逐句比对，
    拦截照抄片段。微信原创校验按片段比对（连续长重复即判非原创），
    仅靠全局相似度不够，必须看「最长公共子串」和「高相似句」。

用法
    python originality_check.py <文章.html> --source <源文URL>
    python originality_check.py <文章.html> --source <源文URL> --json
    python originality_check.py <文章.html> --source-file <源文本地文件>

退出码
    0 = 通过（无高风险片段）
    1 = 存在高风险片段，禁止建稿，必须重写命中句
    2 = 无法比对（源文抓取失败 / 英文源 / 参数错误）——不算失败，但需人工确认
    3 = 脚本错误

判定阈值（可调）
    最长公共子串 LCS >= 25 字          → 硬拦截（连续照抄特征）
    单句 5-gram Dice >= 0.65           → 硬拦截
    全文 4-gram Dice >= 0.20           → 硬拦截
    高相似句(>=0.45) 占比 >= 20%       → 告警（不拦截，但建议重写）
"""
import sys
import os
import re
import io
import json
import gzip
import argparse
import html as htmlmod
import urllib.request

# ---------------- 阈值 ----------------
TH_LCS = 25           # 最长公共子串长度上限（字）
TH_SENT_DICE = 0.65   # 单句相似度上限
TH_GLOBAL_DICE = 0.20 # 全文 4-gram Dice 上限
TH_WARN_RATIO = 0.20  # 高相似句占比告警线
SENT_MIN_LEN = 12     # 参与比对的最短句长
NGRAM_SENT = 5        # 句级 n-gram
NGRAM_GLOBAL = 4      # 全局 n-gram

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')


def strip_html(h):
    """HTML → 纯文本"""
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    return re.sub(r'\s+', ' ', htmlmod.unescape(t)).strip()


def norm(s):
    """只保留中英文数字，用于 n-gram 比对"""
    return re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s)


def ngrams(s, n):
    s = norm(s)
    if len(s) < n:
        return set()
    return set(s[i:i + n] for i in range(len(s) - n + 1))


def dice(a, b, n):
    A, B = ngrams(a, n), ngrams(b, n)
    if not A or not B:
        return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


def split_sent(t):
    parts = re.split(r'[。！？!?；;\n]+', t)
    return [p.strip() for p in parts if len(p.strip()) >= SENT_MIN_LEN]


def lcs_len(a, b):
    """最长公共子串长度（滚动数组，防内存爆）"""
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0, ''
    if len(a) > len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    best = 0
    best_end = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ca = a[i - 1]
        for j in range(1, len(b) + 1):
            if ca == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
                    best_end = i
        prev = cur
    return best, a[max(0, best_end - best):best_end]


def fetch_text(url, timeout=25, max_bytes=3_000_000):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    raw = resp.read(max_bytes)
    if resp.headers.get('Content-Encoding') == 'gzip':
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return strip_html(raw.decode('utf-8', errors='replace'))


def chinese_ratio(s):
    han = len(re.findall(r'[\u4e00-\u9fff]', s))
    return han / max(1, len(s))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('article', help='我们的文章 HTML 文件')
    ap.add_argument('--source', help='源文 URL')
    ap.add_argument('--source-file', help='源文本地文本文件')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--quiet', action='store_true', help='只输出结论行')
    args = ap.parse_args()

    if not os.path.exists(args.article):
        print(f'[ERROR] 文章文件不存在: {args.article}', file=sys.stderr)
        return 3

    with open(args.article, encoding='utf-8') as f:
        our_raw = f.read()
    our = strip_html(our_raw)

    if args.source_file:
        if not os.path.exists(args.source_file):
            print(f'[SKIP] 源文文件不存在: {args.source_file}', file=sys.stderr)
            return 2
        with open(args.source_file, encoding='utf-8') as f:
            src = strip_html(f.read())
        src_desc = args.source_file
    elif args.source:
        try:
            src = fetch_text(args.source)
        except Exception as e:
            print(f'[SKIP] 源文抓取失败（{type(e).__name__}: {e}）— 无法比对，'
                  f'请人工确认原创度', file=sys.stderr)
            return 2
        src_desc = args.source
    else:
        print('[ERROR] 必须指定 --source 或 --source-file', file=sys.stderr)
        return 3

    if not src or len(src) < 100:
        print(f'[SKIP] 源文内容为空或过短（{len(src)} 字）— 无法比对', file=sys.stderr)
        return 2

    # 英文源（岚牧哒场景）：中英 n-gram 不可比
    if chinese_ratio(src) < 0.20:
        print('[SKIP] 源文为英文（岚牧哒场景），中文改写与英文源无法直接比对。'
              '风险点转为「与其他译者的撞车」，需人工评估。')
        return 2

    d4 = dice(our, src, NGRAM_GLOBAL)
    d6 = dice(our, src, 6)

    S = split_sent(our)
    R_grams = [ngrams(r, NGRAM_SENT) for r in split_sent(src)]

    hi = []
    for s in S:
        g = ngrams(s, NGRAM_SENT)
        best, best_ref = 0.0, ''
        for i, rg in enumerate(R_grams):
            if not g or not rg:
                continue
            dd = 2 * len(g & rg) / (len(g) + len(rg))
            if dd > best:
                best = dd
        if best >= 0.45:
            hi.append({'score': round(best, 3), 'sent': s})

    lcs, lcs_seg = lcs_len(our, src)

    n_hi, n_tot = len(hi), len(S)
    ratio = n_hi / n_tot if n_tot else 0.0

    fatal = []
    if lcs >= TH_LCS:
        fatal.append(f'最长公共子串 {lcs} 字（阈值 {TH_LCS}）: 「{lcs_seg[:40]}」')
    worst = max([h['score'] for h in hi], default=0.0)
    if worst >= TH_SENT_DICE:
        top = sorted(hi, key=lambda x: -x['score'])[0]
        fatal.append(f'单句相似度 {worst}（阈值 {TH_SENT_DICE}）: 「{top["sent"][:40]}」')
    if d4 >= TH_GLOBAL_DICE:
        fatal.append(f'全文相似度 {d4:.3f}（阈值 {TH_GLOBAL_DICE}）')

    warn = []
    if ratio >= TH_WARN_RATIO:
        warn.append(f'高相似句占比 {ratio * 100:.1f}%（告警线 {TH_WARN_RATIO * 100:.0f}%）')

    if args.json:
        print(json.dumps({
            'article': os.path.basename(args.article),
            'source': src_desc,
            'our_chars': len(our),
            'src_chars': len(src),
            'dice_4': round(d4, 4),
            'dice_6': round(d6, 4),
            'lcs': lcs,
            'lcs_segment': lcs_seg,
            'hi_sent': n_hi,
            'total_sent': n_tot,
            'hi_ratio': round(ratio, 4),
            'fatal': fatal,
            'warn': warn,
            'top_suspects': sorted(hi, key=lambda x: -x['score'])[:5],
            'verdict': 'BLOCK' if fatal else ('WARN' if warn else 'PASS'),
        }, ensure_ascii=False, indent=2))
        return 1 if fatal else 0

    if not args.quiet:
        print('=' * 78)
        print(f'原创度检测: {os.path.basename(args.article)}')
        print('=' * 78)
        print(f'  源文      : {src_desc}')
        print(f'  字数      : 我们 {len(our)} / 源文 {len(src)}')
        print(f'  全文相似度: 4-gram {d4:.3f}   6-gram {d6:.3f}   (阈值 {TH_GLOBAL_DICE})')
        print(f'  最长重复段: {lcs} 字   (阈值 {TH_LCS})')
        if lcs_seg:
            print(f'              「{lcs_seg[:50]}」')
        print(f'  高相似句  : {n_hi}/{n_tot} = {ratio * 100:.1f}%')
        if hi:
            print('  命中明细（需重写）:')
            for h in sorted(hi, key=lambda x: -x['score'])[:8]:
                print(f'    [{h["score"]:.3f}] {h["sent"][:56]}')
        print()

    if fatal:
        print('裁定: BLOCK — 存在照抄片段，禁止建稿')
        for x in fatal:
            print(f'  ✗ {x}')
        for x in warn:
            print(f'  ⚠ {x}')
        print('  处置: 重写上述命中句（事实保留、句式重构；引语改为转述）')
        return 1
    if warn:
        print('裁定: WARN — 可建稿，但建议重写高相似句后再发')
        for x in warn:
            print(f'  ⚠ {x}')
        return 0
    print('裁定: PASS — 无高风险片段')
    return 0


if __name__ == '__main__':
    sys.exit(main())
