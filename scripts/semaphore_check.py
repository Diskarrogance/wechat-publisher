#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semaphore_check.py - 防重复硬屏障

这是无法被 Agent 绕过的防重复闸门。所有 cron 任务的第〇步必须调用此脚本。
如果脚本返回非零 exit code，Agent 必须立即停止，不得继续。

用法：
  python semaphore_check.py <account_key> [--mode check | --create-done | --clear | --create-in-progress | --clear-in-progress]

--check (默认): 检查今天是否已完成
  - 读 history.db → 今天有记录？ → exit 1 "HISTORY_EXISTS"
  - 读 .done marker 文件 → 今天已完成？ → exit 1 "MARKER_EXISTS"
  - 读 .in_progress marker → 今天有任务进行中？ → exit 1 "IN_PROGRESS"
  → exit 0 "READY"

--create-done: 标记今天已完成
  - 创建 .done marker 文件 → exit 0
  - 由 create_draft.py 在创建草稿成功后调用

--create-in-progress: 标记任务进行中（流程起点写入）
  - 创建 .in_progress marker 文件 → exit 0

--clear-in-progress: 清除进行中标记
  - 删除 .in_progress marker 文件 → exit 0

--clear: 清除今天的标记（用于手动重试）
  - 删除 .done 和 .in_progress marker 文件 → exit 0

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


def today_str() -> str:
    return datetime.date.today().isoformat()


def marker_file(log_dir: str) -> str:
    return os.path.join(marker_dir(log_dir), today_str())


def in_progress_file(log_dir: str) -> str:
    """进行中锁文件路径"""
    return os.path.join(marker_dir(log_dir), today_str() + ".in_progress")


def check_history(db_path: str) -> bool:
    """检查 history.db 今天是否有记录"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM history WHERE date = ?", (today_str(),))
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[WARN] history.db check failed: {e}", file=sys.stderr)
        return False  # 查不到不算已发，但会写 warn


def check_marker(log_dir: str) -> bool:
    """检查 .done marker 文件是否存在"""
    return os.path.exists(marker_file(log_dir))


def check_in_progress(log_dir: str) -> bool:
    """检查 .in_progress 锁文件是否存在"""
    ipf = in_progress_file(log_dir)
    if not os.path.exists(ipf):
        return False
    # 锁文件超过 60 分钟视为过期（可能是异常退出遗留），允许重新执行
    age = datetime.datetime.now().timestamp() - os.path.getmtime(ipf)
    if age > 3600:
        print(f"[WARN] Stale .in_progress ({int(age)}s old), ignoring", file=sys.stderr)
        os.remove(ipf)
        return False
    return True


def create_marker(log_dir: str):
    """创建 .done marker 文件"""
    d = marker_dir(log_dir)
    os.makedirs(d, exist_ok=True)
    with open(marker_file(log_dir), "w") as f:
        f.write(f"done:{datetime.datetime.now().isoformat()}")
    print(f"[SEMAPHORE] .done Marker created: {marker_file(log_dir)}")


def create_in_progress(log_dir: str):
    """创建 .in_progress 锁文件（流程起点写入）"""
    d = marker_dir(log_dir)
    os.makedirs(d, exist_ok=True)
    ipf = in_progress_file(log_dir)
    with open(ipf, "w") as f:
        f.write(f"in_progress:{datetime.datetime.now().isoformat()}")
    print(f"[SEMAPHORE] .in_progress created: {ipf}")


def clear_in_progress(log_dir: str):
    """清除 .in_progress 锁文件"""
    ipf = in_progress_file(log_dir)
    if os.path.exists(ipf):
        os.remove(ipf)
        print(f"[SEMAPHORE] .in_progress cleared: {ipf}")
    else:
        print(f"[SEMAPHORE] No .in_progress to clear")


def clear_marker(log_dir: str):
    """清除今天所有标记（.done + .in_progress）"""
    mf = marker_file(log_dir)
    if os.path.exists(mf):
        os.remove(mf)
        print(f"[SEMAPHORE] .done Marker cleared: {mf}")
    else:
        print(f"[SEMAPHORE] No .done marker to clear")
    clear_in_progress(log_dir)


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
        # 创建 .done 时顺便清理 .in_progress
        clear_in_progress(log_dir)
        sys.exit(0)

    if mode == "clear":
        clear_marker(log_dir)
        sys.exit(0)

    if mode == "create_in_progress" or mode == "create-in-progress":
        create_in_progress(log_dir)
        sys.exit(0)

    if mode == "clear_in_progress" or mode == "clear-in-progress":
        clear_in_progress(log_dir)
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

    # 检查 .in_progress 锁文件（防止同一时间多 cron 并行跑）
    if check_in_progress(log_dir):
        print("ALREADY_DONE [in_progress]")
        sys.exit(1)

    # 检查 .done marker 文件
    if check_marker(log_dir):
        print("ALREADY_DONE [marker]")
        sys.exit(1)

    print("READY")
    sys.exit(0)


if __name__ == "__main__":
    main()
