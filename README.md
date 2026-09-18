# GitHub 热门项目雷达

一个自托管的内网看板：定时抓取 GitHub 每周热门项目、监控短时间内 Star 暴增的项目，并通过网页实时展示。

- **周热门榜**：抓取 GitHub Trending 官方榜单（可切换 今日 / 本周 / 本月）
- **星标暴涨榜**：每小时对已收录仓库做 Star 快照，计算 1 小时 / 24 小时 / 7 天 / 30 天的 Star 增量与"星/天"速度
- **新晋项目**：用 GitHub 搜索接口发现近 7/30/90 天内快速积累 Star 的新仓库
- **筛选**：按语言、时间窗、最低 Star 数、榜单排序筛选（工具栏三个 chip + 右侧时间口径，改完立即生效）
- **项目详情**：Star 增长趋势曲线、上榜记录、Topics、许可证等
- **界面**：按 Fastshot 设计语言重做的单页前端 —— 整屏视频背景 + 毛玻璃「指令条」式筛选器，桌面 / 平板 / 手机三套版式自适应
- **一键导出**：把当前列表导出为 CSV（带 BOM，Excel 直接打开不乱码）
- **零外部依赖前端**：Vue 3、背景视频、Inter 字体全部打包进镜像，**不依赖任何 CDN**，纯内网可用
- **一条命令部署**：`docker compose up -d`

---

## 1. 快速开始

### 方式 A：服务器可以访问外网（推荐）

```bash
cd 项目1
cp .env.example .env
vi .env                 # 至少填 GITHUB_TOKEN
docker compose up -d
```

浏览器打开：`http://<服务器IP>:8080`

首次启动时数据库为空，容器会自动在后台跑一次采集（约 1~3 分钟），之后每 60 分钟自动更新一次。

### 方式 B：服务器完全无外网（离线镜像）

在**一台有外网、有 Docker 的机器**上：

```bash
cd 项目1
./scripts/offline-save.sh          # 构建并导出 dist/github-radar-<arch>.tar 与部署包
```

把 `dist/github-radar-<arch>.tar` 和 `dist/deploy-bundle-<arch>.tar.gz` 拷到内网服务器，然后：

```bash
tar -xzf deploy-bundle-<arch>.tar.gz && cd bundle
cp .env.example .env && vi .env    # 填 GITHUB_TOKEN（若内网也无法访问 GitHub，见第 6 节）
docker load -i github-radar-<arch>.tar
docker compose up -d --no-build
```

或者直接用附带脚本：

```bash
./scripts/offline-load.sh /path/to/github-radar-amd64.tar
```

### 方式 C：本地开发调试（不用 Docker）

```bash
./scripts/dev.sh
# 打开 http://127.0.0.1:8000
```

---

## 2. 目录结构

```
项目1/
├── docker-compose.yml          # 一键部署编排（唯一需要关心的文件）
├── .env.example                # 所有可配置项（复制为 .env 使用）
├── backend/
│   ├── Dockerfile              # 构建上下文为项目根目录
│   ├── requirements.txt
│   └── app/
│       ├── config.py           # 环境变量配置
│       ├── db.py               # SQLite 建表与访问层
│       ├── github_client.py    # GitHub REST / GraphQL / Trending 解析
│       ├── collector.py        # 采集编排：榜单、发现、快照、增速、翻译、清理
│       ├── translate.py        # 可选翻译层（OpenAI 兼容，默认关闭）
│       ├── scheduler.py        # APScheduler 定时任务
│       ├── api.py              # HTTP API
│       └── main.py             # 应用入口 + 静态资源托管
├── frontend/                   # Vue 3 单页应用（无需构建）
│   ├── index.html
│   ├── app.js
│   ├── terms.js                # 内置中文术语词典（标签 / 许可证 / 口径提示）
│   ├── style.css
│   ├── assets/                 # 随镜像打包，无需联网
│   │   ├── bg.mp4              #   整屏背景视频（可替换，见第 5 节）
│   │   └── InterVariable.woff2 #   Inter 可变字体
│   └── vendor/vue.global.prod.js
├── scripts/
│   ├── check-token.sh          # 校验 GITHUB_TOKEN 有效性并查看剩余配额
│   ├── offline-save.sh         # 联网机器：构建 + 导出离线镜像
│   ├── offline-load.sh         # 内网机器：导入镜像 + 启动
│   └── dev.sh                  # 本地开发
├── qa/                         # 可选：前端回归冒烟测试 + 三端截图（不参与镜像构建）
└── data/                       # 运行时生成，SQLite 数据文件（自动创建）
```

