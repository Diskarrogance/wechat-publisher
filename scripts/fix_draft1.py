#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix draft 1 (physical_AI) - replace all non-QR images with new ones."""
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
print(f'Token OK: {token[:20]}...')

log_dir = r'C:\Users\LMD\.qclaw\wechatlog\junxun'

# Load upload results
with open(os.path.join(log_dir, 'upload_results.json'), encoding='utf-8') as f:
    uploads = json.load(f)

qr_img_url = 'http://mmecoa.qpic.cn/sz_mmecoa_jpg/UobsGRjtYicVG1axkc3e3MLf1dtKCBfWjurXQfFWk8DthtyI7bb5dzEP27gUSWtic4CS14sPqVibibhGW97XztYM0ot9tHSq8dplEl364PlBeiaU/0?wx_fmt=jpeg'

# Find the saved draft content for physical_ai
draft_file = None
for f in sorted(os.listdir(log_dir)):
    if f.startswith('draft_') and 'physical' not in f:
        fp = os.path.join(log_dir, f)
        with open(fp, encoding='utf-8') as fh:
            data = json.load(fh)
        src = data.get('content_source_url', '')
        if 'docid=70000021_6646a2d583073452' in src:
            draft_file = fp
            break

if not draft_file:
    print('ERROR: Could not find physical_ai draft content')
    sys.exit(1)

print(f'Found content: {draft_file}')

with open(draft_file, encoding='utf-8') as fh:
    draft_data = json.load(fh)

content = draft_data['content']
thumb_mid = draft_data['thumb_media_id']
title = draft_data['title']
src_url = draft_data.get('content_source_url', '')
digest = '从聊天机器人到物理世界智能体，AI正在完成从"说"到"做"的终极跃迁。'

# Strategy: Find all img src EXCEPT the QR code, then replace each one
# The content has 7 images: 6 article images + 1 QR code
# We need to replace 6 images with 3 new URLs (each URL used twice for img+caption pairs)

new_urls = [
    uploads['results']['physical_ai']['img1']['url'],
    uploads['results']['physical_ai']['img2']['url'],
    uploads['results']['physical_ai']['img3']['url'],
]

# Find all non-QR img src
imgs = re.findall(r'src="([^"]+)"', content)
non_qr_imgs = [src for src in imgs if 'sz_mmecoa_jpg' not in src and 'wximg' not in src]

print(f'Total images: {len(imgs)}, Non-QR: {len(non_qr_imgs)}')

# Replace each non-QR URL sequentially with new URLs cycling
new_content = content
img_pos = 0
for old_url in non_qr_imgs:
    new_url = new_urls[img_pos % len(new_urls)]
    old_short = old_url[-30:]
    new_short = new_url[-30:]
    print(f'  Replacing {old_short} → {new_short}')
    new_content = new_content.replace(f'src="{old_url}"', f'src="{new_url}"', 1)
    img_pos += 1

# Verify replacements
imgs_after = re.findall(r'src="([^"]+)"', new_content)
unique_after = set(imgs_after)
print(f'\nAfter replacement: {len(imgs_after)} images, {len(unique_after)} unique')

# Delete old draft first
old_draft_mid = 'DTu4zlZnETHW4SvORldxosU4nfmEqZFdXbhfiU87NhwlgXcwZl1eQu4PRSoCJtDq'
del_url = f'{proxy}cgi-bin/draft/delete?access_token={token}'
del_payload = json.dumps({'media_id': 'DTu4zlZnETHW4SvORldxovhe31Yo38_uKZog9-e2qeV4Znv9vyWqKaBIhM1BgzE0'}).encode('utf-8')  # The bad draft
r = requests.post(del_url, data=del_payload, headers={'Content-Type': 'application/json'}, timeout=30, verify=False)
print(f'\nDeleted bad draft: {r.json()}')

# Create new draft
draft_url = f'{proxy}cgi-bin/draft/add?access_token={token}'
payload = {
    'articles': [{
        'title': title,
        'author': '君寻',
        'digest': digest,
        'content': new_content,
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
print(f'New draft: {result}')
