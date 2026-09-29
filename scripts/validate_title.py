# -*- coding: utf-8 -*-
"""
validate_title.py - 标题/正文安全校验（轻量老关卡）

历史教训：2026-07-19 标题含「封杀」「活该」→ 文章被微信删除。

与 compliance_check.py 的分工：
    本脚本  = 轻量、零依赖、老关口，只查「情绪对立/硬禁词」这一层；
    compliance_check.py = 覆盖面更宽的新关口（金融数据、绝对化表述、医疗宣称、投资诱导）。
    两者都跑，任何一个 exit≠0 都禁止建稿。

词表来源：`_rules.py`（唯一真源）。_rules.py 缺失时回落内置副本，绝不静默放行。

用法：
    python validate_title.py <title>
    python validate_title.py <title> <content_file|@json:file>

exit code：0=通过  1=未通过  2=参数错误
"""
import sys, io, os, re, json
# UTF-8 输出。用 reconfigure 而不是替换 sys.stdout 对象 ——
# 替换会让被 import 时的调用方 buffer 被 GC 关闭（ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_FALLBACK = {
    'BANNED_WORDS': ['封杀', '慌了', '慌了神', '傻眼', '倒闭', '跑路', '崩盘', '喊杀', '喊打',
                     '活该', '暴雷', '割韭菜', '碾压', '吊打', '血洗', '喊打喊杀'],
    'POLITICAL_WORDS': ['硅谷', '白宫', '美国慌了', '华盛顿', '欧盟', '华尔街',
                        '五角大楼', '国会', '白宫慌了'],
    'ALARMIST_WORDS': ['慌了', '傻眼', '封杀', '喊打喊杀', '慌了神', '暴雷', '割韭菜',
                       '碾压', '吊打', '血洗'],
}

try:
    from _rules import BANNED_WORDS, POLITICAL_WORDS, ALARMIST_WORDS
except ImportError:
    print('[WARN] 未找到 _rules.py，使用内置词表副本', file=sys.stderr)
    BANNED_WORDS = _FALLBACK['BANNED_WORDS']
    POLITICAL_WORDS = _FALLBACK['POLITICAL_WORDS']
    ALARMIST_WORDS = _FALLBACK['ALARMIST_WORDS']


def check_title(title):
    issues = []
    if len(title) > 64:
        issues.append(f"FAIL[1]: 标题长度 {len(title)} > 64 字符")
    for w in BANNED_WORDS:
        if w in title:
            issues.append(f"FAIL[2]: 标题含绝对禁止词「{w}」")
    found_political = [w for w in POLITICAL_WORDS if w in title]
    if len(found_political) >= 2:
        issues.append(f"FAIL[3]: 标题含 {len(found_political)} 个涉外/政治敏感词 {found_political}")
    for w in ALARMIST_WORDS:
        if w in title:
            issues.append(f"FAIL[4]: 标题含情绪对立表达「{w}」")
    return len(issues) == 0, issues


def check_content(content):
    """正文检查：列出全部命中（旧版只报第一个 + 有 c_issues 未定义隐患）"""
    issues = []
    hits = []
    for w in BANNED_WORDS + ALARMIST_WORDS:
        if w in content and w not in hits:
            hits.append(w)
    if hits:
        issues.append(f"FAIL[5]: 正文含敏感词 {hits[:8]}（位置可能致删文）")
    return len(issues) == 0, issues


def main():
    if len(sys.argv) < 2:
        print("用法: python validate_title.py <title> [content_file|@json:file]")
        sys.exit(2)

    title = sys.argv[1]
    passed, issues = check_title(title)

    if len(sys.argv) >= 3:
        path = sys.argv[2]
        if path.startswith('@json:'):
            with open(path[6:], 'r', encoding='utf-8') as f:
                content = json.load(f).get('content', '')
        else:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        cp, c_issues = check_content(content)
        issues = issues + c_issues
        passed = passed and cp

    for i in issues:
        print(i)

    if passed:
        print(f"✅ 标题校验通过：{title[:30]}")
        sys.exit(0)
    print(f"❌ 校验未通过，共 {len(issues)} 项失败")
    sys.exit(1)


if __name__ == '__main__':
    main()