---

## 3. 榜单是怎么算出来的

| 榜单 | 数据来源 | 口径 |
| --- | --- | --- |
| 周热门榜 | `https://github.com/trending?since=weekly` | GitHub 官方榜单的排名与"本周新增 Star" |
| 星标暴涨榜 | 本地 `snapshots` 表的历史快照 | `当前 Star − N 小时/天前的 Star`，并按实际间隔换算成"星/天" |
| 新晋项目 | `GET /search/repositories?q=created:>日期 stars:>N` | GitHub 搜索排序，反映新项目的绝对 Star |

**重要：星标暴涨榜需要时间积累数据**

- 部署后第 1 个小时：只有 1 小时增速
- 满 24 小时后：出现 24 小时增速
- 满 7 天 / 30 天后：出现 7 天 / 30 天增速

**冷启动兜底**：刚部署、快照还没攒够时，选「最近 7 天 / 30 天」会自动回退为 GitHub Trending 官方榜单的周期新增 Star 排名（并把 `stars_gained` 作为增量展示），页面顶部会明确标注数据来源，不会用估算值冒充真实增速。

快照点的密度由 `COLLECT_INTERVAL_MINUTES` 决定（默认 60 分钟），被跟踪的仓库数量上限由 `MAX_TRACKED_REPOS` 决定（默认 3000，按最近活跃度排序取前 N 个）。

综合热度分 `trend_score = 0.5×24h速度 + 0.3×7d速度 + 0.2×30d速度`（缺失窗口自动降权归一）。

---

## 4. 配置项

全部通过 `.env` 覆盖（不填则用括号内默认值）。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST_PORT` | `8080` | 宿主机映射端口 |
| `TZ` | `Asia/Shanghai` | 容器时区 |
| `GITHUB_TOKEN` | 空 | **强烈建议配置**。未认证 60 次/小时，认证后 5000 次/小时 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 空 | 内网需代理出网时填写 |
| `GITHUB_API_BASE` | `https://api.github.com` | 走公司 GitHub 镜像/加速时修改 |
| `GITHUB_TRENDING_BASE` | `https://github.com/trending` | Trending 页面地址 |
| `COLLECT_INTERVAL_MINUTES` | `60` | 采集间隔，最小 5 分钟 |
| `TRENDING_PERIODS` | `weekly` | 榜单周期，可填 `daily,weekly,monthly` |
| `TRENDING_LANGUAGES` | 空 | 额外抓取的语言榜单，如 `python,go` |
| `DISCOVERY_WINDOWS` | `7,30,90` | 新项目发现窗口（天） |
| `DISCOVERY_MIN_STARS` | `100` | 新项目 Star 门槛 |
| `DISCOVERY_PAGES` | `2` | 每个窗口搜索页数（100 条/页） |
| `ENRICH_LIMIT` | `25` | 每轮补齐详情（创建时间/许可证/Topics）的仓库数上限；配了 Token 后可由 GraphQL 覆盖，可设为 `0` |
| `MAX_TRACKED_REPOS` | `3000` | 每小时做快照的仓库上限 |
| `RETENTION_DAYS` | `90` | 历史数据保留天数 |
| `HOURLY_KEEP_DAYS` | `14` | 多少天内保留小时级快照，更早的降采样为每天 1 条 |
| `STALE_REPO_DAYS` | `180` | 长期未出现的仓库自动清理 |
| `RUN_ON_STARTUP` | `true` | 启动时是否开启定时采集 |
| `COLLECT_ON_EMPTY_DB` | `true` | 数据库为空时自动跑首次采集 |
| `TRANSLATE_PROVIDER` | `off` | 中文翻译开关，`off` 关闭 / `openai` 启用（OpenAI 兼容接口） |
| `TRANSLATE_BASE_URL` | 空 | 翻译接口地址，写到 `/v1` 即可 |
| `TRANSLATE_API_KEY` | 空 | 翻译接口密钥 |
| `TRANSLATE_MODEL` | 空 | 模型名，如 `deepseek-chat` / `qwen-plus` / `glm-4-flash` |
| `TRANSLATE_BATCH` | `20` | 一次请求打包多少条，越大越省 token |
| `TRANSLATE_PER_RUN` | `200` | 每轮最多翻译多少条描述 |
| `TRANSLATE_TOPICS_PER_RUN` | `200` | 每轮最多翻译多少个标签 |
| `TRANSLATE_MAX_CHARS` | `300` | 超长描述截断长度 |
| `TRANSLATE_TIMEOUT` | `90` | 单次翻译请求超时（秒） |
| `TRANSLATE_MAX_SECONDS` | `300` | 单轮翻译的时间上限（秒），到点停下、剩余留到下一轮 |

