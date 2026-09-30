#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
geoready_check.py — GEO 就绪度 + 原创可声明性 硬关卡

为什么要有它
    微信原创声明的比对本质是「在先发布比对」——只要站内没有更早的高度相似文章即可声明。
    所以「以后每篇都能过原创」要靠三件事同时成立：
      ① 与源文改写幅度够（相似度 < 30%、无长连续重复）
      ② 有足够「自己的东西」（可检索化四要素 = 信息增量）
      ③ 与本站历史正文不重合（防自己号撞车）
    这三条靠 prompt 里写文字要求是拦不住的（历史教训：URL 去重曾是伪代码注释，同一源文发 5 次），
    必须在建稿前用代码硬拦。

用法
    python geoready_check.py <文章.html> --account junxun
    python geoready_check.py <文章.html> --account lanmuda --source-file src.txt
    python geoready_check.py <文章.html> --account junxun --json
    python geoready_check.py --account junxun --update-index --title "标题" --article <html>

退出码
    0 = PASS（可建稿）
    1 = BLOCK（硬缺陷，禁止建稿）
    2 = 无法完整检查（缺源文 / 站内无索引），不阻断但需人工确认
    3 = 脚本错误

判定
    FAIL: 首段结论句缺失 · 独家数据段缺失或数字失实 · 末尾 FAQ < 2 组 ·
          正文 < 600 字 · 与源文 LCS >= 25 字 / 单句 Dice >= 0.65 / 全文 Dice >= 0.30 ·
          与站内历史正文 Jaccard >= 0.45
    WARN: 品牌嵌入 0 次或 > 3 次 · 与站内历史正文 Jaccard 0.30~0.45 · 数据段数字与库有偏差
