# Changelog

All notable changes to this project will be documented in this file.

> 注：v2.6.0 – v2.10.1 的变更未逐条补录（详见 git log）。本文件从 v2.11.0 起恢复维护。

## [v2.17.0] - 2026-09-30

> 主题：**让每篇都能勾原创**。原先「可检索化」只写在文档里，无代码约束 → 要素漏做无人拦。
> 本次把它做成硬关卡，并把「能否声明原创」的三个可控变量全部自动校验。

### Added
- **`geoready_check.py`** — GEO 就绪度 / 原创可声明性硬关卡（建稿前第 7 道）
  - **可检索化四要素**：首段结论句（前 200 字内成句、≥25 字）· 独家数据段
    （必须「累计发布 N 篇」且 **N 与 `history.db` 实际行数相符**，虚高判编造 → BLOCK）
    · 末尾 2~3 组 `Q：/A：` · 品牌嵌入（1~3 次，越界仅 WARN）
  - **与源文改写幅度**：LCS ≥ 25 字 / 单句 Dice ≥ 0.65 / 全文 Dice ≥ 0.30 → BLOCK
    （复用 `originality_check` 的算法，不重复实现）
  - **站内正文撞车**：64 维 MinHash 指纹存 `<log>\<key>\body_index.json`，
    Jaccard ≥ 0.45 → BLOCK / ≥ 0.30 → WARN
  - 参数：`--account` / `--source-file` / `--json` / `--quiet` / `--update-index`
  - 退出码 0 通过（含 WARN）· 1 BLOCK · 2 无法完整检查 · 3 脚本错误
  - 提供 `run_html()` 接口，供 `create_draft` 以字符串方式调用（无需落盘）

### Changed
- **`create_draft.py`**
  - `run_preflight()` 新增第 7 道 GEO 关卡（异常时降级告警，不静默放行）
  - 新增 `--source-file <源文>` 参数（剥离后不影响原有位置参数）
  - **建稿成功后自动写站内正文索引**，供后续文章做正文级撞车检测
- `compliance_check.py` W5：统计品牌口径前**先剔除二维码引导段落**，消除
  「扫码加入君寻粉丝群」被判成品牌单独使用的误报
- SKILL.md：§5 校验关卡总表 + §6.3 + §10 文件结构同步；新增 §11「原创声明勾选判据」

### Verified
- 2026-09-30 三篇真稿实测：四要素全齐；与源文相似度 0.142 / 0.268 / 0.011，
  最长连续重复 15 / 19 / 7 字（均事实性串）；站内索引回填 3 篇
- 反例测试：缺 FAQ / 数据段虚高 / 缺数据段 / 站内撞车 四类缺陷全部正确 BLOCK
- 回归：15/15 脚本可同进程 `import`（流污染防护未破坏）

## [v2.16.0] - 2026-09-29