### Token 怎么配（2 分钟）

本项目**只读取公开仓库数据**，不写入、不涉及任何私有内容，所以 Token 权限越少越好。

**方式一：经典 Token（Classic，最省事，推荐）**

1. 浏览器登录 GitHub → 打开 <https://github.com/settings/tokens>
2. 点右上角 **Generate new token** → 选 **Generate new token (classic)**
   （直接链接：<https://github.com/settings/tokens/new>）
3. 填写：
   - **Note**：`github-radar`（随便起，用于识别）
   - **Expiration**：建议 `90 days`；不想定期换可选 `No expiration`（部分企业组织禁用了此项）
   - **Select scopes**：**一个都不用勾**。读取公开仓库无需任何权限，认证后配额就从 60 次/小时提升到 5000 次/小时
4. 点底部 **Generate token**，复制页面上出现的 `ghp_...` 字符串
   ⚠️ 这串 Token **只显示一次**，关掉页面就再也看不到了，务必立刻保存

**方式二：细粒度 Token（Fine-grained）**

1. 打开 <https://github.com/settings/personal-access-tokens/new>
2. Token name 填 `github-radar`，Expiration 自选
3. **Repository access** 选 **Public Repositories (read-only)**
   （不要选 Only select repositories，否则 Trending 榜上其他仓库读不到）
4. Permissions 保持默认（只读公开仓库即可），点 **Generate token**，复制 `github_pat_...`

**写入配置并生效**

```bash
vi .env                      # 修改这一行：GITHUB_TOKEN=ghp_你复制的token
./scripts/check-token.sh     # 校验有效性 + 查看剩余配额（推荐先跑一次）
docker compose up -d         # 重建容器让环境变量生效
```

**验证是否生效**

- 脚本方式：`./scripts/check-token.sh` 应输出 `✅ 认证成功，账号：xxx` 和 `✅ GraphQL 可用`
- 网页方式：刷新页面，顶部黄色的「未配置 GITHUB_TOKEN」提示消失
- 接口方式：`curl -s localhost:8080/api/overview | grep -o '"token_configured":[a-z]*'` 应返回 `true`
- 采集日志：`docker compose logs -f` 里 `未配置 GITHUB_TOKEN，跳过批量快照` 这行消失，变成 `批量快照完成: N/N 个仓库`

**注意事项**

- Token 等同于密码，不要提交到 Git。项目的 `.gitignore` 已忽略 `.env`，也请**不要**把 Token 写进 `docker-compose.yml` 提交出去。
- Token 过期后采集会降级为未认证模式（仍能抓榜单，但配额降到 60 次/小时，日志会提示配额耗尽），届时按上面步骤重新生成并替换即可。
- 如果账号属于启用了 SAML SSO 的组织，经典 Token 需要在该 Token 行点 **Configure SSO** 授权一次（仅访问公开数据时通常可忽略）。
- 公司内网若统一走代理出网，记得同时配置 `HTTP_PROXY` / `HTTPS_PROXY`，否则 Token 配好了也连不上。

