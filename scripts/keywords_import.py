# -*- coding: utf-8 -*-
"""
keywords_import.py — 外部搜索热词导入 + 缺口分析

【为什么单独一个文件，而不是塞进 keywords.yaml】
  keywords.yaml     = 自有实体词（从历史标题提取），稳定，手写维护，带注释
  search_terms.yaml = 外部真实搜索词（各平台导入），会反复更新、整段重写
  两者生命周期不同：导入工具只重写后者，不会破坏前者的人写注释与排序。
  这也顺应「词表唯一真源」的纪律 —— 但真源分两类，各有各的维护方式。

【输入格式（自动识别，不挑食）】
  .csv  表头含 word/词/关键词/搜索词 → 词；reads/阅读/曝光/pv/count → 数据；source/来源 → 来源
        无表头则按「词,数字」或「词」逐行解析
  .txt  每行一条：「词」「词,数字」「词<TAB>数字」
  .json [{"word":"..","reads":12}] 或 {"words": [".."]}
  -     从 stdin 读（配合管道）

【用法】
  python keywords_import.py words.csv --platform 微信搜一搜 [--source "..."] [--dry-run]
  python keywords_import.py words.txt --platform 今日头条
  cat w.csv | python keywords_import.py - --platform 小红书 --dry-run

exit: 0=成功  2=参数/文件错误  3=解析或写入异常
"""
import sys, os, io, re, json, argparse, datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(os.path.dirname(HERE), 'config')
KEYWORDS_YAML = os.path.join(CONFIG_DIR, 'keywords.yaml')
SEARCH_YAML = os.path.join(CONFIG_DIR, 'search_terms.yaml')

_WORD_KEYS = {'word', '词', '关键词', '搜索词', '搜索', 'query', 'kw', 'keyword', 'name'}
_READS_KEYS = {'reads', 'read', '阅读', '阅读量', '阅读次数', '曝光', '曝光量', 'pv',
               'count', 'num', 'cnt', 'value', '次数'}
_SOURCE_KEYS = {'source', '来源', '平台', '渠道'}


def load_yaml(p):
    import yaml
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _to_int(x):
    if x is None:
        return 0
    m = re.search(r'\d+', str(x))
    return int(m.group(0)) if m else 0


def _norm_key(h):
    """列名归一。真实后台导出列名五花八门，先精确匹配再模糊包含。"""
    h = str(h).strip().lower()
    if h in _WORD_KEYS:
        return 'word'
    if h in _SOURCE_KEYS:
        return 'source'
    if h in _READS_KEYS:
        return 'reads'
    # 模糊：数字列（「图文阅读次数」「曝光人数」「搜索量」…）
    if any(k in h for k in ('阅读', '曝光', '点击', '浏览', '次数', '人数', 'read', 'pv', 'count', 'num', 'cnt', '量')):
        return 'reads'
    if any(k in h for k in ('词', '搜索', 'keyword', 'query', 'kw')):
        return 'word'
    return None


def parse_csv(text):
    import csv as _csv
    rows = [r for r in _csv.reader(io.StringIO(text)) if r and any(c.strip() for c in r)]
    if not rows:
        return []
    # 判断首行是否表头
    mapped = [_norm_key(c) for c in rows[0]]
    has_header = 'word' in mapped
    out = []
    if has_header:
        idx = {k: i for i, k in enumerate(mapped) if k}
        for r in rows[1:]:
            w = r[idx['word']].strip() if idx.get('word') is not None and idx['word'] < len(r) else ''
            if not w:
                continue
            rd = _to_int(r[idx['reads']]) if idx.get('reads') is not None and idx['reads'] < len(r) else 0
            sc = r[idx['source']].strip() if idx.get('source') is not None and idx['source'] < len(r) else ''
            out.append((w, rd, sc))
    else:
        for r in rows:
            out.append((r[0].strip(), _to_int(r[1]) if len(r) > 1 else 0,
                        r[2].strip() if len(r) > 2 else ''))
    return [x for x in out if x[0]]


def parse_text(text):
    out = []
    for line in text.splitlines():
        line = line.strip().strip('"').strip("'")
        if not line or line.startswith('#'):
            continue
        parts = re.split(r'[\t,，|]+', line)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            continue
        w = parts[0]
        rd = _to_int(parts[1]) if len(parts) > 1 and re.search(r'\d', parts[1]) else 0
        out.append((w, rd, ''))
    return out


def parse_any(path):
    """返回 [(word, reads, source)]"""
    if path == '-':
        text = sys.stdin.read()
    else:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, encoding='utf-8-sig') as f:
            text = f.read()

    ext = '' if path == '-' else os.path.splitext(path)[1].lower()
    if ext == '.json':
        d = json.loads(text)
        items = d if isinstance(d, list) else (d.get('words') or [])
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append((str(it.get('word', '')).strip(), _to_int(it.get('reads')), str(it.get('source', ''))))
            else:
                out.append((str(it).strip(), 0, ''))
        return [x for x in out if x[0]]
    if ext == '.csv':
        return parse_csv(text)
    # txt / 未知 / stdin：首行有逗号就按 CSV 试（可能是无后缀导出），否则按逐行
    first_line = text.splitlines()[0] if text.splitlines() else ''
    if ',' in first_line:
        got = parse_csv(text)
        if got:
            return got
    return parse_text(text)


