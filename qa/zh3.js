const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const list=await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const ws=new WebSocket(list.find(t=>t.type==='page').webSocketDebuggerUrl);
  let seq=0;const pending=new Map();const errs=[];
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
    else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errs.push(m.params.entry.text);});
  await new Promise(r=>ws.addEventListener('open',r));
  const send=(m,p)=>new Promise(res=>{const id=++seq;pending.set(id,res);ws.send(JSON.stringify({id,method:m,params:p}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true});
    const p=r.result||{}; if(p.exceptionDetails) return '<<异常>>';
    return p.result?p.result.result?p.result.result.value:p.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
  await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=zh#/trending'});
  await sleep(7000);
  console.log('=== 卡片描述（应为中文）===');
  const descs = await ev(`[...document.querySelectorAll('.card-item .ci-desc')].slice(0,5).map(function(e){
      return e.textContent.trim().slice(0,34) + (e.title ? '  [悬停原文: '+e.title.slice(0,26)+'…]' : '  [无原文]');}).join('\\n  ')`);
  console.log('  ' + descs);
  console.log('\n=== 状态标识 ===');
  console.log('  ' + await ev("[...document.querySelectorAll('.pill')].map(e=>e.textContent.replace(/\\s+/g,' ').trim()).join(' | ')"));
  console.log('  悬停说明: ' + await ev("(document.querySelector('.pill[title*=翻译]')||{title:''}).title"));
  console.log('\n=== 采集状态标识（之前显示红点那次）===');
  console.log('  ' + await ev("(document.querySelector('.pill.sync')||{textContent:''}).textContent.replace(/\\s+/g,' ').trim()"));
  console.log('\n  控制台错误: ' + (errs.length?JSON.stringify(errs.slice(0,2)):'(无)'));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
