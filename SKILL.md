# wechat-publisher v2.7.0

> 微信公众号多账号自动发布系统 · 配置驱动版

## 核心原则（强制遵守）

1. **抓不到就不发** —— 禁止 AI 生成内容降级，文章必须真实抓取
2. **禁止营销内容** —— 只要资讯，不要推广软文
3. **标题 ≤ 64 字符**，**作者名 ≤ 8 字符**
4. **君寻每天发2篇，岚牧哒每天发1篇** —— 防重复机制必须执行
5. **十年杂志编辑水平** —— 翻译改写信达雅，不是机翻
6. **编码安全** —— Python 脚本必须处理 Windows 中文乱码
7. **原创性保护（硬性）** —— 标题和正文必须与原文章来源显著不同，不得被微信识别为转载
   - 标题：不得复用原文的关键词短语组合（连续3个以上关键词重叠即危险）
   - 正文：必须改变文章结构、切入角度、段落顺序和表达方式
   - 查重自我检查：写完的标题和原文标题放一起读，如果核心意思不变只剩措辞不同→重写

---

## 账号配置

`config/accounts.yaml` 中每个账号有 `key` 字段（如 `junxun`/`lanmuda`），脚本通过 key 匹配。

```
accounts:
  - name: "君寻"
    key: "junxun"
    ...
  - name: "岚牧哒"
    key: "lanmuda"
    ...
```

---

## 君寻内容优先级（2026-05-18）

**AI玩具 > 潮玩 > AI科技资讯 > 其他**

1. 🇨🇳 **中文源优先** — chaoliunews.com（潮玩新品）、rfidworld.com.cn（AI玩具行业）、xkb.com.cn（玩具深度）
2. 📱 **公众号优质源** — 依次搜这三个号的最新文章（仅取AI玩具/潮玩相关）：
   - 南方新消费（搜潮玩/泡泡玛特/盲盒/潮玩诉讼）
   - IP大师（搜潮玩IP/IP设计/角色设计/盲盒IP）
   - 视觉文化研究（搜文创IP/潮玩文化/IP衍生）
3. 🔍 **中文搜索** — online-search 搜「AI玩具 新品」「潮玩 盲盒」「智能玩具 陪护机器人」「智萌体 潮玩」
4. 🌐 **英文源翻译** — WIRED / Ars Technica 抓 AI/机器人/科技方向，翻译改写
5. 🏢 **设计创意** — Yanko Design / ThisIsWhyImBroke 选 AI/智能/机器人相关

选择逻辑：按此顺序尝试。**君寻每天选2篇不同文章**，第一步选完后续继续选第二篇（不同来源/不同主题）。中文源有货就用中文源，不为了凑数去翻英文。

---

## 多账号工作流程

### 第〇步：防重复硬屏障 + 原创性自检（强制！所有任务的第一行代码）

**无论 daily 还是 retry，第〇步必须执行 semaphore_check！不要相信自己的记忆，一定要跑这个脚本检查！**

```powershell
python scripts/semaphore_check.py <account_key> --check
# 如果 exit code != 0（输出 ALREADY_DONE），立即 STOP，不得继续
# exit 0 = READY（可以继续）
# exit 1 = ALREADY_DONE（今天已发过，立即停止）
```

此脚本检查三层：
1. **history.db** — 看今天有没有 draft_created 记录
2. **.in_progress 锁文件** — 看今天是否有任务正在执行中（防止 daily 和 retry 并行双跑）
3. **.done 目录 marker 文件** — create_draft.py 创建草稿后自动写 marker

三层任意一个命中 → 阻塞通过。

### 第〇步-加强：写入 .in_progress 锁（v2.5.1 新增）

**semaphore_check --check 通过后，立即写入 .in_progress 锁**，防止 5 分钟后 retry cron 也启动导致双跑：

```powershell
# 先检查
python scripts/semaphore_check.py <account_key> --check
# exit 0 → 立即写锁
python scripts/semaphore_check.py <account_key> --create-in-progress

# ...执行完整流程（生图、上传、创建草稿）...
# create_draft.py 成功后会调用 --create-done，自动清理 .in_progress
```

**.in_progress 过期策略**：锁文件超过 60 分钟自动视为过期（异常退出后不永久阻塞）。

