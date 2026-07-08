# -*- coding: utf-8 -*-
import sys, io, sqlite3, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

db_path = r'C:\Users\LMD\.qclaw\wechatlog\lanmuda\history.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# 插入记录（适配实际表结构）
c.execute('''INSERT INTO history (date, title, url, media_id, created_at) VALUES (?, ?, ?, ?, ?)''', (
    '2026-05-02',
    '万台交付全球第一，这家中国企业撕开了人形机器人量产的终局',
    'https://so.html5.qq.com/page/real/search_news?docid=70000021_13269f1537a21252',
    'Pr_xVfmq0Kz1JQWsflFwznGef7BAhoO2x6Xk6TEtGcZ8rvX9BxEChUrzkgcruMRx',
    datetime.datetime.now().isoformat()
))

conn.commit()
conn.close()
print('History record saved.')