/* 响应式断点 + 交互链路验证（Chrome DevTools Protocol） */
const fs = require('fs');
const PORT = 9222;
const BASE = process.env.BASE || 'http://127.0.0.1:8099/';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect() {
  let targets = null;
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/list`);
      targets = await r.json();
      if (targets && targets.length) break;
    } catch (e) {}
    await sleep(500);
  }
  const page = targets.find((t) => t.type === 'page') || targets[0];
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let seq = 0;
  const pending = new Map();
  const logs = [];
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    else if (msg.method === 'Log.entryAdded' && msg.params.entry.level === 'error') logs.push(msg.params.entry.text);
    else if (msg.method === 'Runtime.exceptionThrown') logs.push('EXCEPTION ' + JSON.stringify(msg.params.exceptionDetails.text));
  });
  await new Promise((res) => ws.addEventListener('open', res));
  const send = (method, params) => new Promise((res) => {
    const id = ++seq; pending.set(id, res);
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');
  return { send, logs, evalJs: async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    const p = r.result || {};
    if (p.exceptionDetails) return '<<求值异常: ' + p.exceptionDetails.exception.description.split('\n')[0] + '>>';
    return p.result ? p.result.value : undefined;
  } };
}

const MEASURE_TOOLS = `(() => {
  const r = (sel) => { const el = document.querySelector(sel); if (!el) return null; const b = el.getBoundingClientRect();
    return { x:+b.x.toFixed(1), y:+b.y.toFixed(1), w:+b.width.toFixed(1), h:+b.height.toFixed(1), cy:+(b.y+b.height/2).toFixed(1) }; };
  const vis = (sel) => { const el = document.querySelector(sel); if (!el) return false;
    const s = getComputedStyle(el); return s.display !== 'none' && s.visibility !== 'hidden'; };
  const tools = r('.tools'), chips = r('.chips'), right = r('.right'), model = r('.model'), attach = r('.attach'), send = r('.send');
  return {
    tools, chips, right, model, attach, send,
    toolbarOneRow: (chips && right) ? Math.abs(chips.cy - right.cy) < Math.max(chips.h, right.h) : null,
    toolsDir: getComputedStyle(document.querySelector('.tools')).flexDirection,
    modelPos: getComputedStyle(document.querySelector('.model')).position,
    rightPos: getComputedStyle(document.querySelector('.right')).position,
    rightSameRow: (model && send) ? Math.abs(model.cy - send.cy) < 8 : null,
    modelLeftOfSend: (model && send) ? model.x < send.x : null,
    burgerVisible: vis('.burger'), linksVisible: vis('.links'), headerCtaVisible: vis('.nav .cta'),
    sheetH: +document.querySelector('.sheet-panel').getBoundingClientRect().height.toFixed(1),
    cardW: r('.card') ? r('.card').w : null,
    cardH: r('.card') ? r('.card').h : null,
    h1Size: getComputedStyle(document.querySelector('.h1')).fontSize
  };
})()`;

(async () => {
  const cdp = await connect();
  const q = (expr) => cdp.evalJs(expr);

  async function resize(w, h, label, file) {
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 600 });
    await cdp.send('Page.navigate', { url: BASE });
    await sleep(4500);
    const m = await q(MEASURE_TOOLS);
    console.log(`\n=== ${label} (${w}×${h}) ===`);
    if (typeof m === 'string') { console.log(m); return m; }
    console.log('  .tools flex-direction:', m.toolsDir, '| .right:', m.rightPos, '| .model:', m.modelPos);
    console.log('  chips 与 right 同行:', m.toolbarOneRow, '| model 与 send 同行:', m.rightSameRow, '| model 在 send 左:', m.modelLeftOfSend);
    console.log('  card:', m.cardW, 'x', m.cardH, '| h1 字号:', m.h1Size);
    console.log('  burger:', m.burgerVisible, '| links:', m.linksVisible, '| 顶部 CTA:', m.headerCtaVisible, '| 折叠菜单高:', m.sheetH);
    if (file) {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(file, Buffer.from(shot.result.data, 'base64'));
    }
    return m;
  }

  await resize(1560, 1008, '桌面', 'qa/shot-desktop.png');
  await resize(900, 1000, '平板', 'qa/shot-tablet.png');
  const phone = await resize(390, 844, '手机', 'qa/shot-phone.png');

  await q("document.getElementById('menu').checked = true; document.getElementById('menu').dispatchEvent(new Event('change',{bubbles:true})); 'ok'");
  await sleep(700);
  const open = await q("+document.querySelector('.sheet-panel').getBoundingClientRect().height.toFixed(1)");
  console.log('  手风琴菜单: 折叠', phone.sheetH, '-> 展开', open, '=>', open > phone.sheetH ? '可用' : '异常');

  // ---------------- 交互链路 ----------------
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1560, height: 1008, deviceScaleFactor: 1, mobile: false });
  await cdp.send('Page.navigate', { url: BASE });
  await sleep(4500);
  console.log('\n=== 交互链路 ===');
  console.log('  初始: chips =', await q("[...document.querySelectorAll('.chip-label')].map(e=>e.textContent).join(' | ')"),
    '| model =', await q("document.querySelector('.model-text').textContent"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"));

  await q("document.querySelectorAll('.segmented button')[1].click(); 'ok'");
  await sleep(3500);
  console.log('\n  [1] 切星标暴涨榜: chips =', await q("[...document.querySelectorAll('.chip-label')].map(e=>e.textContent).join(' | ')"),
    '| model =', await q("document.querySelector('.model-text').textContent"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"));
  console.log('      空态:', await q("(document.querySelector('.placeholder')||{textContent:'(无)'}).textContent.replace(/\\s+/g,' ').trim().slice(0,56)"));

  await q("(() => { const s = document.querySelector('.model select'); s.value='7d'; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; })()");
  await sleep(3500);
  console.log('\n  [2] 模型位切「最近 7 天」: model =', await q("document.querySelector('.model-text').textContent"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"));
  console.log('      兜底提示:', await q("(document.querySelector('.notice.info')||{textContent:'(无)'}).textContent.replace(/\\s+/g,' ').trim().slice(0,72)"));
  console.log('      首卡:', await q("(document.querySelector('.card-item .repo-name')||{textContent:'-'}).textContent.replace(/\\s+/g,' ').trim()"),
    '|', await q("(document.querySelector('.card-item .ci-foot')||{textContent:'-'}).textContent.replace(/\\s+/g,' ').trim()"));

  await q("document.querySelector('.card-item').click(); 'ok'");
  await sleep(3000);
  console.log('\n  [3] 详情抽屉:', await q("(document.querySelector('.drawer-title')||{textContent:'(未打开)'}).textContent.trim()"));
  console.log('      趋势图 path:', await q("(document.querySelector('.chart path')||{getAttribute:()=>''}).getAttribute('d').length"), '字符',
    '| 纵轴刻度:', await q("[...document.querySelectorAll('.axis-text')].map(e=>e.textContent).join(',')"));
  console.log('      统计卡:', await q("[...document.querySelectorAll('.drawer-stats div')].map(d=>d.textContent.replace(/\\s+/g,' ').trim()).join(' | ')"));
  console.log('      字段:', await q("[...document.querySelectorAll('.kv dt')].map(d=>d.textContent).join(',')"));
  const shot2 = await cdp.send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('qa/shot-drawer.png', Buffer.from(shot2.result.data, 'base64'));
  await q("document.querySelector('.drawer .ghost-btn').click(); 'ok'");
  await sleep(600);
  console.log('      抽屉关闭:', await q("document.querySelector('.overlay') ? '失败' : '成功'"));

  await q("(() => { const s = document.querySelectorAll('.chip select')[0]; s.value='Python'; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; })()");
  await sleep(3000);
  console.log('\n  [4] 语言筛选 Python: chip1 =', await q("document.querySelectorAll('.chip-label')[0].textContent"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"),
    '| 语言徽标 =', await q("[...document.querySelectorAll('.badge.lang')].slice(0,3).map(e=>e.textContent.trim()).join(',')"));

  await q("(() => { const s = document.querySelector('.model select'); s.value='24h'; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; })()");
  await sleep(2000);
  await q("(() => { const s = document.querySelectorAll('.chip select')[2]; s.value='new'; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; })()");
  await sleep(3000);
  console.log('\n  [5] chip3 切「新晋项目」: chip3 =', await q("document.querySelectorAll('.chip-label')[2].textContent"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"),
    '| 空态:', await q("(document.querySelector('.placeholder')||{textContent:''}).textContent.replace(/\\s+/g,' ').trim().slice(0,40)"));

  await q("(() => { const s = document.querySelectorAll('.chip select')[0]; s.value=''; s.dispatchEvent(new Event('change',{bubbles:true})); return 'ok'; })()");
  await q("document.querySelectorAll('.segmented button')[2].click(); 'ok'");
  await sleep(3000);
  console.log('\n  [6] 项目库: chips =', await q("[...document.querySelectorAll('.chip-label')].map(e=>e.textContent).join(' | ')"),
    '| model =', await q("document.querySelector('.model-text').textContent"));
  console.log('      搜索栏已移除: ', await q("!document.querySelector('#search-input, input.ph')"),
    '| 卡片只包一层工具栏:', await q("document.querySelector('.card').children.length === 1"));
  await q("document.querySelector('.send').click(); 'ok'");
  await sleep(2500);
  console.log('      点刷新按钮: 卡片 =', await q("document.querySelectorAll('.card-item').length"),
    '| 按钮 aria =', await q("document.querySelector('.send').getAttribute('aria-label')"));
  await q("document.querySelector('.attach').click(); 'ok'");
  await sleep(1500);
  console.log('      导出 CSV: meta =', await q("(document.querySelector('.meta-line')||{textContent:''}).textContent.trim()"));

  await q("window.scrollTo(0, 1400); 'ok'");
  await sleep(600);
  const before = await q("Math.round(window.scrollY)");
  await q("document.querySelectorAll('.links a')[0].click(); 'ok'");
  await sleep(1800);
  console.log('\n  [7] 导航链接: 滚动', before, '->', await q("Math.round(window.scrollY)"),
    '| 当前视图 =', await q("document.querySelector('.segmented button.active').textContent"),
    '| hash =', await q("location.hash"),
    '| 卡片 =', await q("document.querySelectorAll('.card-item').length"));

  console.log('\n  控制台错误:', cdp.logs.length ? JSON.stringify(cdp.logs.slice(0, 5)) : '(无)');
  process.exit(0);
})().catch((e) => { console.error('FAILED:', e.message); process.exit(1); });
