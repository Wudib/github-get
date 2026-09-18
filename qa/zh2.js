const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const list=await (await fetch('http://127.0.0.1:9222/json/list')).json();
  const ws=new WebSocket(list.find(t=>t.type==='page').webSocketDebuggerUrl);
  let seq=0;const pending=new Map();const errs=[];
  ws.addEventListener('message',e=>{const m=JSON.parse(e.data);
    if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}
    else if(m.method==='Log.entryAdded'&&m.params.entry.level==='error')errs.push(m.params.entry.text);});
  await new Promise(r=>ws.addEventListener('open',r));
  const send=(method,params)=>new Promise(res=>{const id=++seq;pending.set(id,res);ws.send(JSON.stringify({id,method,params}));});
  const ev=async(x)=>{const r=await send('Runtime.evaluate',{expression:x,returnByValue:true});
    const p=r.result||{}; if(p.exceptionDetails) return '<<异常>>';
    return p.result?p.result.result?p.result.result.value:p.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
  await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  // 深链直接打开已知含 svg / knowledge-graph 标签的仓库
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=9#/repo/cathrynlavery/diagram-design'});
  await sleep(6000);
  console.log('=== 服务端术语合并（这些标签不在前端词典里）===');
  console.log('  抽屉标签 :', await ev("[...document.querySelectorAll('.drawer .topic')].map(e=>e.textContent).join(' / ')"));
  console.log('  悬停原文 :', await ev("[...document.querySelectorAll('.drawer .topic')].map(e=>e.title).join(' | ')"));
  console.log('\n=== 描述语言标识 ===');
  console.log('  状态标识 :', await ev("[...document.querySelectorAll('.pill')].map(e=>e.textContent.replace(/\\s+/g,' ').trim()).join(' | ')"));
  console.log('  提示文案 :', await ev("(document.querySelector('.pill[title*=TRANSLATE]')||{title:''}).title.slice(0,80)"));
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=9#/repos'});
  await sleep(5000);
  console.log('\n=== 项目库卡片（前端词典 + 服务端译文混合）===');
  const hits = await ev(`(function(){
     var want={'svg':'SVG 矢量图','ai-video':'AI 视频','knowledge-graph':'知识图谱','3d':'三维','shaders':'着色器'};
     var out=[];
     document.querySelectorAll('.card-item .topic').forEach(function(e){
       var raw=(e.getAttribute('title')||'').replace(/（.*/,'');
       for(var k in want){ if((e.getAttribute('title')||'').indexOf(k+'）')>0||(e.getAttribute('title')||'')===k){
         out.push(k+' → '+e.textContent); } }
     });
     return out.slice(0,8).join(' | ') || '(本页卡片前 4 个标签中未出现这批词)';
  })()`);
  console.log('  命中样例 :', hits);
  console.log('  词典仍优先:', await ev("['machine-learning','self-hosted','mcp-server'].map(k=>k+'→'+GHTerms.topic(k)).join('  ')"));
  console.log('\n  控制台错误:', errs.length?JSON.stringify(errs.slice(0,3)):'(无)');
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