---

## 5. 界面说明

### 视觉与交互

前端遵循 Fastshot 设计语言：整屏背景视频 + 毛玻璃「指令条」式筛选器。所有尺寸都由一个缩放单位推导：

```css
--u: min(0.06410256vw, 0.12400794vh);   /* 1560×1008 参考帧下恰好等于 1px */
```

因此从参考帧到 4K 屏都是整体等比放大、不会错位或裁切；窄屏另有独立版式：

| 断点 | 版式 |
| --- | --- |
| 宽屏 ≥1181px | 导航横排、标题居中、筛选器是一整条单行工具栏、卡内控件绝对定位（与设计稿逐像素对齐） |
| 平板 600–1180px | 筛选器收成一行：语言 / Star / 排序在左，时间口径与刷新键靠右 |
| 手机 ≤599px | 标题左对齐、筛选器纵向堆叠、导航收进右上角手风琴菜单 |

首屏高度是**自适应内容**的（不是撑满 100vh）：搜索栏与「数据来源」页脚各自移走之后，首屏只剩标题加一条工具栏，继续撑满就会在工具栏和看板之间堆出一大片空白。纵向节奏由三个变量控制：

```css
--hero-top-gap: 72;   /* 导航到标题 */
--hero-gap: 34;       /* 标题到工具栏 */
--hero-foot-gap: 60;  /* 工具栏到看板（首屏底部留白） */
```

三个断点下依次收紧到 50/26/44、20/20/34，首屏都能直接看到第一张卡片。

### 筛选器怎么用

页面中间的「指令条」就是筛选器，从左到右（原先的搜索栏已去掉，整条只剩一行）：

| 控件 | 作用 |
| --- | --- |
| 语言 | 全部语言 / 指定语言（周榜按**仓库自身语言**筛选） |
| 最低 Star | 过滤小项目；刚部署时星标暴涨榜建议先选「不限 Star」 |
| 第三个 chip | **随榜单变化**：周热门榜 = 排序方式（**本周期新增**（默认）/ 榜单排名 / Star 总数）；星标暴涨榜 = 榜单模式（按新增 Star / 新晋项目）；项目库 = 收录时间范围 |
| 时间口径（右侧） | **随榜单变化**：周热门榜 = 今日 / 本周 / 本月；星标暴涨榜 = 1 小时 / 24 小时 / 7 天 / 30 天；项目库 = 排序字段 |
| 回形针 | 把当前列表导出为 CSV |
| 橙色 ↻ | 刷新列表（按当前筛选条件重新拉取），加载中图标会持续旋转 |

### 中文解释

界面上凡是能中文化的都中文化了，分三层（前两层零成本、开箱即用）：

| 层次 | 覆盖内容 | 是否需要配置 |
| --- | --- | --- |
| 界面文案 | 榜单名、字段名、按钮、提示语、错误信息、口径说明（鼠标悬停筛选器可见） | 不需要 |
| 内置术语词典 | 412 个常见标签（`machine-learning` → 机器学习）、26 种许可证（`MIT` → MIT 许可证 + 一句话「能不能商用」） | 不需要 |
| 描述与长尾标签翻译 | 项目描述译成中文、词典外的标签由模型补翻 | **需要**，见下 |

**开启描述翻译**（`.env` 里填四项，重启即生效）：

```bash
TRANSLATE_PROVIDER=openai
TRANSLATE_BASE_URL=https://api.deepseek.com/v1     # 通义/智谱/公司内网网关同理
TRANSLATE_API_KEY=sk-xxxxxx
TRANSLATE_MODEL=deepseek-chat
```

