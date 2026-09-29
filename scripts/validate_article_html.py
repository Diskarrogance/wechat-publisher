# -*- coding: utf-8 -*-
"""
validate_article_html.py
正文排版校验脚本

在调用 create_draft.py 之前必须先通过本脚本。**校验未通过 → 禁止建稿。**

用法：
    python validate_article_html.py "<html文件>" [min_images]
    python validate_article_html.py @json:"<draft.json>"
    # min_images 默认 3；SKILL 要求正文配图 3~5 张，故实际调用一般传具体张数

校验项目（任一项失败 → exit 1）：
  1. 配图 <img> 数 ≥ min_images（默认 3）
  2. 无裸 URL（带 ?from=appmsg 却不在 <img src> 内）
  3. <section> 组件数 ≥ 2（2026-09-29 统一：SKILL 要求正文至少 2 个分节，旧版此处为 ≥1，口径漂移已修）
  4. <h2> 标签数 ≥ 2（小节标题）
  5. <img src> 非 https（http 开头）—— mmecoa.qpic.cn 的 http 为微信标准格式，豁免

exit codes：
  0 = 通过
  1 = 未通过（输出 FAIL 条目）
  2 = 参数错误
"""
import sys, io, os, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

MIN_SECTIONS = 2   # 与 SKILL.md「至少 2 个节标题」保持一致
MIN_H2 = 2


def validate_html(content, min_images=3):
    """返回 (passed: bool, issues: list[str])"""
    issues = []

    # 1. 配图 img src 标签数
    img_tags = re.findall(r'<img[^>]+src="([^"]+)"', content)
    img_count = len(img_tags)
    if img_count < min_images:
        issues.append(f"FAIL[1]: 配图 img 标签数 {img_count} < {min_images}（最低要求）")

    # 2. 裸 URL 检查（核心！）：带 from=appmsg 的 URL 不在 img src 内
    all_urls = re.findall(r'https?://[^\s"<>]+', content)
    img_srcs = set(img_tags)
    bare = [u for u in all_urls if 'from=appmsg' in u and u not in img_srcs]
    for u in bare[:5]:
        issues.append(f"FAIL[2]: 裸 URL（带 from=appmsg 但未包在 <img> 内）：{u[:100]}")
    if len(bare) > 5:
        issues.append(f"FAIL[2]: …另有 {len(bare) - 5} 个裸 URL 未列出")

    # 3. section 组件
    section_count = len(re.findall(r'<section[\s>]', content))
    if section_count < MIN_SECTIONS:
        issues.append(f"FAIL[3]: <section> 组件数 {section_count} < {MIN_SECTIONS}（缺少文章结构）")

    # 4. h2 标签（小节标题）
    h2_count = len(re.findall(r'<h2[\s>]', content))
    if h2_count < MIN_H2:
        issues.append(f"FAIL[4]: <h2> 标签数 {h2_count} < {MIN_H2}（缺少小节标题）")

    # 5. img src 必须 https，mmecoa.qpic.cn 的 http 是微信标准格式，豁免
    http_imgs = [src for src in img_tags if src.startswith('http://') and 'mmecoa.qpic.cn' not in src]
    if http_imgs:
        issues.append(f"FAIL[5]: 发现 http（而非 https）img src：{http_imgs[0][:80]}")

    return len(issues) == 0, issues


def main():
    if len(sys.argv) < 2:
        print("用法: python validate_article_html.py <html文件|@json:file> [min_images]")
        sys.exit(2)

    path = sys.argv[1]
    min_images = int(sys.argv[2]) if len(sys.argv) >= 3 else 3

    if path.startswith('@json:'):
        with open(path[6:], 'r', encoding='utf-8') as f:
            content = json.load(f).get('content', '')
    else:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

    if not content:
        print("FAIL[0]: 内容为空")
        sys.exit(1)

    passed, issues = validate_html(content, min_images)
    for issue in issues:
        print(issue)

    if passed:
        img_count = len(re.findall(r'<img[^>]+src="([^"]+)"', content))
        all_urls = re.findall(r'https?://[^\s"<>]+', content)
        img_srcs = set(re.findall(r'<img[^>]+src="([^"]+)"', content))
        bare = [u for u in all_urls if 'from=appmsg' in u and u not in img_srcs]
        sec = len(re.findall(r'<section[\s>]', content))
        h2 = len(re.findall(r'<h2[\s>]', content))
        print(f"✅ 校验通过：img {img_count}张 | 裸URL {len(bare)}个 | section {sec} | h2 {h2}")
        sys.exit(0)
    else:
        print(f"❌ 校验未通过，共 {len(issues)} 项失败")
        sys.exit(1)


if __name__ == '__main__':
    main()