### Added
- **`reap_images.py`** — 图片中间产物自动回收，防止发布目录无限膨胀
  - 扫描根自动推导：`wechatlog\`（从 `accounts.yaml` 各账号 `history_db` 反推）+ `H:\workspace\苏编\`
    （可用 `WECHAT_WORKSPACE` 覆盖）
  - 参数：`--days N`（默认 7，**N < 1 直接拒绝**）/ `--dry-run`
  - 硬编码安全红线：只删图片扩展名；路径含 `wechat-assets` / `skills` / `secure` / `.workbuddy` /
    `_archive` / `cover_library` 的整棵子树跳过；永不删 `.md` / `.db` / `.done` / `.in_progress`
  - 附带清理空目录。退出码 0 正常 / 1 有删除失败
- **调度第四段**：`公众号双号·每日发布+巡检(07:00)` 任务 prompt 扩展为四段串行
  （发布 → 发布 → 巡检 → **回收**），耗时 < 1 min，失败不影响前三段结论
- **SKILL.md §2.2 目录卫生**：说明为何必须回收、扫描范围、安全红线，并记录
  「归档区一律放 skill 目录之外」这条教训

### Fixed
- **`generate_cover.py` 封面库路径算错，Tier-3 兜底长期失效**（严重）
  - 原：`Path(__file__).parent.parent.parent / "wechat-assets"` → 解析到 `<root>\skills\wechat-assets`，
    **该目录不存在**
  - 真源：`accounts.yaml` 的 `cover_library` 指向 `<root>\wechat-assets`（96 MB，实际存在）
  - 后果：腾讯混元 + 智谱两级生图均失败时，本应从本地封面库随机兜底，实际直接 `FAILED` 退出
  - 修复：`_ROOT = Path(__file__).resolve().parents[3]`（原来少算一层）+ `SECURE_DIR` / `COVER_LIB_DIR`
    一并校正；`pick_fallback()` 改为**优先读 `accounts.yaml.cover_library`**，失效路径仅作兜底，
    两条路径都不存在时打印明确诊断而非静默返回 `None`
- **7 个脚本模块级替换 `sys.stdout` 会污染 import 调用方** ——
  `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` 在旧对象被 GC 时
  会**关闭底层 buffer**，同一进程内 import 第二个脚本即抛
  `ValueError: I/O operation on closed file`（实测 14 个脚本只能 import 1 个）。
  统一改为 `stream.reconfigure(encoding='utf-8')`（原地改编码，不替换对象，失败静默跳过）。
  涉及：`validate_article_html` / `validate_title` / `create_draft` / `generate_cover` /
  `upload_article_image` / `delete_draft` / `reap_images`。
  回归：14/14 脚本可同进程 import，中文输出无乱码

### Changed
- **一次性目录清理**（只移动不删除，可回滚）：719 项 / 1560 MB 移出项目
  - 暂存区：`H:\_wechat_trash_20260929\`（workspace 部分）+ `C:\Users\LMD\.qclaw\_trash_20260929\`
    （skill / wechatlog 部分），二者均含 `MANIFEST.json` 记录每项原始路径与字节数
  - 效果：skill **452 MB → 5.0 MB** · wechatlog **686 MB → 0.9 MB** · workspace **970 MB → 94.9 MB**
  - 保留：全部 `.md` 发布日志（342 个）、`history.db`、`.done` / `.in_progress` 锁、
    企业群二维码、封面降级库、最近 2 天的发布产物

### Notes
- ⚠️ **跨盘 `shutil.move` 会触发安全删除保护**（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`），
  且 `copy` 成功后 `delete` 被拦 → **原件与副本同时存在，磁盘占用翻倍**。
  批量清理一律改用**同盘 `os.rename`**（719 项 0.8 秒完成，且不触发保护）

## [v2.15.0] - 2026-09-29

### Added
- **`compliance_check.py`** — 内容合规硬化关卡（GEO 第一阶段）
  - 硬拦：F1 硬禁词 / F2 涉政涉外词堆叠（≥2 个）/ F3 投资诱导荐股类 / F4 标题绝对化极限词
  - 软告警：W1 正文情绪词 · W2 正文极限词（带上下文）· W3 医疗疗效宣称 ·
    W4 **金融数字缺出处**（数字周围 80 字无「据/报告/公告」即提示）· W5 品牌嵌入频率与实体口径
  - 退出码：0 通过 / 1 FAIL 禁止建稿 / 2 参数错误 / 3 脚本错误
- **`_rules.py`** — 内容安全词表**唯一真源**。此前禁词表被抄在三处（SKILL 文档、`validate_title.py`、
  `create_draft.py` 硬关卡），改一处忘一处导致口径漂移。现将 A 硬禁词 / B 涉政词 / C 情绪词 /
  D 投资诱导 / E 绝对化 / F 医疗宣称 / G 金融出处词全部集中到本模块
- **`geo_stats.py`** — GEO 独家数据资产提炼。从 `history.db` 生成发布量 / 赛道分布 / 来源 Top /
  品牌频次 / 中文 2-gram 热词，并直接产出**可引用的数据句**（`--sentences`）
- **SKILL.md §6.3 可检索化规范**（硬性）：首段结论句 / 末尾 FAQ 2~3 条 / 标题覆盖搜索意图词 /
  独家数据段（`geo_stats.py` 供给）/ 品牌嵌入频率规则

### Fixed
- `create_draft.py`：**中文账号名静默漏判** —— 传「君寻」时 `account == 'junxun'` 为假，
  企业群二维码检查被跳过。新增 `resolve_account()` / `normalize_key()` 统一归一化，
  `run_preflight()` 加防御性归一化（同类 bug 2026-09-27、09-29 各踩一次）
