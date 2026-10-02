# wechat-publisher v2.20.0

> 微信公众号多账号自动发布系统 · 配置驱动版
> 两个号：**君寻**（`junxun`，2 篇/天）· **岚牧哒**（`lanmuda`，1 篇/天）

**解释器**：全程显式使用 `C:/Python312/python.exe`，原因见 §8。

---

## 0. 核心原则（强制遵守）

1. **抓不到就不发** —— 抓取失败宁可少发一篇，不许编造内容
2. **主题去重（硬性）** —— 同一天内同一主题/热点/产品/企业的文章最多 1 篇；换角度、换来源也算重复
3. **禁止软文营销** —— 只要资讯，不要推广；禁止活动报名 / 导流口号 / 带货链接 / 下载引导
4. **标题 ≤ 64 字符**，**作者名 ≤ 8 字符**
5. **君寻每天 2 篇、岚牧哒每天 1 篇** —— 配额从 `accounts.yaml` 的 `schedule.articles_per_day` 读取，防重复机制必须执行
6. **十年杂志编辑水平** —— 翻译改写要「信达雅」，不是机翻
7. **原创性保护（硬性）** —— 标题与正文必须与源文显著不同，不得被微信判为转载
8. **内容安全（硬性）** —— 不得触发微信内容安全审核（见 §6.1 / §5）
9. **可检索化（GEO，硬性）** —— 每篇必须含结论句 + FAQ + 独家数据段（见 §6.3）
10. **编码安全** —— Python 脚本必须处理 Windows 中文乱码（见 §9）

---

## 1. 账号配置

`config/accounts.yaml` 中每个账号有 `key` 字段（`junxun` / `lanmuda`），脚本通过 key 匹配。
**脚本内部一律先归一化**：传中文名「君寻」也能正确解析（`create_draft.resolve_account`）。

| | 君寻 | 岚牧哒 |
|---|---|---|
| key | `junxun` | `lanmuda` |
| AppID | 见 `config/accounts.yaml`（不入版本库） | 同左 |
| 作者署名 | **君寻智能** | 岚牧哒 |
| 每日配额 | 2 篇（AI玩具 > 潮玩 > AI科技 > 其他，中文源优先） | 1 篇（英文翻译源） |
| 企业群二维码 | **必加**（正文末尾居中） | 不加 |
| 凭证 | `secure\.env_junxun` | `secure\.env_lanmuda` |
| history.db | `wechatlog\junxun\history.db` | `wechatlog\lanmuda\history.db` |

> ⚠️ 作者署名以 `accounts.yaml` 的 `author` 字段为真源。建稿 JSON 未填 `author` 时
> `create_draft.py` 会自动回落该字段 —— 不要手写「君寻」，实体口径统一为「**君寻智能**」。

---

## 2. 定时任务架构（单任务六段串行）

调度层为 **WorkBuddy Automations**（ACTIVE recurring），每天 **07:00** 启动，六段串行：

| 段 | 内容 | 典型耗时 |
|----|------|---------|
| 第一段 | 君寻发布 2 篇（AI玩具 > 潮玩 > AI科技） | 10~12 min |
| 第二段 | 岚牧哒发布 1 篇（英文翻译源，**必须完整翻译改写为中文**） | 6~8 min |
| 第三段 | 双号巡检：跑 `patrol_check.py` 判定，仅对需补发者补发 | 2~3 min |
| 第四段 | 图片中间产物回收：`reap_images.py --days 7` | < 1 min |
| 第五段 | 原创标识巡检：`copyright_check.py --count 4` | 1~2 min |
| 第六段 | 多平台分发准备：`distribute/prepare.py --count 5`（已发表文章 → 跨平台素材包） | < 1 min |

- 任务名：`公众号双号·每日发布+巡检(07:00)`，rrule `FREQ=DAILY;BYHOUR=7;BYMINUTE=0`
- **段间隔离（硬规则）**：任一段失败只记录该段结果，**必须继续执行下一段**，禁止因前段出错中断整个任务
- 每段结束写 `wechatlog\daily_YYYY-MM-DD.md` —— **这是固定查看点**，想知道发没发出来看这一个文件即可，不必翻会话
- 单次运行上限 **90 分钟**（`AUTOMATION_RUN_TIMEOUT_MS = 54e5`，到点强制销毁会话）；合并后典型耗时 20~25 分钟，余量充足

### 2.1 巡检（第三段）专用规则

第〇步必须跑 `python scripts/patrol_check.py` 拿机器判定，**禁止凭感觉判断**：

| 状态 | 含义 | 动作 |
|------|------|------|
| `DONE` | 已发满配额 | 跳过 |
| `RUNNING` | `.in_progress` 锁新鲜（≤60min）且未发满 | **禁止补发**，立即结束 |
| `STALE_LOCK` | 锁过期（>60min）且未发满 | 按补发处理 |
| `NEEDS_RESEND` | 无锁且未发满 | 必须补发 |
| `DB_MISSING` | 库/配置异常 | 跳过并告警 |

退出码：`0`=全部 DONE / `1`=需补发 / `2`=有账号在跑 / `3`=错误。

> ⚠️ **绝对禁止对 `RUNNING` 补发** —— daily 正在运行，补发会撞车导致同一账号重复发稿（历史事故）。

### 2.2 图片回收（第四段）· 目录卫生

**为什么要这一步**：每篇 5~6 张图（封面 2.6MB + 正文 1.7MB×5）落盘后即完成使命 ——
图已上传微信，而 `mmbiz.qpic.cn` **有防盗链**，本地副本既不能直接引用也不能复用。
历史流程只落盘、从不回收，2026-09-29 实测累积 **≈2 GB**（占项目总量 92%），
其中真正有用的仅约 1.3 MB。

```bash
C:/Python312/python.exe scripts/reap_images.py            # 回收 7 天前（默认）
C:/Python312/python.exe scripts/reap_images.py --days 3   # 改保留期
C:/Python312/python.exe scripts/reap_images.py --dry-run  # 只报告不删
```

扫描根（自动推导，无需配置）：

