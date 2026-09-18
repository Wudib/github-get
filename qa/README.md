# qa —— 前端回归冒烟测试（可选，开发用）

这套脚本用 Chrome DevTools Protocol 直接量取页面真实布局坐标并跑一遍交互链路，
用来验证「窗口尺寸 / 断点 / 筛选器 / 抽屉 / 导出」没有被改坏。**不参与 Docker 构建**
（已在 `.dockerignore` 中忽略）。

## 怎么跑

```bash
# 1. 起一个启用调试端口的 Chrome
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless=new --disable-gpu --remote-debugging-port=9222 \
  --user-data-dir=/tmp/radar-chrome about:blank &

# 2. 指向要测的地址（默认容器 8080，也可指向本地 8099）
BASE=http://127.0.0.1:8080/ node qa/interact.js
```

- `qa/interact.js` —— 三个断点 + 7 条交互链路，输出各断点下 `.tools` 工具条是否保持一行、
  card 尺寸、汉堡菜单、筛选/详情/导出/导航的实际结果，并把截图写到 `qa/shot-*.png`。
- `qa/deeplink.js` —— 详情深链接（`#/repo/{owner}/{name}`）、点卡片同步地址栏、后退键关抽屉。

## 参考基准（桌面 1560×1008，即设计稿参考帧）

| 元素 | 期望值 |
| --- | --- |
| 卡片 | 708 × 143 px |
| 占位文字 left / top / 右内边距 | 27 / 33 / 24 |
| 工具条 left / top / 高 | 19 / 92 / 30 |
| chip 高 | 30 |
| 时间口径 top（相对工具条） | 15.5 |
| 回形针 top / 宽 | 10.14 / 19.79 |
| 发送键 直径 / top / 卡片内右内边距 | 35 / 2 / 14（下沿超出 chip 行 7u） |
| 标题 y | 323 |

## 中文化相关验证

| 文件 | 作用 |
| --- | --- |
| `translate_test.py` | 中译层端到端测试（44 项）：假 OpenAI 兼容接口，覆盖批量请求、缓存命中、标签去重、`/api/terms`、`description_zh`、**翻译与采集解耦**、**慢网关超时拆半**、**模型漏返回时拆半**、**坏接口熔断**、**时间上限**、**分批提交（跑一半也留成果）**。**不消耗真实 token，也不碰真实数据库**（用 `qa/zh-test.db` 副本并清空译文，跑完自动删除） |
| `zh.js` / `zh2.js` / `zh3.js` | 浏览器内验证中文化效果：术语词典、服务端术语合并、许可证中文说明、悬停原文、描述语言标识与翻译进度、采集状态文案 |
| `sort.js` | 校验周热门榜默认排序为「本周期新增」且严格降序 |
| `layout.js` / `refresh.js` / `spin.js` | 校验三端版式（卡片已收缩为单行工具栏、无搜索框、数据来源在页脚最底部）与橙色刷新按钮（点击重载 + 加载中旋转） |
| `shots.js` | 重新生成 `shot-desktop/tablet/phone/drawer.png` |

```bash
# 中译层（无需联网、无需 API Key）
./.venv/bin/python qa/translate_test.py

# 界面回归（容器需在 8080）
BASE=http://127.0.0.1:8080/ node qa/interact.js
node qa/zh2.js
node qa/shots.js
```
