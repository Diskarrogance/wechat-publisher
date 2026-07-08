#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify saved article content and extract img placeholders."""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = r'C:\Users\LMD\.qclaw\wechatlog\junxun'
for f in sorted(os.listdir(d)):
    if not f.startswith('draft_'):
        continue
    fp = os.path.join(d, f)
    with open(fp, encoding='utf-8') as fh:
        data = json.load(fh)
    
    title = data.get('title', 'N/A')
    content = data.get('content', '')
    print(f'=== {f} ===')
    print(f'Title: {title}')
    print(f'Content length: {len(content)}')
    
    # Check for img placeholders vs real URLs
    if '{img' in content:
        import re
        ph = re.findall(r'\{img\d+_url\}', content)
        print(f'  Placeholders found: {ph}')
    
    # Show first line of content
    lines = content.strip().split('\n')
    print(f'  First line: {lines[0][:80]}')
    
    # Find image patterns in content
    import re
    imgs = re.findall(r'src="([^"]+)"', content)
    print(f'  Image URLs: {len(imgs)} (unique: {len(set(imgs))})')
    print()
