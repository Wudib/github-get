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
  const probe = `(function(){
    function B(e){var b=e.getBoundingClientRect();return {t:Math.round(b.top),b:Math.round(b.bottom)};}
    var nav=B(document.querySelector('.nav')), h1=B(document.querySelector('.h1')), card=B(document.querySelector('.card'));
    var dash=document.querySelector('.dash'), inner=document.querySelector('.dash-inner');
    var tabs=document.querySelector('.segmented'), first=document.querySelector('.card-item');
    return JSON.stringify({
      导航底:nav.b, 标题:[h1.t,h1.b], 工具栏:[card.t,card.b],
      看板起点:B(dash).t, 看板内首元素:B(inner).t, 分段标签:B(tabs).t,
      首卡:first?B(first).t:null,
      '导航→标题':h1.t-nav.b, '标题→工具栏':card.t-h1.b, '工具栏→看板':B(dash).t-card.b,
      '工具栏→首卡':first?B(first).t-card.b:null,
      首屏高:window.innerHeight, 文档高:Math.round(document.documentElement.scrollHeight)});})()`;
  for (const [name,w,h] of [['桌面',1560,1008],['平板',900,1000],['手机',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:h,deviceScaleFactor:1,mobile:w<600});
    await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=V'+w+'#/trending'});
    await sleep(4500);
    const d=JSON.parse(await ev(probe));
    console.log('=== '+name+' '+w+'×'+h+' ===');
    console.log('  导航底 '+d.导航底+'  标题 '+d.标题[0]+'~'+d.标题[1]+'  工具栏 '+d.工具栏[0]+'~'+d.工具栏[1]);
    console.log('  看板起点 '+d.看板起点+'  看板内首元素 '+d.看板内首元素+'  分段标签 '+d.分段标签+'  首卡 '+(d.首卡||'-'));
    console.log('  ▸ 导航→标题 '+d['导航→标题']+'   标题→工具栏 '+d['标题→工具栏']+'   工具栏→看板 '+d['工具栏→看板']);
    console.log('  ▸ 首屏里能看到首卡: ' + (d.首卡!=null && d.首卡 < d.首屏高) + '   文档总高 '+d.文档高);
  }
  console.log('\n控制台错误: '+(errs.length?JSON.stringify(errs.slice(0,2)):'(无)'));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