"""
import argparse
import hashlib
import html as htmlmod
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from originality_check import lcs_len, dice, strip_html
    import create_draft as _cd
except ImportError as e:  # 依赖缺失时给明确报错，不静默放行
    print(f'[FATAL] 无法导入依赖模块: {e}', file=sys.stderr)
    sys.exit(3)

# ── 阈值 ────────────────────────────────────────────────────
MIN_BODY_CHARS = 600      # 正文最低字数（微信原创底线 ~300，取保守值）
TH_LCS = 25               # 与源文最长连续重复（字）
TH_SENT_DICE = 0.65       # 与源文单句相似度
TH_SRC_GLOBAL = 0.30      # 与源文全文相似度（微信公开红线 30%）
TH_SITE_BLOCK = 0.45      # 与站内历史正文 Jaccard 硬拦线
TH_SITE_WARN = 0.30       # 站内重合告警线
FAQ_MIN = 2               # 末尾 FAQ 最少组数
FAQ_WINDOW = 500          # 「末尾」窗口（字）
DATA_TOL = 2              # 数据段数字与库行数容差（向上）
DATA_TOL_DOWN = 30        # 向下容差（防瞎写小数）
N_HASH = 64               # MinHash 签名长度
QR_HINT = ('mmecoa', '粉丝群', '扫码')

BRAND = {'junxun': '君寻智能', 'lanmuda': '岚牧哒'}


# ── 文本处理 ────────────────────────────────────────────────
def to_text(h):
    """HTML → 带换行的纯文本（保留段落边界）"""
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', '\n', h, flags=re.I)
    h = re.sub(r'</(p|section|div|h[1-6]|li|blockquote|td|tr)\s*>', '\n', h, flags=re.I)
    t = re.sub(r'<[^>]+>', '', h)
    t = htmlmod.unescape(t)
    t = re.sub(r'[ \t\u3000\u00a0]+', ' ', t)
    return re.sub(r'\n{2,}', '\n', t).strip()


def body_only(txt):
    """剥掉文末二维码块（含二维码文案的尾段），FAQ 与字数判定都基于正文"""
    lines = [x for x in txt.split('\n') if x.strip()]
    keep = []
    for ln in lines:
        if any(k in ln for k in QR_HINT) and ('扫码' in ln or '粉丝群' in ln):
            continue
        if re.match(r'^\s*[（(]?长按|^\s*[（(]?扫描|二维码', ln):
            continue
        keep.append(ln)
    return '\n'.join(keep)


def ngrams(s, n=4):
    s = re.sub(r'[^\u4e00-\u9fffA-Za-z0-9]', '', s)
    if len(s) < n:
        return set()
    return set(s[i:i + n] for i in range(len(s) - n + 1))


def _h(gram, seed):
    return int.from_bytes(
        hashlib.md5(f'{seed}|{gram}'.encode('utf-8')).digest()[:8], 'big')


def minhash(grams, n=N_HASH):
    """64 维 MinHash 签名（Jaccard 估计用）"""
    if not grams:
        return []
    return [min(_h(g, s) for g in grams) for s in range(n)]


def jaccard_est(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


# ── 配置读取 ────────────────────────────────────────────────
def load_accounts():
    """accounts.yaml 全量配置（顶层含 global / accounts 列表）"""
    return _cd.load_config()


def history_rows(db_path):
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        c = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        n = c.execute('SELECT COUNT(*) FROM history').fetchone()[0]
        c.close()
        return n
    except Exception:
        return None


def index_path(db_path, key):
    d = os.path.dirname(db_path) if db_path else os.path.join(
        os.path.expanduser('~'), '.qclaw', 'wechatlog', key)
    return os.path.join(d, 'body_index.json')


def load_index(p):
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        return d.get('items', []) if isinstance(d, dict) else (d or [])
    except Exception:
        return []


def save_index(p, items):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump({'version': 1, 'items': items}, f, ensure_ascii=False, indent=1)


# ── 四项要素检查 ────────────────────────────────────────────
def check_lead_sentence(txt):
    """① 首段结论句：正文起始 200 字内必须成句（含句号），且首段不过短"""
    head = txt[:200]
    m = re.search(r'[。！？!?]', head)
    if not m:
        return False, '正文起始 200 字内未出现完整句子（首段结论句缺失）'
    first = head[:m.end()]
    if len(first) < 25:
        return False, f'首句仅 {len(first)} 字，过短（需 25 字以上的结论句）'
    return True, f'首句 {len(first)} 字'


def check_data_section(txt, rows):
    """② 独家数据段：必须出现「累计发布 N 篇」，且 N 与库行数相符（防编数据）"""
    m = re.search(r'累计发布\s*(\d+)\s*篇', txt)
    if not m:
        return False, '未找到独家数据段（需「…累计发布 N 篇…」句式）', None
    n = int(m.group(1))
    if rows is None:
        return True, f'数据段存在（{n} 篇），库不可读，跳过数字校验', n
    if n > rows + DATA_TOL:
        return False, f'数据段数字虚高：文中 {n} 篇 > 库实际 {rows} 篇（可能编造）', n
    if n < rows - DATA_TOL_DOWN:
        return True, f'⚠ 数据段数字偏低：文中 {n} 篇 vs 库 {rows} 篇', n
    return True, f'数据段数字相符（{n} 篇 / 库 {rows} 篇）', n


def check_faq(txt):
    """③ 末尾 FAQ：文末窗口内 >= 2 组问答"""
    tail = txt[-FAQ_WINDOW:]
    qs = tail.count('？') + tail.count('?')
    marks = len(re.findall(r'[问答QA]\s*[:：]', tail))
    ok = qs >= FAQ_MIN and marks >= 1
    return ok, f'文末 {FAQ_WINDOW} 字内问号 {qs} 个 / 问答标记 {marks} 处'


def check_brand(txt, key):
    """④ 品牌嵌入（GEO 要求，非原创硬条件 → 只告警）"""
    b = BRAND.get(key, '')
    if not b:
        return True, '未知账号，跳过品牌检查'
    n = txt.count(b)
    if n == 0:
        return False, f'品牌「{b}」未出现（GEO 建议 1~2 次）'
    if n > 3:
        return False, f'品牌「{b}」出现 {n} 次，过密（建议 1~2 次）'
    return True, f'品牌「{b}」出现 {n} 次'


# ── 主检查 ──────────────────────────────────────────────────
def run_html(raw, key, source_file=None, name='<inline>'):
    """核心检查入口：接收 HTML 字符串（create_draft 的 content 就是字符串）"""
    txt = to_text(raw)
    body = body_only(txt)

    fails, warns, info = [], [], {}

    # 长度
    n_body = len(re.sub(r'\s', '', body))
    info['body_chars'] = n_body
    if n_body < MIN_BODY_CHARS:
        fails.append(f'正文 {n_body} 字 < {MIN_BODY_CHARS} 字（原创声明字数不足风险）')

    # ① 结论句
    ok, msg = check_lead_sentence(body)
    info['lead'] = msg
    if not ok:
        fails.append(msg)

    # ② 数据段
    acc = _cd.resolve_account(load_accounts(), key) or {}
    rows = history_rows(acc.get('history_db'))
    ok, msg, num = check_data_section(body, rows)
    info['data'] = msg
    info['data_num'] = num
    info['db_rows'] = rows
    if not ok:
        fails.append(msg)
    elif msg.startswith('⚠'):
        warns.append(msg)

    # ③ FAQ
    ok, msg = check_faq(body)
    info['faq'] = msg
    if not ok:
        fails.append(f'末尾 FAQ 不足：{msg}（需 2~3 组问答）')

    # ④ 品牌（告警级）
    ok, msg = check_brand(body, key)
    info['brand'] = msg
    if not ok:
        warns.append(msg)

    # ⑤ 与源文比对
    src_res = None
    if source_file:
        if not os.path.exists(source_file):
            warns.append(f'源文文件不存在，跳过源文比对：{source_file}')
        else:
            with open(source_file, encoding='utf-8', errors='replace') as f:
                src_raw = f.read()
            src = strip_html(src_raw) if '<' in src_raw[:2000] else src_raw
            cn = len(re.findall(r'[\u4e00-\u9fff]', src)) / max(1, len(src))
            if len(src) < 100:
                warns.append(f'源文过短（{len(src)} 字），跳过比对')
            elif cn < 0.20:
                # 英文源（岚牧哒）：改为结构风险提示
                info['src_mode'] = 'english'
                warns.append('源文为英文（翻译场景），无法直接比对；'
                             '风险转为「与其他译者撞车」，须确保观点/数据段为自撰')
            else:
                info['src_mode'] = 'zh'
                lcs, seg = lcs_len(body, src)
                d4 = dice(body, src, 4)
                info['src_lcs'] = lcs
                info['src_lcs_seg'] = seg
                info['src_dice4'] = round(d4, 4)
                if lcs >= TH_LCS:
                    fails.append(f'与源文最长连续重复 {lcs} 字 >= {TH_LCS}：「{seg[:40]}」')
                if d4 >= TH_SRC_GLOBAL:
                    fails.append(f'与源文全文相似度 {d4:.3f} >= {TH_SRC_GLOBAL}')
                # 单句比对
                worst, worst_s = 0.0, ''
                sents = [x.strip() for x in re.split(r'[。！？!?；;\n]+', body)
                         if len(x.strip()) >= 12]
                R = [ngrams(x, 5) for x in re.split(r'[。！？!?；;\n]+', src)
                     if len(x.strip()) >= 12]
                for s in sents:
                    g = ngrams(s, 5)
                    if not g:
                        continue
                    for rg in R:
                        if not rg:
                            continue
                        dd = 2 * len(g & rg) / (len(g) + len(rg))
                        if dd > worst:
                            worst, worst_s = dd, s
                info['src_sent_dice'] = round(worst, 3)
                if worst >= TH_SENT_DICE:
                    fails.append(f'与源文单句相似度 {worst:.3f} >= {TH_SENT_DICE}：'
                                 f'「{worst_s[:40]}」')
                src_res = (lcs, d4, worst)
    else:
        info['src_mode'] = 'none'
        warns.append('未提供源文（--source-file），跳过改写幅度比对')

    # ⑥ 站内撞车（正文级）
    ip = index_path(acc.get('history_db'), key)
    items = load_index(ip)
    sig_new = minhash(ngrams(body))
    if not items:
        warns.append(f'站内正文索引为空（{ip}），本次无法比对自身历史；建稿后自动写入')
    else:
        best, best_it = 0.0, None
        for it in items:
            j = jaccard_est(sig_new, it.get('sig') or [])
            if j > best:
                best, best_it = j, it
        info['site_jaccard'] = round(best, 3)
        if best_it:
            info['site_match'] = f'{best_it.get("date","?")} {best_it.get("title","")[:30]}'
        if best >= TH_SITE_BLOCK:
            fails.append(f'与本站历史正文重合度 {best:.3f} >= {TH_SITE_BLOCK}'
                         f'（撞车：{info.get("site_match","")}）')
        elif best >= TH_SITE_WARN:
            warns.append(f'与本站历史正文重合度 {best:.3f}（告警线 {TH_SITE_WARN}）')

    return {
        'article': name,
        'account': key,
        'info': info,
        'fails': fails,
        'warns': warns,
        'sig': sig_new,
        'src_result': src_res,
        'verdict': 'BLOCK' if fails else ('WARN' if warns else 'PASS'),
    }


def run(html_path, key, source_file=None):
    """文件入口：读 HTML 文件后走 run_html"""
    with open(html_path, encoding='utf-8') as f:
        raw = f.read()
    return run_html(raw, key, source_file, os.path.basename(html_path))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('article', nargs='?', help='文章 HTML 文件')
    ap.add_argument('--account', required=True, help='账号 key 或中文名（junxun / 君寻）')
    ap.add_argument('--source-file', dest='source_file', help='源文纯文本文件')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--update-index', action='store_true',
                    help='把该文正文指纹写入站内索引（建稿成功后调用）')
    ap.add_argument('--title', help='配合 --update-index：文章标题')
    ap.add_argument('--date', help='配合 --update-index：日期 YYYY-MM-DD')
    args = ap.parse_args()

    if not args.article:
        print('[ERROR] 必须指定文章 HTML 文件', file=sys.stderr)
        return 3
    if not os.path.exists(args.article):
        print(f'[ERROR] 文章文件不存在: {args.article}', file=sys.stderr)
        return 3

    try:
        key = _cd.normalize_key(args.account)
    except Exception:
        key = args.account
    acc = _cd.resolve_account(load_accounts(), args.account) or {}
    if not acc:
        print(f'[ERROR] 账号不存在: {args.account}（归一化后 {key}）', file=sys.stderr)
        return 3

    # 仅写索引模式
    if args.update_index:
        try:
            with open(args.article, encoding='utf-8') as f:
                body = body_only(to_text(f.read()))
            ip = index_path(acc.get('history_db'), key)
            items = load_index(ip)
            sig = minhash(ngrams(body))
            import datetime as _dt
            date = args.date or _dt.date.today().isoformat()
            items = [x for x in items if not (x.get('date') == date
                                              and x.get('title') == (args.title or ''))]
            items.append({'date': date, 'title': args.title or '',
                          'chars': len(re.sub(r'\s', '', body)), 'sig': sig})
            save_index(ip, items)
            print(f'[index] 已写入 {key} 站内正文索引（共 {len(items)} 篇）: {ip}')
            return 0
        except Exception as e:
            print(f'[ERROR] 写索引失败: {type(e).__name__}: {e}', file=sys.stderr)
            return 3

    try:
        r = run(args.article, key, args.source_file)
    except Exception as e:
        print(f'[ERROR] 检查异常: {type(e).__name__}: {e}', file=sys.stderr)
        return 3

    if args.json:
        r.pop('sig', None)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 1 if r['fails'] else 0

    if not args.quiet:
        print('=' * 78)
        print(f'GEO 就绪度 / 原创可声明性检查: {r["article"]}')
        print('=' * 78)
        i = r['info']
        print(f'  正文字数  : {i.get("body_chars")}')
        print(f'  首段结论句: {i.get("lead")}')
        print(f'  独家数据段: {i.get("data")}')
        print(f'  末尾 FAQ  : {i.get("faq")}')
        print(f'  品牌嵌入  : {i.get("brand")}')
        if i.get('src_mode') == 'zh':
            print(f'  源文比对  : LCS {i.get("src_lcs")} 字 | '
                  f'全文 Dice {i.get("src_dice4")} | 单句最高 {i.get("src_sent_dice")}')
        elif i.get('src_mode') == 'english':
            print('  源文比对  : 英文源，跳过直接比对')
        if i.get('site_jaccard') is not None:
            print(f'  站内重合  : {i.get("site_jaccard")}'
                  f'{"  ← " + i.get("site_match", "") if i.get("site_match") else ""}')
        print()

    if r['fails']:
        print('裁定: BLOCK — 存在硬缺陷，禁止建稿')
        for x in r['fails']:
            print(f'  ✗ {x}')
        for x in r['warns']:
            print(f'  ⚠ {x}')
        return 1
    if r['warns']:
        print('裁定: WARN — 可建稿，但请关注下列项')
        for x in r['warns']:
            print(f'  ⚠ {x}')
        return 0
    print('裁定: PASS — 可检索化四要素齐全，原创可声明条件满足')
    return 0


if __name__ == '__main__':
    sys.exit(main())
