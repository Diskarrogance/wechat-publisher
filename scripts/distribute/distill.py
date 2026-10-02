#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
distill.py — 母稿蒸馏 + 平台改造任务书（内容改造模块）

设计思路
    公众号母稿里本来就带着**可复用的素材件**（这是 GEO 可检索化改造的副产物）：
      · 首段结论句（40~60 字）      → 头条摘要 / 微博钩子 / 小红书首图文案
      · 独家数据段（"累计发布 N 篇"）→ 各平台共用的「信息增量」——GEO 的核心杠杆
      · 末尾 Q&A（2~3 组）          → 头条/知乎的问答结构、小红书的"问得对"
      · 核心实体（品牌/品类）        → 标题选词 + 平台标签
    所以改造 ≠ 重写一切，而是**重组已有素材 + 按平台调性改写**。

两个命令
    extract <文章>                     从母稿蒸馏出结构化素材（给人和 AI 看都行）
    brief   <平台> <文章>              生成该平台的「改造任务书」（可直接喂给执行会话）

用法
    python distill.py extract  article.json
    python distill.py extract  article.html --title "标题"
    python distill.py brief    toutiao article.json
    python distill.py brief    xiaohongshu article.json

配合
    改造完成后用 `scripts/distribute/geo_adapt.py check <平台> …` 自检。

