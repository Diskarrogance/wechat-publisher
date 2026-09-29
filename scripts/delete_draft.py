# -*- coding: utf-8 -*-
"""delete_draft.py - 删除微信图文草稿（主题撞车 / 误建稿时的撤稿工具）

用法：
    python delete_draft.py <account> <media_id>                  # 只删微信侧草稿
    python delete_draft.py <account> <media_id> --purge-history   # 顺带清理 history.db 占位记录

为什么要有 --purge-history：
    主题撞车时的标准处置是「删草稿 + 清 history 占位 + 换选题重做」。
    以前清 history 要手写 SQL（`DELETE FROM history WHERE rowid=<id>`），
    手动操作真身数据库有风险。本选项把两步并成一条命令，避免手写 SQL。

    ⚠️ 注意：清理只按 media_id 精确匹配，不做模糊匹配，避免误删同日其他篇。

账号参数接受 key（junxun/lanmuda）或中文名（君寻/岚牧哒）。
"""
import sys, io, os, json, time, requests, urllib3, urllib.request, ssl, sqlite3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass


def load_env(env_file):
    env = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def get_token(app_id, app_secret, proxy, retries=3):
    for attempt in range(retries):
        try:
            url = f"{proxy}cgi-bin/token"
            params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
            r = requests.get(url, params=params, timeout=30, verify=False)
            r.raise_for_status()
            data = r.json()
            if "access_token" not in data:
                raise Exception(f"Token failed: {data}")
            return data["access_token"]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise


def resolve_account(cfg, account):
    """key 或中文名 → 账号配置项"""
    for a in cfg.get('accounts', []):
        if a.get('key') == account or a.get('name') == account:
            return a
    return None


def purge_history(db_path, media_id):
    """按 media_id 精确清理 history 中的占位记录（草稿已被删，记录不该留）"""
    if not os.path.exists(db_path):
        print(f"[WARN] history.db 不存在，跳过清理：{db_path}", file=sys.stderr)
        return 0
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute(
            'SELECT rowid, date, title FROM history WHERE draft_media_id = ? OR media_id = ?',
            (media_id, media_id))
        rows = c.fetchall()
        if not rows:
            print("[PURGE] history 中未找到该 media_id 对应记录（可能已清理）")
            return 0
        for rowid, date, title in rows:
            print(f"[PURGE] rowid={rowid} {date}《{(title or '')[:40]}》")
        c.execute('DELETE FROM history WHERE draft_media_id = ? OR media_id = ?',
                  (media_id, media_id))
        conn.commit()
        print(f"[PURGE] 已清理 {len(rows)} 条 history 记录")
        return len(rows)
    finally:
        conn.close()


def main():
    if len(sys.argv) < 3:
        print("用法: python delete_draft.py <account> <media_id> [--purge-history]", file=sys.stderr)
        sys.exit(2)

    account = sys.argv[1]
    media_id = sys.argv[2]
    purge = '--purge-history' in sys.argv[3:]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    import yaml
    with open(os.path.join(os.path.dirname(script_dir), "config", "accounts.yaml"), 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    acct_cfg = resolve_account(cfg, account)
    if not acct_cfg:
        print(f"[FATAL] 账号 '{account}' 不存在（可用 key："
              f"{[a.get('key') for a in cfg.get('accounts', [])]}）", file=sys.stderr)
        sys.exit(2)

    env = load_env(acct_cfg['env_file'])
    proxy = cfg['global']['proxy']
    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')
    token = get_token(app_id, app_secret, proxy)
    print(f"Token OK: {token[:20]}...", file=sys.stderr)

    url = f"{proxy}cgi-bin/draft/delete?access_token={token}"
    payload = {"media_id": media_id}
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    r = urllib.request.urlopen(req, context=ctx, timeout=60)
    resp = json.loads(r.read().decode('utf-8'))
    if resp.get("errcode", 0) != 0:
        raise Exception(f"Delete failed: {resp}")
    print("DELETE_OK", media_id)

    if purge:
        purge_history(acct_cfg.get('history_db', ''), media_id)


if __name__ == '__main__':
    main()
