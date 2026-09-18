/* ============================================================================
 * GitHub Radar — 前端逻辑（Vue 3 全局构建，无打包步骤）
 * 视觉与交互遵循 Fastshot skill；数据结构与接口保持不变。
 * ========================================================================== */
(function () {
  'use strict';

  var Vue = window.Vue;
  var API = './api';
  var PAGE_SIZE = 30;

  var LANG_COLORS = {
    JavaScript: '#f1e05a', TypeScript: '#3178c6', Python: '#3572A5', Go: '#00ADD8',
    Rust: '#dea584', Java: '#b07219', 'C++': '#f34b7d', C: '#8b949e', 'C#': '#178600',
    Ruby: '#701516', PHP: '#4F5D95', Swift: '#F05138', Kotlin: '#A97BFF', Dart: '#00B4AB',
    Shell: '#89e051', HTML: '#e34c26', CSS: '#563d7c', Vue: '#41b883', Svelte: '#ff3e00',
    Scala: '#c22d40', Elixir: '#6e4a7e', Haskell: '#5e5086', Lua: '#000080', Perl: '#0298c3',
    'Jupyter Notebook': '#DA5B0B', Zig: '#ec915c', Nim: '#ffc200', Clojure: '#db5855',
    'Objective-C': '#438eff', R: '#198CE7', Julia: '#a270ba', PowerShell: '#012456',
    Dockerfile: '#384d54', Makefile: '#427819', 'Emacs Lisp': '#c065db', OCaml: '#3be133',
    Solidity: '#AA6746', Cuda: '#3A4E3A', Assembly: '#6E4C13', TeX: '#3D6117'
  };

  var TABS = [
    { id: 'trending', label: '周热门榜' },
    { id: 'surging', label: '星标暴涨榜' },
    { id: 'repos', label: '项目库' }
  ];

  /* 第三个 chip 随视图切换含义 */
  var THIRD = {
    trending: {
      aria: '排序方式',
      options: [
        { value: 'stars_gained', label: '本周期新增' },
        { value: 'rank', label: '榜单排名' },
        { value: 'stars', label: 'Star 总数' }
      ]
    },
    surging: {
      aria: '榜单模式',
      options: [
        { value: 'velocity', label: '按新增 Star' },
        { value: 'new', label: '新晋项目' }
      ]
    },
    repos: {
      aria: '收录时间范围',
      options: [
        { value: 0, label: '全部时间' },
        { value: 7, label: '近 7 天' },
        { value: 30, label: '近 30 天' },
        { value: 90, label: '近 90 天' }
      ]
    }
  };

  /* 右侧“模型位”：当前视图的时间口径 / 排序 */
  var MODEL = {
    trending: {
      aria: '榜单周期',
      options: [
        { value: 'daily', label: '今日榜' },
        { value: 'weekly', label: '本周榜' },
        { value: 'monthly', label: '本月榜' }
      ]
    },
    surging: {
      aria: '统计窗口',
      options: [
        { value: '1h', label: '最近 1 小时' },
        { value: '24h', label: '最近 24 小时' },
        { value: '7d', label: '最近 7 天' },
        { value: '30d', label: '最近 30 天' }
      ]
    },
    repos: {
      aria: '排序方式',
      options: [
        { value: 'stars', label: 'Star 总数' },
        { value: 'gain_24h', label: '24 小时新增' },
        { value: 'gain_7d', label: '7 天新增' },
        { value: 'trend_score', label: '综合热度' },
        { value: 'created_at', label: '创建时间' },
        { value: 'pushed_at', label: '最近更新' }
      ]
    }
  };

  var STAR_OPTIONS = [
    { value: 0, label: '不限 Star' },
    { value: 100, label: '100+ Star' },
    { value: 500, label: '500+ Star' },
    { value: 1000, label: '1k+ Star' },
    { value: 5000, label: '5k+ Star' },
    { value: 20000, label: '20k+ Star' }
  ];

  var WINDOW_LABEL = { '1h': '1 小时', '24h': '24 小时', '7d': '7 天', '30d': '30 天' };

  /* 术语中文化（terms.js）。缺失时退化为原样显示，不会报错。 */
  var terms = window.GHTerms || {
    topic: function (t) { return t; },
    topicTitle: function (t) { return t; },
    license: function () { return null; },
    HINT: {}
  };

  function descOf(repo) {
    if (!repo) return '（暂无描述）';
    return repo.description_zh || repo.description || '（暂无描述）';
  }

  /* 有中文译文时，悬停显示英文原文，便于核对 */
  function descTitle(repo) {
    if (!repo) return '';
    return (repo.description_zh && repo.description) ? repo.description : '';
  }

  /* 服务端术语：翻译层在采集时补翻的标签译文，与内置词典合并
     优先级：内置词典（人工校准） > 服务端翻译 > 原文 */
  var serverTerms = Vue.reactive({
    topics: {}, translation_enabled: false,
    translated: 0, pending: 0, translating: false
  });

  function topicZh(t) {
    if (!t) return '';
    var builtin = terms.topic(t);
    if (builtin && builtin !== t) return builtin;
    var extra = serverTerms.topics[String(t).toLowerCase()];
    return extra || builtin || t;
  }

  function topicTitle(t) {
    var zh = topicZh(t);
    return zh && zh !== t ? zh + '（' + t + '）' : t;
  }
  function licenseZh(l) { var x = terms.license(l); return x ? x.name : l; }
  function licenseNote(l) { var x = terms.license(l); return x ? x.note : ''; }
  function hint(key) { return terms.HINT[key] || ''; }

  /* 采集状态：把 interrupted 等英文状态翻成一句人话，并说明原因 */
  var RUN_SUFFIX = {
    interrupted: '（被中断）',
    error: '（失败）',
    partial: '（部分成功）'
  };
  var RUN_NOTE = {
    interrupted: '上一轮采集被中断：通常是容器在采集途中被重启或停止。数据没有丢失，点「立即采集」或等下一个周期即可。',
    error: '上一轮采集失败，查看容器日志 docker compose logs --tail=100 了解原因。',
    partial: '上一轮采集部分成功：某个步骤失败，其余数据已正常写入。'
  };

  function runSuffix(run) { return (run && RUN_SUFFIX[run.status]) || ''; }

  function runTitle(run) {
    if (!run) return '';
    var note = RUN_NOTE[run.status];
    if (note) return run.message ? note + '（' + run.message + '）' : note;
    return '上次采集：' + run.status;
  }

  /* ------------------------------------------------------------ 工具函数 */
  function apiGet(path, params) {
    var url = new URL(API + path, window.location.href);
    Object.keys(params || {}).forEach(function (key) {
      var value = params[key];
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, value);
      }
    });
    return fetch(url.toString(), { headers: { Accept: 'application/json' } }).then(function (resp) {
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || ('请求失败 HTTP ' + resp.status));
        });
      }
      return resp.json();
    });
  }

  function num(value) {
    var n = Number(value || 0);
    if (!isFinite(n)) return '0';
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
    if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return Math.round(n).toLocaleString('en-US');
  }

  function fmtTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (isNaN(date.getTime())) return value;
    var pad = function (x) { return String(x).padStart(2, '0'); };
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
      ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function relTime(value) {
    if (!value) return '从未';
    var date = new Date(value);
    if (isNaN(date.getTime())) return value;
    var diff = Math.max(0, (Date.now() - date.getTime()) / 1000);
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    return Math.floor(diff / 86400) + ' 天前';
  }

  function optionLabel(list, value) {
    for (var i = 0; i < list.length; i++) {
      if (String(list[i].value) === String(value)) return list[i].label;
    }
    return list.length ? list[0].label : '';
  }

  /* ---------------------------------------------------------------- 应用 */
  var app = Vue.createApp({
    setup: function () {
      var view = Vue.ref('trending');
      var items = Vue.ref([]);
      var loading = Vue.ref(false);
      var error = Vue.ref('');
      var overview = Vue.ref(null);
      var languages = Vue.ref([]);
      var detail = Vue.ref(null);
      var hasMore = Vue.ref(false);
      var page = Vue.ref(1);
      var listMeta = Vue.ref('');
      var fallbackNotice = Vue.ref('');

      var filters = Vue.reactive({
        language: '', min_stars: 0,
        period: 'weekly', trend_sort: 'stars_gained',
        window: '24h', mode: 'velocity',
        max_age_days: 0, sort: 'stars'
      });

      var tabs = TABS;
      var starOptions = STAR_OPTIONS;
      var collecting = Vue.computed(function () {
        return !!(overview.value && overview.value.collecting);
      });

      /* ---- 第三个 chip：不同视图绑定不同字段 ---- */
      var third = Vue.computed(function () { return THIRD[view.value] || THIRD.trending; });
      var thirdOptions = Vue.computed(function () { return third.value.options; });
      var thirdValue = Vue.computed({
        get: function () {
          if (view.value === 'trending') return filters.trend_sort;
          if (view.value === 'surging') return filters.mode;
          return filters.max_age_days;
        },
        set: function (v) {
          if (view.value === 'trending') filters.trend_sort = String(v);
          else if (view.value === 'surging') filters.mode = String(v);
          else filters.max_age_days = Number(v) || 0;
        }
      });
      var chipThirdLabel = Vue.computed(function () {
        return optionLabel(third.value.options, thirdValue.value);
      });
      var chipThirdAria = Vue.computed(function () { return third.value.aria; });

      /* ---- 右侧“模型位” ---- */
      var model = Vue.computed(function () { return MODEL[view.value] || MODEL.trending; });
      var modelOptions = Vue.computed(function () { return model.value.options; });
      var modelValue = Vue.computed({
        get: function () {
          if (view.value === 'trending') return filters.period;
          if (view.value === 'surging') return filters.window;
          return filters.sort;
        },
        set: function (v) {
          if (view.value === 'trending') filters.period = String(v);
          else if (view.value === 'surging') filters.window = String(v);
          else filters.sort = String(v);
        }
      });
      var modelLabel = Vue.computed(function () {
        return optionLabel(model.value.options, modelValue.value);
      });
      var modelAria = Vue.computed(function () { return model.value.aria; });

      var chipLangLabel = Vue.computed(function () { return filters.language || '全部语言'; });
      var chipStarLabel = Vue.computed(function () { return optionLabel(STAR_OPTIONS, filters.min_stars); });
      var windowLabel = Vue.computed(function () { return WINDOW_LABEL[filters.window] || ''; });

      /* 筛选控件的中文口径提示，随视图切换 */
      var thirdHint = Vue.computed(function () {
        if (view.value === 'trending') return terms.HINT.thirdTrending || '';
        if (view.value === 'surging') return terms.HINT.thirdSurging || '';
        return terms.HINT.thirdRepos || '';
      });
      var modelHint = Vue.computed(function () {
        if (view.value === 'trending') return terms.HINT.modelTrending || '';
        if (view.value === 'surging') return terms.HINT.modelSurging || '';
        return terms.HINT.modelRepos || '';
      });

      /* ------------------------------------------------------ 路由与加载 */
      function parseHash() {
        return (window.location.hash || '').replace(/^#\/?/, '').split('/').filter(Boolean);
      }

      function loadOverview() {
        return apiGet('/overview').then(function (data) {
          overview.value = data;
        }).catch(function (err) { error.value = err.message; });
      }

      function loadTerms() {
        return apiGet('/terms').then(function (data) {
          if (!data) return;
          serverTerms.topics = data.topics || {};
          serverTerms.translation_enabled = !!data.translation_enabled;
          serverTerms.translated = data.translated || 0;
          serverTerms.pending = data.pending || 0;
          serverTerms.translating = !!data.translating;
        }).catch(function () { /* 术语表拿不到不影响使用，内置词典仍然生效 */ });
      }

      function loadLanguages() {
        return apiGet('/languages').then(function (data) {
          languages.value = data.items || [];
        }).catch(function () {});
      }

      function gainOf(repo) {
        if (!repo || view.value !== 'surging') return null;
        var value = repo['gain_' + filters.window];
        return value === undefined ? null : value;
      }

      function buildParams() {
        var params = {
          language: filters.language,
          min_stars: filters.min_stars || 0,
          limit: PAGE_SIZE,
          offset: (page.value - 1) * PAGE_SIZE
        };
        if (view.value === 'trending') {
          params.period = filters.period;
          params.sort = filters.trend_sort;
        } else if (view.value === 'surging') {
          params.window = filters.window;
          params.mode = filters.mode;
          params.min_gain = 0;
        } else {
          params.sort = filters.sort;
          params.max_age_days = filters.max_age_days || 0;
        }
        return params;
      }

      function load(reset) {
        if (reset) {
          page.value = 1;
          items.value = [];
          hasMore.value = false;
        }
        loading.value = true;
        error.value = '';
        return apiGet('/' + view.value, buildParams()).then(function (data) {
          var list = data.items || [];
          items.value = reset ? list : items.value.concat(list);
          hasMore.value = !!data.has_more;
          fallbackNotice.value = data.fallback
            ? '历史快照仍在积累中（至少需要一个采集周期）。当前展示的是 GitHub 官方'
              + (data.fallback === 'github-weekly' ? '本周' : '本月')
              + '新增 Star 排名，属于真实数据而非估算。'
            : '';
          if (view.value === 'repos') {
            listMeta.value = '共 ' + (data.total || 0) + ' 个匹配结果';
          } else if (data.collected_at) {
            listMeta.value = '数据采集于 ' + fmtTime(data.collected_at);
          } else {
            listMeta.value = list.length + ' 条结果';
          }
        }).catch(function (err) {
          error.value = err.message;
        }).then(function () {
          loading.value = false;
        });
      }

      function loadMore() {
        page.value += 1;
        load(false);
      }

      function applyFilters() {
        load(true);
      }

      /* 三个 chip（语言 / 最低 Star / 第三个 chip）与右侧时间口径任意改动都立即重新拉取。
         用 watch 而不是在模板里绑 @change，是为了避开 v-model 与 @change 的执行顺序问题。 */
      Vue.watch(
        function () {
          return [
            filters.language, filters.min_stars, filters.trend_sort,
            filters.mode, filters.window, filters.max_age_days, filters.sort
          ].join('\u0001');
        },
        function (next, prev) {
          if (next !== prev) load(true);
        }
      );

      function go(target) {
        view.value = target;
        if (window.location.hash !== '#/' + target) {
          window.location.hash = '#/' + target;
        }
        load(true);
        var dash = document.getElementById('dashboard');
        if (dash && window.scrollY > 0) {
          dash.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }

      /* -------------------------------------------------------- 详情抽屉 */
      function openDetail(repo) {
        var owner = repo.owner || (repo.full_name || '').split('/')[0] || '';
        var name = repo.name || (repo.full_name || '').split('/')[1] || '';
        detail.value = Object.assign({
          owner: owner, name: name, full_name: owner + '/' + name,
          html_url: 'https://github.com/' + owner + '/' + name,
          description: '', topics: [], series: [], point_count: 0, stars: 0, forks: 0
        }, repo, { series: [] });
        // 让地址栏反映当前详情：链接可分享，浏览器后退键能关掉抽屉
        var target = '#/repo/' + owner + '/' + name;
        if (window.location.hash !== target) window.location.hash = target;
        apiGet('/repos/' + owner + '/' + name).then(function (data) {
          detail.value = data;
        }).catch(function (err) { error.value = err.message; });
      }

      function closeDetail() {
        detail.value = null;
        var target = '#/' + view.value;
        if (window.location.hash !== target) window.location.hash = target;
      }

      /* ---------------------------------------------------------- 交互 */
      function triggerCollect() {
        fetch(API + '/collect', { method: 'POST' }).then(function (resp) {
          return resp.json();
        }).then(function (data) {
          listMeta.value = data.message || '已提交采集任务';
          var refresh = function () {
            loadOverview();
            loadLanguages();
            loadTerms();
            load(true);
          };
          // 采集约 2 分钟；翻译在其后单独进行，所以多刷几次把进度带回来
          setTimeout(refresh, 15000);
          setTimeout(refresh, 135000);
          setTimeout(refresh, 210000);
        }).catch(function (err) { error.value = err.message; });
      }

      function exportCsv() {
        if (!items.value.length) {
          listMeta.value = '当前列表为空，没有可导出的数据';
          return;
        }
        var cols = ['full_name', 'html_url', 'description', 'language', 'stars', 'forks',
          'created_at', 'age_days', 'gain_1h', 'gain_24h', 'gain_7d', 'gain_30d',
          'stars_gained', 'topics'];
        var header = ['仓库', '地址', '描述', '语言', 'Stars', 'Forks', '创建时间', '天龄',
          '1h新增', '24h新增', '7d新增', '30d新增', '本周期新增', 'Topics'];
        var lines = [header.join(',')];
        items.value.forEach(function (r) {
          lines.push(cols.map(function (c) {
            var v = r[c];
            if (Array.isArray(v)) v = v.join(' ');
            if (v === null || v === undefined) v = '';
            return '"' + String(v).replace(/"/g, '""') + '"';
          }).join(','));
        });
        var blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'github-radar-' + view.value + '-' + new Date().toISOString().slice(0, 10) + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
        listMeta.value = '已导出 ' + items.value.length + ' 条记录为 CSV';
      }

      /* -------------------------------------------------------- 趋势图 */
      var chart = Vue.computed(function () {
        var series = (detail.value && detail.value.series) || [];
        if (series.length < 2) return null;
        var w = 720, h = 200, pad = 34;
        var xs = series.map(function (p) { return new Date(p[0]).getTime(); });
        var ys = series.map(function (p) { return Number(p[1]); });
        var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
        var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
        // 采集窗口太短时 Star 变化极小，给一个按比例的最小可视区间，
        // 否则曲线会贴着顶边、四条纵轴刻度出现重复值
        var minSpan = Math.max(2, Math.abs(maxY) * 0.0005);
        if (maxY - minY < minSpan) {
          var midY = (maxY + minY) / 2;
          minY = midY - minSpan / 2;
          maxY = midY + minSpan / 2;
        }
        var span = maxY - minY;
        var tickFmt = span < 200
          ? function (v) { return Math.round(v).toLocaleString('en-US'); }
          : num;
        var sx = function (x) { return pad + (maxX === minX ? 0 : (x - minX) / (maxX - minX)) * (w - pad - 12); };
        var sy = function (y) { return h - pad - ((y - minY) / (maxY - minY)) * (h - pad - 16); };
        var line = series.map(function (p, i) {
          return (i ? 'L' : 'M') + sx(xs[i]).toFixed(1) + ' ' + sy(ys[i]).toFixed(1);
        }).join(' ');
        var area = line + ' L ' + sx(maxX).toFixed(1) + ' ' + (h - pad) +
          ' L ' + sx(minX).toFixed(1) + ' ' + (h - pad) + ' Z';
        var ticks = [];
        for (var i = 0; i <= 3; i++) {
          var value = minY + (maxY - minY) * (i / 3);
          ticks.push({ y: sy(value), label: tickFmt(Math.round(value)) });
        }
        return {
          w: w, h: h, pad: pad, line: line, area: area, ticks: ticks,
          minY: minY, maxY: maxY,
          lastX: sx(maxX), lastY: sy(ys[ys.length - 1]),
          firstTs: series[0][0], lastTs: series[series.length - 1][0]
        };
      });

      function langColor(language) { return LANG_COLORS[language] || '#8b949e'; }

      /* -------------------------------------------------- 入场动画（一次） */
      function runEntrance() {
        var root = document.documentElement;
        if (!window.matchMedia || !window.matchMedia('(prefers-reduced-motion: no-preference)').matches) {
          return;
        }
        root.classList.add('anim');
        var settled = false;
        var finish = function () {
          if (settled) return;
          settled = true;
          root.classList.remove('anim');
        };
        var logos = document.querySelectorAll('.logos span');
        var last = logos[logos.length - 1];
        if (last) {
          last.addEventListener('animationend', finish, { once: true });
        }
        setTimeout(finish, 2600);
      }

      Vue.onMounted(function () {
        var parts = parseHash();
        view.value = parts[0] && TABS.some(function (t) { return t.id === parts[0]; })
          ? parts[0] : 'trending';
        loadOverview();
        loadLanguages();
        loadTerms();
        load(true);
        if (parts[0] === 'repo' && parts[1] && parts[2]) {
          openDetail({ owner: parts[1], name: parts[2] });
        }
        window.addEventListener('hashchange', function () {
          var parts = parseHash();
          if (parts[0] === 'repo' && parts[1] && parts[2]) {
            var full = parts[1] + '/' + parts[2];
            if (!detail.value || detail.value.full_name !== full) {
              openDetail({ owner: parts[1], name: parts[2] });
            }
            return;
          }
          if (detail.value) detail.value = null;
          if (parts[0] && parts[0] !== view.value && TABS.some(function (t) { return t.id === parts[0]; })) {
            view.value = parts[0];
            load(true);
          }
        });
        setInterval(loadOverview, 60000);
        runEntrance();
      });

      return {
        tabs: tabs, starOptions: starOptions,
        view: view, items: items, loading: loading, error: error, overview: overview,
        languages: languages, detail: detail, hasMore: hasMore, listMeta: listMeta,
        fallbackNotice: fallbackNotice, page: page, pageSize: PAGE_SIZE, chart: chart,
        filters: filters, collecting: collecting, windowLabel: windowLabel,
        thirdOptions: thirdOptions, thirdValue: thirdValue,
        chipThirdLabel: chipThirdLabel, chipThirdAria: chipThirdAria,
        modelOptions: modelOptions, modelValue: modelValue,
        modelLabel: modelLabel, modelAria: modelAria,
        chipLangLabel: chipLangLabel, chipStarLabel: chipStarLabel,
        hint: hint, thirdHint: thirdHint, modelHint: modelHint,
        descOf: descOf, descTitle: descTitle, topicZh: topicZh, topicTitle: topicTitle,
        descLang: Vue.computed(function () {
          if (!serverTerms.translation_enabled) return '英文原文';
          var total = serverTerms.translated + serverTerms.pending;
          if (serverTerms.pending > 0 && total > 0) return '中文 ' + serverTerms.translated + '/' + total;
          return '中文';
        }),
        descLangHint: Vue.computed(function () {
          if (!serverTerms.translation_enabled) {
            return '项目描述为 GitHub 原文（英文）。在 .env 中配置 TRANSLATE_PROVIDER / TRANSLATE_BASE_URL / TRANSLATE_API_KEY / TRANSLATE_MODEL 并重建容器后，采集时会自动译成中文。';
          }
          var tip = '项目描述由配置的翻译模型自动译成中文，鼠标悬停可查看英文原文。';
          if (serverTerms.pending > 0) {
            tip += ' 已译 ' + serverTerms.translated + ' 条，还有 ' + serverTerms.pending + ' 条排队中'
                 + (serverTerms.translating ? '（正在翻译…）' : '，可在下一轮采集时继续')
                 + '。翻译不占用采集时间，翻不完的会自动留到下一轮。';
          } else {
            tip += ' 全部描述均已翻译完成。';
          }
          return tip;
        }),
        licenseZh: licenseZh, licenseNote: licenseNote,
        runSuffix: runSuffix, runTitle: runTitle,
        num: num, fmtTime: fmtTime, relTime: relTime, langColor: langColor, gainOf: gainOf,
        go: go, loadMore: loadMore, applyFilters: applyFilters,
        openDetail: openDetail, closeDetail: closeDetail, triggerCollect: triggerCollect,
        exportCsv: exportCsv, loadOverview: loadOverview
      };
    }
  });

  app.mount('#app');
})();