**特别注意**：
- **君寻每天2篇**：semaphore_check 只是总开关（是否≥1篇），具体篇数仍需查 history.db 判断今天够不够
- **岚牧哒每天1篇**：semaphore_check 就是最终判断，命中即跳过
- **retry 任务同样必须执行**，即使今天已经发过的概率很高，也必须先 check 再动手
- 手动测试需要跑全流程时，先执行 `--clear` 清除今天的 marker

```
# 手动清除标记（允许重新发布）
python scripts/semaphore_check.py <account_key> --clear
```

---

### 第三步：获取 Access Token

```powershell
curl.exe "$proxy/cgi-bin/token?grant_type=client_credential&appid=$APP_ID&secret=$APP_SECRET"
```

- 从 `env_file` 读取 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET`
- 代理地址从 `global.proxy` 读取

### 第四步：搜索 + 抓取文章

**君寻每天选2篇不同文章，岚牧哒选1篇。**

按 `sources` 列表顺序尝试，两篇文章选完后一起进入后续流程。

```
# 确定本次要选的篇数（君寻=2，岚牧哒=1）
target_count = 2 if account_key == "junxun" else 1
selected_articles = []
used_urls = []  # 记录本次已选的source_url，防止选重

while len(selected_articles) < target_count:
    搜索关键词：从 remaining sources[].topics 中随机选 1-2 个
    搜索站点：按 sources 列表顺序
    对每个搜索结果：
      1. 跳过黑名单域名（global.blacklist）
      2. 用 web_fetch 抓取内容

      # ⚠️ 选定文章前必做：双层防重
      # import sqlite3, datetime
      # db = 对应账号的 history.db 路径（accounts.yaml 中 history_db 字段）
      # conn = sqlite3.connect(db)
      # c = conn.cursor()
      # today = datetime.date.today()
      # seven_ago = (today - datetime.timedelta(days=7)).isoformat()
      # url = 文章来源的完整 URL（不截断）
      # 第一层：查 history.db 排除 7 天内已用过的 source_url
      # c.execute('SELECT COUNT(*) FROM history WHERE source_url = ? AND date >= ?', (url, seven_ago))
      # if c.fetchone()[0] > 0: continue
      # conn.close()
      # 第二层：本次已选中列表中排除
      # if url in used_urls: continue

      # 第三层（v2.5.1）：内容级去重
      # 用改写后的标题（不是原标题）跑 content_dedup，防不同源同新闻
      # python scripts/content_dedup.py <account_key> "<改写后的标题>"
      # exit=1 (DUPLICATE) 则跳过

      3. 内容 ≥ 500 字才算有效
      4. 有效则加入 selected_articles，标记 used_urls，
         来源切换——第二篇尽量选不同来源/不同方向的文章
    
    # 如果所有source都遍历完还没选够，有多少算多少（不下限）
    break

# 输出选中文章列表
for article in selected_articles:
    print(f"✅ 选中：[来源] {article.title}")
```

**注意**：
- 第二篇文章尽量选不同来源，避免两个公众号同天发同一家的内容
- 使用文章具体页面 URL，而不是 RSS feed URL
- 若历史数据库标记某source今日已用，重复机制会拦截，无需手动避免

### 第五步：循环处理选中的每篇文章

**君寻**有2篇文章需要循环处理，**岚牧哒**只有1篇。

对 selected_articles 列表中的每一篇文章，依次执行步骤5-9（生成素材 + 创建草稿）：

```
for idx, article in enumerate(selected_articles):
    print(f"--- 处理第 {idx+1}/{len(selected_articles)} 篇 ---")
    # → 执行第五步（翻译改写生成正文）
    # → 执行第六步（生成封面+配图）
    # → 执行第七步（上传素材）
    # → 执行第八步（追加企业群二维码，仅君寻）
    # → 执行第九步（创建草稿）
