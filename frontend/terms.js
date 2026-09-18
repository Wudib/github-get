/* ============================================================================
 * 术语中文化 —— 不需要任何翻译接口，纯本地映射
 * 未收录的词条原样显示（悬停仍能看到原文），不会出现空白或报错。
 * ========================================================================== */
(function () {
  'use strict';

  /* 许可证：SPDX 标识符 → 中文名 + 一句话人话解释 */
  var LICENSE = {
    'MIT': ['MIT 许可证', '最宽松：可自由使用、修改、商用，保留版权声明即可'],
    'Apache-2.0': ['Apache 2.0 许可证', '可商用，需保留声明并注明修改，附带专利授权'],
    'GPL-2.0': ['GPL 2.0 许可证', '可商用，但基于它的衍生作品必须同样开源'],
    'GPL-3.0': ['GPL 3.0 许可证', '可商用，衍生作品必须同样开源，且禁止附加限制'],
    'AGPL-3.0': ['AGPL 3.0 许可证', '最严格：即使只提供网络服务，也必须开源全部代码'],
    'LGPL-2.1': ['LGPL 2.1 许可证', '可商用，动态链接使用无约束，改动库本身需开源'],
    'LGPL-3.0': ['LGPL 3.0 许可证', '可商用，动态链接使用无约束，改动库本身需开源'],
    'MPL-2.0': ['MPL 2.0 许可证', '文件级开源：改动的文件需开源，可与闭源代码混用'],
    'BSD-2-Clause': ['BSD 2-Clause 许可证', '宽松：可自由使用、修改、商用，保留版权声明'],
    'BSD-3-Clause': ['BSD 3-Clause 许可证', '宽松：可自由商用，但不得用原作者名义背书'],
    'ISC': ['ISC 许可证', '与 MIT 等价的宽松许可证'],
    'Unlicense': ['Unlicense', '放弃全部版权，等同公共领域，随便用'],
    'CC0-1.0': ['CC0 1.0', '放弃全部版权，等同公共领域'],
    'CC-BY-4.0': ['CC BY 4.0', '可商用，需署名原作者'],
    'CC-BY-SA-4.0': ['CC BY-SA 4.0', '可商用，需署名，衍生作品需同协议共享'],
    '0BSD': ['0BSD 许可证', '宽松到不需要保留版权声明'],
    'Zlib': ['zlib 许可证', '宽松：可自由商用，保留声明，不得误标来源'],
    'BSL-1.0': ['Boost 软件许可证', '宽松：可自由商用，保留声明'],
    'PostgreSQL': ['PostgreSQL 许可证', '宽松：类似 MIT，可自由商用'],
    'Python-2.0': ['Python 2.0 许可证', '宽松：可自由商用，保留声明'],
    'Artistic-2.0': ['Artistic 2.0 许可证', '宽松：可自由商用，保留声明'],
    'Elastic-2.0': ['Elastic 许可证 2.0', '限制商用：禁止把本软件作为托管服务转售'],
    'SSPL-1.0': ['SSPL 许可证', '限制商用：把本软件作为服务提供需开源整个服务栈'],
    'WTFPL': ['WTFPL', '放弃全部限制，随便用'],
    'NOASSERTION': ['未标注', '仓库未声明许可证，商用前需联系作者确认'],
    'NO-LICENSE': ['未标注许可证', '仓库未声明许可证，默认保留全部权利，商用需授权']
  };

  /* 常见 Topics（GitHub 标签）→ 中文。只收高频词，其余原样显示 */
  var TOPIC = {
    // 人工智能 / 数据
    'ai': '人工智能', 'artificial-intelligence': '人工智能', 'machine-learning': '机器学习',
    'deep-learning': '深度学习', 'llm': '大语言模型', 'llms': '大语言模型',
    'gpt': 'GPT 模型', 'chatgpt': 'ChatGPT', 'nlp': '自然语言处理',
    'computer-vision': '计算机视觉', 'neural-network': '神经网络', 'transformer': 'Transformer 模型',
    'agent': '智能体', 'agents': '智能体', 'ai-agents': '智能体', 'rag': '检索增强生成',
    'prompt-engineering': '提示词工程', 'fine-tuning': '模型微调', 'dataset': '数据集',
    'data-science': '数据科学', 'data-analysis': '数据分析', 'visualization': '数据可视化',
    'pytorch': 'PyTorch', 'tensorflow': 'TensorFlow', 'openai': 'OpenAI', 'ollama': 'Ollama',
    'langchain': 'LangChain', 'chatbot': '聊天机器人', 'speech-recognition': '语音识别',
    'text-to-speech': '语音合成', 'image-generation': '图像生成', 'diffusion': '扩散模型',
    'vector-database': '向量数据库', 'embeddings': '向量嵌入', 'mcp': 'MCP 协议',
    // 开发工具
    'cli': '命令行工具', 'command-line': '命令行工具', 'command-line-tool': '命令行工具',
    'terminal': '终端工具', 'shell': 'Shell 脚本', 'devtools': '开发工具', 'tool': '工具',
    'tools': '工具集', 'productivity': '效率工具', 'automation': '自动化',
    'api': '接口', 'rest-api': 'REST 接口', 'graphql': 'GraphQL', 'sdk': '开发工具包',
    'framework': '框架', 'library': '代码库', 'libraries': '代码库',
    'template': '模板', 'boilerplate': '项目脚手架', 'starter': '起步模板',
    'awesome': '资源合集', 'awesome-list': '资源合集', 'tutorial': '教程', 'tutorials': '教程',
    'examples': '示例代码', 'docs': '文档', 'documentation': '文档', 'blog': '博客系统',
    'editor': '编辑器', 'ide': '集成开发环境', 'plugin': '插件', 'plugins': '插件',
    'extension': '扩展', 'browser-extension': '浏览器扩展', 'chrome-extension': 'Chrome 扩展',
    'vscode': 'VS Code', 'vscode-extension': 'VS Code 扩展', 'vim': 'Vim', 'neovim': 'Neovim',
    'regex': '正则表达式', 'compiler': '编译器', 'interpreter': '解释器', 'parser': '解析器',
    'testing': '测试', 'debugging': '调试', 'refactoring': '代码重构',
    // Web / 前端
    'web': '网页开发', 'webapp': '网页应用', 'frontend': '前端', 'backend': '后端',
    'full-stack': '全栈', 'react': 'React', 'vue': 'Vue', 'vuejs': 'Vue', 'angular': 'Angular',
    'svelte': 'Svelte', 'nextjs': 'Next.js', 'nodejs': 'Node.js', 'deno': 'Deno',
    'typescript': 'TypeScript', 'javascript': 'JavaScript', 'css': 'CSS', 'html': 'HTML',
    'tailwindcss': 'Tailwind CSS', 'ui': '界面组件', 'ux': '用户体验', 'design': '设计',
    'ui-components': '界面组件', 'component-library': '组件库', 'css-framework': 'CSS 框架',
    'static-site-generator': '静态站点生成器', 'cms': '内容管理系统', 'ecommerce': '电商',
    'websocket': 'WebSocket', 'http': 'HTTP', 'proxy': '代理工具', 'vpn': 'VPN',
    // 语言 / 运行时
    'python': 'Python', 'golang': 'Go', 'go': 'Go', 'rust': 'Rust', 'java': 'Java',
    'kotlin': 'Kotlin', 'swift': 'Swift', 'cpp': 'C++', 'c': 'C 语言', 'csharp': 'C#',
    'ruby': 'Ruby', 'php': 'PHP', 'dart': 'Dart', 'scala': 'Scala', 'elixir': 'Elixir',
    'haskell': 'Haskell', 'lua': 'Lua', 'zig': 'Zig', 'wasm': 'WebAssembly',
    'dotnet': '.NET', 'spring': 'Spring', 'django': 'Django', 'flask': 'Flask',
    'fastapi': 'FastAPI', 'rails': 'Ruby on Rails', 'laravel': 'Laravel',
    // 基础设施
    'docker': 'Docker', 'kubernetes': 'Kubernetes', 'k8s': 'Kubernetes',
    'devops': '运维自动化', 'ci-cd': '持续集成/部署', 'serverless': '无服务器',
    'cloud': '云服务', 'aws': 'AWS', 'azure': 'Azure', 'gcp': '谷歌云',
    'linux': 'Linux', 'macos': 'macOS', 'windows': 'Windows', 'unix': 'Unix',
    'database': '数据库', 'sql': 'SQL', 'nosql': '非关系型数据库', 'postgresql': 'PostgreSQL',
    'mysql': 'MySQL', 'redis': 'Redis', 'sqlite': 'SQLite', 'mongodb': 'MongoDB',
    'monitoring': '监控', 'logging': '日志', 'observability': '可观测性',
    'networking': '网络', 'storage': '存储', 'file-system': '文件系统',
    'self-hosted': '可自托管', 'homelab': '家庭实验室', 'raspberry-pi': '树莓派',
    // 安全 / 其他领域
    'security': '安全', 'cryptography': '密码学', 'authentication': '身份认证',
    'penetration-testing': '渗透测试', 'privacy': '隐私保护', 'blockchain': '区块链',
    'crypto': '加密货币', 'quantitative-finance': '量化金融', 'trading': '交易',
    'finance': '金融', 'game': '游戏', 'game-development': '游戏开发',
    'game-engine': '游戏引擎', 'mobile': '移动端', 'android': 'Android', 'ios': 'iOS',
    'react-native': 'React Native', 'flutter': 'Flutter', 'iot': '物联网',
    'robotics': '机器人', 'education': '教育', 'music': '音乐', 'video': '视频',
    'audio': '音频', 'image': '图像', 'pdf': 'PDF', 'markdown': 'Markdown',
    'json': 'JSON', 'yaml': 'YAML', 'scraping': '网页爬虫', 'crawler': '爬虫',
    'note-taking': '笔记工具', 'chat': '聊天', 'email': '邮件', 'calendar': '日历',
    'algorithm': '算法', 'algorithms': '算法', 'data-structure': '数据结构',
    'interview': '面试题', 'performance': '性能优化', 'opensource': '开源',
    'open-source': '开源', 'free': '免费', 'github': 'GitHub', 'git': 'Git',
    'opencv': 'OpenCV', 'ffmpeg': 'FFmpeg', 'pandas': 'Pandas', 'numpy': 'NumPy',
    'jupyter': 'Jupyter', 'notebook': '笔记本', 'discord': 'Discord',
    'telegram': 'Telegram', 'slack': 'Slack', 'unity': 'Unity', 'unreal-engine': '虚幻引擎',
    // 智能体 / AI 编程（按真实库内高频标签补充）
    'ai-agent': '智能体', 'ai-agents': '智能体', 'agentic-ai': '智能体 AI',
    'multi-agent': '多智能体', 'agent-skills': '智能体技能', 'agent-skill': '智能体技能',
    'ai-coding': 'AI 编程', 'coding-agent': '编程智能体', 'coding-agents': '编程智能体',
    'mcp-server': 'MCP 服务', 'mcp-servers': 'MCP 服务', 'model-context-protocol': 'MCP 协议',
    'llm-inference': '大模型推理', 'llm-app': '大模型应用', 'ai-tools': 'AI 工具',
    'ai-tool': 'AI 工具', 'skills': '技能', 'skill': '技能', 'harness': '运行框架',
    'developer-tools': '开发工具', 'developer-tool': '开发工具', 'devtool': '开发工具',
    'local-first': '本地优先', 'cross-platform': '跨平台', 'desktop-app': '桌面应用',
    'desktop': '桌面端', 'electron': 'Electron', 'tauri': 'Tauri', 'threejs': 'Three.js',
    'webgl': 'WebGL', 'animation': '动画', 'seo': '搜索引擎优化',
    'claude': 'Claude', 'claude-code': 'Claude Code', 'claude-skills': 'Claude 技能',
    'codex': 'Codex', 'cursor': 'Cursor', 'anthropic': 'Anthropic',
    'deepseek': 'DeepSeek', 'deepseek-harness': 'DeepSeek Harness',
    'dsh': 'DSH', 'dsh-plugin': 'DSH 插件', 'dsh-plugins': 'DSH 插件',
    'opencode': 'OpenCode', 'cordis': 'Cordis', 'hermes-agent': 'Hermes 智能体',
    'codex-skill': 'Codex 技能', 'diagram-as-code': '图表即代码',
    'architecture-diagram': '架构图', 'visualization-tool': '可视化工具',
    'productivity-tool': '效率工具', 'text-processing': '文本处理', 'code-generation': '代码生成',
    'static-analysis': '静态分析', 'code-review': '代码审查', 'formatter': '代码格式化',
    'cli-tool': '命令行工具', 'tui': '终端界面', 'gui': '图形界面', 'web-ui': '网页界面',
    'api-client': '接口客户端', 'http-client': 'HTTP 客户端', 'webhook': 'Webhook',
    'crawler': '爬虫', 'web-scraping': '网页抓取', 'browser-automation': '浏览器自动化',
    'pdf-generation': 'PDF 生成', 'file-converter': '文件转换', 'image-processing': '图像处理',
    'video-processing': '视频处理', 'audio-processing': '音频处理', 'streaming': '流媒体',
    'realtime': '实时', 'websockets': 'WebSocket', 'database-migration': '数据库迁移',
    'orm': '对象关系映射', 'caching': '缓存', 'message-queue': '消息队列', 'task-queue': '任务队列',
    'scheduler': '定时任务', 'cron': '定时任务', 'workflow': '工作流', 'workflow-automation': '工作流自动化',
    'microservice': '微服务', 'microservices': '微服务', 'monorepo': '单仓库多包',
    'configuration': '配置管理', 'dotfiles': '配置文件', 'backup': '备份',
    'encryption': '加密', 'oauth': 'OAuth 认证', 'jwt': 'JWT 令牌', 'sso': '单点登录',
    'vulnerability': '漏洞', 'reverse-engineering': '逆向工程', 'binary-analysis': '二进制分析',
    'webassembly': 'WebAssembly', 'embedded': '嵌入式', 'firmware': '固件',
    'shell-script': 'Shell 脚本', 'bash': 'Bash', 'zsh': 'Zsh', 'powershell': 'PowerShell',
    'dotfiles-manager': '配置管理', 'package-manager': '包管理器', 'build-tool': '构建工具',
    'bundler': '打包工具', 'linter': '代码检查', 'code-quality': '代码质量',
    'unit-testing': '单元测试', 'e2e-testing': '端到端测试', 'benchmark': '性能基准测试',
    'documentation-generator': '文档生成', 'changelog': '更新日志', 'release-automation': '发布自动化',
    'accessibility': '无障碍', 'internationalization': '国际化', 'i18n': '国际化',
    'dark-mode': '深色模式', 'responsive': '响应式', 'pwa': '渐进式网页应用',
    'frontend-framework': '前端框架', 'state-management': '状态管理', 'router': '路由',
    'ssr': '服务端渲染', 'jamstack': 'Jamstack', 'headless': '无头架构',
    'markdown-editor': 'Markdown 编辑器', 'knowledge-base': '知识库', 'wiki': '维基',
    'rss': 'RSS 订阅', 'reader': '阅读器', 'bookmark': '书签管理', 'todo': '待办事项',
    'kanban': '看板', 'project-management': '项目管理', 'time-tracking': '时间追踪',
    'dashboard': '仪表盘', 'admin-panel': '后台管理', 'analytics': '数据分析',
    'chart': '图表', 'charts': '图表', 'graph': '图形', 'map': '地图', 'gis': '地理信息',
    'weather': '天气', 'stock': '股票', 'currency': '汇率', 'translation': '翻译',
    'ocr': '文字识别', 'tts': '语音合成', 'stt': '语音识别', 'voice': '语音',
    'recommendation-system': '推荐系统', 'reinforcement-learning': '强化学习',
    'transfer-learning': '迁移学习', 'gan': '生成对抗网络', 'stable-diffusion': 'Stable Diffusion',
    'model': '模型', 'models': '模型', 'inference': '推理', 'quantization': '模型量化',
    'vllm': 'vLLM', 'llama': 'Llama', 'mistral': 'Mistral', 'gemini': 'Gemini',
    'huggingface': 'Hugging Face', 'transformers': 'Transformers',
    'chrome': 'Chrome', 'firefox': 'Firefox', 'safari': 'Safari', 'edge': 'Edge',
    'ios-app': 'iOS 应用', 'android-app': '安卓应用', 'macos-app': 'macOS 应用',
    'windows-app': 'Windows 应用', 'linux-app': 'Linux 应用', 'cross-platform-app': '跨平台应用',
    'blender': 'Blender', 'godot': 'Godot', 'minecraft': 'Minecraft', 'emulator': '模拟器',
    'screenshot': '截图工具', 'screen-recording': '屏幕录制', 'clipboard': '剪贴板',
    'notification': '通知', 'menu-bar': '菜单栏', 'status-bar': '状态栏', 'tray': '系统托盘'
  };

  /* 界面里残留的英文标签 → 中文 */
  var FIELD = {
    'Stars': 'Star 数',
    'Forks': 'Fork 数',
    'Open Issues': '未解决 Issue',
    'Topics': '标签',
    'Watchers': '关注数'
  };

  /* 各筛选控件的「人话」解释（鼠标悬停可见） */
  var HINT = {
    lang: '按项目的主要编程语言筛选。周热门榜按仓库自身语言判断，不是抓取榜单时用的语言。',
    stars: '只显示 Star 数达到该值的项目。刚部署时星标暴涨榜数据少，建议先选「不限 Star」。',
    thirdTrending: '周热门榜的排序方式。默认「本周期新增」= 按 GitHub 公布的涨粉数严格降序，涨得多的排前面。'
      + '「榜单排名」= GitHub 官方榜序，官方排序里掺了增速与新鲜度权重，所以涨粉多的不一定排前面。'
      + '「Star 总数」= 按仓库累计 Star 排。',

    thirdSurging: '星标暴涨榜的模式：按新增 Star = 看绝对增量；新晋项目 = 只看最近收录的新项目。',
    thirdRepos: '按收录时间范围筛选，只看最近发现的项目。',
    modelTrending: '榜单周期：GitHub 官方提供今日榜、本周榜、本月榜三份。',
    modelSurging: '统计窗口：与多久之前的快照对比来算增幅。窗口越长需要积累的历史越久。',
    modelRepos: '项目库的排序字段：可按总星数、近期新增或综合热度排。'
  };

  function license(spdx) {
    if (!spdx) return null;
    var hit = LICENSE[spdx] || LICENSE[String(spdx).toUpperCase()];
    if (hit) return { name: hit[0], note: hit[1], raw: spdx };
    return { name: spdx, note: '', raw: spdx };
  }

  function topic(slug) {
    if (!slug) return '';
    return TOPIC[String(slug).toLowerCase()] || slug;
  }

  function topicTitle(slug) {
    if (!slug) return '';
    var zh = TOPIC[String(slug).toLowerCase()];
    return zh && zh !== slug ? zh + '（' + slug + '）' : slug;
  }

  function field(name) { return FIELD[name] || name; }

  window.GHTerms = {
    license: license,
    topic: topic,
    topicTitle: topicTitle,
    field: field,
    HINT: HINT,
    LICENSE: LICENSE,
    TOPIC: TOPIC
  };
})();