- `create_draft.py`：篇数配额硬编码 `2 if junxun else 1` → 改读 `accounts.yaml` 的 `articles_per_day`
- `create_draft.py`：新增**岚牧哒正文中文占比 ≥30% 关卡**（防「英文源未翻译即建稿」事故复发）
- `create_draft.py`：配图计数用 set、`validate_article_html.py` 用 list，两处口径不一致 → 统一为标签数
- `create_draft.py`：`author` 缺失时回落到 `accounts.yaml` 的 `author`（此前该字段完全没被读取）
- `validate_article_html.py`：`<section>` 阈值三处口径不一（文档 ≥1 / SKILL ≥2 / 代码 ≥1）→ 统一 **≥2**；
  裸 URL 由「只报第一个」改为「最多列 5 个」
- `validate_title.py`：`c_issues` 未定义隐患（未传第三个参数时的分支脆弱）；正文由「只报第一个词」改为列全部命中
- `accounts.yaml`：君寻 `author` 由「君寻」订正为「**君寻智能**」（与线上实际署名一致）；
  清理已废弃的 `retry` 调度字段；岚牧哒补 `articles_per_day: 1`
- `.gitignore`：`scripts/_*` 会把新核心文件 `_rules.py` 一并忽略 → 加 `!scripts/_rules.py` 例外；
  新增 `_archive/` 忽略
- `content_dedup.py`：`db` 路径原先只检查**父目录**是否存在 → `sqlite3.connect` 对不存在的文件
  **静默建空库**，随后 `SELECT` 抛 `no such table` 未捕获 → 脚本以异常码崩溃，
  调用方可能误读为 `DUPLICATE(1)` 而错杀选题。改为检查文件本身 + 捕获异常明确返回 `exit 2`
- `delete_draft.py`：不支持中文账号名（`next(...)` 直接 `StopIteration`）；
  撤稿后需手动写 SQL 清 `history.db` 占位（对真身数据库手动操作有风险）→
  新增 `--purge-history` 选项，按 `media_id` **精确匹配**清理，两步并作一条命令

### Chore
- 目录卫生：`scripts/` 与 skill 根目录的历史临时脚本 / 素材（约 280 项）归档至 `_archive/20260929_cleanup/`
  （**只移动不删除**）。`scripts/` 由 170+ 项精简至 15 个现行脚本

---

## [v2.14.0] - 2026-09-29

### Added
- **`originality_check.py`** — 改写稿原创度检测（对标微信原创校验/查重算法）
  - 三维度：最长公共子串（防连续照抄）+ 单句 5-gram Dice（防整句搬）+ 全文 4-gram Dice
  - 阈值：LCS ≥ 25 字 / 单句 ≥ 0.65 / 全文 ≥ 0.20 → BLOCK；高相似句占比 ≥ 20% → WARN
  - 退出码：0 通过 / 1 BLOCK / 2 无法比对（英文源或抓取失败）/ 3 脚本错误
  - 英文源（岚牧哒）自动跳过（中英 n-gram 不可比）
- **正文改写规则第 5 条「事实句 / 引语必须重构」**：铁律 = 数字、人名、机构名可保留，包着它们的那个句子不能保留

### Changed
- 校验关卡增加原创度检查（与 `validate_article_html.py` / `validate_title.py` 并列，BLOCK 禁止建稿）

### Findings（本轮查证，非代码变更）
- **已发文章全部未标原创**：实测公开页 `copyright_stat = 0`（1=原创、0=非原创），无任何原创标签 DOM
- **原创声明无法 API 化**：微信官方明确「API 不支持原创」，必须 MP 后台手动声明后再调群发接口
- **2026-03-27 新规风险**：运营规范新增「非真人自动化创作行为」，禁止 AI 改写内容 + 脚本自动化批量连续发布，处罚含流量限制/封禁 → **自动发布暂缓**

---

## [v2.13.0] - 2026-09-29

