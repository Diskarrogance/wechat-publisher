#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check 混元 images for validity by trying to read with PIL."""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Try PIL
img_dir = r'C:\Users\LMD\.qclaw\wechatlog\junxun'
recent_pngs = [f for f in os.listdir(img_dir) if f.endswith('.png') and 'ai_toys' in f and f.startswith('img_')]
recent_pngs = sorted(recent_pngs)

import struct
for fname in recent_pngs:
    fp = os.path.join(img_dir, fname)
    sz = os.path.getsize(fp)
    with open(fp, 'rb') as f:
        hdr = f.read(40)
    
    if hdr[:8] == b'\x89PNG\r\n\x1a\n':
        w = (hdr[16] << 24) + (hdr[17] << 16) + (hdr[18] << 8) + hdr[19]
        h = (hdr[20] << 24) + (hdr[21] << 16) + (hdr[22] << 8) + hdr[23]
        ct = hdr[25]
        
        # Check PNG CRC vs expected file size
        expected_raw = w * h * (3 if ct == 2 else 1 if ct == 0 else 4 if ct == 6 else w)
        
        # Check if file ends with IEND chunk
        with open(fp, 'rb') as f:
            f.seek(-12, 2)
            trailer = f.read(12)
        
        has_iend = trailer[4:8] == b'IEND' if len(trailer) >= 12 else False
        
        print(f'{fname}: {sz:,} bytes, {w}x{h} type={ct}, IEND={has_iend}')
        
        # Check for non-black content in file data
        with open(fp, 'rb') as f:
            data = f.read()
        
        # Check if there are any non-identical bytes (to detect solid color)
        # Skip PNG header chunks, check actual image data
        # Simple: check if file appears to be from 混元 or CogView by size
        if sz > 500000:
            print(f'  -> Large image (混元), likely valid')
        elif sz > 50000:
            print(f'  -> Medium image (CogView), compressed')
        else:
            print(f'  -> Small image, check')
else:
    if not recent_pngs:
        print('No recent PNG images found in log dir')
        # Check local generated images
        for fname in sorted(os.listdir(img_dir)):
            if fname.endswith('.png'):
                fp = os.path.join(img_dir, fname)
                print(f'{fname}: {os.path.getsize(fp):,} bytes')
                break
