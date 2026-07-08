#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2: Generate fresh images for both articles.
Generates 2 covers + 6 配图 = 8 images total."""
import sys, io, os, subprocess, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import yaml
cfg = yaml.safe_load(open(r'C:\Users\LMD\.qclaw\skills\wechat-publisher\config\accounts.yaml', encoding='utf-8'))

gen_script = r'C:\Users\LMD\.qclaw\skills\wechat-publisher\scripts\generate_cover.py'
out_dir = r'C:\Users\LMD\.qclaw\wechatlog\junxun'

os.makedirs(out_dir, exist_ok=True)

# Article 1: AI玩具大混战 (from 腾讯新闻)
# Article 2: 物理AI (from 环球网)
articles = [
    {
        'name': 'AI玩具',
        'file_slug': 'ai_toys',
        'cover_prompt': '参考图的卡通形象，穿着休闲T恤，坐在一个堆满了各种AI玩具的房间里开心地拿着一个毛绒智能玩具。堆满科技感的玩具，柔和的暖光灯。3D渲染，超现实主义，皮克斯风格，卡通可爱，丁达尔效应，丰富细节，景深层次感，电影级质感，8K高清画质',
        'img_prompts': [
            '参考图的卡通形象，穿着休闲T恤，抱着一个可爱的毛绒智能玩具熊，开心地贴着脸。柔和暖光，温馨家居氛围。3D渲染，皮克斯风格，卡通可爱，丁达尔效应，景深层次感，电影级质感，8K高清画质',
            '参考图的卡通形象，穿着休闲T恤，坐在桌前和一个AI学伴机互动，对着机器说话。桌上散落着积木和画纸，暖光台灯。3D渲染，皮克斯风格，卡通可爱，顶光，景深层次感，电影级质感，8K高清画质',
            '参考图的卡通形象，穿着休闲T恤，站在书桌前举起一个刚拼好的创意作品给AI展示，脸上带着期待的笑容。晨光从窗户洒入。3D渲染，皮克斯风格，卡通可爱，丁达尔效应，明暗对比，景深层次感，8K高清画质',
        ]
    },
    {
        'name': '物理AI',
        'file_slug': 'physical_ai',
        'cover_prompt': '参考图的卡通形象，穿着白色科技感外套，站在充满未来感的AI实验室中央。全息投影的机器人手臂和数据显示屏闪烁。冷色调蓝光为主。3D渲染，超现实主义，皮克斯风格，科幻感，丁达尔效应，霓虹光效，景深层次感，电影级质感，8K高清画质',
        'img_prompts': [
            '参考图的卡通形象，穿着科技感外套，站在巨大的城市全息地图前，用手指着地图上的发光交互点，好奇地转头看。蓝紫色冷光。3D渲染，超现实主义，皮克斯风格，科幻感，丁达尔效应，景深层次感，8K高清画质',
            '参考图的卡通形象，穿着科技感外套，在一台正在运作的人形机器人面前，伸出小手和机器人的机械手轻轻碰触。冷色实验室灯光，金属质感。3D渲染，皮克斯风格，科幻感，伦勃朗光，电影级质感，8K高清画质',
            '参考图的卡通形象，穿着科技感外套，坐在全息投影屏幕前查看AI数据流，各种虚拟窗口环绕。蓝色冷光为主，科技感十足。3D渲染，超现实主义，皮克斯风格，丁达尔效应，景深层次感，电影级质感，8K高清画质',
        ]
    }
]

# Generate cover + 3 images for each article
for art_idx, art in enumerate(articles):
    article_num = art_idx + 1
    slug = art['file_slug']
    
    print(f'\n{"="*60}')
    print(f'Article {article_num}: {art["name"]}')
    print(f'{"="*60}')
    
    # Cover
    cover_out = os.path.join(out_dir, f'cover_{slug}.png')
    print(f'\nGenerating cover...')
    cmd = [
        'python', gen_script,
        'junxun', 'cover', art['cover_prompt'], cover_out
    ]
    subprocess.run(cmd, cwd=out_dir)
    # Wait for cooldown
    time.sleep(15)
    
    # 3 images
    for img_idx, img_prompt in enumerate(art['img_prompts']):
        img_num = img_idx + 1
        img_out = os.path.join(out_dir, f'img_{slug}_{img_num}.png')
        print(f'\nGenerating img{img_num}...')
        cmd = [
            'python', gen_script,
            'junxun', f'img{img_num}', img_prompt, img_out
        ]
        subprocess.run(cmd, cwd=out_dir)
        if img_idx < 2:  # No need to wait after last image
            time.sleep(20)  # Longer cooldown for rate limit

print('\n✅ All images generated!')
print(f'Files in {out_dir}:')
for f in sorted(os.listdir(out_dir)):
    if any(f.endswith(f'{slug}_{n}.png') or f.endswith(f'{slug}.png') for slug in ['ai_toys', 'physical_ai'] for n in range(1,4) + ['']):
        fp = os.path.join(out_dir, f)
        size_kb = os.path.getsize(fp) // 1024
        print(f'  {f} ({size_kb}KB)')