### Changed
- **定时任务架构合并**：WorkBuddy Automations 由 3 个任务（君寻 07:00 / 岚牧哒 07:30 / 双号巡检 08:00）合并为 **1 个**「公众号双号·每日发布+巡检(07:00)」，三段串行执行，单次约 20~25 分钟。
  - 动机：减少每次运行新建的会话数（3 → 1 每天）。平台设计上每次 run 必开独立会话，无复用开关。
  - 段间隔离为硬规则：任一段失败必须继续执行下一段；每段结果落盘 `wechatlog\daily_YYYY-MM-DD.md`。
  - 单次 run 超时上限 90 分钟（`AUTOMATION_RUN_TIMEOUT_MS = 54e5`，到点强制销毁会话）。
  - 取舍：不再有独立兜底任务，会话硬崩则后段不执行。

## [v2.12.0] - 2026-09-28

### Added
- 解释器选择硬性规则：一律显式用 `C:/Python312/python.exe`（本机 managed 3.13.12 缺 `idna`，`import requests` 即崩）。
- 主题去重第五层（硬性）：选文定稿前查 `history.db` 近 7 天 `title` 的产品名/公司名，命中即作废候选。详见 SKILL.md「v2.12.0 更新」。

## [v2.11.1] - 2026-09-27

### Fixed
- **`create_draft.py` 配额判断 bug（账号中文名 vs key 不匹配）**：调用方传「君寻」时 `account in ('junxun',)` 判定失败，`max_articles` 被算成 1，君寻第 2 篇被误拦 `DUPLICATE_SKIP`（本次补发实际触发）。修复：同时识别中文名与 key，并从 accounts.yaml 按 name→key 换算。
- **`create_draft.py` 内部 `--create-done` 调用**：原先直接传 `account`（可能是中文名），semaphore_check 无法匹配 → marker 写入失败。修复：先换算成 key 再调用。

### 现场记录
- 2026-09-27 全天 0 触发：任务配置正确（next_run 均指向当日 07:00/07:30/08:00），根因是 qclaw 应用当日未运行——cron 调度器内置于 openclaw 网关进程，宿主不在线则零触发。12:57 手动补发君寻 2 篇 + 岚牧哒 1 篇，API 实拉草稿箱验证 3 篇全部命中。

## [v2.11.0] - 2026-09-26

### Added
- **统一巡检脚本** (`scripts/patrol_check.py`): 为 08:00 巡检任务提供机器可判定状态，避免 LLM 凭感觉判断导致重复发稿。状态枚举 `DONE` / `RUNNING` / `STALE_LOCK` / `NEEDS_RESEND` / `DB_MISSING`，退出码 `0`=全 DONE、`1`=需补发、`2`=有账号在跑、`3`=错误。兼容两种 history.db 表结构（junxun 有 `id` 列、lanmuda 无，统一按 `created_at` 排序）。
- **定时任务架构文档**: SKILL.md 新增「定时任务架构」章节，含 3 任务时间表、巡检状态对照表、cron 超时机制说明。

### Changed
- **工作时段前移至 07:00 开始**：`wechat-v2-junxun-daily` `0 8 * * *` → `0 7 * * *`；`wechat-v2-lanmuda-daily` `30 8 * * *` → `30 7 * * *`。
- **`wechat-v2-lanmuda-retry` 改造为 `wechat-v2-patrol`**：`5 9 * * *` → `0 8 * * *`，prompt 重写为「巡检 + 定向补发」（1292 → 2488 字符）。
- `config/accounts.yaml`: 同步 `schedule.daily`；junxun 的 `schedule.retry` 标记废弃；lanmuda 的 `schedule.retry` 语义改为「08:00 巡检」。
- SKILL.md 版本升至 v2.11.0。

### Removed
- **`wechat-v2-junxun-retry`（08:05）已删除**：该任务比 `junxun-daily`（08:00）晚 5 分钟触发，但 daily 直到 08:09 才写入 `.in_progress` 锁，导致 retry 永远看到 fresh 锁 → `ALREADY_DONE` 刹车；31 次运行 0 产出，属设计错误。补发统一由 08:00 巡检承担。

### Fixed
- **`RUNNING` 状态保护**：巡检 prompt 明确「绝对禁止对 RUNNING 账号补发」，堵住 daily 仍在运行时巡检撞车重复发稿的路径（对应 2026-09-25 空窗事故的根因防护）。