| 根 | 来源 |
|---|---|
| `<wechatlog>\` | 从 `accounts.yaml` 各账号 `history_db` 反推 |
| `H:\workspace\苏编\` | `WECHAT_WORKSPACE` 环境变量可覆盖 |

**硬编码安全红线**（不可配，写在脚本里）：

- 只删图片扩展名（`.png/.jpg/.jpeg/.webp/.gif/.bmp`）
- 路径中出现 `wechat-assets` / `skills` / `secure` / `.workbuddy` / `_archive` / `cover_library` → **整棵子树跳过**
- 永不删 `.md` / `.db` / `.done` / `.in_progress`
- `--days < 1` 直接拒绝执行

> ⚠️ 归档区一律放在 **skill 目录之外**。归档留在 skill 内部不会减小体积，
> 只会让 skill 自身变成垃圾场（2026-09-29 踩过：把 446MB 从根目录挪进 `_archive/`，体积分文未减）。

### 2.3 历史沿革（排查参考）

- **2026-09-26 前**：4 个 qclaw cron 任务（`openclaw.sqlite` 的 `cron_jobs`），`wechat-v2-junxun-retry` 因设计错误删除
- **2026-09-27**：整体迁移至 WorkBuddy Automations（3 任务）。原因：qclaw cron 调度器内置于 openclaw 网关进程，宿主不在线则**零触发**（9/26 晚启动、9/27 全天零触发两次事故）。qclaw 侧 `wechat-v2-*` 已全部 `enabled=0` 防双跑；脚本、history.db、锁机制原位不变
- **2026-09-29**：**3 任务合并为 1 个**（减少每次执行新建的会话数，3 会话/天 → 1）。取舍：失去错峰与独立兜底（会话硬崩则后段不执行），缓解手段为段间隔离 + 每段落盘日志 + 巡检可事后手动补跑
- **2026-09-29（同日）**：新增**第四段「图片回收」**，把 `reap_images.py --days 7` 挂在巡检之后。至此单任务四段：发布 → 发布 → 巡检 → 回收

---

## 3. 内容来源与选题

### 3.1 君寻内容优先级

**AI玩具 > 潮玩 > AI科技资讯 > 其他**

1. 🇨🇳 **中文源优先** — chaoliunews.com（潮玩新品）、rfidworld.com.cn（AI玩具行业）、xkb.com.cn（玩具深度）
2. 📱 **公众号优质源**（依次找最新文章，仅取 AI玩具/潮玩相关）：南方新消费、IP大师、视觉文化研究
3. 🔍 **中文搜索** — 搜「AI玩具 新品」「潮玩 盲盒」「智能玩具 陪护机器人」「智萌体 潮玩」
4. 🌐 **英文源翻译** — WIRED / Ars Technica 抓 AI/机器人/科技方向，翻译改写
5. 🏢 **设计创意** — Yanko Design / ThisIsWhyImBroke 选 AI/智能/机器人相关

选择逻辑：按顺序尝试，**中文源有货就用中文源**，不为凑数去翻英文。第二篇尽量换来源/换方向。

### 3.2 岚牧哒来源

英文翻译源：WIRED / TechCrunch / Ars Technica / Yanko Design / ThisIsWhyImBroke。
**与君寻的来源逻辑完全独立，不可混用。** 建稿前必须确认已完整翻译改写为中文（`create_draft.py` 有中文占比关卡）。

### 3.3 站点黑名单

`baike.baidu.com`、`zhuanlan.zhihu.com`、`sap.cn`、`gartner.com`、`cloudflare.com`、
`nsfc.gov.cn`、`github.com`、`caijing.com.cn`（配置于 `global.blacklist`）

> ⚠️ **研报类源文（PDF 转网页，如 sgpjbg）风险最高** —— 全文照抄片段多，
> 选文时优先新闻类源文。若必须用，改写力度要加倍。

---

## 4. 发布流程（逐篇循环）

### 第〇步：防重复硬屏障 + 写锁（强制，所有任务的第一行）

```powershell
C:/Python312/python.exe scripts/semaphore_check.py <account_key> --check
# exit 0 = READY → 立即写锁
C:/Python312/python.exe scripts/semaphore_check.py <account_key> --create-in-progress
# exit 1 = ALREADY_DONE → 立即 STOP，不得继续
```

三层屏障，任一命中即阻塞：**history.db 今日记录** → **`.in_progress` 锁** → **`.done` marker**。
锁超过 60 分钟自动视为过期（异常退出后不永久阻塞）；`create_draft.py` 成功后自动写 `.done` 并清 `.in_progress`。

**特别注意**：
- **君寻 2 篇**：`semaphore_check` 只是总开关（是否 ≥1 篇），篇数仍需查 history.db
- **岚牧哒 1 篇**：`semaphore_check` 即最终判断，命中即跳过
- **第三段巡检**：先跑 `patrol_check.py` 拿状态再决定动作

### 第三步：获取 Access Token

```powershell
curl.exe "$proxy/cgi-bin/token?grant_type=client_credential&appid=$APP_ID&secret=$APP_SECRET"
```

从 `env_file` 读取 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`，代理地址从 `global.proxy` 读取。

### 第四步：搜索 + 抓取 + 选文

`target_count` = 2（君寻）/ 1（岚牧哒）。按 `sources` 顺序尝试，逐个候选执行以下过滤：

```
# ① URL 去重（代码强制，禁止跳过）
C:/Python312/python.exe scripts/filter_candidates.py <account_key> "@候选列表.json"
# 候选 JSON：[{"title":"...","url":"...","source":"..."}, ...]
# 只能在过滤后的列表里选文，exit 0 = 正常（即使全被过滤）

# ② 内容级去重（用改写后的标题跑）
C:/Python312/python.exe scripts/content_dedup.py <account_key> "<改写后的标题>"
# exit=1 DUPLICATE → 跳过

# ③ 本轮已选列表内排除（used_urls）

# ④ 主题去重（硬性，Agent 判断）
#   同一热点 / 同一产品 / 同一公司 / 同一展会 → 跳过，不论角度
#   拿不准时宁可少选

# ⑤ 跨天产品/公司查库比对（硬性，见 §4.1）
```

内容 ≥ 500 字才算有效；使用文章**具体页面 URL**，不是 RSS feed URL。

#### 4.1 跨天主题去重：查库比对产品/公司名（硬性）

现有四层拦不住「同一公司/同一产品、不同稿件、不同 URL」。选文定稿前**必须**执行：

```powershell
C:/Python312/python.exe -c "import sqlite3;c=sqlite3.connect(r'C:\Users\LMD\.qclaw\wechatlog\junxun\history.db');[print(r) for r in c.execute(\"SELECT date,title,source_url FROM history WHERE date >= date('now','-7 day') ORDER BY rowid DESC\")]"
```

逐条比对候选文章涉及的产品名 / 公司名 / 核心人物。**命中即作废该候选，不许换角度重写。**

> ⏰ **查「今日是否已发」不要用 `date('now')`** —— SQLite 的 `date('now')` 走 **UTC**，
> 而任务固定在 **07:00（UTC+8）** 跑，此时 UTC 还停在前一天 → 查询结果会静默漏掉当天记录
> （2026-09-30 踩过：两篇 09-30 的草稿已入库，`WHERE date=date('now')` 却只返回 09-29 的行）。
> 核验一律按 `ORDER BY rowid DESC LIMIT n`，或显式写本地日期字符串。

> 📌 两次事故：2026-09-26、2026-09-28（bibo / 杭州镭萌科技，两篇 URL 不同、标题 4-gram Dice = 0.000，所有脚本全部放行）。
> 处置一条命令搞定：`delete_draft.py <key> <media_id> --purge-history`（撤稿 + 清 history 占位），然后换选题重做。

### 第五步：翻译改写 + 排版

**君寻**循环 2 篇，**岚牧哒** 1 篇。用 Agent 能力直接改写，不需要 Python 脚本。
保留原文核心数据与事实，输出标题 / 作者 / 正文 HTML / 摘要 / 配图描述。规则见 **§6**。

### 第六步：生成封面 + 配图

```powershell
C:/Python312/python.exe scripts/generate_cover.py junxun cover "prompt带早八主角" cover.png
C:/Python312/python.exe scripts/generate_cover.py junxun img1 "prompt" img1.png
# 临时换角色（仅本次生效）
C:/Python312/python.exe scripts/generate_cover.py junxun cover "prompt" cover.png --character 森森
```

降级链路（脚本自动）：🥇 腾讯混元 HY-Image-V3.0（支持参考图）→ 🥈 智谱 CogView-4 → 🥉 本地封面库。

详见 **§7**。

### 第七步：上传素材

```powershell
# 封面（永久素材，--type thumb 不可省！）
C:/Python312/python.exe scripts/upload_article_image.py junxun cover.png --type thumb --permanent
# 返回 media_id（无 URL），用作 thumb_media_id

# 配图（图文正文内嵌图片）
C:/Python312/python.exe scripts/upload_article_image.py junxun img1.png img2.png img3.png
```

