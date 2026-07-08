#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1: Delete old WeChat drafts."""
import sys, io, os, json, requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import yaml

cfg = yaml.safe_load(open(r'C:\Users\LMD\.qclaw\skills\wechat-publisher\config\accounts.yaml', encoding='utf-8'))
acct = next(a for a in cfg['accounts'] if a.get('key') == 'junxun')
proxy = cfg['global']['proxy']

env = {}
with open(acct['env_file'], encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
app_sec = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')

url = f'{proxy}cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_sec}'
r = requests.get(url, timeout=30, verify=False)
data = r.json()
token = data['access_token']
print(f'Token OK: {token[:20]}...')

# Delete draft
def delete_draft(media_id):
    del_url = f'{proxy}cgi-bin/draft/delete?access_token={token}'
    payload = json.dumps({'media_id': media_id}).encode('utf-8')
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    r = requests.post(del_url, data=payload, headers=headers, timeout=30, verify=False)
    result = r.json()
    if result.get('errcode', -1) == 0:
        print(f'  ✅ Deleted: {media_id[:40]}...')
    else:
        print(f'  ❌ Delete failed: {result}')
    return result

# The drafts from today
drafts_to_delete = [
    'DTu4zlZnETHW4SvORldxosU4nfmEqZFdXbhfiU87NhwlgXcwZl1eQu4PRSoCJtDq',
    'DTu4zlZnETHW4SvORldxogbOgVKSAZIebvLTr5Fv6Vh1GOgUNfAi1MwGGg5-soB9',
]

print('\nDeleting old drafts...')
for mid in drafts_to_delete:
    delete_draft(mid)