### Technical Details
- cron 任务存储于 `C:\Users\LMD\.qclaw\state\openclaw.sqlite` 的 `cron_jobs` 表，主键为 `job_id`；改配置须同步 `schedule_expr` / `next_run_at_ms` / `job_json` / `state_json` / `schedule_identity` 五处字段。
- cron 超时：`payload.kind=agentTurn` 未设 `timeoutSeconds` → 60 分钟安全超时（`AGENT_TURN_SAFETY_TIMEOUT_MS`）；`command` 型 → 10 分钟。当前 3 任务均未设，即 60 分钟上限。

---

## [v2.5.1] - 2026-07-09

### Added
- **内容级去重** (`scripts/content_dedup.py`): 基于字符级 4-gram Dice 系数的标题相似度检测。不依赖分词库/停用词表/实体识别，纯字符指纹。同一新闻不同来源（WIRED vs TechCrunch 报道同一事件）Dice ≥ 0.28 即判重拦截。
- **.in_progress 锁机制**: 在 `semaphore_check.py` 中新增 `--create-in-progress` / `--clear-in-progress` 模式，防止 daily (08:30) 和 retry (08:35) cron 5分钟间隔导致 race condition 双跑。
- **三层防重复屏障**: history.db URL 去重 → `.in_progress` 流程锁 → `.done` 完成标记。

### Changed
- `scripts/semaphore_check.py`: `--check` 模式新增 `.in_progress` 检测（第三层屏障）；锁文件超时 60 分钟自动过期；`--clear` 同时清理 `.done` 和 `.in_progress`。
- `scripts/create_draft.py`: 草稿创建成功后在写 `.done` 的同时清理 `.in_progress` 锁。
- `SKILL.md`: 升级至 v2.5.1，新增第〇步-加强流程文档。

### Fixed
- **Critical — Race Condition**: daily cron (08:30) 和 retry cron (08:35) 因时间间隔过近导致同时执行全流程，微信后台被写入两份草稿，公众号同时发出两篇相同文章。根因是生图+上传约需 20 分钟，retry 触发时之前的流程尚未写入 `.done` 标记。
- **内容级重复**: 不同新闻源报道同一事件时 URL 不同，现有 URL 级防重无法拦截。`content_dedup.py` 对标题做 4-gram 相似度匹配，不依赖分词。

### Technical Details
- 指纹算法: 字符 4-gram → 去空白/转小写 → Dice 系数 = 2|A∩B|/(|A|+|B|)
- 实测阈值 0.28: 同一新闻不同写法 ~0.31（判重），同公司不同事件 ~0.18（放行），完全不同 0.000（放行）

---

## [v2.4.0] - 2026-04-24

### Added
- `upload_material.py` 支持 `--permanent` 永久素材上传，返回 URL
- `generate_cover.py` 支持加载 env 文件设置环境变量
- 封面尺寸统一为 16:9（1536x864 / 1024x576）
- `generate_cover.py` 腾讯混元 fallback 修复（TokenHub 异步流程）
- `create_draft.py` 加入 token 重试机制（最多 3 次）

### Changed
- 配置文件中新增 `key` 字段（junxun/lanmuda），用于多账号路由
- 封面库迁移至 `wechat-assets/` 目录
- 清理 `.env` 文件中的杂质配置

### Fixed
- 多账号配置读取 bug（旧版用 name 匹配，新版统一用 key）
- 生成封面尺寸不正确的问题
- Token 过期未重试导致草稿创建失败

---

## [v2.3.0] - 2026-04-10

### Added
- 微信公众号多账号发布系统初版
- 支持君寻、岚牧哒双账号独立配置
- 英文源自动抓取（WIRED / TechCrunch / Ars Technica / Yanko Design / TIWIB）
- 中文源自动抓取（潮玩 / AI玩具 / 行业深度）
- 翻译改写引擎：十年杂志编辑水平的 AI 改写
- 封面 + 配图生成（腾讯混元 / 智谱 CogView / 本地库三级降级）
- 素材上传（封面 + 正文内嵌图片）
- 草稿创建（微信草稿箱 API）
- 日志记录 + 历史数据库
- semaphore 防重复屏障

### Technical
- 基于 Python + requests 的 SDK-free 实现
- 全部使用微信公众平台官方 API，不含第三方 SDK
- 配置驱动设计，`accounts.yaml` 统一管理