| 模式 | 接口 | 返回 | 用途 |
|------|------|------|------|
| `--type image`（默认） | `media/uploadimg` | `?from=appmsg` 开头的 URL | **正文配图** |
| `--type thumb` | `material/add_material?type=thumb` | `media_id` | **封面缩略图** |

> 🔥 封面**务必**加 `--type thumb`，否则微信自动缩略图转换会生成全黑图片。
> 🔥 正文配图**只能**用 `media/uploadimg`；把 `add_material` 的 media_id 塞正文会被微信过滤不显示。

### 第八步：追加企业群二维码（仅君寻）

```html
<p style="text-align:center;margin:30px auto 10px;">
  <img src="http://mmecoa.qpic.cn/sz_mmecoa_jpg/UobsGRjtYicVG1axkc3e3MLf1dtKCBfWjurXQfFWk8DthtyI7bb5dzEP27gUSWtic4CS14sPqVibibhGW97XztYM0ot9tHSq8dplEl364PlBeiaU/0?wx_fmt=jpeg"
       style="width:50%;height:auto;display:block;margin:0 auto;border-radius:8px;">
</p>
<p style="text-align:center;font-size:14px;color:#888888;margin-top:5px;">
  <span>扫码加入君寻粉丝群，获取更多AI前沿资讯</span>
</p>
```

- **仅君寻**需要，岚牧哒不加
- 二维码 URL 永久不变。校验标识：正文含「粉丝群」且含 `mmecoa`
- 本地文件：`<your-local-path>/君寻企业微信群二维码.jpg`

### 第九步：创建草稿

```powershell
# 🔥 必须写 UTF-8 临时文件 + @file 传参！
# PowerShell 管道用 CP936 解码中文，标题汉字会变问号
$draft_json = @{
  title = "文章标题"
  author = "君寻智能"
  content = "<p>正文HTML...</p>"
  digest = "摘要"
  thumb_media_id = "封面media_id"
  need_open_comment = 1
  only_fans_can_comment = 0
  content_source_url = "文章来源原始URL"
} | ConvertTo-Json -Depth 10

$tmpFile = "$env:TEMP\draft_$(Get-Random).json"
$draft_json | Out-File -FilePath $tmpFile -Encoding utf8
C:/Python312/python.exe scripts/create_draft.py junxun "@$tmpFile"
Remove-Item $tmpFile -Force
```

必填参数：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `need_open_comment` | `1` | ⚠️ 必须 1，开启评论区 |
| `only_fans_can_comment` | `0` | 1=仅粉丝，0=所有人 |
| `content_source_url` | `""` | ⚠️ 必须填源文 URL，不能留空 |

> `create_draft.py` 内部已内置 §5 全部关卡，任一不通过直接 exit 1 拒绝建稿（双保险）。

### 第十步：收尾核验 + 记日志

**必须实拉草稿箱核验**（`lastRunStatus=ok` 与 `exit=0` 都**不等于**文章真建出来了）：

```powershell
curl.exe "$proxy/cgi-bin/draft/batchget?access_token=$TOKEN"
```

核对：标题 / 作者 / 配图数 / `from=appmsg` / 君寻二维码 / 中文无乱码（须以 `json.loads(r.content.decode('utf-8'))` 解码，否则 requests 默认 Latin-1 会误报乱码）。

然后写日志 `$log_dir/wechat_v2_YYYY-MM-DD.md`。

---

## 5. 校验关卡总表（不可跳过）

排版完成后、建稿前**必须**依次跑完。**任何一个 exit ≠ 0 → 禁止建稿**，回到上一步修复。

| 脚本 | 职责 | exit 码 | 不通过的处置 |
|------|------|---------|-------------|
| `validate_article_html.py` | 排版结构：img ≥ 配图数 / 裸 URL=0 / `<section>` ≥ 2 / `<h2>` ≥ 2 | 0 通过 · 1 失败 | 修排版 |
| `validate_title.py` | 标题：≤64 字符 / 硬禁词 / 涉政词 / 情绪对立 | 0 通过 · 1 失败 | 改标题 |
| `compliance_check.py` | **合规硬化**：金融数据出处 / 绝对化表述 / 医疗宣称 / 投资诱导 | 0 通过 · 1 FAIL | 改命中处 |
| `originality_check.py` | 原创度：与源文逐句比对，拦照抄片段 | 0 通过 · **1 BLOCK** · 2 无法比对 | 重写命中句 |
| `geoready_check.py` | **GEO 就绪度 / 原创可声明性**：四要素齐全 + 与源文相似度 + 站内正文撞车 | 0 通过（含 WARN）· **1 BLOCK** · 2 无法完整检查 | 补要素 / 重写撞车段 |
| `content_dedup.py` | 内容级去重（选文阶段） | 1 = DUPLICATE · 2 = 读库异常（**非**重复） | 换选题 / 排查 |
| `filter_candidates.py` | URL 去重（选文阶段） | 0 正常 | 只在过滤结果里选 |

```powershell
C:/Python312/python.exe scripts/validate_article_html.py "<html文件>" <配图数>
C:/Python312/python.exe scripts/validate_title.py "<标题>" "<html文件>"
C:/Python312/python.exe scripts/compliance_check.py "<html文件>" --title "<标题>"
C:/Python312/python.exe scripts/originality_check.py "<html文件>" --source "<源文URL>"
C:/Python312/python.exe scripts/geoready_check.py "<html文件>" --account <key> --source-file "<源文纯文本>"
```

> **GEO 关卡是「每篇都能勾原创」的保证**（2026-09-30 新增，详见 §6.3 与 §11）：
> 它把可检索化四要素、与源文改写幅度、站内正文撞车三件事合成一道硬关卡，
> **`create_draft.py` 内部已内置调它**（第 7 道），因此建稿时无需单独跑，
> 但**必须用 `--source-file` 把源文传给建稿脚本**，否则跳过源文比对（只告警不拦）。

> **词表真源**：`scripts/_rules.py`。禁词表只此一份，`validate_title.py` / `compliance_check.py` /
> `create_draft.py` 全部从这里导入 —— 改词表只改这一个文件，不再出现文档与代码口径漂移。
>
> 📌 历史教训：
> - 2026-07-19 标题含「封杀」「活该」→ 文章被删除
> - 2026-08-11 君寻第 2 篇 5 张配图被以**裸 URL 文本**写进正文，微信端只显示链接。靠人眼自检漏过，必须代码强制
> - 2026-09-29 实测 8 篇已发文章，全局相似度都只有 0.01~0.23，但 2 篇藏着 24%~27% 高相似句、
>   1 篇有 **36 字连续照抄**、另有 1 句相似度 **1.000**。**全局相似度看不出问题，必须做片段级检测**

---

## 6. 改写与排版规范

### 6.1 标题规则

**A. 防转载（不遵守 → 被判转载 → 流量归零）**

1. **换角度切入**：不要跟原文标题说同一件事
   - ❌ 原文「潮玩传统赛道加速转型 AI等新渠道或成破局关键」→ 你写「潮玩加速转型：AI新渠道如何撕开千亿市场突破口」（5 个关键词重叠，命中）
   - ✅ 改为具体案例切入：「泡泡玛特悄悄投了一家AI芯片公司」
2. **换句式结构**：原文「XXX加速转型 XXX成为XX关键」→ 你写同结构只是换词，没用。改用提问句 / 反常识 / 具体数字
3. **词库替换**：原文标题的关键词，你**最多保留 1 个**
4. **自检**：把两个标题放一起读 —— 核心意思一样只剩措辞不同 → **重写**

**B. 内容安全（不遵守 → 文章被删或限流）**

