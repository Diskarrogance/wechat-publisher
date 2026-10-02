"""
create_draft.py - 创建微信图文草稿
用法：python create_draft.py <account> <draft_json|@file>

参数：
  account    : junxun | lanmuda（也接受中文名「君寻」「岚牧哒」，内部统一归一化为 key）
  draft_json : JSON 字符串或 @文件路径，格式：
    {
      "title": "标题",
      "author": "作者（可省略，省略时回落到 accounts.yaml 的 author）",
      "content": "正文HTML",
      "digest": "摘要",
      "thumb_media_id": "封面media_id",
      "need_open_comment": 1,
      "only_fans_can_comment": 0,
      "content_source_url": "文章来源原始URL"
    }

内置硬关卡（任一不通过 → exit 1 拒绝建草稿）：
  1. 标题长度 ≤ 64
  2. 内容合规（compliance_check：硬禁词 / 涉政词堆叠 / 投资诱导 / 标题绝对化）
  3. 正文裸 URL（带 from=appmsg 但不在 <img> 内）
  4. 正文 <img> 数 ≥ 3
  5. 君寻：正文末尾必须有企业群二维码（含「粉丝群」+ mmecoa）
  6. 岚牧哒：正文中文占比 ≥ 30%（防「未翻译即建稿」事故）

编码：创建草稿走 urllib + 显式 UTF-8 Content-Type，绕开 Nginx 代理的 Latin-1 污染。
"""
import sys, io, os, json, requests, time, urllib3, ssl, urllib.request
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# requests 仅用于 token 获取；创建草稿用 urllib（避免 Nginx 代理的 Content-Type/gzip 编码问题）
# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_env(env_file):
    """加载 .env 文件到字典"""
    env = {}
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def get_token(app_id, app_secret, proxy, retries=3):
    """获取微信 access_token（自动重试）"""
    for attempt in range(retries):
        try:
            url = f"{proxy}cgi-bin/token"
            params = {"grant_type": "client_credential", "appid": app_id, "secret": app_secret}
            r = requests.get(url, params=params, timeout=30, verify=False)
            r.raise_for_status()
            data = r.json()
            if "access_token" not in data:
                if attempt < retries - 1:
                    print(f"[WARN] Token attempt {attempt+1} failed: {data}, retrying...", file=sys.stderr)
                    time.sleep(2)
                    continue
                raise Exception(f"Token failed after {retries} attempts: {data}")
            return data["access_token"]
        except Exception as e:
            if attempt < retries - 1:
                print(f"[WARN] Token attempt {attempt+1} error: {e}, retrying...", file=sys.stderr)
                time.sleep(2)
                continue
            raise Exception(f"Token error after {retries} attempts: {e}")


def create_draft(token, draft_info, proxy):
    """创建图文草稿（使用 urllib 替代 requests，避免 Nginx 代理的 Latin-1 编码问题）"""
    url = f"{proxy}cgi-bin/draft/add?access_token={token}"

    payload = {
        "articles": [{
            "title": draft_info['title'],
            "author": draft_info['author'],
            "digest": draft_info.get('digest', ''),
            "content": draft_info['content'],
            "thumb_media_id": draft_info['thumb_media_id'],
            "need_open_comment": draft_info.get('need_open_comment', 1),
            "only_fans_can_comment": draft_info.get('only_fans_can_comment', 0),
            "content_source_url": draft_info.get('content_source_url', '')
        }]
    }

    # 🔥 使用 urllib 替代 requests 发送 POST
    # requests 在通过自建 Nginx 代理网关时 Content-Type 被篡改，
    # UTF-8 字节被当 Latin-1 存入微信服务器 → 中文正文变乱码（第 4 次复发）
    # urllib 更底层，不进行编码猜测
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json; charset=utf-8')
    r = urllib.request.urlopen(req, context=ctx, timeout=60)
    resp = json.loads(r.read().decode('utf-8'))
    if resp.get("errcode", 0) != 0:
        raise Exception(f"Draft failed: {resp}")
    return resp.get("media_id", "")