```

---

### 第五步-内：翻译改写（十年杂志编辑水平）

- 用 Agent 能力直接改写，不需要 Python 脚本
- 保留原文核心数据和事实
- 语言风格：科技媒体编辑风，不机翻
- 生成内容要求：
  - 标题：≤ 64 字符，吸引力优先

    ### 🚨 标题防转载硬性规则
    > **不遵守此规则 → 文章被标记为转载 → 流量归零**
    
    1. **换角度切入**：不要跟原文标题说同一件事。
       - ❌ 原文「潮玩传统赛道加速转型 AI等新渠道或成破局关键」
       - ❌ 你写「潮玩加速转型：AI新渠道如何撕开千亿市场突破口」←「潮玩/加速转型/AI/新渠道/破局」5个关键词重叠，被命中
       - ✅ 改为具体案例/产品切入：「泡泡玛特悄悄投了一家AI芯片公司」
    
    2. **换句式结构**：原文是「XXX加速转型 XXX成为XX关键」，你写「XXX转型：XXX如何XXX」→ 结构一样，换词没用。
       - 用提问句：`AI能让一个潮玩公仔开口说话吗？`
       - 用反常识：`千亿潮玩市场最大的对手不是同行，是AI`
       - 用具体数字：`23秒卖空1万只：潮玩靠AI赌对了什么`
    
    3. **词库替换规则**：原文标题的关键词，你最多保留1个。如果原文有「潮玩」「转型」「AI」「新渠道」「破局」，你标题里只能出现其中1个。
    
    4. **自检方法**：写完后把原文标题和你的标题放一起读——如果核心意思一样，只是换了说法，**重写**。

  - 作者署名：来自 accounts.yaml 的 author 字段（≤ 8 字符）
  - **正文防转载硬性规则**：

    ### 🚨 正文防转载硬性规则
    > **不遵守此规则 → 内容相似度过高 → 被微信自动转为转载**

    1. **改变文章结构**：原文的结构顺序不可照搬。
       - 原文：现状分析 → 案例1 → 案例2 → 趋势预测
       - 你写：具体案例开篇 → 引出趋势 → 反方观点 → 展望
       - 如果两篇文章的分段顺序都一样，就是危险信号

    2. **替换切入角度**：不要从原文的观察角度出发。
       - 原文从「行业趋势」讲→ 你从「消费者/产品」讲
       - 原文从「数据报告」讲→ 你从「企业动作」讲
       - 同一组事实，讲法可以完全不同

    3. **核心表达重写**：原文的关键论点、判断句、总结句不能原意复述。
       - 原文说「AI技术正在改变潮玩行业的销售模式」
       - 你不能写「AI技术正在改变潮玩行业的销售方式」，这是同义复述
       - ✅ 写具体行动：哪些AI工具在改变，怎么变的，结果如何

    4. **每段自检**：如果一段话的核心信息去掉修饰词后跟原文差不多 → 整段重写或删掉。

  - 正文：每 2 段落必须插 1 张配图，最长3行的段落跳过，总配图数按段落/2计算，不低于3张、不超过5张
    - 例：6段落→3张，8段落→4张，10段落以上→5张
    - 绝对禁止只配1~2张就敷衍了事

  ### 🚨 排版格式化硬性规则
  > **不遵守此规则 → 文章纯段落堆砌无排版 → 读者体验归零**

  1. **必须使用 `<section>` 节标题组件**：正文顶部+每个章节必须有「蓝渐变圆标标题」或「左侧竖线标题」组件（来自下方「排版规范」模板），**禁止全篇只有 `<p>` 段落**
  2. **至少 2 个节标题**：一篇正常文章至少 2~3 个分节（引言不算），用 `01/02/03` 圆标依次编号
  3. **配图必须用 `<img src="...">` 标签**：`{IMG1}` 占位符必须替换为 `upload_article_image.py` 返回的 URL，写上完整 `<img>` 标签
  4. **君寻必须追加企业群二维码**：第八步的二维码 HTML 块必须附加在正文末尾
  5. **排版自检（在创建草稿之前执行）**：
     | 检查项 | 通过条件 |
     |--------|--------|
     | `<section>` 标签数 | ≥ 2 |
     | `<h2>` 标签数 | ≥ 2 |
     | `<img>` 标签数 | ≥ 配图数（3~5） |
     | [君寻] 二维码 HTML | 正文末尾有 `粉丝群` |
  自检未通过 → **禁止创建草稿**，回到生成内容步骤重新排版

  - 配图描述：每张图生成一句简短 caption

### 排版规范（正文 HTML 标准模板）

按以下模板生成正文 HTML。所有 section 组件只用 inline style，不依赖外部编辑器。

#### 组件：分节标题（背景条 + 蓝渐变数字圆标，参考 135 编辑器模板 #167085）

```html
<section style="margin: 18px auto;background: linear-gradient(to right, #e8f0fe, #f5f9ff);border-radius: 6px;padding: 8px 14px;box-sizing: border-box;text-align: justify;">
  <section style="display: flex;justify-content: center;align-items: center;">
    <!-- ▎左侧：标题文字（居中） -->
    <section style="flex: 1;text-align: center;">
      <h2 style="font-size: 17px;color: #1a73e8;font-weight: bold;margin: 0;padding: 0 10px 0 0;line-height: 1.5;">
        <span style="color: #1a73e8;font-size: 17px;font-weight: bold;">小标题文字</span>
      </h2>
    </section>
    <!-- ▎右侧：蓝渐变数字圆标 -->
    <section style="flex-shrink: 0;box-sizing: border-box;">
      <section style="font-size: 14px;font-weight: bold;color: #ffffff;text-align: center;background: linear-gradient(135deg, #1a73e8, #4a9eff);width: 32px;height: 32px;border-radius: 50%;display: flex;justify-content: center;align-items: center;">
        <strong><span>01</span></strong>
      </section>
    </section>
  </section>
