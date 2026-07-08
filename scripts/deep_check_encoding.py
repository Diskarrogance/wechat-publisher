#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep check content encoding - scan beyond first 2k chars."""
import sys, io, os, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

d = r'C:\Users\LMD\.qclaw\wechatlog\junxun'
for f in sorted(os.listdir(d)):
    if not (f.startswith('draft_1_') or f.startswith('draft_2_')) or not f.endswith('.json'):
        continue
    fp = os.path.join(d, f)
    with open(fp, encoding='utf-8') as fh:
        data = json.load(fh)
    
    content = data.get('content', '')
    
    print(f'=== {f[:50]}... ===')
    print(f'Total content length: {len(content)}')
    
    # Search entire content for Chinese characters
    chinese = re.findall(r'[\u4e00-\u9fff]+', content)
    print(f'Chinese character groups in full content: {len(chinese)}')
    if chinese:
        for c in chinese[:5]:
            print(f'  [{c[:80]}]')
    else:
        # What ARE in the content instead of Chinese?
        # Find non-ASCII non-HTML characters
        non_ascii = [(i, c, hex(ord(c))) for i, c in enumerate(content[8000:9000]) if ord(c) > 127]
        print(f'Non-ASCII chars in range [8000:9000]: {len(non_ascii)}')
        if non_ascii:
            for i, c, h in non_ascii[:20]:
                idx = 8000 + i
                context = content[max(0,idx-5):idx+5]
                print(f'  pos={idx} char={repr(c)} hex={h} context=...{repr(context)}')
        
        # Look for HTML entities
        entities = re.findall(r'&#\d+;|&[a-z]+;', content[5000:15000])
        print(f'HTML entities: {len(entities)}')
        if entities:
            for e in entities[:10]:
                print(f'  {e}')
        
        # Check if content is all HTML tags with no real text
        text_only = re.sub(r'<[^>]+>', '', content)
        text_only = re.sub(r'\s+', ' ', text_only).strip()
        print(f'Text after stripping HTML (first 200): {repr(text_only[:200])}')
        
        # Check with latin-1 decode
        raw_bytes = content.encode('latin-1')
        try:
            decoded = raw_bytes.decode('utf-8')
            print(f'\nUTF-8 from latin-1 (first 300): {repr(decoded[:300])}')
        except:
            print('\nCannot decode as UTF-8 from latin-1')
        
        # Check if the content has embedded escaped unicode
        if '\\u' in content:
            print('Found \\u escapes in content!')
        if '&quot;' in content:
            print('Found HTML &quot; escapes')
    print()