def load_config():
    config_dir = os.path.dirname(os.path.abspath(__file__))
    yaml_file = os.path.join(os.path.dirname(config_dir), "config", "accounts.yaml")
    import yaml
    with open(yaml_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_account(cfg, account):
    """把 key 或中文名统一解析为账号配置项。

    修复 2026-09-27/2026-09-29 同类 bug：脚本各处曾硬编码 key 比较
    （如 `account == 'junxun'`），调用方传中文名「君寻」时全部漏判——
    配额被误判为 1 篇、二维码检查被跳过。现在统一在这里归一化。
    """
    if not account:
        return None
    for a in cfg.get('accounts', []):
        if a.get('key') == account or a.get('name') == account:
            return a
    return None


_CFG_CACHE = None


def _cfg():
    """accounts.yaml 只读一次并缓存"""
    global _CFG_CACHE
    if _CFG_CACHE is None:
        _CFG_CACHE = load_config()
    return _CFG_CACHE


def normalize_key(account):
    """任意写法（key / 中文名）→ 规范 key。解析不到时原样返回。"""
    if account in ('junxun', 'lanmuda'):
        return account
    try:
        a = resolve_account(_cfg(), account)
    except Exception:
        a = None
    return (a or {}).get('key') or account


def run_preflight(acct_key, title, content, source_file=None):
    """建稿前硬关卡。返回 exit_code（0=通过，1=拒绝）或 None（校验异常，不阻断）

    防御性归一化：调用方可能传中文名「君寻」，不归一化会导致
    君寻二维码检查被静默跳过（2026-09-27/09-29 踩过两次同类 bug）。
    """
    import re as _re
    acct_key = normalize_key(acct_key)
    has_qr = ('粉丝群' in content) and ('mmecoa' in content)

    # ── 1/2. 标题长度 + 内容合规 ──
    if len(title) > 64:
        print(f"TITLE_VALIDATE_FAIL: 标题长度 {len(title)} > 64，禁止创建草稿")
        return 1

    # ── 1b. 标题搜索友好度（2026-10-02 起为硬关卡）──
    # 依据：两号均为服务号，微信官方明确「推荐是订阅号的能力」→ 推荐恒为 0，
    # 搜一搜是唯一能自主争取的增量流量。故标题前 12 字必须含可搜索实体（品牌/产品/品类词），
    # 且不超过 26 字（搜索结果会截断）。规则见 SKILL.md §6.1-C，
    # 词库见 config/keywords.yaml + config/search_terms.yaml。
    try:
        import validate_title as _vt
        _sf_ok, _sf_msgs = _vt.search_friendliness(title, '微信搜一搜')
        if not _sf_ok:
            print("TITLE_GEO_FAIL: 标题不符合搜索友好规则，禁止创建草稿")
            for _m in _sf_msgs:
                print(f"  ✗ {_m}")
            print("处置：把「品牌名/产品名/品类词」提到前 12 字、标题压到 26 字以内，再重交")
            return 1
    except Exception as _ve:
        print(f"[WARN] validate_title 不可用（{type(_ve).__name__}: {_ve}），"
              f"降级跳过标题搜索友好度检查", file=sys.stderr)

    try:
        import compliance_check as _cc
        _fails, _warns, _stats = _cc.check(title, content)
        for _w in _warns:
            print(_w)
        if _fails:
            print("COMPLIANCE_VALIDATE_FAIL: 内容合规检查未通过，禁止创建草稿")
            for _f in _fails:
                print(f"  ✗ {_f}")
            return 1
    except Exception as _e:
        # 词表模块不可用时降级为内置最小集合，不静默放行
        print(f"[WARN] compliance_check 不可用（{type(_e).__name__}: {_e}），降级为内置禁词校验",
              file=sys.stderr)
        _builtin = ['封杀', '慌了', '慌了神', '傻眼', '倒闭', '跑路', '崩盘', '喊杀', '喊打',
                    '活该', '暴雷', '割韭菜', '碾压', '吊打', '血洗', '喊打喊杀']
        _hits = [w for w in _builtin if w in title]
        if _hits:
            print(f"TITLE_VALIDATE_FAIL: 标题含敏感词 {_hits}，禁止创建草稿（防删文）")
            return 1

    # ── 3. 裸 URL（带 from=appmsg 但未包在 <img> 内）──
    # 计数口径与 validate_article_html.py 保持一致：用「img 标签数」（去重前），
    # 裸 URL 判定才用 set 去重比较。
    _all_urls = _re.findall(r'https?://[^\s"<>]+', content)
    _img_list = _re.findall(r'<img[^>]+src="([^"]+)"', content)
    _img_set = set(_img_list)
    _bare = [u for u in _all_urls if 'from=appmsg' in u and u not in _img_set]
    if _bare:
        print(f"HTML_VALIDATE_FAIL: 正文存在 {len(_bare)} 个裸 URL（带 from=appmsg 但未包在 <img> 内），禁止创建草稿")
        print(f"首个裸 URL: {_bare[0][:100]}")
        print("请先运行 validate_article_html.py 定位并修复，再重新提交")
        return 1

    # ── 4. 配图数量 ──
    if len(_img_list) < 3:
        print(f"HTML_VALIDATE_FAIL: 正文 <img> 标签数 {len(_img_list)} < 3，禁止创建草稿（配图不足）")
        return 1

    # ── 5. 君寻企业群二维码 ──
    if acct_key == 'junxun' and not has_qr:
        print("QR_VALIDATE_FAIL: 君寻正文缺少企业群二维码（需含「粉丝群」文案 + mmecoa 二维码图），禁止创建草稿")
        print("请按 SKILL.md 第八步在正文末尾追加二维码 HTML 块")
        return 1

    # ── 6. 岚牧哒中文占比（防未翻译即建稿）──
    if acct_key == 'lanmuda':
        import re as _re2
        _text = _re2.sub(r'<[^>]+>', ' ', content)
        _han = len(_re2.findall(r'[\u4e00-\u9fff]', _text))
        _ratio = _han / max(1, len(_re2.sub(r'\s+', '', _text)))
        if _ratio < 0.30:
            print(f"LANG_VALIDATE_FAIL: 岚牧哒正文中文占比仅 {_ratio:.0%}（<30%），"
                  f"疑似英文源未翻译，禁止创建草稿")
            return 1

    # ── 7. GEO 就绪度 / 原创可声明性（2026-09-30 新增）──
    # 目的：保证每篇都具备「可检索化四要素」且与源文/本站历史无高重合，
    # 使文章在 MP 后台能顺利勾选原创声明（见 SKILL.md §11）。
    try:
        import geoready_check as _gr
        _r = _gr.run_html(content, acct_key, source_file=source_file)
        for _w in _r.get('warns', []):
            if _w.startswith('未提供源文'):
                continue          # 无源文是常态（补发/手工稿），不刷屏
            print(f"  ⚠ {_w}")
        if _r.get('fails'):
            print("GEOREADY_FAIL: 可检索化 / 原创可声明性未通过，禁止创建草稿")
            for _f in _r['fails']:
                print(f"  ✗ {_f}")
            print("处置：补齐要素（首段结论句 / 独家数据段 / 末尾 2~3 组 Q&A）或重写撞车片段")
            return 1
    except Exception as _ge:
        print(f"[WARN] geoready_check 不可用（{type(_ge).__name__}: {_ge}），"
              f"降级跳过 GEO 就绪度检查", file=sys.stderr)

    return 0


def main():
    # 可选参数剥离：--source-file <路径>（供 GEO 就绪度关卡做源文相似度比对）
    _argv = list(sys.argv[1:])
    source_file = None
    if '--source-file' in _argv:
        _i = _argv.index('--source-file')
        if _i + 1 < len(_argv):
            source_file = _argv[_i + 1]
            del _argv[_i:_i + 2]
        else:
            del _argv[_i]

    if len(_argv) < 1:
        print("用法: python create_draft.py <account> [draft_json|@file] [--source-file <源文>]",
              file=sys.stderr)
        sys.exit(2)

    account = _argv[0]
    if len(_argv) >= 2:
        draft_json_arg = _argv[1]
        if draft_json_arg.startswith('@'):
            with open(draft_json_arg[1:], 'r', encoding='utf-8') as _f:
                draft_json = _f.read()
        else:
            draft_json = draft_json_arg
    else:
        draft_json = sys.stdin.read()

    try:
        cfg = _cfg()
    except Exception as e:
        print(f"[FATAL] 读取 accounts.yaml 失败: {e}", file=sys.stderr)
        sys.exit(2)

    acct_cfg = resolve_account(cfg, account)
    if not acct_cfg:
        print(f"[FATAL] 账号 '{account}' 不存在于 accounts.yaml（可用 key："
              f"{[a.get('key') for a in cfg.get('accounts', [])]}）", file=sys.stderr)
        sys.exit(2)
    acct_key = acct_cfg.get('key') or account

    try:
        draft_info = json.loads(draft_json)
    except Exception as e:
        print(f"[FATAL] draft_json 解析失败: {e}", file=sys.stderr)
        sys.exit(2)

    # author 回落：json 未填时用 accounts.yaml 的 author（避免署名写成临时值）
    if not draft_info.get('author'):
        draft_info['author'] = acct_cfg.get('author', '')

    # 🚨 建稿前硬关卡（详见模块 docstring）
    try:
        _code = run_preflight(acct_key, draft_info.get('title', ''), draft_info.get('content', ''),
                              source_file=source_file)
        if _code:
            sys.exit(_code)
    except Exception as _e:
        print(f"HTML_VALIDATE_WARN: 校验异常（不阻断）：{_e}", file=sys.stderr)

    # ── 防重复：查 history.db，今天已达配额则跳过 ──
    import sqlite3, datetime
    db_path = acct_cfg['history_db']
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    c.execute('SELECT COUNT(*) FROM history WHERE date = ?', (today,))
    count_today = c.fetchone()[0]
    # 配额从 accounts.yaml 的 schedule.articles_per_day 读取（真源），默认 1
    try:
        max_articles = int((acct_cfg.get('schedule') or {}).get('articles_per_day', 1) or 1)
    except (TypeError, ValueError):
        max_articles = 1
    if count_today >= max_articles:
        print("DUPLICATE_SKIP")
        sys.exit(0)

    # 🔥 URL 级去重（v2.10.1）：查 history.db，7 天内同一 source_url 已发过则跳过
    # 修复背景：同一源文 URL 被反复选中（煤球精灵 5 次、NFC芯片 3 次），
    # 因为 URL 检查只存在于 SKILL.md 伪代码中，靠 agent 自觉执行不可靠
    src_url_check = draft_info.get('content_source_url', '')
    if src_url_check:
        import datetime as _dt
        seven_ago = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
        c.execute('SELECT COUNT(*) FROM history WHERE source_url = ? AND date >= ?', (src_url_check, seven_ago))
        url_count = c.fetchone()[0]
        if url_count > 0:
            print(f"URL_DUPLICATE_SKIP (source_url used {url_count} time(s) in last 7 days): {src_url_check}")
            sys.exit(0)

    env = load_env(acct_cfg['env_file'])
    proxy = cfg['global']['proxy']

    app_id = env.get('WECHAT_APP_ID') or env.get('APP_ID')
    app_secret = env.get('WECHAT_APP_SECRET') or env.get('APP_SECRET')

    if not app_id or not app_secret:
        raise Exception(f"Missing WECHAT_APP_ID or WECHAT_APP_SECRET in {acct_cfg['env_file']}")

    token = get_token(app_id, app_secret, proxy)
    print(f"Token OK: {token[:20]}...", file=sys.stderr)

    now = datetime.datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    ts = now.isoformat()
    from urllib.parse import urlparse
    src_url = draft_info.get('content_source_url', '')
    source = 'auto'
    if src_url:
        domain = urlparse(src_url).netloc
        source = domain.replace('www.', '')[:30]

    # ★ 先写 history.db 占位（status='creating'），再调微信 API 创建草稿
    # 这样即使脚本在创建草稿后异常退出，占位记录也会阻止二次调用
    # 注意：用 INSERT（不是 INSERT OR REPLACE），确保多篇场景各自独立
    c.execute('INSERT INTO history (date, title, source, source_url, cover_media_id, status, created_at, draft_media_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (today_str, draft_info['title'], source, src_url, '', 'creating', ts, ''))
    row_id = c.lastrowid
    conn.commit()

    try:
        media_id = create_draft(token, draft_info, proxy)
    except Exception as e:
        c.execute('UPDATE history SET status=?, created_at=? WHERE rowid=?',
                  ('create_failed', datetime.datetime.now().isoformat(), row_id))
        conn.commit()
        raise

    c.execute('UPDATE history SET status=?, draft_media_id=?, created_at=? WHERE rowid=?',
              ('draft_created', media_id, ts, row_id))
    conn.commit()

    # ★ 写 semaphore .done marker（防重复硬屏障），自动清理 .in_progress
    try:
        sem_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'semaphore_check.py')
        import subprocess
        subprocess.run([sys.executable, sem_script, acct_key, '--create-done'],
                       check=True, capture_output=True, timeout=10)
    except Exception as sem_e:
        print(f'[WARN] semaphore_check --create-done failed: {sem_e}', file=sys.stderr)

    # ★ 写站内正文索引（供后续文章做正文级撞车检测，见 geoready_check.py）
    try:
        import re as _re
        import geoready_check as _gr
        _ip = _gr.index_path(db_path, acct_key)
        _items = _gr.load_index(_ip)
        _body = _gr.body_only(_gr.to_text(draft_info.get('content', '')))
        _sig = _gr.minhash(_gr.ngrams(_body))
        _items = [x for x in _items
                  if not (x.get('date') == today_str and x.get('title') == draft_info['title'])]
        _items.append({'date': today_str, 'title': draft_info['title'],
                       'chars': len(_re.sub(r'\s', '', _body)), 'sig': _sig})
        _gr.save_index(_ip, _items)
        print(f'[index] 站内正文索引已更新（{len(_items)} 篇）', file=sys.stderr)
    except Exception as _ie:
        print(f'[WARN] 写站内正文索引失败: {_ie}', file=sys.stderr)

    print(media_id)


if __name__ == '__main__':
    main()
