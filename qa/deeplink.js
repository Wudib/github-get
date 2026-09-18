const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const list=await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const page=list.find(t=>t.type==='page');
  const ws=new WebSocket(page.webSocketDebuggerUrl);
  let seq=0; const pending=new Map(); const errs=[];
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
    else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errs.push(m.params.entry.text);});
  await new Promise(r=>ws.addEventListener('open',r));
  const send=(method,params)=>new Promise(res=>{const id=++seq;pending.set(id,res);ws.send(JSON.stringify({id,method,params}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true});return (r.result||{}).result?r.result.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'about:blank'}); await sleep(600);
  await send('Page.navigate',{url:'http://127.0.0.1:8080/#/repo/fmtlib/fmt'});
  await sleep(6000);
  console.log('  深链接 #/repo/fmtlib/fmt ->');
  console.log('    抽屉标题 :', await ev("(document.querySelector('.drawer-title')||{textContent:'(未打开)'}).textContent.trim()"));
  console.log('    概览     :', await ev("(document.querySelector('.drawer-sub')||{textContent:''}).textContent.replace(/\\s+/g,' ').trim().slice(0,80)"));
  console.log('    趋势图路径:', await ev("(document.querySelector('.chart path')||{getAttribute:()=>''}).getAttribute('d').length"),'字符');
  console.log('    纵轴刻度 :', await ev("[...document.querySelectorAll('.axis-text')].map(e=>e.textContent).join(' / ')"));
  console.log('    许可证   :', await ev("[...document.querySelectorAll('.kv dd')].map(e=>e.textContent.trim()).slice(0,6).join(' | ')"));
  console.log('    看板卡片 :', await ev("document.querySelectorAll('.card-item').length"), '（深链接下方看板应同时正常加载）');
  await ev("document.querySelector('.drawer .ghost-btn').click(); 'ok'");
  await sleep(500);
  console.log('    关闭后    :', await ev("document.querySelector('.overlay') ? '仍打开' : '已关闭'"));
  console.log('    控制台错误:', errs.length?JSON.stringify(errs.slice(0,3)):'(无)');
  // 点卡片后地址栏是否同步，后退键是否关抽屉
  await send('Page.navigate',{url:'http://127.0.0.1:8080/'}); await sleep(5000);
  await ev("document.querySelector('.card-item').click(); 'ok'"); await sleep(2500);
  console.log('  点卡片后 hash :', await ev("location.hash"), '| 抽屉:', await ev("!!document.querySelector('.drawer-title')"));
  await ev("history.back(); 'ok'"); await sleep(1500);
  console.log('  后退键        :', await ev("document.querySelector('.overlay')?'仍打开':'已关闭'"), '| hash:', await ev("location.hash"));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
