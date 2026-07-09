#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
content_dedup.py - 内容级去重（v2.5.1）

策略：用文章标题与历史库近7天的标题做 4-gram Dice 比较。
不依赖分词/停用词表/英文实体识别，纯字符级指纹。

实测效果：
  同一新闻不同写法 → Dice ~0.30~0.45 → 判重
  同公司不同新闻   → Dice ~0.10~0.20 → 放行
  完全不同主题     → Dice 0.000       → 放行

用法：
  python scripts/content_dedup.py <account_key> "<title>"
  注意：title 参数中不要附加号/特殊符号，避免 PowerShell 转义问题

返回：
  exit 0 = UNIQUE（无重复，可继续）
  exit 1 = DUPLICATE（内容重复，停止）
  exit 2 = ERROR（异常，保守放行）
"""
import sys, os, re, sqlite3, datetime

SIMILARITY_THRESHOLD = 0.28
LOOKBACK_DAYS = 7
NGRAM_N = 4

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "accounts.yaml")


def get_account_config(account_key: str) -> dict:
    import yaml
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for acct in cfg.get("accounts", []):
        if acct.get("key") == account_key:
            return acct
    return {}


def ngram_set(text: str, n: int = NGRAM_N) -> set:
    """字符级 n-gram 集合"""
    t = re.sub(r'\s+', '', text).lower()
    if len(t) < n:
        return {t}
    return {t[i:i+n] for i in range(len(t) - n + 1)}


def dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2.0 * len(a & b) / (len(a) + len(b))


def load_recent_titles(db_path: str) -> list:
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT title FROM history WHERE date >= ? ORDER BY rowid DESC', (start,))
    rows = [r[0] for r in c.fetchall() if r[0]]
    conn.close()
    return rows


def main():
    if len(sys.argv) < 3:
        print("Usage: content_dedup.py <account_key> \"<title>\"", file=sys.stderr)
        sys.exit(2)

    account_key = sys.argv[1]
    title = sys.argv[2]

    if not title or len(title) < 4:
        print("UNIQUE [short_title]")
        sys.exit(0)

    acct = get_account_config(account_key)
    if not acct:
        print("[FATAL] Account not found", file=sys.stderr)
        sys.exit(2)

    db_path = acct.get('history_db', '')
    if not db_path or not os.path.exists(os.path.dirname(db_path)):
        print("UNIQUE [no_history]")
        sys.exit(0)

    new_fp = ngram_set(title)
    if len(new_fp) < 3:
        print("UNIQUE [tiny_fp]")
        sys.exit(0)

    history = load_recent_titles(db_path)
    if not history:
        print("UNIQUE [no_recent]")
        sys.exit(0)

    max_sim = 0.0
    most_similar = ""
    for h_title in history:
        h_fp = ngram_set(h_title)
        sim = dice(new_fp, h_fp)
        if sim > max_sim:
            max_sim = sim
            most_similar = h_title

    print(f"[DEDUP] max_sim={max_sim:.3f} threshold={SIMILARITY_THRESHOLD}", file=sys.stderr)
    if max_sim >= 0.15:
        print(f"[DEDUP] most_similar: {most_similar[:60]}", file=sys.stderr)

    if max_sim >= SIMILARITY_THRESHOLD:
        print(f"DUPLICATE [{max_sim:.3f}]")
        sys.exit(1)

    print("UNIQUE")
    sys.exit(0)


if __name__ == '__main__':
    main()