</section>

<!-- 标题后空一行 -->
<p style="margin: 0 8px;font-size: 17px;line-height: 1.75em;">
  <span style="font-size: 14px;"><span><br></span></span>
</p>
```

#### 组件：无数字圆标的节标题（左侧竖线版，如"写在最后"纯文字结尾段）

```html
<section style="margin: 18px auto;background: linear-gradient(to right, #e8f0fe, #f5f9ff);border-radius: 6px;padding: 10px 14px;box-sizing: border-box;text-align: justify;">
  <section style="display: flex;justify-content: flex-start;align-items: center;">
    <!-- ▎左侧：竖向色条 -->
    <section style="flex-shrink: 0;width: 4px;height: 22px;border-radius: 25px;background: linear-gradient(to bottom, #1a73e8, #4a9eff);margin-right: 10px;"></section>
    <!-- ▎标题文字 -->
    <h2 style="font-size: 17px;color: #1a73e8;font-weight: bold;margin: 0;padding: 0;line-height: 1.5;">
      <span style="color: #1a73e8;font-size: 17px;font-weight: bold;">写在最后</span>
    </h2>
  </section>
</section>
```

#### 组件：正文段落

```html
<p style="text-align: justify;font-size: 15px;line-height: 1.75em;letter-spacing: 0.5px;margin: 0 8px 12px;text-indent: 2em;">
  <span style="font-size: 15px;letter-spacing: 0.5px;">正文内容……</span>
</p>
```

#### 组件：强调（品牌名 / 核心关键词）

```html
<span style="font-weight: bold;color: #1a73e8;">品牌名</span>
```

#### 组件：数据高亮

```html
<strong>关键数据</strong>
```

#### 组件：配图 + 图注

```html
<p style="text-align: center;margin: 10px auto;">
  <img src="{配图URL}" style="width: 85%;height: auto;display: block;margin: 0 auto;border-radius: 8px;" alt="配图描述">
</p>
<p style="text-align: center;font-size: 13px;color: #888;margin-top: -5px;">
  <span>▲ 图注说明 | 来源：XXX</span>
</p>
```

#### 组件：分割线

```html
<hr style="border-style: solid;border-width: 1px 0 0;border-color: rgba(0,0,0,0.08);margin: 20px 0;">
```

#### 组件：引用块

```html
<blockquote style="border-left: 3px solid #1a73e8;padding: 8px 16px;margin: 16px 8px;background: #f5f7fa;border-radius: 4px;">
  <span style="font-size: 14px;color: #555;">引用内容……</span>
