#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
geo_adapt.py — 多平台内容适配校验器（GEO 主轴）

为什么这样设计
    多平台分发的目的**不是"发得多"，而是补搜索/推荐入口**（详见 config/platforms.yaml 头部）。
    一份母稿要变成 N 个平台的版本，靠人记规则必然漂移 —— 所以规则落在
    `config/platforms.yaml`（数据），校验落在本脚本（代码强制）。
    这符合项目一贯原则：**代码强制胜过 Agent 自觉**。

分工
    config/platforms.yaml  = 平台能力矩阵 + GEO 规则（唯一真源，改规则改那里）
    本脚本                 = 按规则校验某一个平台的适配版本
    AI（执行会话）          = 按校验反馈改写，直到通过

用法
    python geo_adapt.py list                                  # 列出平台与优先级
    python geo_adapt.py matrix                                # GEO 入口矩阵（哪个平台补哪个入口）
    python geo_adapt.py check <platform> --title "标题"
    python geo_adapt.py check <platform> --title "标题" --content a.html --tags "AI玩具,机器人"
    python geo_adapt.py guide <platform>                      # 输出该平台的完整适配要求

退出码
    0 = 通过（可有告警）
    1 = 不通过（需改）
    2 = 参数 / 配置错误
    3 = 脚本错误
