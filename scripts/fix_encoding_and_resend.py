#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix garbled Chinese text in saved draft content and recreate drafts."""
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

# Correct Chinese content for both articles
articles = [
    {
        'slug': 'physical_ai',
        'title': 'AI不再困在屏幕里：2026智源大会宣告"物理AI"时代来临',
        'digest': '从聊天机器人到物理世界智能体，AI正在完成从"说"到"做"的终极跃迁。',
        'src_url': 'https://so.html5.qq.com/page/real/search_news?docid=70000021_6646a2d583073452',
        'thumb_mid': '',
        'draft_mid': ''
    },
    {
        'slug': 'ai_toys',
        'title': 'AI玩具大混战：2026年，你的毛绒玩具可能比你更聪明',
        'digest': '从能看会说的AI学伴机到长着毛的智能音箱，2026年AI玩具市场到底有多卷？这篇产业梳理把主流产品全盘了一遍。',
        'src_url': 'https://new.qq.com/rain/a/20260615A03J7M00',
        'thumb_mid': '',
        'draft_mid': ''
    }
]

# Find the saved content files and fix the encoding
# The content was saved as latin-1 decoded bytes → encode latin-1 → decode utf-8
import glob
for art in articles:
    slug = art['slug']
    # Search for matching file
    found = False
    for f in sorted(os.listdir(log_dir)):
        if not f.startswith('draft_') or not f.endswith('.json'):
            continue
        fp = os.path.join(log_dir, f)
        with open(fp, encoding='utf-8') as fh:
            data = json.load(fh)
        src = data.get('content_source_url', '')
        if slug == 'physical_ai' and '70000021' in src:
            found = True
        elif slug == 'ai_toys' and '20260615A03J7M00' in src:
            found = True
        
        if found:
            print(f'Found content for [{slug}]: {f}')
            raw_content = data.get('content', '')
            thumb_mid = data.get('thumb_media_id', '')
            
            # Fix the double-encoding
            art['content_raw'] = raw_content.encode('latin-1').decode('utf-8')
            art['thumb_mid'] = thumb_mid
            
            # Verify
            chinese = re.findall(r'[\u4e00-\u9fff]+', art['content_raw'][:1000])
            print(f'  Chinese groups in first 1k: {len(chinese)}')
            if chinese:
                print(f'  Sample: {chinese[0][:40]}')
            break
    
    if not found:
        print(f'ERROR: Could not find content for {slug}')

# Replace images in content
def replace_all_images(html_content, new_urls):
    """Replace ALL img src URLs except QR code with new URLs cyclically."""
    imgs = re.findall(r'src="([^"]+)"', html_content)
    non_qr = [s for s in imgs if 'sz_mmecoa_jpg' not in s and 'wximg' not in s]
    
    result = html_content
    for i, old in enumerate(non_qr):
        new = new_urls[i % len(new_urls)]
        result = result.replace(f'src="{old}"', f'src="{new}"', 1)
    
    final_imgs = re.findall(r'src="([^"]+)"', result)
    print(f'  Images: {len(final_imgs)} total → {len(set(final_imgs))} unique')
    return result

# Create drafts
for art in articles:
    content = art.get('content_raw', '')
    if not content:
        print(f'\n❌ Skipping {art["slug"]}: no content')
        continue
    
    print(f'\n=== Creating draft: {art["title"]} ===')
    
    new_urls = [
        uploads['results'][art['slug']]['img1']['url'],
        uploads['results'][art['slug']]['img2']['url'],
        uploads['results'][art['slug']]['img3']['url'],
    ]
    
    new_content = replace_all_images(content, new_urls)
    
    # Create draft
    draft_url = f'{proxy}cgi-bin/draft/add?access_token={token}'
    payload = {
        'articles': [{
            'title': art['title'],
            'author': '君寻',
            'digest': art['digest'],
            'content': new_content,
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

print('\n=== RESULTS ===')
for art in articles:
    if art['draft_mid']:
        print(f'✅ {art["title"][:40]}... → {art["draft_mid"][:40]}...')
    else:
        print(f'❌ {art["title"][:40]}... → FAILED')