</blockquote>
```

**排版规则摘要**：
- 正文：15px / 1.75em 行高 / letter-spacing 0.5px / 段间距 12px / 首行缩进 2em
- 分节标题：**嵌套 section 组件**，浅蓝渐变背景条（`#e8f0fe → #f5f9ff` / 圆角 6px / padding 8px 14px）+ 左侧标题居中（17px / #1a73e8 / 加粗）+ 右侧蓝渐变数字圆标（32×32px / `linear-gradient(135deg, #1a73e8, #4a9eff)` / border-radius 50% / 白字 14px 加粗）
- 无数字的节标题：同背景条，左侧改用竖向渐变色条（4px 宽 / 22px 高 / 圆角 25px）+ 标题
- 强调：品牌名蓝色加粗，数据直接加粗不换色
- 配图：width 85% 不铺满，圆角 8px，下方图注用 13px 灰色 #888
- 分割线：极浅灰 0.08 透明度
- 引用块：左侧蓝色竖线 + #f5f7fa 浅灰背景

**禁止添加的广告类内容**：
- 活动报名 / 展会推广（"点击报名，免费领取"）
- 平台导流口号（"做XX，就上XX"）
- 产品推广链接 / 带货二维码
- 下载引导（"扫码下载""点击链接下载"）
- 软文营销话术（"别再死磕XX""XX迎来机遇""限时XX"等）
- 商品卡片 / 带货插件
- 底部推广 Banner 或活动图（如末尾的事件报名图）

**尺寸**：
- 封面（cover）：16:9 = **1536x864**（微信图文封面最佳）
- 配图（img1~5）：16:9 = **1024x576**（正文配图）

**调用脚本**：

```powershell
# 封面（1536x864，自动读取配置决定是否传参考图）
python scripts/generate_cover.py junxun cover "prompt带早八主角" cover.png
# 配图（1024x576）
python scripts/generate_cover.py junxun img1 "prompt" img1.png
# 临时换角色（仅本次生效）
python scripts/generate_cover.py junxun cover "prompt" cover.png --character 森森
```

**降级链路**（脚本自动执行）：
1. 🥇 **腾讯混元 HY-Image-V3.0**（首发，支持传早八参考图）
2. 🥈 智谱 CogView-4（降级，纯文本到图，无参考图）
3. 🥉 本地封面库（兜底）

## ⚙️ IP角色参考图配置

在 `accounts.yaml` 中通过 `ip_character` 字段控制——**封面和文章配图独立配置**：

```yaml
ip_character:
  cover:                                   # 封面参考图
    character_dir: "F:/文章资料/IP形象图/早八.png"  # 图片路径，空则不传
  article:                                 # 文章配图参考图（独立控制）
    character_dir: "F:/文章资料/IP形象图/早八.png"
```

**逻辑**：
- `character_dir` 是**完整的图片文件路径**。有路径+文件存在→传参考图。空路径或文件不存在→纯文本生图。
- 封面和配图**可以不同角色**（如封面用早八配图用森森）：各自指定 `character_dir` 路径即可。
- 所有公众号都必须配置 `ip_character`（路径设为空字符串就是不启用）。

**临时覆盖**：
```powershell
# 用配置默认的路径
python scripts/generate_cover.py junxun cover "prompt" output.png

# 临时换参考图（不影响配置）
python scripts/generate_cover.py junxun cover "prompt" output.png --ref-path "F:/文章资料/IP形象图/森森.png"
# 当篇配图换参考图
python scripts/generate_cover.py junxun img1 "prompt" img1.png --ref-path "F:/文章资料/IP形象图/淼淼喵.png"
```

---

**君寻配图提示词模板（prompt框架）**：

采用 **三段式 + 标准化风格词库** 结构：

```
# ① 主角：参考图的卡通形象 + 服装 + 动作（参考图由混元images参数传入原始素材文件）
# ⚠️ 封面图必须确保IP角色是唯一/核心主角，占据画面视觉中心
参考图的卡通形象，穿着[服装描述]，在做[具体动作/事情]。

# ② 场景氛围：场景 + 构图 + 氛围
[场景描述，如：深夜办公室，窗外城市霓虹，桌面上……]

# ③ 标准化风格词库（固定套餐，每张图都用这套）
3D渲染，超现实主义，皮克斯风格，卡通，可爱，
丁达尔效应，伦勃朗光色影调色，景深，层次感，
顶级高清，顶级品质，电影级质感，8K高清画质。
```

**核心规则（封面必须遵守）**：
- 封面图必须以IP角色为**视觉中心**，不能是场景中不起眼的小人
- prompt 第①段必须是「参考图的卡通形象」开头的角色描述
- 封面角色的服装/动作/表情描述越具体越好
- 配图可以角色偏小、偏侧面，但封面必须是正面/近景/主角位

