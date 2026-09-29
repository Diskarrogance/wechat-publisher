#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patrol_check.py - 每日发布巡检（只读，无副作用）

给 08:00 单一巡检任务提供**机器可判定**的账号状态，避免 LLM 凭感觉判断
「是否已发 / daily 是否还在跑」而重复发稿或漏补发。

背景：历史事故中 daily 被网关重启掐断后残留 .in_progress 锁，
retry 看到"新鲜锁"误判为任务在跑而刹车，导致当天 0 产出（9/25 空窗）。
本脚本把「锁龄」显式区分出来，让补发决策有据可依。

用法：
  python patrol_check.py                 # 巡检所有 enabled 账号
  python patrol_check.py junxun          # 只巡检指定账号
  python patrol_check.py --json          # 额外输出 JSON 块

状态语义：
  DONE         已发满配额 → 无需任何操作
  RUNNING      .in_progress 锁新鲜（<=60min）且未发满 → daily 正在跑，禁止补发
  STALE_LOCK   锁已过期（>60min）且未发满 → 可补发（semaphore_check 会自动清过期锁）
  NEEDS_RESEND 无锁、未发满 → 必须补发
  DB_MISSING   history.db 不存在 → 需补发（或配置错误）

退出码：
  0 = 全部 DONE，无需操作
  1 = 有账号需要补发（NEEDS_RESEND / STALE_LOCK / DB_MISSING）
  2 = 有账号正在运行（RUNNING），且没有需要补发的
  3 = 配置或运行错误
"""
import sys
import os
import json
import sqlite3
import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(SCRIPT_DIR, "..", "config", "accounts.yaml")

# 锁过期阈值，必须与 semaphore_check.py 的 3600 保持一致
LOCK_EXPIRE_SEC = 3600

NEED_RESEND_STATES = ("NEEDS_RESEND", "STALE_LOCK", "DB_MISSING")


def load_accounts():
    """从 accounts.yaml 读取 enabled 账号及其配额"""
    import yaml
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = []
    for a in cfg.get("accounts", []):
        if not a.get("enabled", True):
            continue
        sched = a.get("schedule") or {}
        # articles_per_day 未配置时默认 1 篇
        try:
            quota = int(sched.get("articles_per_day", 1) or 1)
        except (TypeError, ValueError):
            quota = 1
        out.append({
            "key": a.get("key"),
            "name": a.get("name"),
            "log_dir": a.get("log_dir", "") or "",
            "history_db": a.get("history_db", "") or "",
            "quota": quota,
        })
    return out


def today_str():
    return datetime.date.today().isoformat()


def read_history(db_path):
    """返回当日已入库的 (篇数, 最后一篇时间, 最后一篇标题, 全部标题列表)

    兼容两种表结构：junxun 有 id 列，lanmuda 没有 → 一律用 created_at 排序。
    """
    if not db_path or not os.path.exists(db_path):
        return 0, None, None, [], "db_missing"
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute(
            "SELECT title, created_at FROM history WHERE date = ? ORDER BY created_at DESC",
            (today_str(),),
        )
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        return 0, None, None, [], f"read_error: {e}"

    if not rows:
        return 0, None, None, [], None
    titles = [r[0] for r in rows]
    last_time, last_title = rows[0][1], rows[0][0]
    return len(rows), last_time, last_title, titles, None


def inspect_lock(log_dir):
    """返回 (状态字符串, 锁龄秒数或None)"""
    if not log_dir:
        return "no_logdir", None
    d = os.path.join(log_dir, ".done")
    ipf = os.path.join(d, today_str() + ".in_progress")
    if not os.path.exists(ipf):
        return "none", None
    age = int(datetime.datetime.now().timestamp() - os.path.getmtime(ipf))
    if age > LOCK_EXPIRE_SEC:
        return "stale", age
    return "fresh", age


def inspect_marker(log_dir):
    """返回 .done marker 状态：none / done / cleared"""
    if not log_dir:
        return "no_logdir"
    mf = os.path.join(log_dir, ".done", today_str())
    if not os.path.exists(mf):
        return "none"
    try:
        with open(mf, "r") as f:
            first = f.readline().strip()
        return "cleared" if first.startswith("cleared:") else "done"
    except Exception:
        return "done"


def fmt_time(s):
    """'2026-09-26T09:45:47.735026' → '09:45'"""
    if not s:
        return "--:--"
    try:
        return str(s)[11:16]
    except Exception:
        return "--:--"


def evaluate(acct):
    """判定单个账号状态"""
    count, last_time, last_title, titles, db_err = read_history(acct["history_db"])
    lock_state, lock_age = inspect_lock(acct["log_dir"])
    marker_state = inspect_marker(acct["log_dir"])
    quota = acct["quota"]

    if db_err == "db_missing":
        status = "DB_MISSING"
    elif count >= quota:
        status = "DONE"
    elif lock_state == "fresh":
        status = "RUNNING"
    elif lock_state == "stale":
        status = "STALE_LOCK"
    else:
        status = "NEEDS_RESEND"

    return {
        "key": acct["key"],
        "name": acct["name"],
        "status": status,
        "count": count,
        "quota": quota,
        "last_time": fmt_time(last_time),
        "last_title": last_title,
        "titles": titles,
        "lock": lock_state,
        "lock_age_sec": lock_age,
        "marker": marker_state,
        "db_error": db_err,
    }


def main():
    argv = [a for a in sys.argv[1:] if a not in ("--json",)]
    want_json = "--json" in sys.argv[1:]
    only = argv[0] if argv else None

    try:
        accounts = load_accounts()
    except Exception as e:
        print(f"[FATAL] cannot load accounts.yaml: {e}", file=sys.stderr)
        sys.exit(3)

    if only:
        accounts = [a for a in accounts if a["key"] == only]
        if not accounts:
            print(f"[FATAL] account '{only}' not found or disabled", file=sys.stderr)
            sys.exit(3)

    results = [evaluate(a) for a in accounts]

    print(f"PATROL {today_str()}  ({len(results)} account(s))")
    print("-" * 68)
    for r in results:
        lock_desc = r["lock"]
        if r["lock_age_sec"] is not None:
            lock_desc = f"{r['lock']}/{r['lock_age_sec'] // 60}min"
        line = (
            f"{r['key']:<8} {r['status']:<12} {r['count']}/{r['quota']}"
            f"  lock={lock_desc:<14} marker={r['marker']:<8}"
        )
        if r["last_title"]:
            line += f" last={r['last_time']}《{r['last_title'][:28]}》"
        if r["db_error"]:
            line += f"  [{r['db_error']}]"
        print(line)

    print("-" * 68)

    need = [r for r in results if r["status"] in NEED_RESEND_STATES]
    running = [r for r in results if r["status"] == "RUNNING"]

    if need:
        print("ACTION: RESEND REQUIRED -> " + ", ".join(
            f"{r['key']}({r['status']}, {r['count']}/{r['quota']})" for r in need
        ))
    if running:
        print("ACTION: WAIT (daily still running) -> " + ", ".join(
            f"{r['key']}(lock {r['lock_age_sec'] // 60}min)" for r in running
        ))
    if not need and not running:
        print("ACTION: NONE (all accounts DONE)")

    if want_json:
        print("```json")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print("```")

    if need:
        sys.exit(1)
    if running:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
