#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
filter_candidates.py - 候选文章 URL 过滤（v2.10.1 新增）

用途：在选文阶段硬性过滤，防止同一源文 URL 被反复选中。
大模型把候选文章列表交给本脚本，脚本自动剔除 7 天内已发过的 URL，
大模型只能在过滤后的干净列表里选文，根本没有机会选重复。

用法：
  python scripts/filter_candidates.py <account_key> <candidates_json 或 @file>
  candidates_json 格式：
    [
      {"title": "候选标题", "url": "https://...", "source": "来源名(可选)"},
      ...
    ]

输出：
  stdout: 过滤后的候选列表 JSON（可安全用于选文）
  stderr: 过滤详情（剔除的 URL 及原因）

返回：
  exit 0 = 正常（即使全被过滤）
  exit 2 = 参数/文件错误
"""
import sys, os, json, sqlite3, datetime
from urllib.parse import urlparse, urlunparse

sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = __import__('io').TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

URL_LOOKBACK_DAYS = 7
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "accounts.yaml")


def get_account_config(account_key: str) -> dict:
    import yaml
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for acct in cfg.get("accounts", []):
        if acct.get("key") == account_key:
            return acct
    return {}


def normalize_url(url: str) -> str:
    """URL 规范化：统一 scheme/host 大小写、去 www.、去尾部斜杠、query 参数排序。
    保证同一篇文章的不同写法（http/https、www、尾斜杠、参数顺序）能匹配上。"""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or 'https').lower()
        netloc = p.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        path = p.path.rstrip('/')
        # query 参数按 key 排序（保留，因为部分源用 query 区分文章，如 docid=）
        query = '&'.join(sorted(p.query.split('&'))) if p.query else ''
        return urlunparse((scheme, netloc, path, '', query, ''))
    except Exception:
        return url.strip()


def load_recent_urls(db_path: str) -> set:
    """加载 7 天内 history 中所有 source_url（规范化后）"""
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=URL_LOOKBACK_DAYS)).isoformat()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT source_url FROM history WHERE date >= ? AND source_url IS NOT NULL AND source_url != ""', (start,))
    urls = {normalize_url(r[0]) for r in c.fetchall() if r[0]}
    conn.close()
    return urls


def main():
    if len(sys.argv) < 3:
        print("Usage: filter_candidates.py <account_key> <candidates_json|@file>", file=sys.stderr)
        sys.exit(2)

    account_key = sys.argv[1]
    arg = sys.argv[2]
    if arg.startswith('@'):
        with open(arg[1:], 'r', encoding='utf-8') as f:
            raw = f.read()
    else:
        raw = arg

    try:
        candidates = json.loads(raw)
    except Exception as e:
        print(f"[FATAL] Cannot parse candidates JSON: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(candidates, list):
        print("[FATAL] candidates must be a JSON list", file=sys.stderr)
        sys.exit(2)

    acct = get_account_config(account_key)
    if not acct:
        print("[FATAL] Account not found", file=sys.stderr)
        sys.exit(2)

    db_path = acct.get('history_db', '')
    if not db_path or not os.path.exists(db_path):
        print("[WARN] history.db not found, passing all candidates", file=sys.stderr)
        print(json.dumps(candidates, ensure_ascii=False))
        sys.exit(0)

    recent_urls = load_recent_urls(db_path)
    print(f"[FILTER] {len(recent_urls)} unique URLs in history last {URL_LOOKBACK_DAYS} days", file=sys.stderr)

    kept = []
    dropped = []
    for cand in candidates:
        url = cand.get('url', '') or cand.get('link', '')
        norm = normalize_url(url)
        if norm and norm in recent_urls:
            dropped.append(cand)
            print(f"[FILTER] DROP: {cand.get('title', '')[:50]} | {url}", file=sys.stderr)
        else:
            kept.append(cand)

    print(f"[FILTER] kept={len(kept)} dropped={len(dropped)}", file=sys.stderr)
    print(json.dumps(kept, ensure_ascii=False))
    sys.exit(0)


if __name__ == '__main__':
    main()