- 任何 OpenAI 兼容接口都能用：DeepSeek、通义千问（`https://dashscope.aliyuncs.com/compatible-mode/v1`）、智谱 GLM、公司内网大模型网关。
- **成本**：以本项目实测的 450 条描述 + 1326 个标签为例，一次性回填约 **3 万 token（0.1~0.3 元）**，总共只发出 **54 次请求**；之后每小时只翻新增仓库，每月大约几元到几十元。
- 省钱靠三件事：**同一段描述只翻一次**（按内容哈希缓存，原文变了才重翻）、**标签全站去重后只翻一次**、**一次请求打包 20 条**（提示词成本摊薄）。
- **翻译独立于采集**：采集只负责抓数据（约 2 分钟），结束后另起一轮翻译。所以再慢的翻译接口也不会让采集变慢，页面能立刻看到已经译好的部分；翻不完的自动留到下一轮，也可以随时 `curl -X POST http://<IP>:8080/api/translate` 单独催一次。
- **慢网关自适应**：整批超时会自动拆成两半重试（实测 20 条超时 → 拆 10+10，其中一个再超时 → 拆 5+5，**20 条全部救回**），而不是整批丢弃；连续 3 批失败会熔断本轮，不会在坏接口上空转几十分钟。
- 翻译失败（断网、欠费、超时）只会记日志并跳过，**不影响采集**，页面自动回落到英文原文；下一轮会自动重试。
- 日志里会给出调参建议，例如 `翻译网关较慢：20 条用了 160 秒（约 8.0 秒/条）。建议把 TRANSLATE_BATCH 调小到 3，或把 TRANSLATE_TIMEOUT 调到 126`。
- 关掉（`TRANSLATE_PROVIDER=off`）时**不会发出任何外部请求**，页面显示英文原文，悬停可看。
- 译文与原文同时保留：卡片描述默认显示中文，鼠标悬停可查看英文原文；标签悬停显示「中文（原文）」。
- 想控制成本可以调小 `TRANSLATE_PER_RUN` / `TRANSLATE_TOPICS_PER_RUN`，翻完即止。

**网关很慢怎么办？** 有些内部网关（实测约 8 秒/条）需要调参，两个方向二选一：

```bash
# 方向一：批量调小（推荐，等待时间可预期）
TRANSLATE_BATCH=5
TRANSLATE_TIMEOUT=60

# 方向二：保持批量，超时放宽
TRANSLATE_BATCH=20
TRANSLATE_TIMEOUT=180
```

页面右上角的状态标识会显示进度，如「描述 中文 200/450」，鼠标悬停能看到还剩多少条排队。

> 内网服务器**完全无法访问外网**时，翻译接口也不可达，此时前两层仍然完整生效；若必须离线翻译，可把 `TRANSLATE_BASE_URL` 指向内网自建的 OpenAI 兼容网关。

### 换成自己的背景视频 / 字体

背景视频和字体都在 `frontend/assets/`，不依赖网络：

```bash
# 换成公司自己的视频：建议 mp4 / H.264，1080p 以内、10MB 以下
cp 你的视频.mp4 frontend/assets/bg.mp4
docker compose up -d --build
```

- 视频必须是**无声**的（`muted`），否则浏览器会拦截自动播放。
- 视频太亮或太花会影响文字可读性，可调 `frontend/style.css` 中 `.stage-scrim` 的遮罩透明度。
- 想彻底关掉视频：删掉 `frontend/index.html` 里的 `<video class="stage-video">` 一行，页面会退化成深色渐变背景。
- 换字体：替换 `frontend/assets/InterVariable.woff2`，同时改 `frontend/style.css` 顶部的 `@font-face` 与 `--font-text`。

---

## 6. API 一览

