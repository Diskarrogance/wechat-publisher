# Changelog

All notable changes to this project will be documented in this file.

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
