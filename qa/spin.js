const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const list=await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const ws=new WebSocket(list.find(t=>t.type==='page').webSocketDebuggerUrl);
  let seq=0;const pending=new Map();
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}});
  await new Promise(r=>ws.addEventListener('open',r));
  const send=(m,p)=>new Promise(res=>{const id=++seq;pending.set(id,res);ws.send(JSON.stringify({id,method:m,params:p}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true});
    const p=r.result||{}; if(p.exceptionDetails) return '<<异常>>';
    return p.result?p.result.result?p.result.result.value:p.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Network.setCacheDisabled',{cacheDisabled:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  // 给所有请求加 2 秒延迟，模拟慢网络
  await send('Network.emulateNetworkConditions',{offline:false,latency:2000,downloadThroughput:-1,uploadThroughput:-1});
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=S1#/trending'});
  await sleep(9000);
  const snap = "JSON.stringify({spinning:document.querySelector('.send').classList.contains('spinning'),anim:getComputedStyle(document.querySelector('.send svg')).animationName,dur:getComputedStyle(document.querySelector('.send svg')).animationDuration})";
  console.log('静态时: ' + await ev(snap));
  await ev("document.querySelector('.send').click(); 'ok'");
  for (const t of [300, 800, 1500]) {
    await sleep(t===300?300:500);
    console.log('点击后 ' + t + 'ms: ' + await ev(snap));
  }
  await sleep(4000);
  console.log('请求完成后: ' + await ev(snap));
  console.log('卡片数: ' + await ev("document.querySelectorAll('.card-item').length"));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
