#!/usr/bin/env python3
"""Direct draft creator - reads JSON from file, creates draft via API"""
import sys, os, json, requests, time, sqlite3, datetime, io, yaml, subprocess
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

account = sys.argv[1]
json_path = sys.argv[2]  # path to JSON file

script_dir = os.path.dirname(os.path.abspath(__file__))
config_dir = os.path.join(os.path.dirname(script_dir), "config")
yaml_file = os.path.join(config_dir, "accounts.yaml")

# Load config
with open(yaml_file, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

acct = next((a for a in cfg['accounts'] if a.get('key') == account), None)
if not acct:
    acct = next(a for a in cfg['accounts'] if a['name'] == account)

# Load env
env = {}
with open(acct['env_file'], 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

app_id = env.get('WECHAT_APP_ID')
app_secret = env.get('WECHAT_APP_SECRET')
proxy = cfg['global']['proxy']

# Check history
db_path = acct['history_db']
conn = sqlite3.connect(db_path)
c = conn.cursor()
today = datetime.date.today().isoformat()
c.execute('SELECT COUNT(*) FROM history WHERE date = ?', (today,))
count_today = c.fetchone()[0]
max_articles = 2 if account in ('junxun',) else 1
if count_today >= max_articles:
    print("DUPLICATE_SKIP")
    sys.exit(0)

# Get token
for attempt in range(3):
    try:
        url = f"{proxy}cgi-bin/token"
        params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
        r = requests.get(url, params=params, timeout=30, verify=False)
        r.raise_for_status()
        data = r.json()
        if "access_token" in data:
            token = data["access_token"]
            break
        print(f"[WARN] Token attempt {attempt+1}: {data}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] Token attempt {attempt+1}: {e}", file=sys.stderr)
    time.sleep(2)
else:
    raise Exception("Token failed after 3 attempts")

print(f"Token OK: {token[:20]}...", file=sys.stderr)

# Load draft info
with open(json_path, 'r', encoding='utf-8') as f:
    draft_info = json.load(f)

# Pre-insert history record
src_url = draft_info.get('content_source_url', '')
source = 'auto'
if src_url:
    domain = urlparse(src_url).netloc
    source = domain.replace('www.', '')[:30]

ts = datetime.datetime.now().isoformat()
c.execute('INSERT INTO history (date, title, source, source_url, cover_media_id, status, created_at, draft_media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
          (today, draft_info['title'], source, src_url, '', 'creating', ts, ''))
row_id = c.lastrowid
conn.commit()

# Create draft
try:
    payload = {
        "articles": [{
            "title": draft_info['title'],
            "author": draft_info.get('author', '君寻'),
            "digest": draft_info.get('digest', ''),
            "content": draft_info['content'],
            "thumb_media_id": draft_info['thumb_media_id'],
            "need_open_comment": draft_info.get('need_open_comment', 1),
            "only_fans_can_comment": draft_info.get('only_fans_can_comment', 0),
            "content_source_url": draft_info.get('content_source_url', '')
        }]
    }

    draft_url = f"{proxy}cgi-bin/draft/add?access_token={token}"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    
    print(f"Sending draft request... ({len(data)} bytes)", file=sys.stderr)
    r = requests.post(draft_url, data=data, headers=headers, timeout=90, verify=False)
    r.raise_for_status()
    resp = r.json()
    
    if resp.get("errcode", 0) != 0:
        raise Exception(f"Draft failed: {resp}")
    
    media_id = resp.get("media_id", "")
    print(f"Draft created: {media_id}", file=sys.stderr)
    
    # Update history
    c.execute('UPDATE history SET status=?, draft_media_id=?, created_at=? WHERE rowid=?',
              ('draft_created', media_id, datetime.datetime.now().isoformat(), row_id))
    conn.commit()
    
    # Write semaphore .done marker
    try:
        sem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'semaphore_check.py')
        subprocess.run([sys.executable, sem_path, account, '--create-done'],
                      check=True, capture_output=True, timeout=10)
    except Exception as sem_e:
        print(f'[WARN] semaphore --create-done: {sem_e}', file=sys.stderr)
    
    print(media_id)
    
except Exception as e:
    c.execute('UPDATE history SET status=?, created_at=? WHERE rowid=?',
              ('create_failed', datetime.datetime.now().isoformat(), row_id))
    conn.commit()
    raise
finally:
    conn.close()
