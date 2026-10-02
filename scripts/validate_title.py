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


# ────────────────────────────────────────────────────────────
# 搜索友好度（搜一搜场景 · 2026-10-02 新增）
#   背景：两号均为**服务号** —— 微信官方明确「推荐是订阅号的能力」，服务号不进推荐池，
#   因此**搜一搜是唯一能自主争取的增量流量**。存量诊断（264+147 篇）：标题平均 27~29 字，
#   85% 超过 22 字；结构普遍是「场景白描/悬念：结论」，前 12 字多为文学描写而非可搜索实体。
#   本检查**只告警、不影响 exit code**（先收一段时间的数据再决定是否升级为硬关卡）。
# ────────────────────────────────────────────────────────────
HEAD_LEN = 12           # 前 N 字 = 搜索命中关键位
LEN_TARGET_MAX = 26     # 标题长度目标上限

# 词库真源 = config/keywords.yaml（category + brand + search_terms）。
# 下面的内置副本仅在 yaml 不可读时回落，**绝不静默放行**（历史教训：禁词表被抄成三份，改一处漏两处）。
_FALLBACK_KEYWORDS = [
    'AI玩具', '陪伴机器人', '人形机器人', '机器人', '潮玩', '盲盒', '谷子', '手办', '模型',
    'AI眼镜', '智能眼镜', '助听器', '耳机', '音箱', '芯片', '算力', '大模型', '具身智能',
    '智能体', '掌机', '无人机', '毛绒', '挂件', '戒指', '投影', '相机', '眼镜', '玩具',
    '平板', '手机', '泡泡玛特', 'LABUBU',
]
CATEGORY_WORDS = _FALLBACK_KEYWORDS      # 兼容旧引用
_KEYWORD_CACHE = {}                      # {platform_key: [words]} —— 按平台分开缓存

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
KEYWORDS_YAML = os.path.join(CONFIG_DIR, 'keywords.yaml')
SEARCH_YAML = os.path.join(CONFIG_DIR, 'search_terms.yaml')


def _read_yaml(p):
    import yaml
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _load_keywords(platform=None):
    """词库 = 自有实体词（keywords.yaml）+ 外部真实搜索词（search_terms.yaml）。

    platform 为空 → 合并全部平台的外部词；指定平台 → 只用该平台的（+自有词）。
    任一文件缺失都不静默放行；只有全部为空才回落内置副本并告警。
    """
    words = []
    try:
        d = _read_yaml(KEYWORDS_YAML)
        for section in ('category', 'brand', 'search_terms'):
            for item in (d.get(section) or []):
                if isinstance(item, dict) and item.get('word'):
                    words.append(str(item['word']))
                elif isinstance(item, str):
                    words.append(item)
    except Exception as e:
        print(f'[WARN] 读取 keywords.yaml 失败（{type(e).__name__}: {e}）', file=sys.stderr)

    try:
        sd = _read_yaml(SEARCH_YAML)
        plats = sd.get('platforms') or {}
        picked = [plats[platform]] if (platform and platform in plats) else list(plats.values())
        for node in picked:
            for item in ((node or {}).get('words') or []):
                w = item.get('word') if isinstance(item, dict) else item
                if w:
                    words.append(str(w))
    except Exception as e:
        print(f'[WARN] 读取 search_terms.yaml 失败（{type(e).__name__}: {e}）', file=sys.stderr)

    if words:
        seen, out = set(), []
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out
    print('[WARN] 词库为空，回落内置副本', file=sys.stderr)
    return _FALLBACK_KEYWORDS


def _keywords(platform=None):
    key = platform or '__all__'
    if key not in _KEYWORD_CACHE:
        _KEYWORD_CACHE[key] = _load_keywords(platform)
    return _KEYWORD_CACHE[key]


def search_friendliness(title, platform=None):
    """搜索友好度评估。返回 (ok, msgs)。msgs 只作告警，不参与 exit code。

    platform 可选 —— 指定后只用该平台的搜索词判实体命中（如「微信搜一搜」）。
    """
    msgs = []
    head = title[:HEAD_LEN]
    has_entity = bool(re.search(r'[A-Za-z][A-Za-z0-9\-]{1,}', head)) or \
        any(w in head for w in _keywords(platform))
    if not has_entity:
        msgs.append(f"WARN[GEO-1]: 前 {HEAD_LEN} 字无「品牌名/品类词」实体 → 受搜一搜匹配率低"
                    f"（实为：{head}）")
    if len(title) > LEN_TARGET_MAX:
        msgs.append(f"WARN[GEO-2]: 标题 {len(title)} 字 > 目标 {LEN_TARGET_MAX} 字"
                    f"（搜索结果易截断，钩子请放在实体之后）")
    return (not msgs), msgs


def main():
    argv = sys.argv[1:]
    platform = None
    geo_warn_only = '--geo-warn-only' in argv
    argv = [a for a in argv if a != '--geo-warn-only']
    if '--platform' in argv:
        _i = argv.index('--platform')
        platform = argv[_i + 1] if _i + 1 < len(argv) else None
        del argv[_i:_i + 2]

    if not argv:
        print("用法: python validate_title.py <title> [content_file|@json:file] "
              "[--platform 微信搜一搜] [--geo-warn-only]")
        sys.exit(2)

    title = argv[0]
    passed, issues = check_title(title)
    _sf_ok, sf_msgs = search_friendliness(title, platform)
    # 搜索友好度自 v2.20.0 起计入失败（硬关卡）。--geo-warn-only 为逃生阀，供临时放宽。
    geo_fail = (not _sf_ok) and (not geo_warn_only)
    if geo_fail:
        passed = False

    if len(argv) >= 2:
        path = argv[1]
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
    for m in sf_msgs:
        print(m + ("" if geo_warn_only else "   ← 计入失败"))

    if passed:
        print(f"✅ 标题校验通过：{title[:30]}" + ("" if _sf_ok else "（搜索友好度仅告警）"))
        sys.exit(0)
    print(f"❌ 校验未通过，共 {len(issues) + (1 if geo_fail else 0)} 项失败")
    sys.exit(1)


if __name__ == '__main__':
    main()
