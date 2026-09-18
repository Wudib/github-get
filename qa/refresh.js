const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const list=await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const ws=new WebSocket(list.find(t=>t.type==='page').webSocketDebuggerUrl);
  let seq=0;const pending=new Map();const errs=[];const reqs=[];
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
    else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errs.push(m.params.entry.text);
    else if(m.method==='Network.requestWillBeSent'&&m.params.request.url.includes('/api/'))reqs.push(m.params.request.url);});
  await new Promise(r=>ws.addEventListener('open',r));
  const send=(m,p)=>new Promise(res=>{const id=++seq;pending.set(id,res);ws.send(JSON.stringify({id,method:m,params:p}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true,awaitPromise:true});
    const p=r.result||{}; if(p.exceptionDetails) return '<<异常>>';
    return p.result?p.result.result?p.result.result.value:p.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
  await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=R1#/trending'});
  await sleep(5000);

  console.log('按钮属性: ' + await ev("[JSON.stringify(function(){var b=document.querySelector('.send');return {aria:b.getAttribute('aria-label'),title:b.title};}())]".replace(/^\[|\]$/g,'')));
  const before = await ev("(document.querySelector('.card-item .repo-name')||{}).textContent");
  console.log('刷新前首卡: ' + before);
  reqs.length = 0;
  console.log('\n--- 点击刷新按钮 ---');
  await ev("document.querySelector('.send').click(); 'ok'");
  await sleep(150);
  console.log('  点击后立即: spinning=' + await ev("document.querySelector('.send').classList.contains('spinning')")
            + '  动画=' + await ev("getComputedStyle(document.querySelector('.send svg')).animationName"));
  await sleep(4000);
  console.log('  请求: ' + JSON.stringify(reqs.slice(0,3)));
  console.log('  加载完成后: spinning=' + await ev("document.querySelector('.send').classList.contains('spinning')"));
  console.log('  刷新后首卡: ' + await ev("(document.querySelector('.card-item .repo-name')||{}).textContent"));
  console.log('  卡片数: ' + await ev("document.querySelectorAll('.card-item').length"));

  // 直接点工具栏空白处不应再有任何"聚焦搜索框"的行为
  await ev("document.querySelector('.card').click(); 'ok'");
  console.log('\n  点卡片空白处后 activeElement: ' + await ev("document.activeElement.tagName + (document.activeElement.id?'#'+document.activeElement.id:'')"));
  console.log('  控制台错误: ' + (errs.length?JSON.stringify(errs.slice(0,2)):'(无)'));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