1. **绝对禁止词**（出现即重写）：`封杀` `慌了` `慌了神` `傻眼` `倒闭` `跑路` `崩盘`
   `喊杀` `喊打` `活该` `暴雷` `割韭菜` `碾压` `吊打` `血洗` `喊打喊杀`
2. **涉外/政治敏感词**（出现 ≥2 个即拦）：`硅谷` `白宫` `华盛顿` `欧盟` `华尔街` `五角大楼` `国会`
3. **绝对化/极限词**（广告法风险，标题出现即拦）：`最好` `最强` `全球第一` `唯一选择`
   `首家` `首款` `首个` `顶级` `极致` `绝对` `国家级` `世界级` `100%` `史上最` …
   若为可举证事实，改写为带出处的表述：「据《××报告》× 项指标居首」
4. **投资诱导词**（出现即拦）：`荐股` `炒股` `抄底` `买入` `稳赚` `必涨` `加仓` …
5. **正确的替代写法**：
   - ❌ `Kimi K3碾压排行榜，硅谷慌了：有人在喊封杀，有人在喊活该` → 被删
   - ✅ `Kimi K3登顶多项AI评测，技术文档透露了这些细节`

**C. 搜索友好（搜一搜场景 · 2026-10-02 新增，实验阶段）**

> **为什么加这条**：两号均为**服务号**，微信官方明确「**推荐是订阅号的能力**」，服务号
> **不进推荐池**（微信官方运营专员原话：「**推荐是订阅号的能力**……服务号的流量平台不会做干预，
> 不会多分发也不会限流」）→ **搜一搜是唯一能自主争取的增量流量**。
> 存量回测（君寻 264 篇 / 岚牧哒 147 篇）：标题平均 27~29 字，**85% 超过 22 字**；
> 结构普遍是「场景白描/悬念 **：** 结论」，前 12 字多为文学描写而非可搜索实体
> → 完全达标率仅 **29% / 24%**。

1. **前 12 字必须含 ≥1 个可搜索实体**（品牌名 / 产品名 / 品类词）。用户搜的是实体，不是修辞。
   - ❌ 「看表情、听语速、辨姿态：一台机器人怎么读懂青少年的情绪」→ 前 12 字零可搜词
   - ✅ 「陪伴机器人靠表情识别读情绪」
2. **总长目标 18~24 字（上限 26）** —— 搜索结果里标题会截断，后半段的钩子等于不存在
3. **钩子（数字 / 冲突）放实体之后**，不要占用前半段
   - ❌ 「卖了12万台、单日百亿Token：一只AI毛球正在跑量」→"AI毛球"没人搜
   - ✅ 「AI毛绒机器人卖了12万台」
4. **选词依据 = 两个词库文件**（分工不同，勿混）：
   - `config/keywords.yaml` —— **自有实体词**（品类词 + 品牌词），由 `history.db` 411 篇标题
     自动提取，回答「**我们写过什么**」；稳定，手写维护。
   - `config/search_terms.yaml` —— **外部真实搜索词**（各平台接口 / 后台导出），按平台分节，
     回答「**用户搜什么**」；用 `scripts/keywords_import.py` 导入，可反复更新。
     · 手动：`keywords_import.py <文件.csv|.txt|.json|-> --platform "微信搜一搜"`
     · 接口：`keywords_import.py --url "<接口地址>" --platform "..." --replace`
       （需鉴权加 `-H "Authorization: ..."`；格式自适应 CSV/JSON/TXT）
     ⚠️ **接口每天给全量词表时必须加 `--replace`** —— 否则过期词永久残留、reads 只增不减
   `validate_title.py` 同时读这两个文件 —— **改词只改这两个，不许在脚本里再抄一份**。
   导入时脚本自动输出「**缺口分析**」：用户搜、但我们实体词表里没有的词 = **机会点**。
5. **自检**：念给一个没看过文章的人，问他「想搜这条新闻会打什么字」—— 那个词不在前 12 字里，就重写

> **自 v2.20.0 起升级为硬关卡（2026-10-02 拍板）**：`WARN[GEO-1]`（前 12 字无实体）/
> `WARN[GEO-2]`（超 26 字）命中即 `exit 1`；`create_draft.py` 内置同名关卡同步拒绝建稿。
> 临时放宽用 `--geo-warn-only`（逃生阀，不建议常态使用）。
> ⚠️ 代价：会掉一部分「杂志味」，社交场景点击率可能下降 —— 这正是要观察的取舍。

### 6.2 正文规则

1. **改变文章结构** —— 原文「现状分析 → 案例1 → 案例2 → 趋势预测」，
   你写「具体案例开篇 → 引出趋势 → 反方观点 → 展望」。分段顺序一致 = 危险信号
2. **替换切入角度** —— 原文从「行业趋势」讲，你从「消费者/产品」讲；原文从「数据报告」讲，你从「企业动作」讲
3. **核心表达重写** —— 关键论点、判断句、总结句不得原意复述
4. **每段自检** —— 去掉修饰词后与原文差不多 → 整段重写或删掉
5. **【2026-09-29 实测新增】事实句 / 引语必须重构**

   | 句式类型 | ❌ 禁止 | ✅ 正确做法 |
   |---------|--------|-----------|
   | 数据句 | 整句搬「报告预计 2029 年达到 3358 亿元」 | 数字保留，**主谓宾全换**：「3358 亿元是这份报告给 2029 年的数字」 |
   | 直接引语 | 照抄当事人原话 | 优先**转述**；必须直引则加引号并写明「×× 在接受采访时说」 |
   | 人名+学历+机构 | 「张喜寒拥有耶鲁大学心理学系神经科学方向博士学位与哈佛大学计算生物学硕士学位」 | 拆开重组：「两位联创都出自耶鲁——一位读的神经科学，一位读的计算机」 |
   | 金句/结论句 | 原句照搬（**最容易被判抄**） | **必须完全重写**，连语序都不能留 |
   | 报告/研报类源文 | 大段引用其结论段 | **风险最高，尽量避免选研报 PDF 转网页作源** |

   > **铁律：数字、人名、机构名可以保留，包着它们的那个句子不能保留。**
   > 建稿前必须跑 `originality_check.py`，BLOCK 就重写命中句，不许绕过。
   >
   > ⚠️ **高发区：榜单/评测段 + 人才名单段**（2026-10-01 实测）。这两类段落最容易被整句顺译，
   > 单句 Dice 直接冲到 1.000、LCS 破百（当日诺因稿：LCS 143 字 / 单句 1.000 / 全文 0.378）。对策：
   > - 评测数字写成**倒装**——「RoboDojo 摆了 18 项任务，GLOW 报出 62.2%」，
   >   而不是「GLOW 在 RoboDojo 的 18 项仿真任务中取得 62.2% 的平均成功率」
   > - 人才段**加小标题断句**——「一个负责生成式视觉与空间智能，另一个负责数据与计算基础设施」，
   >   而不是「分别在生成式视觉与空间智能、数据与计算基础设施方向」
   > - 按源文顺序「融资 → 技术 → 评测 → 人才 → 展望」写 ≈ 送分；改成**案例开篇**再复盘数据

6. **配图节奏** —— 每 2 段插 1 张，最长 3 行的段落跳过，配图数 3~5 张（6 段→3 张，8 段→4 张，10 段以上→5 张）。**禁止只配 1~2 张敷衍**

### 6.3 GEO 可检索化规范（2026-09-29 新增，硬性）

