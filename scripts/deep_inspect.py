#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep inspect draft images - check every single image URL."""
import sys, io, os, json, requests, re, yaml
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

# Get ALL drafts with content
list_url = f'{proxy}cgi-bin/draft/batchget?access_token={token}'
payload = json.dumps({'offset': 0, 'count': 5, 'no_content': 0}).encode('utf-8')
headers = {'Content-Type': 'application/json; charset=utf-8'}
r2 = requests.post(list_url, data=payload, headers=headers, timeout=60, verify=False)
result = r2.json()

if 'item' not in result:
    print(f'Error: {result}')
    sys.exit(1)

for item in result['item']:
    art = item.get('content', {}).get('news_item', [{}])[0]
    content_raw = art.get('content', '')
    title_raw = art.get('title', '')
    
    # Fix Mojibake
    try:
        title = title_raw.encode('latin-1').decode('utf-8')
    except:
        title = title_raw
    
    try:
        content = content_raw.encode('latin-1').decode('utf-8')
    except:
        content = content_raw
    
    print(f'\n=== {title[:50]} ===')
    
    img_urls = re.findall(r'src="([^"]+)"', content)
    img_urls = list(dict.fromkeys(img_urls))  # dedupe but preserve order
    
    for j, u in enumerate(img_urls):
        typ = 'QR  ' if 'sz_mmecoa_jpg' in u else 'COVER' if j == 0 else f'IMG {j}'
        
        # Try to download
        try:
            r = requests.get(u, timeout=15, verify=False, 
                           headers={'User-Agent': 'Mozilla/5.0'})
            sz = len(r.content)
            status = r.status_code
            if sz > 100:
                print(f'  [{typ}] ...{u[-60:]} → {sz:,} bytes (OK)')
            else:
                print(f'  [{typ}] ...{u[-60:]} → {sz} bytes (status={status}) ⚠️')
        except Exception as e:
            print(f'  [{typ}] ...{u[-60:]} → ERROR: {e}')