**示例（早八为主角，混元传参考图）**：
```
参考图的卡通形象，穿着连帽卫衣和运动裤，坐在堆满代码屏幕的办公桌前，
一手拿咖啡一手敲键盘，屏幕泛着蓝光打在脸上，桌面堆着能量饮料罐。
深夜办公室氛围，窗外城市霓虹。
3D渲染，超现实主义，皮克斯风格，卡通，可爱，
丁达尔效应，伦勃朗光色影调色，景深，层次感，
顶级高清，顶级品质，电影级质感，8K高清画质。
```

**说明**：
- 三段式骨架不变：`[主角+场景] → [视觉元素] → [风格光影]`
- 混元 `images` 参数传入角色素材文件（路径取自 `accounts.yaml` 的 `ip_character` 配置），prompt中不写角色外貌，用「参考图的卡通形象」引导
- 风格词库固定，整篇文章所有配图风格统一
- 同一篇文章的封面和配图共用核心风格词，保持视觉一致性
- use_reference=false 的账号（如岚牧哒），省略「参考图的卡通形象」引导词，直接描述画面

### 第七步：上传素材

```powershell
# 上传封面（永久素材，必须用 --type thumb！）
python scripts/upload_material.py junxun cover.png --permanent --type thumb
# 返回 media_id（无 URL），用作 thumb_media_id

# 上传配图（图文正文内嵌图片，必须用 upload_article_image.py！）
python scripts/upload_article_image.py junxun img1.png img2.png img3.png
```

**⚠️ 关键区别（长期 bug 根因）**：
- `upload_material.py --permanent`：上传到**素材库**，返回 media_id + URL，但此 URL **不能**放在文章正文里——微信会过滤外部图片链接，正文配图不显示
- `upload_article_image.py`（新）：调用 **`media/uploadimg`** 接口，专门用于文章正文内嵌图片，返回带 `?from=appmsg` 的 URL，**正文里正常显示**

**参数**：
- `--type thumb`：封面缩略图专用，调用 `add_material` + `type=thumb`，仅返回 `media_id`
- 🔥 **封面务必加 `--type thumb`**，否则微信自动缩略图转换会生成全黑图片
- 封面 `media_id` 直接传给草稿接口的 `thumb_media_id` 字段
- 配图用 `upload_article_image.py`，返回的 URL 直接插正文 `<img src="...">`

### 第八步：追加企业群二维码（仅君寻）

每篇**君寻**文章末尾必须添加企业微信群二维码，居中放置。

```html
<!-- 追加到正文 content 末尾 -->
<p style="text-align:center;margin:30px auto 10px;">
  <img src="http://mmecoa.qpic.cn/sz_mmecoa_jpg/UobsGRjtYicVG1axkc3e3MLf1dtKCBfWjurXQfFWk8DthtyI7bb5dzEP27gUSWtic4CS14sPqVibibhGW97XztYM0ot9tHSq8dplEl364PlBeiaU/0?wx_fmt=jpeg" 
       style="width:50%;height:auto;display:block;margin:0 auto;border-radius:8px;">
</p>
<p style="text-align:center;font-size:14px;color:#888888;margin-top:5px;">
  <span>扫码加入君寻粉丝群，获取更多AI前沿资讯</span>
</p>
```

**注意**：
- 仅君寻账号需加，岚牧哒不加此二维码
- 封面media_id入库后可复用，但二维码URL不变
- 本地文件：`<your-local-path>/君寻企业微信群二维码.jpg`
- 微信永久素材 media_id：`<!-- 请联系项目维护者获取 -->`

### 第九步：创建草稿

> 🚨 **排版自检**：在提交草稿之前，最后检查一遍正文 HTML：
> - `<section>` 标签数 ≥ 2（否则纯段落堆叠，无排版效果）
> - `<h2>` 标签数 ≥ 2（没有节标题等于没有文章结构）
> - `<img>` 标签数 ≥ 3（配图数硬性下限）
> - 君寻：正文末尾包含 `粉丝群` 文本（企业群二维码已附加）
> 
> **不通过 → 不创建草稿 → 回到第五步重新排**

