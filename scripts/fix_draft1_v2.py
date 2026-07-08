#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix draft 1 (physical_AI) - clean title, proper images."""
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

log_dir = r'C:\Users\LMD\.qclaw\wechatlog\junxun'

with open(os.path.join(log_dir, 'upload_results.json'), encoding='utf-8') as f:
    uploads = json.load(f)

# Hardcoded correct title (from log, since WeChat API returned garbled)
title = 'AI不再困在屏幕里：2026智源大会宣告"物理AI"时代来临'
print(f'Title: {title} ({len(title)} chars)')
assert len(title) <= 64, f'Title too long: {len(title)}'

digest = '从聊天机器人到物理世界智能体，AI正在完成从"说"到"做"的终极跃迁。'
src_url = 'https://so.html5.qq.com/page/real/search_news?docid=70000021_6646a2d583073452'

# Read content from saved draft file  
# Find the correct file
draft_file = None
import subprocess
result = subprocess.run(['powershell', '-Command', 
    "Get-ChildItem 'C:\\Users\\LMD\\.qclaw\\wechatlog\\junxun\\draft_1_*.json' | Select-Object -First 1 -ExpandProperty FullName"],
    capture_output=True, text=True, encoding='utf-8')
draft_file = result.stdout.strip()

if not draft_file:
    print('ERROR: Cannot find draft file')
    sys.exit(1)

print(f'Reading content from: {os.path.basename(draft_file)}')
with open(draft_file, encoding='utf-8') as fh:
    draft_data = json.load(fh)

content = draft_data['content']
thumb_mid = draft_data['thumb_media_id']

# New image URLs (cycling through 3 for 6 positions)
new_urls = [
    uploads['results']['physical_ai']['img1']['url'],
    uploads['results']['physical_ai']['img2']['url'],
    uploads['results']['physical_ai']['img3']['url'],
]

# Replace all non-QR images sequentially
imgs = re.findall(r'src="([^"]+)"', content)
non_qr = [s for s in imgs if 'sz_mmecoa_jpg' not in s and 'wximg' not in s]
print(f'Non-QR images to replace: {len(non_qr)}')

new_html = content
for i, old in enumerate(non_qr):
    new = new_urls[i % len(new_urls)]
    new_html = new_html.replace(f'src="{old}"', f'src="{new}"', 1)

# Verify
final_imgs = re.findall(r'src="([^"]+)"', new_html)
final_unique = set(final_imgs)
print(f'Final: {len(final_imgs)} images, {len(final_unique)} unique')

# Create draft  
draft_url = f'{proxy}cgi-bin/draft/add?access_token={token}'
payload = {
    'articles': [{
        'title': title,
        'author': '君寻',
        'digest': digest,
        'content': new_html,
        'thumb_media_id': thumb_mid,
        'need_open_comment': 1,
        'only_fans_can_comment': 0,
        'content_source_url': src_url,
    }]
}
headers = {'Content-Type': 'application/json; charset=utf-8'}
data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
r = requests.post(draft_url, data=data, headers=headers, timeout=60, verify=False)
result = r.json()
print(f'Draft result: {result}')

if result.get('errcode', 0) == 0 or 'media_id' in result:
    print(f'✅ Draft created: {result.get("media_id", "N/A")[:40]}...')
else:
    print(f'❌ Failed: {result}')