> **代码强制（2026-09-30）**：①②④ 已由 `scripts/geoready_check.py` 自动校验，
> 建稿时作为第 7 道关卡执行（`create_draft.py` 内置），**缺一即 BLOCK**；
> ③ 标题搜索意图词仍由改写环节人工保证（无法可靠自动化）。

> 背景：流量诊断结论 —— 两个号粉丝仅 27/23，**推荐权重为 0**，30 天阅读量 82% 来自**搜一搜**。
> 「推给粉丝」天花板极低，必须走外部流量。以下四条是 GEO 与涨粉**共用**的核心动作。

**① 首段结论句（必做）**
正文第一段 40~60 字内给出**完整结论**，含关键实体 + 数字。生成式引擎与搜索结果摘要优先摘录这一段。

- ❌ 「近年来 AI 玩具市场发展迅速，越来越多的企业开始布局……」
- ✅ 「一只毛绒机器人 7 小时卖出 100 万美元 —— 这是 AI 玩具第一次跑出消费电子的销量曲线。」

**② 末尾 FAQ 2~3 条（必做）**
以 `Q：` / `A：` 形式回答**真实搜索意图**（不是自问自答的软文）。例如：
- `Q：AI 陪伴玩具有必要买吗？` `Q：这款产品国内什么时候能买到？` `Q：和上一代比升级了什么？`

**③ 标题覆盖搜索意图词（必做）**
标题含 1~2 个用户真会搜的词（产品名 / 品类词 / 场景词），但**不得堆砌**，
且与 §6.1 的防转载规则不冲突（最多保留原文 1 个关键词）。

**④ 独家数据段（必做，末尾）**

```powershell
C:/Python312/python.exe scripts/geo_stats.py --sentences   # 生成可引用的数据句
```

把生成的数据句（改写成自己的语气）放在文末，**必须标注口径与时间范围**，例如：

> 据君寻智能内容团队统计，2026 年 4 月 29 日至 9 月 29 日，君寻累计发布 258 篇科技消费资讯，
> 选题覆盖 AI 大模型（53%）、AI 玩具与陪伴机器人（39%）、潮玩与谷子（31%）。

> ⚠️ **数据必须真统计**（来源 `history.db`）。一旦被查出编数据，品牌信誉不可逆。
> ⚠️ 统计口径 = **history.db 入库记录数**（发表为人工动作，脚本不回写状态），不要写成「已发表」。

**⑤ 品牌嵌入规则（硬性）**
- 一篇 **1~2 次**，语义必须成立；硬塞 = 被判软文降权
- 实体口径统一用「**君寻智能**」，不要单用「君寻」（易与其他实体混淆）
- 同一篇**不要**同时硬塞两个号（实体互相稀释 + 判营销）

### 6.4 排版组件模板

所有 section 组件只用 inline style，不依赖外部编辑器。

**分节标题（背景条 + 蓝渐变数字圆标）**

```html
<section style="margin: 18px auto;background: linear-gradient(to right, #e8f0fe, #f5f9ff);border-radius: 6px;padding: 8px 14px;box-sizing: border-box;text-align: justify;">
  <section style="display: flex;justify-content: center;align-items: center;">
    <section style="flex: 1;text-align: center;">
      <h2 style="font-size: 17px;color: #1a73e8;font-weight: bold;margin: 0;padding: 0 10px 0 0;line-height: 1.5;">
        <span style="color: #1a73e8;font-size: 17px;font-weight: bold;">小标题文字</span>
      </h2>
    </section>
    <section style="flex-shrink: 0;box-sizing: border-box;">
      <section style="font-size: 14px;font-weight: bold;color: #ffffff;text-align: center;background: linear-gradient(135deg, #1a73e8, #4a9eff);width: 32px;height: 32px;border-radius: 50%;display: flex;justify-content: center;align-items: center;">
        <strong><span>01</span></strong>
      </section>
    </section>
  </section>
</section>
```

**无数字圆标的节标题（左侧竖线版，如「写在最后」）**

```html
<section style="margin: 18px auto;background: linear-gradient(to right, #e8f0fe, #f5f9ff);border-radius: 6px;padding: 10px 14px;box-sizing: border-box;text-align: justify;">
  <section style="display: flex;justify-content: flex-start;align-items: center;">
    <section style="flex-shrink: 0;width: 4px;height: 22px;border-radius: 25px;background: linear-gradient(to bottom, #1a73e8, #4a9eff);margin-right: 10px;"></section>
    <h2 style="font-size: 17px;color: #1a73e8;font-weight: bold;margin: 0;padding: 0;line-height: 1.5;">
      <span style="color: #1a73e8;font-size: 17px;font-weight: bold;">写在最后</span>
    </h2>
  </section>
</section>
```

**正文段落**

```html
<p style="text-align: justify;font-size: 15px;line-height: 1.75em;letter-spacing: 0.5px;margin: 0 8px 12px;text-indent: 2em;">
  <span style="font-size: 15px;letter-spacing: 0.5px;">正文内容……</span>
</p>
```

**强调 / 数据高亮 / 配图 / 分割线 / 引用块**

```html
<span style="font-weight: bold;color: #1a73e8;">品牌名</span>     <!-- 品牌名：蓝色加粗 -->
<strong>关键数据</strong>                                       <!-- 数据：直接加粗不换色 -->

<p style="text-align: center;margin: 10px auto;">
  <img src="{配图URL}" style="width: 85%;height: auto;display: block;margin: 0 auto;border-radius: 8px;" alt="配图描述">
</p>
<p style="text-align: center;font-size: 13px;color: #888;margin-top: -5px;">
  <span>▲ 图注说明 | 来源：XXX</span>
</p>

<hr style="border-style: solid;border-width: 1px 0 0;border-color: rgba(0,0,0,0.08);margin: 20px 0;">

<blockquote style="border-left: 3px solid #1a73e8;padding: 8px 16px;margin: 16px 8px;background: #f5f7fa;border-radius: 4px;">
  <span style="font-size: 14px;color: #555;">引用内容……</span>
</blockquote>
```

**排版规则摘要**
- 正文：15px / 1.75em 行高 / letter-spacing 0.5px / 段间距 12px / 首行缩进 2em
- 分节标题：`<section>` 嵌套组件，浅蓝渐变背景条（`#e8f0fe → #f5f9ff`，圆角 6px）
- 配图：width 85% 不铺满，圆角 8px，图注 13px 灰色 `#888`
- **禁止**全篇只有 `<p>` 段落；至少 2 个分节标题，`01/02/03` 圆标依次编号

**禁止的广告类内容**：活动报名 / 展会推广 / 平台导流口号 / 产品推广链接 / 带货二维码 /
下载引导 / 软文话术（「别再死磕XX」「限时XX」）/ 商品卡片 / 底部推广 Banner

### 6.5 尺寸规范

- 封面（cover）：16:9 = **1536x864**
- 配图（img1~5）：16:9 = **1024x576**

---

## 7. 配图

### 7.1 IP 角色参考图配置

在 `accounts.yaml` 通过 `ip_character` 控制 —— **封面和文章配图独立配置**：

```yaml
ip_character:
  cover:
    character_dir: "F:/文章资料/IP形象图/早八.png"   # 图片文件路径，空则不传
  article:
    character_dir: "F:/文章资料/IP形象图/早八.png"
```

- `character_dir` 是**完整图片文件路径**。有路径 + 文件存在 → 传参考图；空或不存在 → 纯文本生图
- 封面和配图**可以不同角色**（各自指定路径即可）
- 临时覆盖：`--ref-path "F:/文章资料/IP形象图/森森.png"`
- ⚠️ **君寻、岚牧哒都已配置 `早八.png`** —— 两号 prompt 第①段**都必须**以「参考图的卡通形象」开头。
  旧说法「岚牧哒无参考图」已过期（2026-09-28 订正）