```powershell
# 🔥 必须写临时文件传参！不要直接传 json 字符串到命令行，
# PowerShell 管道会用 CP936 编码解码中文，标题中的汉字会变问号。
$draft_json = @{
  title = "文章标题"
  author = "君寻"
  content = "<p>正文HTML...</p>"
  digest = "摘要"
  thumb_media_id = "封面media_id"
  need_open_comment = 1
  only_fans_can_comment = 0
  content_source_url = "文章来源原始URL"
} | ConvertTo-Json -Depth 10

$tmpFile = "$env:TEMP\draft_$(Get-Random).json"
$draft_json | Out-File -FilePath $tmpFile -Encoding utf8
python scripts/create_draft.py junxun "@$tmpFile"
Remove-Item $tmpFile -Force
```

**注意**：`json=` 参数禁止，必须 `data=` + `json.dumps(..., ensure_ascii=False).encode('utf-8')`

**必填参数（通过 draft_json 传入）**：
| 字段 | 默认值 | 说明 |
|------|--------|------|
| `need_open_comment` | `1` | ⚠️ 必须设为1，开启评论区 |
| `only_fans_can_comment` | `0` | 仅粉丝可评：1=仅粉丝，0=所有人 |
| `content_source_url` | `""` | ⚠️ 必须填写文章来源原始URL，不能留空 |

示例传参：
```json
{"title":"...","thumb_media_id":"...","need_open_comment":1,"only_fans_can_comment":0,"content_source_url":"https://example.com/original-article"}
```

### 第十步：记日志

日志文件：`$log_dir/wechat_v2_YYYY-MM-DD.md`

---

## 文件结构

```
C:\Users\LMD\.qclaw\
├── skills\wechat-publisher\
│   ├── SKILL.md           ← 本文件
│   ├── config\accounts.yaml
│   └── scripts\
│       ├── upload_material.py   ← 上传图片（--permanent 永久素材 / --type image）
│       ├── create_draft.py      ← 创建草稿（自动 token 重试）
│       └── generate_cover.py    ← 生成封面（16:9，双链路）
    ├── content_dedup.py      ← 内容级去重（4-gram Dice）
├── secure\
│   ├── .env_junxun             ← 君寻凭证
│   └── .env_lanmuda            ← 岚牧哒凭证
├── wechatlog\
│   ├── junxun\history.db
│   └── lanmuda\history.db
└── wechat-assets\
    ├── cover_library_junxun\
    └── cover_library_lanmuda\
```

---

## Cron 任务调用方式

```
--account junxun
--account lanmuda
```

脚本会自动根据 `key` 字段匹配账号。

---

## 编码规范（强制）

Python 脚本开头必须有：

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
```

`requests.post` 禁止用 `json=` 参数：

```python
import json, requests
payload = {"key": "value"}
headers = {"Content-Type": "application/json; charset=utf-8"}
data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
r = requests.post(url, data=data, headers=headers)
```

---

## v2.5.1 更新（2026-07-09）

### 新增
1. ✅ `content_dedup.py` — 内容级去重脚本，基于 4-gram Dice 系数
2. ✅ 选文阶段增加内容级去重（第三层防重），防止不同源不同URL写同一件事

### 修复
3. ✅ `.in_progress` 锁机制修复 daily + retry cron 双跑 race condition
4. ✅ semaphore_check 三层屏障：history.db → .in_progress → .done

---

## v2.4.0 更新（2026-04-24）

### 已修复
1. ✅ env key 名统一：`WECHAT_APP_ID`/`WECHAT_APP_SECRET`
2. ✅ upload_material.py 支持 `--permanent` 永久素材（返回 URL）
4. ✅ generate_cover.py 加载 env_file 设置环境变量
5. ✅ generate_cover.py 封面尺寸 16:9（1536x864 / 1024x576）
6. ✅ accounts.yaml 加 `key` 字段（junxun/lanmuda）
7. ✅ gen_tencent fallback 修复（TokenHub 异步流程）
8. ✅ cover_library 迁移到 `wechat-assets/` 目录
9. ✅ create_draft.py 加 token 重试（最多 3 次）
10. ✅ .env_junxun 清理杂质
11. ✅ .env_lanmuda 补充 TENCENT_MAAS_KEY
