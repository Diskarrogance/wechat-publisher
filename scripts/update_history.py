import sqlite3, sys, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

db = r'C:\Users\LMD\.qclaw\wechatlog\lanmuda\history.db'
now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
today = '2026-06-01'

cover_media_id = 'Pr_xVfmq0Kz1JQWsflFwzrBK_LH50ltmqJWJ3-QzCuGphZHbDglaaUMU0j2y8vd6'

conn = sqlite3.connect(db)
c = conn.cursor()

# Update cover_media_id and status
c.execute("""
    UPDATE history 
    SET cover_media_id = ?, 
        source = ?,
        status = ?
    WHERE date = ?
""", (cover_media_id, 'TechCrunch', '草稿已创建（含封面+配图）', today))

print(f'Updated {c.rowcount} record(s)')

# Verify
c.execute("SELECT * FROM history WHERE date = ?", (today,))
row = c.fetchone()
if row:
    print(f'Date: {row[0]}')
    print(f'Title: {row[1]}')
    print(f'Source: {row[2]}')
    print(f'Source URL: {row[3]}')
    print(f'Draft MediaID: {row[4]}')
    print(f'Cover MediaID: {row[5]}')
    print(f'Status: {row[6]}')
    print(f'Created: {row[7]}')

conn.commit()
conn.close()