### 7.2 配图 prompt 模板（三段式）

```
# ① 主角：参考图的卡通形象 + 服装 + 动作
#    ⚠️ 封面必须确保 IP 角色是唯一/核心主角，占据画面视觉中心
参考图的卡通形象，穿着[服装描述]，在做[具体动作/事情]。

# ② 场景氛围：场景 + 构图 + 氛围
[场景描述，如：深夜办公室，窗外城市霓虹，桌面上……]

# ③ 标准化风格词库（固定套餐，每张图都用这套）
3D渲染，超现实主义，皮克斯风格，卡通，可爱，
丁达尔效应，伦勃朗光色影调色，景深，层次感，
顶级高清，顶级品质，电影级质感，8K高清画质。
```

- 混元 `images` 参数传入角色素材文件，prompt 中**不写角色外貌**，用「参考图的卡通形象」引导
- 风格词库固定，整篇文章所有配图风格统一；封面必须是正面/近景/主角位

**混元使用要点**
- 支持参考图，约 10 秒出图，**并发上限 1（必须串行）**，内置 3 次重试
- 分辨率参数用**冒号**格式（`1024:576`）
- ⚠️ **返回尺寸不稳定**：封面映射 `1280:720`，但可能返回 1024x576 →
  流程走完**必须用 PIL 复检**封面实际像素，不足 1536x864 时用 LANCZOS 放大后再上传

---

## 8. 解释器选择（强制）

**本机 PATH 首位的 `python` 不能跑本技能的第三方依赖脚本。**

- PATH 首位指向 `C:\Users\LMD\.workbuddy\binaries\python\versions\3.13.12\python.exe`（managed），
  该环境**缺 `idna` 模块**，`import requests` 直接抛 `ModuleNotFoundError`
  → `generate_cover.py` / `create_draft.py` / `upload_article_image.py` 全部无法启动
- ✅ **一律显式调用 `C:/Python312/python.exe`**（requests / idna / yaml / PIL / urllib3 齐全，已实测）
- 无第三方依赖的脚本（`semaphore_check.py` / `validate_*.py` / `patrol_check.py`）用 `python` 亦可，
  但为统一起见建议全部用 `C:/Python312/python.exe`
- 症状识别：报 `ModuleNotFoundError: No module named 'idna'` 或 `RequestsDependencyWarning`
  → 换解释器，**不要 pip install 污染用户环境**

---

## 9. 编码规范（强制）

Python 脚本开头必须有：

```python
import sys
# ⚠ 用 reconfigure，不要写 sys.stdout = io.TextIOWrapper(sys.stdout.buffer, ...)
#   替换对象会让旧对象 GC 时关闭底层 buffer → 同进程 import 第二个脚本即崩
#   （ValueError: I/O operation on closed file）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except Exception:
        pass
```

> 脚本要能被 `import`（被别的脚本当模块用），这是硬要求 ——
> `compliance_check.py` 曾因模块级 `sys.exit(3)` 导致 import 即退出，已修。

**`requests.post` 禁止用 `json=` 参数**：

```python
import json, requests
payload = {"key": "value"}
headers = {"Content-Type": "application/json; charset=utf-8"}
data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
r = requests.post(url, data=data, headers=headers)
```

**已踩 4 次的坑**：自建 Nginx 反向代理网关会篡改 `requests` POST 的 Content-Type，
UTF-8 字节被当 Latin-1 存进微信 → 中文乱码。**根治方案已固化在 `create_draft.py`**：
改用 `urllib.request.urlopen` + 显式 `Content-Type: application/json; charset=utf-8`。
`--create-in-progress` / `@file` 传参同理（PowerShell 管道走 CP936）。

---

## 10. 文件结构

```
<skill_dir>\                          ← 本技能根目录（保持精简，归档勿放此处）
├── SKILL.md                          ← 本文件（改文档改这里）
├── CHANGELOG.md
├── README.md
├── config\accounts.yaml
├── config\keywords.yaml               ← 自有实体词（品类/品牌，从历史标题提取）
├── config\search_terms.yaml           ← 外部真实搜索词（按平台分节，由 keywords_import.py 写入）
├── config\platforms.yaml              ← 多平台能力矩阵 + GEO 规则（分发模块真源）
└── scripts\
    ├── _rules.py                     ← ★ 内容安全词表唯一真源
    ├── semaphore_check.py            ← 第〇步防重复硬屏障（三层）
    ├── patrol_check.py               ← 巡检状态机（5 状态）
    ├── filter_candidates.py          ← 选文 URL 去重（7 天）
    ├── content_dedup.py              ← 选文内容级去重（4-gram Dice）
    ├── generate_cover.py             ← 封面 + 配图生成（三级降级）
    ├── upload_article_image.py       ← 上传素材（image / thumb 双模式）
    ├── validate_article_html.py      ← 关卡①排版结构
    ├── validate_title.py             ← 关卡②标题安全 + 搜索友好度
    ├── keywords_import.py            ← 搜索热词导入（CSV/TXT/JSON → search_terms.yaml + 缺口分析）
    ├── compliance_check.py           ← 关卡③合规硬化（金融/绝对化/医疗/投资）
    ├── originality_check.py          ← 关卡④原创度（片段级）
    ├── geoready_check.py             ← 关卡⑤GEO 就绪度 / 原创可声明性（四要素 + 源文 + 站内撞车）
    ├── geo_stats.py                  ← GEO 数据资产提炼
    ├── reap_images.py                ← 图片中间产物回收（第四段）
    ├── copyright_check.py            ← 原创标识巡检（第五段）
    ├── create_draft.py               ← 建稿（内置全部关卡双保险）
    ├── delete_draft.py               ← 撤稿（主题撞车时用，--purge-history 连带清 history 占位）
    └── distribute\                   ← ★ 多平台分发模块（GEO 主轴 · 2026-10-02）
        ├── geo_adapt.py              ← 平台适配校验：list / matrix / check / guide
        └── distill.py                ← 母稿蒸馏 + 改造任务书：extract / brief

**多平台分发模块**（详细规则见 `config/platforms.yaml` 头部）：设计主轴是 **GEO —— 每加一个
平台 = 补一个搜索/推荐入口**，不是「多发几个平台」。工作流：
`distill.py brief <平台> <母稿>` 生成任务书 → 执行会话按任务书改造 → `geo_adapt.py check <平台> …` 自检。
优先级：公众号(已打通) → 头条号 → 百家号 → 小红书 → 微博。

<qclaw_home>\
├── secure\.env_junxun / .env_lanmuda  ← 凭证
├── wechat-assets\cover_library_*      ← 封面降级库（勿删）
├── wechatlog\
│   ├── daily_YYYY-MM-DD.md            ← ★ 每天运行结果固定查看点
│   ├── junxun\{history.db, .done, wechat_v2_*.md, *.png}
│   └── lanmuda\{history.db, .done, wechat_v2_*.md, *.png}
└── _trash_YYYYMMDD\                   ← 清理暂存区（项目外，确认无碍后整体删除）
```

---

### 10.1 模块化接入（规划中）

**定位变化（2026-10-02）**：本 skill 将作为**内容生产 + GEO 优化模块**引入自研「**入海平台**」，
服务平台的多个用户 —— 从「两个号的自用工具」变为「平台组件」。分工：

| 环节 | 归属 |
|---|---|
| 内容生产（选题 / 改写 / 配图 / 建稿）· GEO 优化 · 多平台适配 | **本模块** |
| 账号管理 · 持久化登录 · 实际发布 | **入海平台** |

