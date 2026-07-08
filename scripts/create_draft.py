"""
create_draft.py - 创建微信图文草稿
用法：python create_draft.py <account> <draft_json>

参数：
  account    : junxun | lanmuda（accounts.yaml 中的 key）
  draft_json : JSON 字符串，格式：
    {
      "title": "标题",
      "author": "作者",
      "content": "正文HTML",
      "digest": "摘要",
      "thumb_media_id": "封面media_id",
      "need_open_comment": 1,
      "only_fans_can_comment": 0,
      "content_source_url": "文章来源原始URL"
    }

必填参数：
  - need_open_comment: 必须为1（开启评论区）
  - content_source_url: 必须填写文章来源链接

功能：
  - 自动重试获取 token（最多 3 次）
  - 自动处理编码（ensure_ascii=False）
"""
import sys, io, os, json, requests, time, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_env(env_file):
    """加载 .env 文件到字典"""
    env = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def get_token(app_id, app_secret, proxy, retries=3):
    """获取微信 access_token（自动重试）"""
    for attempt in range(retries):
        try:
            url = f"{proxy}cgi-bin/token"
            params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
            r = requests.get(url, params=params, timeout=30, verify=False)
            r.raise_for_status()
            data = r.json()
            if "access_token" not in data:
                if attempt < retries - 1:
                    print(f"[WARN] Token attempt {attempt+1} failed: {data}, retrying...", file=sys.stderr)
                    time.sleep(2)
                    continue
                raise Exception(f"Token failed after {retries} attempts: {data}")
            return data["access_token"]
        except Exception as e:
            if attempt < retries - 1:
                print(f"[WARN] Token attempt {attempt+1} error: {e}, retrying...", file=sys.stderr)
                time.sleep(2)
                continue
            raise Exception(f"Token error after {retries} attempts: {e}")

def create_draft(token, draft_info, proxy):
    """创建图文草稿"""
    url = f"{proxy}cgi-bin/draft/add?access_token={token}"
    
    payload = {
        "articles": [{
            "title": draft_info['title'],
            "author": draft_info['author'],
            "digest": draft_info.get('digest', ''),
            "content": draft_info['content'],
            "thumb_media_id": draft_info['thumb_media_id'],
            "need_open_comment": draft_info.get('need_open_comment', 1),
            "only_fans_can_comment": draft_info.get('only_fans_can_comment', 0),
            "content_source_url": draft_info.get('content_source_url', '')
        }]
    }
    
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = requests.post(url, data=data, headers=headers, timeout=60, verify=False)
    r.raise_for_status()
    resp = r.json()
    if resp.get("errcode", 0) != 0:
        raise Exception(f"Draft failed: {resp}")
    return resp.get("media_id", "")

def main():
    account = sys.argv[1]
    if len(sys.argv) >= 3:
        draft_json_arg = sys.argv[2]
        if draft_json_arg.startswith('@'):
            with open(draft_json_arg[1:], 'r', encoding='utf-8') as _f:
                draft_json = _f.read()
        else:
            draft_json = draft_json_arg
    else:
        # Read from stdin
        draft_json = sys.stdin.read()

    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(os.path.dirname(config_dir), "config", "accounts.yaml")

    import yaml
    with open(yaml_file, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    # 用 key 字段匹配账号
    acct_cfg = next((a for a in cfg['accounts'] if a.get('key') == account), None)
    if not acct_cfg:
        # 兼容旧的 name 匹配
        acct_cfg = next(a for a in cfg['accounts'] if a['name'] == account)

    # 防重复：查 history.db，今天已有记录则跳过
    import sqlite3, datetime
    db_path = acct_cfg['history_db']
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    # 查询各账号每日篇数上限
    c.execute('SELECT COUNT(*) FROM history WHERE date = ?', (today,))
    count_today = c.fetchone()[0]
    # 君寻每天2篇，其他账号1篇（从 accounts.yaml 中的 articles_per_day 读取更佳）
    max_articles = 2 if account in ('junxun',) else 1
    if count_today >= max_articles:
        print("DUPLICATE_SKIP")
        sys.exit(0)

    env = load_env(acct_cfg['env_file'])
    proxy = cfg['global']['proxy']

    # 使用正确的 env key 名（兼容旧格式）
    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')
    
    if not app_id or not app_secret:
        raise Exception(f"Missing WECHAT_APP_ID or WECHAT_APP_SECRET in {acct_cfg['env_file']}")

    token = get_token(app_id, app_secret, proxy)
    print(f"Token OK: {token[:20]}...", file=sys.stderr)
    
    draft_info = json.loads(draft_json)
    
    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    ts = now.isoformat()
    from urllib.parse import urlparse
    src_url = draft_info.get('content_source_url', '')
    source = 'auto'
    if src_url:
        domain = urlparse(src_url).netloc
        source = domain.replace('www.', '')[:30]

    # ★ 先写 history.db 占位（status='creating'），再调微信 API 创建草稿
    # 这样即使脚本在创建草稿后异常退出，占位记录也会阻止二次调用
    # 注意：用 INSERT（不是 INSERT OR REPLACE），确保多篇场景各自独立
    c.execute('INSERT INTO history (date, title, source, source_url, cover_media_id, status, created_at, draft_media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (today_str, draft_info['title'], source, src_url, '', 'creating', ts, ''))
    row_id = c.lastrowid
    conn.commit()

    try:
        media_id = create_draft(token, draft_info, proxy)
    except Exception as e:
        # 草稿创建失败 → 按 id 更新（不覆盖其他条）
        c.execute('UPDATE history SET status=?, created_at=? WHERE id=?',
                  ('create_failed', datetime.datetime.now().isoformat(), row_id))
        conn.commit()
        raise

    # 草稿创建成功 → 按 id 更新（不覆盖其他条的 draft_media_id）
    c.execute('UPDATE history SET status=?, draft_media_id=?, created_at=? WHERE id=?',
              ('draft_created', media_id, ts, row_id))
    conn.commit()

    # ★ 写 semaphore marker（防重复硬屏障）
    try:
        sem_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'semaphore_check.py')
        import subprocess
        subprocess.run([sys.executable, sem_script, account, '--create-done'],
                       check=True, capture_output=True, timeout=10)
    except Exception as sem_e:
        print(f'[WARN] semaphore_check --create-done failed: {sem_e}', file=sys.stderr)

    print(media_id)

if __name__ == '__main__':
    main()