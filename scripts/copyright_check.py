#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
copyright_check.py — 原创标识巡检（每日）

为什么要有它
    微信 API **既不能声明原创，也不返回原创标记**（官方社区置顶答复：草稿接口
    `draft/add` / 发布接口 `freepublish/submit` 都没有原创相关参数；`freepublish/batchget`
    返回的 news_item 字段里也没有 copyright_stat）。
    唯一可行的自动检测途径：**抓已发表文章的页面**，看有没有原创标签元素
    `<span id="copyright_logo" ...>原创</span>`（实测：未标原创的老文章页面里没有该元素，
    已标的有 —— 是可靠的条件渲染信号）。

    原创标识只能在编辑时声明、群发时由系统检测通过才生效，**已群发文章不支持事后补标**
    （官方明确），想补只能删文重新群发。所以漏标必须尽早发现 —— 这就是本脚本的意义。

用法
    python copyright_check.py                      # 双号，各查最近 3 篇
    python copyright_check.py --account junxun     # 单号
    python copyright_check.py --count 5 --json
    python copyright_check.py --quiet              # 只输出漏标项

退出码
    0 = 全部已标原创
    1 = 存在未标原创的文章（需人工处理：删文重新群发时勾选原创）
    2 = 接口/网络异常，无法完成检查
    3 = 脚本错误
"""
import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import create_draft as _cd
except ImportError as e:
    print(f'[FATAL] 无法导入 create_draft: {e}', file=sys.stderr)
    sys.exit(3)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

MAX_PAGE_BYTES = 4_000_000     # 页面读取上限（正文页实测 ~3.5MB）
CHUNK = 65536
MARK = b'copyright_logo'       # 原创标签元素 id


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def read_env(path):
    env = {}
    if not path or not os.path.exists(path):
        return env
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def http_json(url, body=None, timeout=30):
    ctx = _ctx()
    if body is None:
        r = urllib.request.urlopen(url, context=ctx, timeout=timeout)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=utf-8'})
        r = urllib.request.urlopen(req, context=ctx, timeout=timeout)
    return json.loads(r.read().decode('utf-8'))


def has_original_tag(url, timeout=30):
    """抓文章页，判断是否带原创标签。增量读取，命中即返回（省带宽）。"""
    req = urllib.request.Request(url, headers={'User-Agent': UA,
                                               'Accept-Encoding': 'identity'})
    r = urllib.request.urlopen(req, context=_ctx(), timeout=timeout)
    buf = b''
    try:
        while len(buf) < MAX_PAGE_BYTES:
            chunk = r.read(CHUNK)
            if not chunk:
                break
            buf += chunk
            i = buf.find(MARK)
            if i >= 0:
                seg = buf[i:i + 400].decode('utf-8', errors='replace')
                if '原创' in seg:          # id 命中且附近出现「原创」字样
                    return True
    finally:
        r.close()
    return False


def check_account(acc, count):
    proxy = None
    cfg = _cd.load_config()
    proxy = cfg.get('global', {}).get('proxy', '')
    env = read_env(acc.get('env_file'))
    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_sec = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')
    if not app_id or not app_sec:
        return {'key': acc.get('key'), 'error': f'凭证缺失: {acc.get("env_file")}'}

    tok = http_json(f'{proxy}cgi-bin/token?grant_type=client_credential'
                    f'&appid={app_id}&secret={app_sec}')
    token = tok.get('access_token')
    if not token:
        return {'key': acc.get('key'), 'error': f'取 token 失败: {tok}'}

    d = http_json(f'{proxy}cgi-bin/freepublish/batchget?access_token={token}',
                  {"offset": 0, "count": count, "no_content": 0})
    if d.get('errcode'):
        return {'key': acc.get('key'), 'error': f"batchget 失败: {d}"}

    items = []
    for it in (d.get('item') or []):
        for ni in ((it.get('content') or {}).get('news_item') or []):
            title = ni.get('title', '')
            url = ni.get('url', '')
            ts = it.get('update_time', 0)
            rec = {'title': title, 'date': time.strftime('%m-%d', time.localtime(ts)) if ts else '?',
                   'url': url, 'has_original': None}
            try:
                rec['has_original'] = has_original_tag(url)
            except Exception as e:
                rec['error'] = f'{type(e).__name__}: {e}'
            items.append(rec)
    return {'key': acc.get('key'), 'name': acc.get('name'), 'items': items}


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--account', default='all', help='账号 key / 中文名 / all（默认）')
    ap.add_argument('--count', type=int, default=3, help='每个账号查最近几篇（默认 3）')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--quiet', action='store_true', help='只输出漏标项')
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
            return 3
        targets = [a]

    results, errs = [], []
    for acc in targets:
        try:
            r = check_account(acc, max(1, args.count))
        except Exception as e:
            r = {'key': acc.get('key'), 'error': f'{type(e).__name__}: {e}'}
        results.append(r)
        if r.get('error'):
            errs.append(r)

    missing = [(r['key'], it) for r in results if not r.get('error')
               for it in r['items'] if it.get('has_original') is False]

    if args.json:
        print(json.dumps({'results': results, 'missing_count': len(missing)},
                         ensure_ascii=False, indent=2))
        return 1 if missing else (2 if errs else 0)

    if not args.quiet:
        print('=' * 76)
        print('原创标识巡检（已发表文章）')
        print('=' * 76)
        for r in results:
            if r.get('error'):
                print(f"  [{r['key']}] ⚠ {r['error']}")
                continue
            print(f"  --- {r.get('name', r['key'])} ---")
            for it in r['items']:
                if it.get('has_original') is True:
                    flag = '✅ 原创'
                elif it.get('has_original') is False:
                    flag = '❌ 未标'
                else:
                    flag = '⚠ 未知'
                err = f"  ({it['error'][:40]})" if it.get('error') else ''
                print(f"    {flag}  [{it['date']}] {it['title'][:40]}{err}")
        print()

    if missing:
        print(f'裁定: 有 {len(missing)} 篇未标原创 —— 需人工处理')
        for k, it in missing:
            print(f"  ✗ [{k}] [{it['date']}] {it['title'][:44]}")
        print('  说明: 原创标识只能在编辑时声明、群发时通过系统检测才生效，'
              '已群发文章不支持事后补标（官方明确）。')
        print('  处置: 如需补标，删文后在 MP 后台编辑时勾「声明原创」重新群发。')
        print('  根治: MP 后台「内容与互动 → 原创声明 → 发布时自动声明原创」开启开关，新建图文默认声明。')
        return 1
    if errs:
        print(f'裁定: 完成，但有 {len(errs)} 个账号检查失败（接口/网络）')
        return 2
    print(f'裁定: 全部已标原创（共 {sum(len(r.get("items", [])) for r in results)} 篇）✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