服务启动后可访问 `http://<服务器IP>:8080/api/docs` 查看交互式文档。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/overview` | 总览：收录数、上次采集状态、限流余量、配置快照 |
| GET | `/api/trending?period=weekly&language=&sort=rank&min_stars=0&limit=50` | 周热门榜 |
| GET | `/api/surging?window=24h&mode=velocity&language=&min_stars=0&min_gain=1` | 星标暴涨榜 |
| GET | `/api/repos?q=&language=&sort=stars&min_stars=0&max_age_days=0&limit=30&offset=0` | 项目库列表/排序（`q` 关键词参数保留，界面已无搜索框，可直接调接口） |
| GET | `/api/repos/{owner}/{name}` | 单个仓库详情 + Star 趋势序列 |
| GET | `/api/languages` | 语言分布（用于筛选下拉） |
| POST | `/api/translate` | 只跑翻译、不重新采集（配好翻译后补存量描述用） |
| GET | `/api/terms` | 中文术语表 + 翻译进度（`translated` / `pending` / `translating`） |
| GET | `/api/runs` | 最近采集记录 |
| POST | `/api/collect` | 手动触发一次采集（202 立即返回） |
| GET | `/api/health` | 健康检查（供负载均衡/容器探针） |

`surging` 的 `window` 可选 `1h|24h|7d|30d`，`mode` 可选 `velocity`（按新增 Star）或 `new`（新晋项目按增速）。

`trending` 的 `sort` 默认 `stars_gained`（本周期新增），可选 `rank`（GitHub 官方榜序）/ `stars`（Star 总数）。

> 官方榜序与「本周期新增」并不一致：GitHub 的 trending 排序掺了增速与新鲜度权重，所以涨粉多的不一定排前面（实测本周榜 231 个两两比较里有 94 对倒挂，例如 `fmtlib/fmt` 只涨 920 却排在涨 12,356 的 `mattpocock/skills` 前面）。默认按本周期新增排，即严格降序；同分时按官方榜序兜底。

其余：`repos` 的 `sort` 可选 `stars` / `gain_24h` / `gain_7d` / `trend_score` / `created_at` / `pushed_at`。

> `trend_entries.language` 存的是「抓取该榜单时所用的语言」（通用榜单为空串），与仓库自身语言并不相同。因此按 `language` 筛选周榜时会同时匹配 `repos.language`，否则通用周榜按任何语言筛选都会返回 0 条。

> 所有返回仓库对象的接口（`/api/trending`、`/api/surging`、`/api/repos`、`/api/repos/{owner}/{name}`）都会额外带上 `description_zh` 字段：开启了翻译且已译好时为中文，否则为空字符串，此时看 `description` 的英文原文即可。

---

## 7. 运维

```bash
docker compose ps                      # 查看状态
docker compose logs -f --tail=200      # 实时日志
docker compose restart                 # 重启
docker compose down                    # 停止（数据保留在 ./data）
docker compose up -d --build           # 修改代码后重建
```

**数据备份**：整个数据就是一个文件，直接复制即可。

```bash
docker compose stop
cp data/github_trending.db ~/backup-$(date +%F).db
docker compose start
```

**换端口**：改 `.env` 里的 `HOST_PORT`，重新 `docker compose up -d`。

**手动补数据**：页面右上角「立即采集」，或 `curl -X POST http://<IP>:8080/api/collect`。

---

## 8. 常见问题

**Q：页面能打开，但周热门榜是空的？**
还没有采集完。看右上角状态与 `docker compose logs -f`，确认容器能访问 `github.com`。也可点「立即采集」。

**Q：日志出现 `GitHub REST 配额耗尽`？**
没配 `GITHUB_TOKEN`，或配额被其它程序占用。配好 Token 后重建容器；也可以把 `COLLECT_INTERVAL_MINUTES` 调大（如 180）。

**Q：走公司代理后仍然超时？**
`.env` 中需要同时配置 `HTTP_PROXY` 与 `HTTPS_PROXY`，并把内网网段加入 `NO_PROXY`。改完执行 `docker compose up -d` 重建容器（环境变量变更需要重建）。

**Q：内网完全无法访问 GitHub 怎么办？**
两种做法：
1. 在能上网的机器上跑同一镜像，把 `./data/github_trending.db` 拷到内网服务器的 `./data/` 目录（只读看板模式）；
2. 把 `GITHUB_API_BASE` / `GITHUB_TRENDING_BASE` 指向公司内部的 GitHub 代理或镜像服务。

**Q：星标暴涨榜一直没有数据？**
它依赖历史快照。至少等 1 小时（一个采集周期）才会出现 1 小时增速；`min_stars` 过高也会过滤掉库存不足的小项目，可先调到 0。

