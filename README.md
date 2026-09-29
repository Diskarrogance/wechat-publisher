# wechat-publisher

> 微信公众号多账号自动发布系统 · 配置驱动版

基于腾讯混元 AI（HY-Image-V3.0）生成封面/配图，自动化完成「搜索 → 防重 → 改写 → 配图 → 排版 → 校验 → 建稿」全流程。支持多个公众号并行发布，每个账号可独立配置篇数、来源偏好与配额。

---

## 功能特性

| 特性 | 说明 |
|------|------|
| 🔒 **防重复五层屏障** | URL 去重 → `.in_progress` 锁 → `.done` 标记 → 内容级 Dice 去重 → 主题/产品名查库 |
| 🧾 **五道校验关卡** | 排版结构 / 标题安全 / **合规硬化** / **原创度** / 内容去重，任一不过即拒绝建稿 |
| 🛡️ **合规硬化** | 金融数据出处、绝对化极限词、涉政涉外词、投资诱导、医疗宣称 —— 词表集中于 `_rules.py` 单一真源 |
| 📐 **原创度片段级检测** | 最长公共子串 + 单句 5-gram Dice + 全文 4-gram Dice，拦「事实句/引语照抄」 |
| 🔎 **GEO 可检索化** | 首段结论句 / 末尾 FAQ / 搜索意图词 / **独家数据段**（`geo_stats.py` 从历史库提炼真统计） |
| 🎨 **AI 配图** | 混元 HY-Image-V3.0 生成封面 + 正文配图，支持 IP 角色参考图一致性 |
| 📝 **自动排版** | 预设 HTML 组件模板（15px 字体、蓝渐变节标题、自适应配图尺寸） |
| 🌍 **多源抓取** | 按来源优先级抓取真实文章，抓不到就不发，拒绝 AI 编造内容 |
| 🔁 **编码安全** | 绕开 PowerShell CP936 与 Nginx 代理的 Latin-1 污染（`@file` 传参 + urllib 显式 UTF-8） |
| 🖼️ **企业群二维码** | 支持指定账号文章底部自动追加二维码（代码强制校验） |
| 🚨 **假成功防护** | 任务结束必须实拉草稿箱核验，`exit=0` 不等于文章真建出来了 |

---

## 项目结构

```
wechat-publisher/
├── SKILL.md                      ← 完整操作手册（十步流程 + 规范）
├── CHANGELOG.md
├── _archive/                     ← 历史临时脚本与素材（只归档，不删除）
├── config/
│   └── accounts.yaml             ← 账号配置（**不含密钥，需自行填写**）
├── assets/
│   └── cover_library/            ← 本地封面兜底库
└── scripts/
    ├── _rules.py                 ← ★ 内容安全词表唯一真源
    ├── semaphore_check.py        ← 第〇步防重复硬屏障（三层）
    ├── patrol_check.py           ← 巡检状态机（DONE/RUNNING/STALE_LOCK/NEEDS_RESEND/DB_MISSING）
    ├── filter_candidates.py      ← 选文 URL 去重（7 天窗口）
    ├── content_dedup.py          ← 选文内容级去重（4-gram Dice）
    ├── generate_cover.py         ← 封面 + 配图生成（混元 → CogView → 本地库三级降级）
    ├── upload_article_image.py   ← 上传素材（--type image 正文配图 / --type thumb 封面）
    ├── validate_article_html.py  ← 关卡① 排版结构
    ├── validate_title.py         ← 关卡② 标题安全
    ├── compliance_check.py       ← 关卡③ 合规硬化
    ├── originality_check.py      ← 关卡④ 原创度（片段级）
    ├── geo_stats.py              ← GEO 数据资产提炼
    ├── create_draft.py           ← 建稿（内部内置全部关卡双保险）
    └── delete_draft.py           ← 撤稿（主题撞车时用）
```

---

## 快速开始

### 1. 配置账号

编辑 `config/accounts.yaml`：