"""
import argparse
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_THIS)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _THIS)

PLATFORMS_YAML = os.path.join(_ROOT, 'config', 'platforms.yaml')

# 跨平台通用禁项（对「非微信」平台生效）——
# 这些在公众号里是必需项，搬到外部平台就是引流违规/降权项。
GENERIC_FORBID = [
    (r'mmecoa', '企业群二维码图片'),
    (r'粉丝群', '「粉丝群」引导文案'),
    (r'扫码', '「扫码」引导'),
    (r'二维码', '二维码'),
    (r'关注公众号', '跨平台引流话术'),
    (r'微信搜索', '跨平台引流话术'),
    (r'微信号', '联系方式'),
    (r'\b1[3-9]\d{9}\b', '手机号'),
]

_NO_QR_PLATFORMS = ('wechat_mp',)      # 只有公众号允许/要求二维码


def load_platforms():
    try:
        import yaml
    except ImportError:
        print('[FATAL] 需要 pyyaml', file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(PLATFORMS_YAML):
        print(f'[FATAL] 找不到配置: {PLATFORMS_YAML}', file=sys.stderr)
        sys.exit(2)
    with open(PLATFORMS_YAML, encoding='utf-8') as f:
        d = yaml.safe_load(f) or {}
    return d.get('platforms') or {}


def strip_html(h):
    try:
        from originality_check import strip_html as _sh
        return _sh(h)
    except Exception:
        h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S | re.I)
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()


def read_content(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    if path.lower().endswith('.json'):
        try:
            import json
            return json.loads(raw).get('content', '')
        except Exception:
            return raw
    return strip_html(raw) if '<' in raw[:2000] else raw


def keywords():
    try:
        from validate_title import _keywords
        return _keywords()
    except Exception:
        return []


def has_entity_in_head(title, n):
    head = title[:n] if n else title
    if re.search(r'[A-Za-z][A-Za-z0-9\-]{1,}', head):
        return True, '品牌/产品名(英文)'
    for w in keywords():
        if w in head:
            return True, w
    return False, ''


def check(pid, plat, title='', content='', tags=None):
    fails, warns, info = [], [], []
    t = plat.get('title') or {}
    b = plat.get('body') or {}
    tg = plat.get('tags') or {}

    # ── 标题 ──
    if title:
        n = len(title)
        if t.get('max'):
            if n > t['max']:
                fails.append(f'标题 {n} 字 > 该平台上限 {t["max"]} 字')
            elif n > t['max'] - 3:
                warns.append(f'标题 {n} 字，接近上限 {t["max"]} 字（搜索/信息流易截断）')
        if t.get('min') and n < t['min']:
            fails.append(f'标题 {n} 字 < 该平台下限 {t["min"]} 字')
        hn = t.get('must_have_entity_in_head') or 0
        if hn:
            ok, w = has_entity_in_head(title, hn)
            if ok:
                info.append(f'前 {hn} 字命中实体：{w}')
            else:
                fails.append(f'前 {hn} 字无「品牌/品类实体」（实为「{title[:hn]}」）'
                             f'→ 该平台搜索匹配率低')
    else:
        if t.get('max') not in (0, None):
            warns.append('未提供标题')

    # ── 正文 ──
    if content:
        body = strip_html(content) if '<' in content[:2000] else content
        nc = len(re.sub(r'\s', '', body))
        lo, hi = b.get('min_chars') or 0, b.get('max_chars') or 0
        if lo and nc < lo:
            fails.append(f'正文 {nc} 字 < 该平台建议下限 {lo} 字')
        if hi and nc > hi:
            fails.append(f'正文 {nc} 字 > 该平台建议上限 {hi} 字（该平台不吃长文）')
        for key in (b.get('require') or []):
            info.append(f'需人工确认必备项：{key}')
    else:
        warns.append('未提供正文（跳过正文校验）')

    # ── 跨平台禁项 ──
    if content and pid not in _NO_QR_PLATFORMS:
        text = strip_html(content) if '<' in content[:2000] else content
        hits = []
        for pat, label in GENERIC_FORBID:
            if re.search(pat, text, re.I):
                hits.append(label)
        if hits:
            fails.append(f'含 {len(hits)} 项跨平台禁项（公众号有、外部平台降权）：'
                         f'{"、".join(dict.fromkeys(hits))}')

    # ── 标签 ──
    if tg.get('required'):
        cnt = len([x for x in (tags or []) if x.strip()])
        want = tg.get('count') or [0, 0]
        if cnt == 0:
            fails.append(f'该平台要求标签 {want[0]}~{want[1]} 个，当前 0 个')
        elif want and not (want[0] <= cnt <= want[1]):
            warns.append(f'标签 {cnt} 个，建议 {want[0]}~{want[1]} 个')
        else:
            info.append(f'标签 {cnt} 个（符合 {want[0]}~{want[1]}）')

    return fails, warns, info


def cmd_list(plats):
    print('=' * 78)
    print(f'{"平台":<14}{"优先级":<8}{"状态":<20}{"发布方式":<10} 推荐')
    print('-' * 78)
    for pid, p in sorted(plats.items(), key=lambda kv: kv[1].get('priority', 99)):
        pub = (p.get('publish') or {}).get('method', '-')
        rec = '✅' if (p.get('geo') or {}).get('recommend') else '❌'
        print(f'{pid:<14}{p.get("priority","-"):<8}{p.get("status","-"):<20}{pub:<10} {rec}')
    print('=' * 78)
    print('提示：推荐=❌ 的平台拿不到公域推荐分发（如公众号服务号）')


def cmd_matrix(plats):
    print('=' * 78)
    print('GEO 入口矩阵 —— 每加一个平台 = 多一个「能被搜到/被推荐」的入口')
    print('=' * 78)
    for pid, p in sorted(plats.items(), key=lambda kv: kv[1].get('priority', 99)):
        g = p.get('geo') or {}
        print(f'\n【{pid}】{p.get("name")}')
        print(f'  推荐能力: {"有" if g.get("recommend") else "无"}'
              f'{("  → " + g["recommend_note"][:60]) if g.get("recommend_note") else ""}')
        for e in (g.get('entries') or []):
            print(f'  · 入口: {e.get("name")}  [{e.get("confidence","?")}]'
                  f'{("  — " + e["note"][:50]) if e.get("note") else ""}')
        if g.get('ai_crawlers_blocked'):
            print(f'  ✗ 被屏蔽的爬虫: {"、".join(g["ai_crawlers_blocked"])}')


def cmd_guide(pid, plat):
    print('=' * 78)
    print(f'适配要求：{plat.get("name")}（{pid}）')
    print('=' * 78)
    t, b, tg = plat.get('title') or {}, plat.get('body') or {}, plat.get('tags') or {}
    print(f'  标题: {t.get("min",0)}~{t.get("max","∞")} 字'
          + (f'，前 {t.get("must_have_entity_in_head")} 字须含实体' if t.get('must_have_entity_in_head') else ''))
    if b:
        print(f'  正文: {b.get("min_chars",0)}~{b.get("max_chars") or "∞"} 字')
        for r in (b.get('require') or []):
            print(f'    ✔ 必备: {r}')
        for f_ in (b.get('forbid') or []):
            print(f'    ✘ 禁止: {f_}')
    if tg:
        print(f'  标签: {"必填 " if tg.get("required") else ""}{tg.get("count") or ""}'
              f'{("  — " + tg["note"]) if tg.get("note") else ""}')
    pub = plat.get('publish') or {}
    print(f'  发布: {pub.get("method")} / {pub.get("endpoint")}'
          f'{"  （需扫码）" if pub.get("need_scan") else ""}')
    if pub.get('note'):
        print(f'        {pub["note"]}')
    if pid not in _NO_QR_PLATFORMS:
        print('  ⚠ 跨平台禁项（本脚本强制查）: '
              + '、'.join(dict.fromkeys(l for _, l in GENERIC_FORBID)))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('cmd', choices=['list', 'matrix', 'check', 'guide'])
    ap.add_argument('platform', nargs='?')
    ap.add_argument('--title', default='')
    ap.add_argument('--content', default='')
    ap.add_argument('--tags', default='')
    args = ap.parse_args()

    try:
        plats = load_platforms()
    except SystemExit:
        raise
    except Exception as e:
        print(f'[ERROR] 读取 platforms.yaml 失败: {e}', file=sys.stderr)
        return 3

    if args.cmd == 'list':
        cmd_list(plats)
        return 0
    if args.cmd == 'matrix':
        cmd_matrix(plats)
        return 0

    if not args.platform:
        print(f'[ERROR] {args.cmd} 需要指定平台：{"、".join(plats)}', file=sys.stderr)
        return 2
    pid = args.platform
    if pid not in plats:
        print(f'[ERROR] 未知平台 {pid}；可选：{"、".join(plats)}', file=sys.stderr)
        return 2
    plat = plats[pid]

    if args.cmd == 'guide':
        cmd_guide(pid, plat)
        return 0

    content = ''
    if args.content:
        if not os.path.exists(args.content):
            print(f'[ERROR] 正文文件不存在: {args.content}', file=sys.stderr)
            return 2
        content = read_content(args.content)
    tags = [x.strip() for x in args.tags.split(',') if x.strip()]

    try:
        fails, warns, info = check(pid, plat, args.title, content, tags)
    except Exception as e:
        print(f'[ERROR] 校验异常: {type(e).__name__}: {e}', file=sys.stderr)
        return 3

    print('=' * 78)
    print(f'GEO 适配校验：{plat.get("name")}（{pid}）')
    print('=' * 78)
    for i in info:
        print(f'  ✔ {i}')
    for w in warns:
        print(f'  ⚠ {w}')
    if fails:
        print()
        print(f'裁定: 不通过（{len(fails)} 项）')
        for f_ in fails:
            print(f'  ✗ {f_}')
        return 1
    print()
    print('裁定: 通过 —— 该平台版本符合 GEO 适配规则')
    return 0


if __name__ == '__main__':
    sys.exit(main())