def merge_platform(existing_platform, items, source):
    """把 items 并入某平台的 words。返回 (新 dict, 新增数, 更新数)"""
    cur = {}
    for it in (existing_platform or {}).get('words') or []:
        if isinstance(it, dict) and it.get('word'):
            cur[str(it['word'])] = _to_int(it.get('reads'))
        elif isinstance(it, str):
            cur[it] = 0

    new_cnt = upd_cnt = 0
    for w, rd, sc in items:
        if w in cur:
            if rd > cur[w]:
                cur[w] = rd
                upd_cnt += 1
        else:
            cur[w] = rd
            new_cnt += 1

    # 排序：有数据的按 reads 降序在前，无数据按原始顺序在后
    ordered = sorted(cur.items(), key=lambda kv: (-kv[1],))
    words = [{'word': w, 'reads': n} for w, n in ordered]

    node = {
        'source': source or (existing_platform or {}).get('source', '') or '（未标注来源）',
        'updated': datetime.date.today().isoformat(),
        'count': len(words),
        'words': words,
    }
    return node, new_cnt, upd_cnt


def gap_analysis(search_words):
    """用户搜的词 vs 我们的实体词表 —— 差集即机会点"""
    try:
        kw = load_yaml(KEYWORDS_YAML)
    except Exception:
        kw = {}
    ours = set()
    for sec in ('category', 'brand', 'search_terms'):
        for it in (kw.get(sec) or []):
            if isinstance(it, dict) and it.get('word'):
                ours.add(str(it['word']))
            elif isinstance(it, str):
                ours.add(it)
    gaps = [w for w in search_words if w and w not in ours]
    return ours, gaps


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('file', help='输入文件（.csv/.txt/.json）或 - 表示 stdin')
    ap.add_argument('--platform', required=True, help='平台名，如「微信搜一搜」「今日头条」')
    ap.add_argument('--source', default='', help='数据来源说明（写入文件备注）')
    ap.add_argument('--dry-run', action='store_true', help='只预览，不写文件')
    args = ap.parse_args()

    try:
        items = parse_any(args.file)
    except Exception as e:
        print(f'[FATAL] 读取/解析失败：{type(e).__name__}: {e}', file=sys.stderr)
        return 3

    if not items:
        print('[ERROR] 未解析出任何词 —— 检查文件格式（CSV 需 word 列；TXT 每行一个词）', file=sys.stderr)
        return 2

    try:
        doc = load_yaml(SEARCH_YAML)
    except Exception as e:
        print(f'[FATAL] search_terms.yaml 读取失败：{e}', file=sys.stderr)
        return 3

    doc.setdefault('version', 1)
    plats = doc.setdefault('platforms', {})
    node, new_cnt, upd_cnt = merge_platform(plats.get(args.platform), items, args.source)
    plats[args.platform] = node
    doc['updated'] = __import__('datetime').date.today().isoformat()

    print(f'[[导入报告]]')
    print(f'  平台      : {args.platform}')
    print(f'  来源      : {node["source"]}')
    print(f'  解析词数  : {len(items)}')
    print(f'  新增 {new_cnt} · 更新 {upd_cnt} · 平台累计 {node["count"]}')

    ours, gaps = gap_analysis([w for w, _, _ in items])
    if gaps:
        print()
        print(f'[[缺口分析]] 用户搜、但我们实体词表里没有的（机会点 {len(gaps)} 个）')
        for w in gaps[:20]:
            print(f'  · {w}')
        if len(gaps) > 20:
            print(f'  … 另有 {len(gaps) - 20} 个')
    else:
        print()
        print('[[缺口分析]] 导入词全部已在实体词表内（无需补充）')

    if args.dry_run:
        print()
        print('（--dry-run：未写入文件）')
        return 0

    try:
        import yaml
        with open(SEARCH_YAML, 'w', encoding='utf-8') as f:
            f.write('# ============================================================\n')
            f.write('# 外部搜索热词库 · 按平台分节（由 keywords_import.py 导入，可覆盖重写）\n')
            f.write('#\n')
            f.write('# 与 keywords.yaml 的分工：\n')
            f.write('#   keywords.yaml     = 我们的实体词（category/brand），从历史标题提取，稳定\n')
            f.write('#   search_terms.yaml = 真实搜索词（各平台后台导出），随平台更新，可反复导入\n')
            f.write('#\n')
            f.write('# 用法：写标题时优先选 reads 高的词，且放在前 12 字。\n')
            f.write('# ⚠️ 词必须与正文相符 —— 硬塞不相关热词会拉低完读率，反被降权。\n')
            f.write('# ============================================================\n')
            yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=1000)
        print()
        print(f'✅ 已写入 {SEARCH_YAML}')
    except Exception as e:
        print(f'[FATAL] 写入失败：{type(e).__name__}: {e}', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
