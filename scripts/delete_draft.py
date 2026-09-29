# -*- coding: utf-8 -*-
"""delete_draft.py - 删除微信图文草稿
用法：python delete_draft.py <account> <media_id>
"""
import sys, io, os, json, time, requests, urllib3, urllib.request, ssl
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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

def main():
    account = sys.argv[1]
    media_id = sys.argv[2]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(os.path.dirname(script_dir), "config", "accounts.yaml"), 'r', encoding='utf-8') as f:
        import yaml
        cfg = yaml.safe_load(f)
    acct_cfg = next(a for a in cfg['accounts'] if a.get('key') == account)
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

if __name__ == '__main__':
    main()