**当前耦合点**（平台化前需解耦；**现阶段不改** —— 等入海平台的接口形态确定再动，
否则是猜）：

| # | 耦合点 | 现状 | 解耦方向 |
|---|---|---|---|
| 1 | 账号写死 | `accounts.yaml` 固定两个号 + 本机绝对路径 | 账号配置由平台注入 |
| 2 | 品牌口径写死 | `compliance_check.py` / `geoready_check.py` 硬编码「君寻智能」「岚牧哒」 | 移入账号配置字段 |
| 3 | 账号专属规则写死 | `create_draft.py`「君寻必加二维码 / 岚牧哒不加」 | 配置化开关 |
| 4 | 词库未隔离 | 见 §6.1-C：已拆成 `keywords.yaml` + `search_terms.yaml`，但全租户共用一份 | 按租户 / 行业分片 |

**解耦原则**：本模块**不碰账号、不做登录**，只吃「内容」、吐「各平台版本」——
这样与入海平台的进度完全解耦，谁先就绪都不阻塞对方。

## 11. 版本历史

| 版本 | 日期 | 要点 |
|------|------|------|
| **v2.20.0** | 2026-10-02 | **标题搜索友好度升级为硬关卡**（GEO-1/GEO-2 命中即拒建稿） |
| **v2.19.0** | 2026-10-02 | **外部搜索热词导入**（各平台词表 → search_terms.yaml + 缺口分析） |
| **v2.18.0** | 2026-10-02 | **原创标识自动巡检**（API 拿不到标记 → 抓页面判断，第五段） |
| v2.17.0 | 2026-09-30 | GEO 硬关卡：让每篇都能勾原创 |
| v2.16.0 | 2026-09-29 | 目录卫生：图片自动回收 + 封面库路径 bug 修复 |
| v2.15.0 | 2026-09-29 | GEO 第一阶段：合规硬化 + 可检索化 |
| v2.14.0 | 2026-09-29 | 新增 `originality_check.py`；正文规则新增「事实句/引语必须重构」 |
| v2.13.0 | 2026-09-29 | 定时任务 3 任务合并为 1 个；90 分钟超时机制 |
| v2.12.0 | 2026-09-28 | 解释器硬性规则；主题去重第五层（产品/公司名查库） |
| v2.11.0 | 2026-09-18 | 新增 `validate_article_html.py` / `validate_title.py` 双关卡 + create_draft 内置双保险 |
| v2.10.x | 2026-07 | 主题聚类去重；`filter_candidates.py` URL 硬过滤 |
| v2.9.0 | 2026-07-20 | `create_draft.py` 中文乱码最终修复（requests → urllib） |
| v2.8.0 | 2026-07-19 | 标题内容安全硬性规则 |
| v2.7.0 | 2026-07-17 | 排版自检硬性规则；原创保护第 7 条 |
| v2.5.1 | 2026-07-09 | `content_dedup.py`；`.in_progress` 锁修复双跑 |
| v2.3~2.4 | 2026-04 | 多账号发布系统初版；`key` 字段路由；封面尺寸 16:9 |

### v2.18.0 变更（2026-10-02）

**背景**：老大问「以后上传默认选择原创，我记得是有这个参数的」。查证结论 —— **参数确实存在，
但在 MP 后台不在 API**。

**查证过程（全部有据）**
1. 官方社区置顶答复：草稿 / 发布接口**无原创相关参数**（运营专员明确「不支持」）
2. 实测 `freepublish/batchget`：news_item 仅 12 个字段，**不含 `copyright_stat`**
3. 实测**抓文章页**可判断：`<span id="copyright_logo" ...>原创</span>` 是可靠信号
   （老文章无、新文章有，已双向验证）
4. 后台开关：**内容与互动 → 原创声明 → 「发布时自动声明原创」**

**新增**
1. ✅ **`copyright_check.py`** —— 原创标识巡检。双号拉最近 N 篇已发表文章，
   逐篇抓页面判断原创标签，输出未标清单。退出码 0 全标 / 1 有漏标 / 2 接口异常 / 3 错误。
   增量读取（命中关键字即停），带 `--account` / `--count` / `--json` / `--quiet`
2. ✅ **调度第五段** —— `copyright_check.py --count 4`，发现未标即在 daily 日志醒目列出
   （原创标识**不支持事后补标**，漏了只能删文重发，所以必须尽早发现）

**实测进展**
- **2026-09-30 起两号文章均已带原创标识**：君寻 09-30 谷子经济 + 10-02 三篇；
  岚牧哒 09-30 DIY 掌机 + 10-02 DYNA 2.1
- 09-15 及更早的历史文章未标（那时尚未开始声明）

### v2.17.0 变更（2026-09-30）

**背景**：老大要求「完善缺陷，以后文章都要可以原创」。原先 §6.3 可检索化规范只写在文档里、
调度 prompt 也无硬要求 —— 靠执行会话自觉，**要素漏做无人拦**（同类历史教训：URL 去重曾是
伪代码注释，同一源文发了 5 次）。

**新增**
1. ✅ **`geoready_check.py`** —— GEO 就绪度 / 原创可声明性硬关卡，一次校验三件事：
   - **可检索化四要素**：首段结论句（前 200 字内成句且 ≥25 字）· 独家数据段（必须
     「累计发布 N 篇」且 N 与 `history.db` 实际相符 —— **防编数据**）· 末尾 2~3 组 `Q：/A：`
     · 品牌嵌入（1~3 次，越界仅告警）
   - **与源文改写幅度**：LCS ≥ 25 字 / 单句 Dice ≥ 0.65 / 全文 Dice ≥ 0.30 → **BLOCK**
   - **站内正文撞车**：64 维 MinHash 指纹（存 `<log>\<key>\body_index.json`），
     Jaccard ≥ 0.45 → **BLOCK**（0.30 告警）
2. ✅ **`create_draft.py` 第 7 道关卡** —— 内置调 geoready_check；新增 `--source-file <源文>`
   参数（不传则跳过源文比对，只告警不拦）；**建稿成功后自动写站内正文索引**。
3. ✅ 调度 prompt 同步：第一段加「可检索化（GEO 硬要求，缺一不建稿）」四条，
   第二段注明岚牧哒用自家口径（不出现「君寻智能」）。

**修复**
4. 🔧 **`compliance_check.py` W5 误报** —— 品牌口径统计把二维码引导文案
   「扫码加入君寻粉丝群」里的「君寻」算作品牌单独使用 → 改为**先剔除二维码段落再统计**
   （三篇真稿 WARN → PASS）。

**首日实测**（2026-09-30 三篇真稿）：四要素全齐（结论句 / 258·144 篇数据段 / 各 3 组 Q&A /
品牌 2·2·1 次）；与源文全文相似度 0.142 / 0.268 / 0.011，最长连续重复 15 / 19 / 7 字
（均为专有名词、时间、公司名单等事实性串）；站内正文索引已回填 3 篇。

### v2.16.0 变更（2026-09-29）

**背景**：老大问「这个项目冗余是不是很多，感觉越来越大但有用的很少」。
实测坐实：全项目 **≈2.1 GB**，其中 PNG 中间产物 **≈1.9 GB（92%）**，
真正有用的代码+文档+日志+数据库**合计仅 ≈1.3 MB——占比 0.06%**。根因是发布流程
**只落盘、从不回收**（3 篇/天 × 5~6 张 × 2~3 MB ≈ 每天 +20~30 MB）。

