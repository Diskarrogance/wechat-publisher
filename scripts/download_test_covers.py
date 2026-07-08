#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download and check a recent WeChat material image."""
import sys, io, os, json, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Try to access the cover upload URL directly (this is the CDN URL from today)
# Cover 1 from today's article
urls = [
    'http://mmecoa.qpic.cn/sz_mmecoa_png/UobsGRjtYicVoP1R0sVp5bkt78RchY8XqgYSAKaVGUgfeUbYRpJZAFT84Q9gS6PaWOE8qKJnkT5lZprR44DZia1Q/0?wx_fmt=png',
    'http://mmecoa.qpic.cn/sz_mmecoa_png/UobsGRjtYicXGEmRcyiaFr17giaJShSYksVXOFicMZQ9PjUC4T8HttcQyoYVzax7SBLl9gBcp4j93AoC5BVjs7zibg/0?wx_fmt=png',
]

for i, url in enumerate(urls):
    try:
        r = requests.get(url, timeout=15, verify=False)
        sz = len(r.content)
        if sz > 100:
            outpath = f'test_cover_{i+1}.png'
            with open(outpath, 'wb') as f:
                f.write(r.content)
            print(f'Image {i+1}: {sz:,} bytes → saved to {outpath}')
            
            # Quick hex check of first bytes
            hdr = r.content[:16]
            print(f'  Header: {hdr.hex()}')
            is_png = hdr[:8] == b'\x89PNG\r\n\x1a\n'
            is_jpeg = hdr[6:10] in (b'JFIF', b'Exif')
            print(f'  Format: {"PNG" if is_png else "JPEG" if is_jpeg else "OTHER"}')
        else:
            print(f'Image {i+1}: {sz} bytes - very small!')
            print(f'  Content: {r.content[:200]}')
    except Exception as e:
        print(f'Image {i+1}: ERROR {e}')
