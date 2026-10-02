#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prepare.py — 多平台分发准备（已发表文章 → 各平台改造任务书）

【为什么这样设计：一个硬约束决定了整个架构】
    微信原创声明要求「文章必须首发微信」→ 所以**所有平台分发只能发生在公众号发表之后**。
    而公众号发表是人工完成的 —— 这意味着分发**不能挂进 07:00 的建稿流程**
    （那时文章还只是草稿，还没过原创检测）。

    解法：以「**已发表文章**」为输入源。`freepublish/batchget` 能拉到已发表文章的
    正文 + url + article_id，所以本脚本可以每天跑一次，**自动补上最近新发表的**文章，
    用 article_id 去重。时序问题就此消失 —— 不依赖"什么时候发的"。

【它做什么】
    1. 拉两个号最近的已发表文章（含正文）
    2. 与 state 比对，挑出尚未准备过的
    3. 每篇：蒸馏素材 + 生成 toutiao / baijiahao / xiaohongshu / weibo 四份改造任务书
    4. 落到 wechatlog\\distribute_<date>\\<key>_<article_id前缀>\\

【它不做什么】
    不发布。各平台发布接口/资质未就绪（头条需开发者资质、百家需养号、小红书无官方接口），
    且发布动作需人工确认。本脚本只产出「改什么、怎么改」的任务书。

用法
    python prepare.py                       # 两个号，各看最近 5 篇
    python prepare.py --account junxun
    python prepare.py --count 10
    python prepare.py --dry-run             # 只列出会处理哪些，不写文件
    python prepare.py --force               # 忽略 state，重做最近 N 篇