```yaml
accounts:
  - name: "公众号A"
    key: "account_a"
    author: "账号A署名"
    env_file: "/path/to/.env_account_a"
    history_db: "/path/to/account_a/history.db"
    cover_library: "/path/to/cover_library_a/"
    schedule:
      articles_per_day: 2        # 每日配额（patrol_check / create_draft 均读此字段）
    sources:
      - name: "示例源"
        url: "https://example.com/feed"

  - name: "公众号B"
    key: "account_b"
    env_file: "/path/to/.env_account_b"
    history_db: "/path/to/account_b/history.db"
    schedule:
      articles_per_day: 1

global:
  proxy: "https://your-proxy.com/wechat-proxy/"
  blacklist:
    - "example-blacklist.com"
```

> `key` 是脚本路由依据。脚本内部会做归一化，传 `name` 或 `key` 都能解析。

### 2. 配置凭证

每个账号对应一个 `.env` 文件（示例 `.env_account_a`）：

```ini
WECHAT_APP_ID=wx0000000000000000
WECHAT_APP_SECRET=your_app_secret_here
TENCENT_MAAS_KEY=your_hunyuan_key_here
TENCENT_MAAS_SECRET=your_hunyuan_secret_here
```

> ⚠️ `.env_*` 文件已在 `.gitignore` 中排除，不会误上传

### 3. 创建草稿（以 `account_a` 为例）

```powershell
# 将 draft JSON 写入 UTF-8 临时文件（防 CP936 编码问题）
$json = @{
  title = "文章标题"
  author = "账号A署名"          # 可省略，省略时回落到 accounts.yaml 的 author
  content = "<p>正文HTML</p>"
  thumb_media_id = "封面media_id"
  content_source_url = "https://example.com/original"
  need_open_comment = 1
  only_fans_can_comment = 0
} | ConvertTo-Json -Depth 10

$tmp = "$env:TEMP\draft_$(Get-Random).json"
$json | Out-File $tmp -Encoding utf8
python scripts/create_draft.py account_a "@$tmp"
Remove-Item $tmp -Force
```

---

## 工作流程

```
       ┌─────────────────────┐
       │ semaphore_check     │ ← 三层锁检查：今天发过吗？
       └────────┬────────────┘
                ↓ READY（并写 .in_progress 锁）
       ┌─────────────────────┐
       │ 获取 Access Token   │ ← 通过代理请求微信 API
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 搜索 + 抓取文章     │ ← 按来源优先级选文
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 五层防重            │ ← filter_candidates / content_dedup / 主题判断 / 产品名查库
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 改写 + 排版         │ ← 防转载规则 + GEO 可检索化
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 五道校验关卡        │ ← 任一 exit≠0 → 禁止建稿，回炉重写
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 生成封面 + 配图     │ ← 混元，16:9，IP 角色参考图
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 上传素材 + 追加二维码│ ← --type thumb 封面 / uploadimg 配图
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 创建草稿(@file)     │ ← 内部再跑一遍关卡（双保险）
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 实拉草稿箱核验 + 日志│ ← exit=0 不等于成功，必须核验
       └─────────────────────┘
```

---

## 校验关卡（不可跳过）

| 脚本 | 职责 | 退出码 |
|------|------|--------|
| `validate_article_html.py` | img 数 ≥ 配图数 / 裸 URL=0 / `<section>` ≥ 2 / `<h2>` ≥ 2 | 0 通过 · 1 失败 |
| `validate_title.py` | 标题 ≤64 字符 / 硬禁词 / 涉政词 / 情绪对立 | 0 通过 · 1 失败 |
| `compliance_check.py` | 金融数据出处 / 绝对化极限词 / 医疗宣称 / 投资诱导 | 0 通过 · 1 FAIL |
| `originality_check.py` | 与源文逐句比对，拦照抄片段 | 0 通过 · **1 BLOCK** · 2 无法比对 |
| `content_dedup.py` | 内容级去重（选文阶段） | 1 = DUPLICATE |

> 词表真源：`scripts/_rules.py`。`validate_title.py` / `compliance_check.py` /
> `create_draft.py` 全部从这里导入，改词表只改一个文件。

---

## 防重复架构（五层）

