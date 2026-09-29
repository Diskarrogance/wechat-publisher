#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片中间产物回收 —— 防止发布目录无限膨胀。

背景：每篇文 5~6 张配图（封面 2.6MB + 正文 1.7MB×5），落盘后即完成使命——
      图片已上传微信（mmbiz.qpic.cn 有防盗链，本地副本无法复用）。
      历史上从未回收，导致项目累积 2GB 垃圾。本脚本负责自动回收。

用法:
  python reap_images.py                 # 回收 7 天前的图（默认）
  python reap_images.py --days 3        # 改成 3 天
  python reap_images.py --dry-run       # 只报告不删

退出码: 0=正常（含无文件可删）  1=有文件删除失败

安全红线（硬编码，不可配）:
  · 只删图片扩展名（.png/.jpg/.jpeg/.webp/.gif/.bmp）
  · 永不进入 wechat-assets / skills / secure / .workbuddy / _archive
  · 永不删 .md / .db / .done / .in_progress
"""
import os, sys, io, json, time, argparse

# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = _SCRIPT_DIR.parent / "config" / "accounts.yaml"

WORKSPACE_ROOT = os.environ.get('WECHAT_WORKSPACE', r'H:\workspace\苏编')

IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}
# 这些目录名一旦出现在路径中，整棵子树跳过
SKIP_DIRS = {'wechat-assets', 'skills', 'secure', '.workbuddy', '_archive',
             '_reap', 'node_modules', '.git', '__pycache__', 'cover_library'}


def collect_roots():
    """扫描根：wechatlog（从 accounts.yaml 的 history_db 推导）+ workspace"""
    roots = []
    try:
        import yaml
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        for acct in data.get('accounts', []):
            db = acct.get('history_db', '')
            if db:
                # <wechatlog>/<key>/history.db -> <wechatlog>
                r = os.path.dirname(os.path.dirname(db))
                if os.path.isdir(r):
                    roots.append(r)
    except Exception as e:
        print(f"[WARN] 读取 accounts.yaml 失败，仅扫 workspace: {e}")

    if os.path.isdir(WORKSPACE_ROOT):
        roots.append(WORKSPACE_ROOT)

    # 去重（大小写不敏感）
    seen, out = set(), []
    for r in roots:
        k = os.path.normcase(os.path.abspath(r))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def is_skipped(path):
    parts = {p.lower() for p in Path(path).parts}
    return bool(parts & SKIP_DIRS)


def scan(root, cutoff):
    """返回 (待删文件列表, 总字节)"""
    victims, total = [], 0
    for dp, dn, fn in os.walk(root):
        if is_skipped(dp):
            dn[:] = []
            continue
        dn[:] = [d for d in dn if not is_skipped(os.path.join(dp, d))]
        for f in fn:
            if os.path.splitext(f)[1].lower() not in IMG_EXT:
                continue
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_mtime < cutoff:
                victims.append((p, st.st_size))
                total += st.st_size
    return victims, total


def prune_empty_dirs(root, protected_files=None):
    """自下而上删空目录（不删 root 本身）"""
    removed = 0
    for dp, dn, fn in os.walk(root, topdown=False):
        if os.path.normcase(dp) == os.path.normcase(root) or is_skipped(dp):
            continue
        try:
            if not os.listdir(dp):
                os.rmdir(dp)
                removed += 1
        except OSError:
            pass
    return removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7, help='保留最近 N 天（默认 7）')
    ap.add_argument('--dry-run', action='store_true', help='只报告不删除')
    args = ap.parse_args()

    if args.days < 1:
        print('[FATAL] --days 必须 >= 1（禁止回收今天/未来的文件）', file=sys.stderr)
        return 1

    cutoff = time.time() - args.days * 86400
    roots = collect_roots()
    if not roots:
        print('[FATAL] 没有可扫描的根目录', file=sys.stderr)
        return 1

    print(f'[reap] 保留 {args.days} 天内的图片；模式={"DRY-RUN" if args.dry_run else "执行"}')
    print(f'[reap] 扫描根: {roots}')

    all_victims, grand_total, failed = [], 0, 0
    for root in roots:
        victims, total = scan(root, cutoff)
        all_victims += victims
        grand_total += total
        print(f'  {total/1024/1024:8.1f} MB  {len(victims):4d} 个  {root}')

    if not all_victims:
        print('[reap] 无超期图片，目录干净 ✓')
        return 0

    # 按所在目录聚合展示 TOP
    from collections import Counter
    by_dir = Counter()
    for p, s in all_victims:
        by_dir[os.path.dirname(p)] += s
    print('[reap] 待回收目录 TOP8:')
    for d, s in by_dir.most_common(8):
        print(f'    {s/1024/1024:8.1f} MB  {d}')

    if args.dry_run:
        print(f'[reap] DRY-RUN：将回收 {len(all_victims)} 个文件 / {grand_total/1024/1024:.1f} MB')
        return 0

    for p, _ in all_victims:
        try:
            os.remove(p)
        except OSError as e:
            failed += 1
            print(f'  [FAIL] {p} :: {e}', file=sys.stderr)

    pruned = 0
    for root in roots:
        pruned += prune_empty_dirs(root)

    ok = len(all_victims) - failed
    print(f'[reap] 已回收 {ok}/{len(all_victims)} 个文件，释放 '
          f'{grand_total/1024/1024:.1f} MB；清理空目录 {pruned} 个')
    if failed:
        print(f'[reap] {failed} 个文件删除失败', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