**Q：想换掉首页背景视频，或者干脆关掉？**
背景视频是 `frontend/assets/bg.mp4`，替换后 `docker compose up -d --build` 即可（详见第 5 节）。视频必须无声，否则浏览器不允许自动播放；想彻底关闭就删掉 `frontend/index.html` 里的 `<video class="stage-video">`。

**Q：手机上排版和电脑不一样？**
前端有三套断点版式（见第 5 节）：≤599px 时导航会收进右上角菜单、筛选器纵向堆叠，这是预期行为，不是样式错乱。

**Q：周热门榜按语言筛选后没有结果？**
周榜只有 GitHub 官方当期的几十条，某些语言（如 Rust）确实可能一条都没有；列表为空时下拉里仍有该语言，说明筛选生效了。想要更全的语言覆盖，可用「项目库」视图或调大 `DISCOVERY_*` 配置。

**Q：项目描述还是英文，看着费劲？**
配好第 5 节的 `TRANSLATE_*` 四项并重建容器，下一轮采集就会把描述与标签翻成中文。没配也不至于全是英文：界面文案、412 个常见标签、许可证说明都已内置中文。注意翻译在**采集时**进行，配好后点一次「立即采集」，或等下一个采集周期。

**Q：翻译会不会很烧钱 / 很慢？**
不会。本项目实测 450 条描述 + 1326 个标签，一次性回填约 3 万 token（0.1~0.3 元）、54 次请求；之后每小时只翻新增的十几到几十个仓库。慢也不影响页面：翻译是采集的**最后一步**，失败或超时只记日志，页面照常显示英文原文。

**Q：用哪个模型做翻译合适？**
便宜的对话模型足够（`deepseek-chat`、`qwen-plus`、`glm-4-flash` 等），中英互译是大模型最扎实的能力，不需要推理型模型。想再省可以把 `TRANSLATE_BATCH` 调到 30~40，或把 `TRANSLATE_PER_RUN` 调小让翻译分几轮慢慢补齐。

**Q：翻译结果是错的 / 很生硬怎么办？**
译文只做展示、不改动原始数据，`repos.description` 里始终保留英文原文（悬停即可看到）。想修正个别仓库，可直接改数据库：`UPDATE desc_translations SET text='正确译文' WHERE full_name='owner/name';`

**Q：数据量会不会撑爆磁盘？**
默认策略下（3000 仓库 / 每小时 / 90 天）数据库约几百 MB。14 天以前的小时级快照会自动降采样成每天 1 条，`RETENTION_DAYS` 之外的数据会被删除。

**Q：「项目库」里搜不到某个知名仓库？**
项目库只包含**已收录**的仓库（Trending 榜 + 新项目发现 + 历史快照跟踪过的），不是全量 GitHub 搜索。想扩大覆盖面可以调大 `DISCOVERY_PAGES`、`DISCOVERY_WINDOWS`、`DISCOVERY_MIN_STARS` 与 `MAX_TRACKED_REPOS`。

**Q：怎么确认采集真的在跑？**
```bash
curl -s localhost:8080/api/overview | python3 -m json.tool | head -30   # 看 last_run / next_run_at
curl -s localhost:8080/api/runs     | python3 -m json.tool              # 历史采集记录
```

---

## 9. 技术栈

- 后端：Python 3.12 + FastAPI + APScheduler + httpx + BeautifulSoup
- 存储：SQLite（WAL 模式，单文件，零运维）
- 前端：Vue 3.4（全局构建，本地内置，无 CDN、无打包步骤）+ 本地 Inter 可变字体与背景视频 + 本地术语词典
- 中文化：内置术语词典（零依赖）+ 可选翻译层（任意 OpenAI 兼容接口，批量 + 内容哈希缓存，默认关闭，失败自动降级）
- 界面：Fastshot 设计语言（单位缩放 `--u`、毛玻璃卡片、三套响应式版式、CSS 入场动画）
- 部署：Docker + docker compose，单容器（内置调度器，单 worker）
