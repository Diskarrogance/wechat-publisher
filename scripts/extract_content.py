#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Get full article content from WeChat drafts and save to files."""
import sys, io, os, json, re, requests, urllib3
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

# Get draft list
list_url = f'{proxy}cgi-bin/draft/batchget?access_token={token}'
payload = json.dumps({'offset': 0, 'count': 10, 'no_content': 0}).encode('utf-8')
headers = {'Content-Type': 'application/json; charset=utf-8'}
r2 = requests.post(list_url, data=payload, headers=headers, timeout=60, verify=False)
result = r2.json()

log_dir = r'C:\Users\LMD\.qclaw\wechatlog\junxun'
if 'item' in result:
    for i, item in enumerate(result['item']):
        art = item.get('content', {}).get('news_item', [{}])[0]
        title = art.get('title', 'N/A')
        content = art.get('content', '')
        digest = art.get('digest', '')
        src_url = art.get('content_source_url', '')
        thumb_mid = art.get('thumb_media_id', '')
        
        # Save content to file for reuse
        out = {
            'title': title,
            'digest': digest,
            'content': content,
            'content_source_url': src_url,
            'thumb_media_id': thumb_mid,
        }
        
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title[:30])
        fname = f'{log_dir}/draft_{i+1}_{safe_title}.json'
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f'Saved draft {i+1}: {fname}')
        print(f'  Title: {title[:50]}')
        print(f'  Content length: {len(content)}')

        # Check images
        imgs = re.findall(r'<img[^>]+src="([^"]+)"', content)
        print(f'  Images: {len(imgs)} (unique: {len(set(imgs))})')
        for j, src in enumerate(imgs):
            short = src[-40:]
            print(f'    img{j+1}: ...{short}')
else:
    print(f'Error: {result}')