**新增**
1. ✅ **`reap_images.py`** —— 图片中间产物自动回收（详见 §2.2）。
   接入调度第四段，`--days 7`，带硬编码安全红线 + `--dry-run`。

**修复**
2. 🔴 **`generate_cover.py` 封面库路径算错（Tier-3 兜底长期失效）** ——
   `Path(__file__).parent.parent.parent / "wechat-assets"` 解析出 `<root>\skills\wechat-assets`
   （**不存在**），而 `accounts.yaml` 里真源是 `<root>\wechat-assets`（96 MB，实际存在）。
   后果：腾讯 + 智谱两级生图都失败时，本该从本地封面库兜底，实际直接 `FAILED`。
   修复：`_ROOT = parents[3]` 校正层级 + `pick_fallback()` 优先取 `accounts.yaml.cover_library`。

**清理（本次一次性，只移动不删除）**
3. 719 项 / **1560 MB** 移出项目 → `H:\_wechat_trash_20260929\` 与
   `C:\Users\LMD\.qclaw\_trash_20260929\`（含 `MANIFEST.json` 回滚凭据）。
   效果：skill **452 MB → 5.0 MB**、wechatlog **686 MB → 0.9 MB**、
   workspace **970 MB → 94.9 MB**。
   **保留**：全部 `.md` 日志（342 个发布日志）、`history.db`、`.done` 锁、企业群二维码、封面库。

**踩坑记录**
4. ⚠️ **跨盘 `shutil.move` 会触发安全删除保护**（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`），
   且 copy 完成后 delete 被拦 → **原件与副本同时存在，占用翻倍**。
   对策：清理一律用**同盘 `os.rename`**，瞬间完成且不触发保护。

### v2.15.0 变更（2026-09-29）

**背景**：两个号已有「内容违规 → 删文/警告」先例，且定下 GEO 第一阶段验收标准为
「能过原创 + 不触发限流」。原关卡只覆盖「情绪对立词」，金融类与绝对化表述完全没覆盖。

**新增**
1. ✅ **`compliance_check.py`** —— 合规硬化关卡。四个维度：
   - **F1** 硬禁词（标题命中即拦）· **F2** 涉政涉外词堆叠（≥2 个拦）
   - **F3** 投资诱导 / 荐股类（拦）· **F4** 标题绝对化极限词（拦，广告法风险）
   - **W1~W5** 软告警：正文情绪词 / 正文极限词（列上下文）/ 医疗疗效宣称 /
     **金融数字缺出处**（数字周围 80 字无「据/报告/公告」→ 提示补出处）/ 品牌嵌入频率
2. ✅ **`_rules.py`** —— 内容安全词表**唯一真源**。此前禁词表被抄在三处
   （SKILL 文档 / `validate_title.py` / `create_draft.py`），改一处忘一处。现统一导入
3. ✅ **`geo_stats.py`** —— GEO 独家数据资产提炼。从两个 `history.db` 生成
   发布量 / 赛道分布 / 来源 Top / 品牌频次 / 热词，并直接产出**可引用的数据句**（`--sentences`）
4. ✅ **§6.3 可检索化规范** —— 首段结论句 / 末尾 FAQ / 标题搜索意图词 / 独家数据段 / 品牌嵌入频率

**修复**
- `create_draft.py`：中文账号名（「君寻」）会**静默跳过**二维码检查与配额判断 →
  新增 `resolve_account()` / `normalize_key()` 统一归一化；`run_preflight()` 加防御性归一化
- `create_draft.py`：篇数配额硬编码 2/1 → 改读 `accounts.yaml` 的 `articles_per_day`
- `create_draft.py`：新增**岚牧哒中文占比 ≥30% 关卡**（防「英文源未翻译即建稿」）
- `create_draft.py`：配图计数口径与 `validate_article_html.py` 不一致（set vs list）→ 统一
- `validate_article_html.py`：`<section>` 阈值文档写 ≥1、SKILL 写 ≥2、代码判 ≥1 → 统一为 **≥2**
- `validate_title.py`：`c_issues` 未定义隐患；正文只报第一个词 → 改为列全部命中
- `accounts.yaml`：君寻 `author` 由「君寻」订正为「**君寻智能**」（与线上署名一致）；
  清理已废弃的 `retry` 调度字段；岚牧哒补上 `articles_per_day: 1`
- 目录卫生：scripts 与 skill 根目录的历史临时脚本 / 图片归档至 `_archive/`

**待办**
- `freepublish/submit` 自动发布 → **暂缓**。2026-03-27 微信新规《运营规范》新增
  「**非真人自动化创作行为**」，禁止 ① AI 生成/改写/拼接/搬运内容 ② 脚本、程序托管等方式
  **批量、连续发布** ③ 传播此类教程服务。处罚含流量限制、删除、账号能力限制、封禁。
  我方两条均命中 → **发布环节保留人工**
- **原创声明无法 API 化**（2026-10-02 复核确认）
  - 官方社区置顶答复：草稿接口 `draft/add` / 发布接口 `freepublish/submit` **都没有原创相关参数**
    （请求体只有 article_type / title / author / digest / content / content_source_url /
    thumb_media_id / need_open_comment / only_fans_can_comment / 裁剪与商品字段）
  - `freepublish/batchget` 返回的 news_item **也不含 `copyright_stat`**（实测字段仅 12 个）
  - → **既不能声明、也读不到**，必须人工在 MP 后台勾选后群发才有标识
  - ⚠️ **已群发文章不支持事后补标**（官方明确）—— 想补只能删文重新群发，所以漏标必须尽早发现
- **后台有「默认声明原创」开关**（老大问的「那个参数」就是它，位置在后台不在 API）
  **MP 后台 → 内容与互动 → 原创声明 → 开启「发布时自动声明原创」**，勾选适用内容类型后，
  新建图文默认触发原创检测，不必每次手动勾。需账号已获原创功能权限（系统评估，非申请制）
- **自动巡检已上线**（v2.18.0）：`copyright_check.py` 抓已发表文章页面，判断有无
  `<span id="copyright_logo" ...>原创</span>`（实测：未标的老文章页面无此元素，已标的有 → 可靠信号）。
  已挂**调度第五段**（`--count 4`），发现未标即在 `daily` 日志醒目列出
- **实测进展**：2026-09-30 起两号文章均已带原创标识（君寻 09-30 谷子经济、10-02 三篇；
  岚牧哒 09-30 DIY 掌机、10-02 DYNA 2.1）；09-15 及更早的历史文章未标（那时还没开始勾）
- **原创声明勾选判据**（2026-09-30 补：本地实测 + 平台规则）
  - 微信原创比对本质是**在先发布比对**（记录时间，不是衡量改写幅度）→ 对「整篇照搬」最有效，
    对改写型内容，**只要站内没有更早的高度相似文章即可声明**
  - 本地可控指标（发文前自检）：与源文**全文相似度 < 30%**、**最长连续重复 < 20 字**。
    命令：`difflib.SequenceMatcher(None, 稿, 源文).ratio()`；重复块若为专有名词 /
    时间地点 / 公司名单等事实性串，属 §6.2 允许保留范围，不计入风险
  - **勾选失败无惩罚**：后台提示「无法声明原创」即放弃，不扣分；真正的处罚风险在被投诉并经
    **洗稿合议**认定（恶意把他人原创声明为自己的）
  - ⚠️ **翻译稿（岚牧哒）风险相对高**：平台规则明确「翻译外文内容要注明出处」，翻译作品
    能否声明原创存在争议 → 可试，失败即弃（**实测 09-30 与 10-02 的翻译稿均成功标上原创**）
