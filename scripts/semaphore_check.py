#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semaphore_check.py - 防重复硬屏障

这是无法被 Agent 绕过的防重复闸门。所有 cron 任务的第〇步必须调用此脚本。
如果脚本返回非零 exit code，Agent 必须立即停止，不得继续。

用法：
  python semaphore_check.py <account_key> [--mode check | --create-done | --clear]

--check (默认): 检查今天是否已完成
  - 读 history.db → 今天有记录？ → exit 1 "HISTORY_EXISTS"
  - 读 marker 文件 → 今天已完成？ → exit 1 "MARKER_EXISTS"
  → exit 0 "READY"

--create-done: 标记今天已完成
  - 创建 marker 文件 → exit 0
  - 由 create_draft.py 在创建草稿成功后调用

--clear: 清除今天的标记（用于手动重试）
  - 删除 marker 文件 → exit 0

账号通过 accounts.yaml 的 key 字段匹配，自动读取 log_dir。
"""
import sys
import os
import datetime

# ─── 直接硬路径读 accounts.yaml ───
import yaml

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "accounts.yaml")

def get_log_dir(account_key: str) -> str:
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for acct in cfg.get("accounts", []):
        if acct.get("key") == account_key:
            return acct.get("log_dir", "")
    print(f"[FATAL] Account '{account_key}' not found in {CONFIG}", file=sys.stderr)
    sys.exit(2)


def marker_dir(log_dir: str) -> str:
    """Marker 文件存放目录"""
    return os.path.join(log_dir, ".done")


def marker_file(log_dir: str) -> str:
    today = datetime.date.today().isoformat()
    return os.path.join(marker_dir(log_dir), today)


def check_history(db_path: str) -> bool:
    """检查 history.db 今天是否有记录"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        today = datetime.date.today().isoformat()
        c.execute("SELECT COUNT(*) FROM history WHERE date = ?", (today,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[WARN] history.db check failed: {e}", file=sys.stderr)
        return False  # 查不到不算已发，但会写 warn


def check_marker(log_dir: str) -> bool:
    """检查 marker 文件是否存在"""
    return os.path.exists(marker_file(log_dir))


def create_marker(log_dir: str):
    """创建 marker 文件"""
    d = marker_dir(log_dir)
    os.makedirs(d, exist_ok=True)
    with open(marker_file(log_dir), "w") as f:
        f.write(f"done:{datetime.datetime.now().isoformat()}")
    print(f"[SEMAPHORE] Marker created: {marker_file(log_dir)}")


def clear_marker(log_dir: str):
    mf = marker_file(log_dir)
    if os.path.exists(mf):
        os.remove(mf)
        print(f"[SEMAPHORE] Marker cleared: {mf}")
    else:
        print(f"[SEMAPHORE] No marker to clear: {mf}")


def main():
    if len(sys.argv) < 2:
        print("Usage: semaphore_check.py <account_key> [--mode check|create-done|clear]", file=sys.stderr)
        sys.exit(2)

    account_key = sys.argv[1]
    mode = "check"
    if len(sys.argv) >= 3:
        mode_arg = sys.argv[2]
        if mode_arg.startswith("--mode="):
            mode = mode_arg.split("=", 1)[1]
        elif mode_arg == "--create-done":
            mode = "create-done"
        elif mode_arg == "--clear":
            mode = "clear"
        elif mode_arg == "--check":
            mode = "check"
        else:
            mode = mode_arg.lstrip("-").replace("-", "_")

    log_dir = get_log_dir(account_key)

    if mode == "create-done":
        create_marker(log_dir)
        sys.exit(0)

    if mode == "clear":
        clear_marker(log_dir)
        sys.exit(0)

    # ── check mode ──
    # 读取 accounts.yaml 取 history.db 路径
    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    db_path = ""
    for acct in cfg.get("accounts", []):
        if acct.get("key") == account_key:
            db_path = acct.get("history_db", "")
            break
    if not db_path:
        print(f"[FATAL] Account '{account_key}' history_db not found", file=sys.stderr)
        sys.exit(2)

    if not os.path.exists(os.path.dirname(db_path)):
        print(f"[WARN] history.db dir not found: {os.path.dirname(db_path)}", file=sys.stderr)
        # 目录不存在 → 肯定没发过 → 允许继续
        sys.exit(0)

    # 检查 history.db
    if check_history(db_path):
        print("ALREADY_DONE [history]")
        sys.exit(1)

    # 检查 marker 文件
    if check_marker(log_dir):
        print("ALREADY_DONE [marker]")
        sys.exit(1)

    print("READY")
    sys.exit(0)


if __name__ == "__main__":
    main()