退出码：0 正常（含「无新文章」）· 2 参数错误 · 3 脚本错误
"""
import argparse
import contextlib
import datetime
import io
import json
import os
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

import create_draft as _cd          # noqa: E402
import distill                      # noqa: E402
from copyright_check import http_json, read_env   # noqa: E402

TARGET_PLATFORMS = ['toutiao', 'baijiahao', 'xiaohongshu', 'weibo']


def state_file(log_root):
    return os.path.join(log_root, 'distribute_state.json')


def load_state(p):
    if not os.path.exists(p):
        return {'version': 1, 'processed': {}}
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        d.setdefault('processed', {})
        return d
    except Exception:
        return {'version': 1, 'processed': {}}


def save_state(p, st):
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def fetch_published(acc, count):
    """拉已发表文章（含正文）。返回 [(article_id, key, date, title, html), ...]"""
    cfg = _cd.load_config()
    proxy = cfg['global']['proxy']
    env = read_env(acc.get('env_file'))
    app_id = env.get('WECHAT_APP_ID')
    sec = env.get('WECHAT_APP_SECRET')
    if not app_id or not sec:
        raise RuntimeError(f'凭证缺失: {acc.get("env_file")}')
    tok = http_json(f'{proxy}cgi-bin/token?grant_type=client_credential'
                    f'&appid={app_id}&secret={sec}')
    token = tok.get('access_token')
    if not token:
        raise RuntimeError(f'取 token 失败: {tok}')
    d = http_json(f'{proxy}cgi-bin/freepublish/batchget?access_token={token}',
                  {"offset": 0, "count": count, "no_content": 0})
    if d.get('errcode'):
        raise RuntimeError(f'batchget 失败: {d}')
    out = []
    for it in (d.get('item') or []):
        aid = it.get('article_id') or ''
        ts = it.get('update_time', 0)
        date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts else '?'
        for ni in ((it.get('content') or {}).get('news_item') or []):
            out.append({
                'article_id': aid,
                'key': acc.get('key'),
                'name': acc.get('name'),
                'date': date,
                'title': ni.get('title', ''),
                'url': ni.get('url', ''),
                'html': ni.get('content', ''),
            })
    return out


def prepare_one(art, outdir, plats, dry=False):
    os.makedirs(outdir, exist_ok=True)
    m = distill.extract_html(art['html'], art['title'])

    if not dry:
        with open(os.path.join(outdir, 'source.html'), 'w', encoding='utf-8') as f:
            f.write(art['html'])
        with open(os.path.join(outdir, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in art.items() if k != 'html'},
                      f, ensure_ascii=False, indent=1)
        with open(os.path.join(outdir, 'material.json'), 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in m.items() if k != 'body_text'},
                      f, ensure_ascii=False, indent=1)
        for pid in TARGET_PLATFORMS:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                distill.cmd_brief(pid, m, plats)
            with open(os.path.join(outdir, f'brief_{pid}.txt'), 'w', encoding='utf-8') as f:
                f.write(buf.getvalue())
    return m


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--account', default='all', help='key / 中文名 / all')
    ap.add_argument('--count', type=int, default=5, help='每号看最近几篇（默认 5）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='忽略 state 重做')
    args = ap.parse_args()

    try:
        cfg = _cd.load_config()
    except Exception as e:
        print(f'[ERROR] 读取 accounts.yaml 失败: {e}', file=sys.stderr)
        return 3

    if args.account == 'all':
        targets = list(cfg.get('accounts') or [])
    else:
        a = _cd.resolve_account(cfg, args.account)
        if not a:
            print(f'[ERROR] 账号不存在: {args.account}', file=sys.stderr)
            return 2
        targets = [a]

    log_root = os.path.dirname((targets[0].get('log_dir') or '').rstrip('\\/')) or \
        os.path.expanduser('~/.qclaw/wechatlog')
    sp = state_file(log_root)
    st = load_state(sp)

    try:
        plats = distill.load_yaml(distill.PLATFORMS_YAML).get('platforms') or {}
    except Exception as e:
        print(f'[ERROR] 读取 platforms.yaml 失败: {e}', file=sys.stderr)
        return 3

    today = datetime.date.today().isoformat()
    total_new = 0
    print('=' * 78)
    print(f'多平台分发准备 · {today}{"  [DRY-RUN]" if args.dry_run else ""}')
    print('=' * 78)

    for acc in targets:
        key = acc.get('key')
        print(f'\n--- {acc.get("name")}（{key}）---')
        try:
            arts = fetch_published(acc, max(1, args.count))
        except Exception as e:
            print(f'  ⚠ 拉取失败: {e}')
            continue
        if not arts:
            print('  无已发表文章')
            continue
        for a in arts:
            aid = a['article_id']
            done = st['processed'].get(aid)
            if done and not args.force:
                print(f'  · 已准备过  [{a["date"]}] {a["title"][:36]}')
                continue
            safe = ''.join(c for c in a['title'][:16]
                           if c not in '\\/:*?"<>|').strip() or 'untitled'
            outdir = os.path.join(log_root, f'distribute_{today}',
                                  f'{key}_{aid[:10]}_{safe}')
            try:
                m = prepare_one(a, outdir, plats, dry=args.dry_run)
            except Exception as e:
                print(f'  ✗ 准备失败 [{a["date"]}] {a["title"][:32]}: {e}')
                continue
            total_new += 1
            print(f'  ✔ [{a["date"]}] {a["title"][:34]}')
            print(f'      素材：结论句{"✔" if m["lead"] else "✘"} · '
                  f'数据段{"✔" if m["data_sentence"] else "✘"} · '
                  f'FAQ {len(m["faqs"])} 组 · 实体 {len(m["entities"])} 个')
            if not args.dry_run:
                print(f'      输出：{outdir}')
                st['processed'][aid] = {
                    'date': a['date'], 'key': key, 'title': a['title'],
                    'prepared_at': datetime.datetime.now().isoformat(timespec='seconds'),
                    'platforms': TARGET_PLATFORMS,
                }

    if not args.dry_run and total_new:
        save_state(sp, st)
    print()
    print(f'待改造文章：{total_new} 篇' + ('' if total_new else '（无新文章）'))
    if total_new and not args.dry_run:
        print('下一步（由执行会话完成，或人工）：')
        print('  1. 读 <输出目录>/brief_<平台>.txt 的任务书')
        print('  2. 按任务书改造出该平台版本')
        print('  3. python scripts/distribute/geo_adapt.py check <平台> … 自检，exit 0 才算过')
        print('  4. 不自动发布 —— 头条/百家需账号资质，小红书只能浏览器自动化')
    return 0


if __name__ == '__main__':
    sys.exit(main())
