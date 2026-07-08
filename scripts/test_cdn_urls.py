#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test WeChat CDN URLs with /0 and /640 sizes."""
import sys, io, os, json, requests, yaml
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Test the cover images from today's draft
# From draft content (image URLs used in article body = /640)
body_urls = [
    'http://mmecoa.qpic.cn/sz_mmecoa_png/UobsGRjtYicVoP1R0sVp5bkt78RchY8XqgYSAKaVGUgfeUbYRpJZAFT84Q9gS6PaWOE8qKJnkT5lZprR44DZia1Q/640?wx_fmt=png',
]

# From material list (image URLs returned by API = /0)
material_urls = [
    'http://mmecoa.qpic.cn/sz_mmecoa_png/UobsGRjtYicVoP1R0sVp5bkt78RchY8XqgYSAKaVGUgfeUbYRpJZAFT84Q9gS6PaWOE8qKJnkT5lZprR44DZia1Q/0?wx_fmt=png',
]

# Also test the older images from June 21
jun21_body = [
    'http://mmecoa.qpic.cn/mmecoa_png/UobsGRjtYicXiasJiaPLvEDJ8g2GibY0HBPLhl95hY5RWjsgbof3PMFdFnLQNYoZSBMNDw/640?wx_fmt=png',
]

print('=== Article body URLs (/640) ===')
for url in body_urls:
    r = requests.get(url, timeout=15, verify=False)
    print(f'  /640: {len(r.content):,} bytes, status={r.status_code}')

print('\n=== Material list URLs (/0) ===')
for url in material_urls:
    r = requests.get(url, timeout=15, verify=False)
    print(f'  /0: {len(r.content):,} bytes, status={r.status_code}')

# Try other sizes
for size in ['640', '300', '200', '120']:
    url = body_urls[0].replace('/640?', f'/{size}?')
    r = requests.get(url, timeout=10, verify=False)
    print(f'  /{size}: {len(r.content):,} bytes, status={r.status_code}')

print('\n=== June 21 article body URL ===')
for url in jun21_body:
    r = requests.get(url, timeout=15, verify=False)
    print(f'  /640: {len(r.content):,} bytes, status={r.status_code}')