退出码：0 正常 · 2 参数/文件错误 · 3 脚本错误
"""
import argparse
import html as htmlmod
import json
import os
import re
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_THIS)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _THIS)

try:
    import yaml
except ImportError:
    print('[FATAL] 需要 pyyaml', file=sys.stderr)
    sys.exit(3)

PLATFORMS_YAML = os.path.join(_ROOT, 'config', 'platforms.yaml')
KEYWORDS_YAML = os.path.join(_ROOT, 'config', 'keywords.yaml')

# 平台调性：改造时最该注意的一句话
PLATFORM_TONE = {
    'wechat_mp': '对话式长文，允许完整论述与排版；保留可检索化四要素与二维码。',
    'toutiao': '资讯体，结论必须前置（开篇 3 秒抓眼）；短段落、小标题分段；不吃品牌腔调。',
    'baijiahao': '知识科普体，为「被百度搜到」写作：关键词自然分布、结构清晰、信息完整。',
    'xiaohongshu': '第一人称口语，像人在分享而不是媒体在报道；分点、短句、emoji 分隔；结论要"有用"。',
    'weibo': '话题体，一句话给出冲击性结论或数据，末尾抛问题引互动；不求完整，求被转发。',
}


def strip_tags(html):
    h = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    h = re.sub(r'<br\s*/?>', '\n', h, flags=re.I)
    h = re.sub(r'</(p|section|div|h[1-6]|li|blockquote)\s*>', '\n', h, flags=re.I)
    t = re.sub(r'<[^>]+>', '', h)
    return re.sub(r'[ \t\u3000\u00a0]+', ' ', htmlmod.unescape(t))


def blocks(html):
    """→ 段落列表（去空段、去二维码块）"""
    txt = strip_tags(html)
    out = []
    for ln in (x.strip() for x in txt.split('\n')):
        if not ln or len(ln) < 2:
            continue
        if re.search(r'(扫码|粉丝群|二维码|长按识别)', ln) and len(ln) < 60:
            continue                      # 二维码引导段
        if re.fullmatch(r'https?://\S+', ln):
            continue
        out.append(ln)
    return out


def load_yaml(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def known_entities(text):
    """从 keywords.yaml 匹配命中的品牌/品类词，按长度降序（长词优先）"""
    d = load_yaml(KEYWORDS_YAML)
    words = []
    for sec in ('category', 'brand'):
        for it in (d.get(sec) or []):
            if isinstance(it, dict) and it.get('word'):
                words.append(str(it['word']))
    words.sort(key=len, reverse=True)
    hit = []
    for w in words:
        if w in text and w not in hit:
            hit.append(w)
    return hit


def read_article(path, title=None):
    """读 draft.json 或 html，返回 (title, html)"""
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    if path.lower().endswith('.json'):
        try:
            d = json.loads(raw)
            return (d.get('title') or title or ''), d.get('content', '')
        except Exception:
            pass
    return (title or ''), raw


def extract(path, title=None):
    t, html = read_article(path, title)
    bs = blocks(html)
    body_text = '\n'.join(bs)

    # ① 首段结论句 = 第一个 >=40 字的段落（跳过小标题）
    lead = next((b for b in bs if len(b) >= 40 and not b.startswith('#')), '')

    # ② 独家数据段
    data = next((b for b in bs if re.search(r'累计发布\s*\d+\s*篇|内容团队统计', b)), '')

    # ③ FAQ 组（Q：/A： 成对）
    faqs, cur_q = [], None
    for b in bs:
        m = re.match(r'^\s*[Q问]\s*[:：]\s*(.+)', b)
        if m:
            cur_q = m.group(1).strip()
            continue
        m = re.match(r'^\s*[A答]\s*[:：]\s*(.+)', b)
        if m and cur_q:
            faqs.append({'q': cur_q, 'a': m.group(1).strip()})
            cur_q = None

    # ④ 实体
    ents = known_entities(t + body_text)

    # ⑤ 带数字的句子（钩子候选）
    nums = [b for b in bs if re.search(r'\d', b) and 10 <= len(b) <= 80][:6]

    return {
        'source': os.path.basename(path),
        'title': t,
        'title_len': len(t),
        'lead': lead,
        'data_sentence': data,
        'faqs': faqs,
        'entities': ents,
        'number_sentences': nums,
        'body_text': body_text,
        'body_chars': len(re.sub(r'\s', '', body_text)),
        'paragraphs': len(bs),
    }


def cmd_extract(m):
    print('=' * 78)
    print(f'母稿蒸馏：{m["source"]}')
    print('=' * 78)
    print(f'  标题（{m["title_len"]} 字）: {m["title"]}')
    print(f'  正文 {m["body_chars"]} 字 / {m["paragraphs"]} 段')
    print()
    print('  【可复用素材件】')
    print(f'   ① 结论句 : {m["lead"][:110]}{"…" if len(m["lead"])>110 else ""}')
    print(f'   ② 数据段 : {m["data_sentence"][:110]}{"…" if len(m["data_sentence"])>110 else ""}')
    print(f'   ③ FAQ    : {len(m["faqs"])} 组')
    for f_ in m['faqs']:
        print(f'        Q: {f_["q"][:50]}')
        print(f'        A: {f_["a"][:60]}…')
    print(f'   ④ 实体   : {"、".join(m["entities"][:12]) or "（未命中词表）"}')
    print()
    print('  【数字钩子候选】')
    for n in m['number_sentences']:
        print(f'       · {n[:76]}')
    return 0


def cmd_brief(pid, m, plats):
    plat = plats.get(pid)
    if not plat:
        print(f'[ERROR] 未知平台 {pid}；可选：{"、".join(plats)}', file=sys.stderr)
        return 2
    t = plat.get('title') or {}
    b = plat.get('body') or {}
    tg = plat.get('tags') or {}
    geo = plat.get('geo') or {}
    pub = plat.get('publish') or {}

    print('=' * 78)
    print(f'改造任务书 · {plat.get("name")}（{pid}）')
    print('=' * 78)
    print()
    print('## 一、这个平台要什么')
    print(f'- 目标入口：{"、".join(e.get("name", "") for e in (geo.get("entries") or []))}')
    print(f'- 公域推荐：{"有" if geo.get("recommend") else "无"}'
          + (f' —— {geo.get("recommend_note","")}' if geo.get("recommend_note") else ''))
    print(f'- 调性：{PLATFORM_TONE.get(pid, "—")}')
    if t.get('max'):
        print(f'- 标题：{t.get("min",0)}~{t["max"]} 字'
              + (f'，前 {t.get("must_have_entity_in_head")} 字须含实体' if t.get('must_have_entity_in_head') else ''))
    if b.get('min_chars') or b.get('max_chars'):
        print(f'- 正文：{b.get("min_chars",0)}~{b.get("max_chars") or "∞"} 字')
    for r in (b.get('require') or []):
        print(f'- 必备：{r}')
    for f_ in (b.get('forbid') or []):
        print(f'- 禁止：{f_}')
    if tg:
        print(f'- 标签：{"必填 " if tg.get("required") else ""}{tg.get("count") or ""}'
              + (f'（{tg.get("note")}）' if tg.get('note') else ''))
    if pub.get('note'):
        print(f'- 发布：{pub.get("note")}')
    if plat.get('geo', {}).get('ai_crawlers_blocked'):
        print(f'- 注意：该平台内容会被 {"、".join(plat["geo"]["ai_crawlers_blocked"])} 屏蔽')
    print()
    print('## 二、从母稿可直接复用的素材')
    print(f'- 原标题（{m["title_len"]} 字）：{m["title"]}')
    print(f'- 结论句：{m["lead"][:130]}')
    print(f'- 独家数据段：{m["data_sentence"][:130]}')
    print(f'- FAQ {len(m["faqs"])} 组：' + ' / '.join(f_['q'][:22] for f_ in m['faqs']))
    print(f'- 核心实体：{"、".join(m["entities"][:12]) or "（未命中词表）"}')
    print(f'- 母稿正文：{m["body_chars"]} 字（改造目标见上）')
    print()
    print('## 三、改造动作（按顺序执行）')
    print('1. **标题重写**：把「核心实体」提到前 12 字，长度压进上面的区间；'
          '钩子（数字/反差）放实体之后。不要直接沿用原标题。')
    print('2. **正文重组**：')
    print('   - 保留：结论句（可放最前）、独家数据段、FAQ 里的信息点、数字钩子')
    print('   - 删除：企业群二维码、粉丝群/扫码话术、公众号特有署名与引导语')
    print('   - 改写：按上面的「调性」重写过渡句，不要照搬公众号的排版结构')
    print('3. **数据段处理**：数字必须与母稿一致（**禁止编造或改写数字**），'
          '但可换表述方式以适配平台语气。')
    print('4. **标签/话题**：按上面的数量要求选取，优先用「核心实体」里的词。')
    print('5. **自检（必须）**：')
    print(f'   `python scripts/distribute/geo_adapt.py check {pid} '
          f'--title "<新标题>" --content <新正文> --tags "a,b,c"`  → 必须 exit 0')
    print()
    print('## 四、平台搜索意图（写标题时参考）')
    print(f'- {plat.get("extra", {}).get("intent", "（未标注）")}')
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('cmd', choices=['extract', 'brief'])
    ap.add_argument('rest', nargs='*', help='extract: <文章>；brief: <平台> <文章>')
    ap.add_argument('--title', default='')
    args = ap.parse_args()

    try:
        plats = load_yaml(PLATFORMS_YAML).get('platforms') or {}
    except Exception as e:
        print(f'[ERROR] 读取 platforms.yaml 失败: {e}', file=sys.stderr)
        return 3

    if args.cmd == 'extract':
        if not args.rest:
            print('[ERROR] 用法: distill.py extract <文章>', file=sys.stderr)
            return 2
        article = args.rest[0]
        if not os.path.exists(article):
            print(f'[ERROR] 文件不存在: {article}', file=sys.stderr)
            return 2
        try:
            return cmd_extract(extract(article, args.title))
        except Exception as e:
            print(f'[ERROR] 蒸馏异常: {type(e).__name__}: {e}', file=sys.stderr)
            return 3

    # brief <platform> <article>
    if len(args.rest) < 2:
        print('[ERROR] 用法: distill.py brief <平台> <文章>', file=sys.stderr)
        return 2
    platform, article = args.rest[0], args.rest[1]
    if not os.path.exists(article):
        print(f'[ERROR] 文件不存在: {article}', file=sys.stderr)
        return 2
    try:
        m = extract(article, args.title)
        return cmd_brief(platform, m, plats)
    except Exception as e:
        print(f'[ERROR] 生成任务书异常: {type(e).__name__}: {e}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
