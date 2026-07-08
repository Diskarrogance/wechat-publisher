# wechat-publisher

> 微信公众号多账号自动发布系统 · 配置驱动版

基于腾讯混元 AI（HY-Image-V3.0）生成封面/配图，自动化完成「搜索→防重→写稿→配图→排版→创建草稿」全流程。支持多个公众号并行发布，每个账号可独立配置篇数、来源偏好。

---

## 功能特性

| 特性 | 说明 |
|------|------|
| 🔒 **防重复硬屏障** | 锁文件 + history.db 双层检测，同一天绝不发第二遍 |
| 🎨 **AI 配图** | 腾讯混元 HY-Image-V3.0 生成封面 + 正文配图，支持 IP 角色一致性 |
| 📝 **自动排版** | 预设 HTML 模板（15px 字体、蓝渐变标题、自适应配图尺寸） |
| 🌍 **多源抓取** | 按来源优先级抓取真实文章，拒绝 AI 编造内容 |
| 🔁 **编码安全** | PowerShell CP936 乱码保护，`@file` 临时文件传参 |
| 🖼️ **企业群二维码** | 支持指定账号文章底部自动追加二维码 |
| 🎯 **配图数规则** | 段落数 ÷ 2，最低 3 张，最高 5 张 |

---

## 项目结构

```
wechat-publisher/
├── SKILL.md                  ← 完整操作手册（九步流程）
├── config/
│   └── accounts.yaml         ← 账号配置（**不含密钥，需自行填写**）
├── scripts/
│   ├── create_draft.py       ← 创建微信图文草稿
│   ├── semaphore_check.py    ← 防重复硬屏障
│   ├── generate_cover.py     ← 腾讯混元封面生成
│   ├── upload_material.py    ← 上传素材（封面/永久素材）
│   ├── upload_article_image.py ← 正文配图上传
│   ├── save_history.py       ← 写入发布历史
│   └── update_history.py     ← 更新历史记录
├── assets/                   ← 资源文件
├── temp/                     ← 临时文件（gitignore）
└── .gitignore
```

---

## 快速开始

### 1. 配置账号

编辑 `config/accounts.yaml`：

```yaml
accounts:
  - name: "公众号A"
    key: "account_a"
    env_file: "/path/to/.env_account_a"
    history_db: "/path/to/account_a/history.db"
    cover_library: "/path/to/cover_library/"

  - name: "公众号B"
    key: "account_b"
    env_file: "/path/to/.env_account_b"
    history_db: "/path/to/account_b/history.db"
    cover_library: "/path/to/cover_library/"

global:
  proxy: "https://your-proxy.com/wechat-proxy/"
```

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
# 将 draft JSON 写入临时文件（防 CP936 编码问题）
$json = @{
  title = "文章标题"
  content = "<p>正文HTML</p>"
  thumb_media_id = "封面media_id"
  # ...
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
       │ semaphore_check     │ ← 锁文件检查：今天发过吗？
       └────────┬────────────┘
                ↓ 未发过
       ┌─────────────────────┐
       │ 获取 Access Token   │ ← 通过代理请求微信API
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 搜索 + 抓取文章     │ ← 按来源优先级选文
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 双层防重            │ ← history.db 7天窗口
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 生成封面(Hunyuan)   │ ← 16:9，IP角色参考图
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 上传封面(--type thumb)│
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 撰写正文HTML        │ ← SKILL.md 排版组件
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 生成配图 + 上传     │ ← 3~5张，upload_article_image.py
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ [可选] 追加群二维码  │ ← 永久素材 media_id
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 创建草稿(@file)     │ ← write JSON → create_draft.py
       └────────┬────────────┘
                ↓
       ┌─────────────────────┐
       │ 写日志              │ ← history.db + markdown 日志
       └─────────────────────┘
```

---

## 关键配置参考

### 配图规则

- 正文段落数 ÷ 2 = 配图张数（向下/向上取整均可，满足 3~5 张即可）
- **硬性约束**：最少 3 张，最多 5 张，禁止 1~2 张敷衍
- 配图宽度：`style="width:85%;max-width:500px;display:block;margin:0 auto;border-radius:8px;"`

### 腾讯混元参数

| 参数 | 值 |
|------|-----|
| 引擎 | HY-Image-V3.0 |
| 分辨率 | 1024:576 / 1536x864（16:9） |
| 并发限制 | 1 个任务 |
| 重试 | 内嵌 3 次（间隔 15s） |
| IP 参考图 | 支持 Base64 / URL |

### 编码安全（Windows 必知）

PowerShell 命令行传递中文 JSON → 自动转为 CP936 → Python 解码为乱码。解决方案：

```
❗ 禁止：python create_draft.py account_a $json_str
✅ 正确：python create_draft.py account_a "@$tmpFile"  （写 UTF-8 临时文件）
```

---

## 注意事项

1. 正文配图必须用 `media/uploadimg` 接口（通过 `upload_article_image.py`），不能用 `material/add_material`，否则微信过滤不显示
2. 封面上传必须带 `--type thumb` 参数
3. 来源去重需 7 天窗口

---

## Cron 集成

支持配置为 cron 定时任务（sessionTarget: isolated），每个账号可独立设置每日篇数和发布时间。cron prompt 统一指向 SKILL.md 获取完整流程。

---

## 致谢

- [腾讯混元大模型](https://hunyuan.tencent.com/) — AI 封面/配图生成
- [微信公众号开发文档](https://developers.weixin.qq.com/doc/offiaccount/) — API 参考
