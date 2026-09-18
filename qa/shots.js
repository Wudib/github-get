/* 重新生成 qa/ 下的界面截图（桌面 / 平板 / 手机 / 详情抽屉） */
const fs = require('fs');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const list = await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const ws = new WebSocket(list.find(t => t.type === 'page').webSocketDebuggerUrl);
  let seq = 0; const pending = new Map();
  ws.addEventListener('message', e => { const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  await new Promise(r => ws.addEventListener('open', r));
  const send = (method, params) => new Promise(res => { const id = ++seq; pending.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
  const ev = x => send('Runtime.evaluate', { expression: x, returnByValue: true }).then(r => r.result && r.result.result && r.result.result.value);
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Network.setCacheDisabled', { cacheDisabled: true });

  const shot = async (file, w, h, url, wait) => {
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1.5, mobile: w < 600 });
    await send('Page.navigate', { url: url + '?shot=' + Date.now() });
    await sleep(wait);
    const r = await send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync('qa/' + file, Buffer.from(r.result.data, 'base64'));
    console.log('  ' + file.padEnd(20) + w + '×' + h + '  ' + Math.round(Buffer.from(r.result.data, 'base64').length / 1024) + ' KB');
  };

  const B = 'http://127.0.0.1:8080/';
  await shot('shot-desktop.png', 1560, 1008, B + '#/trending', 7000);
  await shot('shot-tablet.png', 900, 1000, B + '#/trending', 6000);
  await shot('shot-phone.png', 390, 844, B + '#/trending', 6000);
  // 详情抽屉：先回桌面尺寸，点开第一张卡片
  await send('Emulation.setDeviceMetricsOverride', { width: 1560, height: 1008, deviceScaleFactor: 1.5, mobile: false });
  await send('Page.navigate', { url: B + '?shot=drawer' });
  await sleep(6000);
  await ev("document.querySelector('.card-item').click(); 'ok'");
  await sleep(3000);
  const d = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync('qa/shot-drawer.png', Buffer.from(d.result.data, 'base64'));
  console.log('  shot-drawer.png      1560×1008  ' + Math.round(Buffer.from(d.result.data, 'base64').length / 1024) + ' KB');
  process.exit(0);
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
