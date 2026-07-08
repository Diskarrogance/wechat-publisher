#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify new drafts and check images."""
import sys, io, os, json, re, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
token = r.json()['access_token']
print(f'Token OK')

# List drafts
list_url = f'{proxy}cgi-bin/draft/batchget?access_token={token}'
payload = json.dumps({'offset': 0, 'count': 10, 'no_content': 0}).encode('utf-8')
headers = {'Content-Type': 'application/json; charset=utf-8'}
r2 = requests.post(list_url, data=payload, headers=headers, timeout=60, verify=False)
result = r2.json()

if 'item' in result:
    items = result['item']
    print(f'Total drafts: {len(items)}')
    for i, item in enumerate(items):
        art = item.get('content', {}).get('news_item', [{}])[0]
        title = art.get('title', 'N/A')[:50]
        content = art.get('content', '')
        imgs = re.findall(r'src="([^"]+)"', content)
        unique = set(imgs)
        print(f'\nDraft {i+1}: {title}')
        print(f'  Total images: {len(imgs)}, Unique: {len(unique)}')
        # Show last 30 chars of each unique URL
        for j, url in enumerate(unique):
            print(f'  Unique img {j+1}: ...{url[-30:]}')
else:
    print(f'Error: {result}')