| 层级 | 机制 | 范围 | 说明 |
|------|------|------|------|
| 1️⃣ | **URL 去重**（`filter_candidates.py`） | 7 天 | URL 规范化后比对，同一源文 URL 不再入选 |
| 2️⃣ | **`.done` 标记 + `.in_progress` 流程锁**（`semaphore_check.py`） | 当天 | 硬文件锁；`.done` 清除时写 `cleared:` 前缀保留历史，不物理删除；锁超 1 小时自动过期 |
| 3️⃣ | **内容级去重**（`content_dedup.py`） | 7 天 | 4-gram Dice 系数，阈值 0.28，无需分词 |
| 4️⃣ | **同日主题去重**（Agent 判断 + SKILL 规则） | 当天 | 同一热点/展会/公司/产品只留 1 篇，换角度也算重复 |
| 5️⃣ | **跨天产品/公司名查库**（`history.db`） | 7 天 | 选文定稿前比对近 7 天标题中的产品名/公司名，命中即作废候选 |

> 📌 第 5 层是最容易被忽略的一层：同一产品的两篇稿件 URL 不同、标题 Dice 甚至为 0.000，
> 前四层全部放行，只有查库比对产品名才发现。

---

## 关键参数参考

### 配图规则

- 正文段落数 ÷ 2 = 配图张数（6 段→3 张，8 段→4 张，10 段以上→5 张）
- **硬性约束**：最少 3 张，最多 5 张，禁止 1~2 张敷衍
- 封面 1536x864；正文配图 1024x576

### 腾讯混元参数

| 参数 | 值 |
|------|-----|
| 引擎 | HY-Image-V3.0 |
| 分辨率 | `1024:576` / `1536x864`（16:9，冒号格式） |
| 并发限制 | **1**（必须串行） |
| 重试 | 内嵌 3 次 |
| IP 参考图 | 支持（由 `accounts.yaml` 的 `ip_character` 配置） |

> ⚠️ 混元返回尺寸**不稳定**：封面映射 `1280:720` 但可能返回 1024x576，
> 流程走完必须用 PIL 复检，不足 1536x864 时 LANCZOS 放大后再上传。

### 编码安全（Windows 必知）

PowerShell 命令行传递中文 JSON → 自动转为 CP936 → Python 解码为乱码。解决方案：

```
❗ 禁止：python create_draft.py account_a $json_str
✅ 正确：python create_draft.py account_a "@$tmpFile"   （写 UTF-8 临时文件）
```

另有已踩 4 次的坑：Nginx 代理篡改 `requests` POST 的 Content-Type，UTF-8 字节被当 Latin-1
存入微信 → 中文乱码。根治方案已固化在 `create_draft.py`：改用 `urllib.request.urlopen`
并显式声明 `Content-Type: application/json; charset=utf-8`。

---

## 调度集成

本项目**只负责执行层**，不含调度器。推荐接入具备以下能力的调度平台（如 WorkBuddy Automations）：

- 支持每日定时触发与失约补触发
- 支持会话级超时终止
- prompt 自包含（调度层每次运行通常开新会话，无上下文继承）

典型做法是把「多账号发布 + 巡检补发」合并为**一个任务、多段串行**，段间互不阻塞：

```yaml
schedule:
  daily: "0 7 * * *"
  articles_per_day: 2
timeout:
  daily: 1800
```

每段结束写一份 `daily_YYYY-MM-DD.md` 作为固定查看点，便于进程中途异常时追溯进度。

---

## 注意事项

1. 正文配图必须用 `media/uploadimg` 接口（通过 `upload_article_image.py`），不能用 `material/add_material`，否则微信过滤不显示
2. 封面上传必须带 `--type thumb`，否则微信自动缩略图转换会生成全黑图片
3. 判断「发没发出去」必须**实拉草稿箱**（`draft/batchget`），`exit=0` 不代表成功
4. 原创声明无法 API 化（微信官方明确「API 不支持原创」），须在公众号后台手动勾选
5. 涉及 AI 改写 + 自动化发布的场景，请自行核对平台运营规范

---

## 致谢

- [腾讯混元大模型](https://hunyuan.tencent.com/) — AI 封面/配图生成
- [微信公众号开发文档](https://developers.weixin.qq.com/doc/offiaccount/) — API 参考
