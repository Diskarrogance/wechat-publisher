#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1: Delete all existing drafts (garbled), then step 2: recreate with fixed encoding."""
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

# === STEP 1: Delete all existing drafts ===
list_url = f'{proxy}cgi-bin/draft/batchget?access_token={token}'
payload = json.dumps({'offset': 0, 'count': 10, 'no_content': 1}).encode('utf-8')
headers = {'Content-Type': 'application/json; charset=utf-8'}
r2 = requests.post(list_url, data=payload, headers=headers, timeout=30, verify=False)
result = r2.json()

to_delete = []
if 'item' in result:
    for item in result['item']:
        mid = item.get('media_id', '')
        art = item.get('content', {}).get('news_item', [{}])[0]
        title = art.get('title', '')[:30]
        if mid:
            to_delete.append(mid)
            print(f'Found draft: {title}... → {mid[:40]}...')

if to_delete:
    print(f'\nDeleting {len(to_delete)} garbled drafts...')
    for mid in to_delete:
        del_url = f'{proxy}cgi-bin/draft/delete?access_token={token}'
        del_payload = json.dumps({'media_id': mid}).encode('utf-8')
        r3 = requests.post(del_url, data=del_payload, headers=headers, timeout=30, verify=False)
        res = r3.json()
        if res.get('errcode', -1) == 0:
            print(f'  ✅ Deleted: {mid[:40]}...')
        else:
            print(f'  ❌ Failed: {res}')
else:
    print('No drafts to delete')

# === STEP 2: Load upload results ===
with open(os.path.join(log_dir, 'upload_results.json'), encoding='utf-8') as f:
    uploads = json.load(f)

# === STEP 3: Fix saved content encoding and create new drafts ===
articles = [
    {
        'slug': 'physical_ai',
        'title': 'AI不再困在屏幕里：2026智源大会宣告"物理AI"时代来临',
        'digest': '从聊天机器人到物理世界智能体，AI正在完成从"说"到"做"的终极跃迁。',
        'src_url': 'https://so.html5.qq.com/page/real/search_news?docid=70000021_6646a2d583073452',
    },
    {
        'slug': 'ai_toys',
        'title': 'AI玩具大混战：2026年，你的毛绒玩具可能比你更聪明',
        'digest': '从能看会说的AI学伴机到长着毛的智能音箱，2026年AI玩具市场到底有多卷？这篇产业梳理把主流产品全盘了一遍。',
        'src_url': 'https://new.qq.com/rain/a/20260615A03J7M00',
    }
]

# Find and fix content
for art in articles:
    found = False
    for f in sorted(os.listdir(log_dir)):
        if not f.startswith('draft_') or not f.endswith('.json'):
            continue
        fp = os.path.join(log_dir, f)
        try:
            with open(fp, encoding='utf-8') as fh:
                data = json.load(fh)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        src = data.get('content_source_url', '')
        match = False
        if art['slug'] == 'physical_ai' and '70000021' in src:
            match = True
        elif art['slug'] == 'ai_toys' and '20260615A03J7M00' in src:
            match = True
        
        if match:
            print(f'\nFound content for [{art["slug"]}]: {f}')
            raw = data.get('content', '')
            art['thumb_mid'] = data.get('thumb_media_id', '')
            
            # FIX: decode from latin-1 to fix double-encoding
            raw_bytes = raw.encode('latin-1')
            art['content'] = raw_bytes.decode('utf-8')
            
            # Verify
            chinese = re.findall(r'[\u4e00-\u9fff]+', art['content'][:500])
            print(f'  Chinese in first 500 chars: {len(chinese)} groups')
            if chinese:
                print(f'  Sample: {chinese[0][:50]}')
            found = True
            break
    
    if not found:
        print(f'\nERROR: No content for {art["slug"]}')

# Create drafts
for art in articles:
    if 'content' not in art:
        print(f'\n❌ Skipping {art["slug"]}: no content')
        continue
    
    print(f'\n=== Creating draft: {art["title"][:40]}... ===')
    
    new_urls = [
        uploads['results'][art['slug']]['img1']['url'],
        uploads['results'][art['slug']]['img2']['url'],
        uploads['results'][art['slug']]['img3']['url'],
    ]
    
    # Replace images
    html = art['content']
    imgs = re.findall(r'src="([^"]+)"', html)
    non_qr = [s for s in imgs if 'sz_mmecoa_jpg' not in s]
    
    result_html = html
    for i, old in enumerate(non_qr):
        new = new_urls[i % len(new_urls)]
        result_html = result_html.replace(f'src="{old}"', f'src="{new}"', 1)
    
    final_imgs = re.findall(r'src="([^"]+)"', result_html)
    print(f'  Images: {len(final_imgs)} total → {len(set(final_imgs))} unique')
    
    # Create draft
    draft_url = f'{proxy}cgi-bin/draft/add?access_token={token}'
    payload = {
        'articles': [{
            'title': art['title'],
            'author': '君寻',
            'digest': art['digest'],
            'content': result_html,
            'thumb_media_id': art['thumb_mid'],
            'need_open_comment': 1,
            'only_fans_can_comment': 0,
            'content_source_url': art['src_url'],
        }]
    }
    
    headers = {'Content-Type': 'application/json; charset=utf-8'}
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    r = requests.post(draft_url, data=data, headers=headers, timeout=60, verify=False)
    result = r.json()
    
    if 'media_id' in result:
        mid = result['media_id']
        print(f'  ✅ Draft created: {mid[:40]}...')
        art['draft_mid'] = mid
    else:
        print(f'  ❌ Failed: {result}')

print('\n✅ Done!')
for art in articles:
    if art.get('draft_mid'):
        print(f'  ✅ {art["title"]}')
