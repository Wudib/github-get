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
    const p=r.result||{}; if(p.exceptionDetails) return '<<异常:'+JSON.stringify(p.exceptionDetails).slice(0,120)+'>>';
    return p.result?p.result.result?p.result.result.value:p.result.value:null;};
  await send('Page.enable');await send('Runtime.enable');await send('Log.enable');
  await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});

  const probe = `(function(){
    function r(sel){var e=document.querySelector(sel); if(!e) return null; var b=e.getBoundingClientRect();
      return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};}
    var chips=[...document.querySelectorAll('.chip')].map(function(c){
      var b=c.getBoundingClientRect(); return Math.round(b.y);});
    return JSON.stringify({
      搜索框: !!document.querySelector('input.ph, #search-input'),
      卡片: r('.card'), 工具栏: r('.tools'), 标题: r('.h1'),
      刷新按钮: r('.send'), 回形针: r('.attach'), 模型位: r('.model'),
      chip同一行: chips.length===0 ? null : (new Set(chips).size===1),
      chip数: chips.length,
      页脚: r('.proof'), 页脚文案: (document.querySelector('.proof .by')||{}).textContent,
      页脚在文档末尾: (function(){var p=document.querySelector('.proof');
        return p && p.getBoundingClientRect().bottom <= document.documentElement.scrollHeight+1;})(),
      页脚下方还有内容: (function(){var p=document.querySelector('.proof'); if(!p) return null;
        var n=p.nextElementSibling; return n? (n.tagName+'.'+n.className) : null;})(),
      已滚动高度: Math.round(document.documentElement.scrollHeight),
      卡片内子元素: [...document.querySelector('.card').children].map(function(e){return e.className;}),
    });})()`;

  for (const [name, w, h] of [['桌面',1560,1008],['平板',900,1000],['手机',390,844]]) {
    await send('Emulation.setDeviceMetricsOverride',{width:w,height:h,deviceScaleFactor:1,mobile:w<600});
    await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=L'+w+'#/trending'});
    await sleep(4500);
    const d = JSON.parse(await ev(probe));
    console.log('=== ' + name + ' ' + w + '×' + h + ' ===');
    console.log('  搜索框存在: ' + d.搜索框 + '   卡片: ' + JSON.stringify(d.卡片) + '   工具栏: ' + JSON.stringify(d.工具栏));
    console.log('  标题: ' + JSON.stringify(d.标题) + '   刷新按钮: ' + JSON.stringify(d.刷新按钮) + '   回形针: ' + JSON.stringify(d.回形针));
    console.log('  chip 数: ' + d.chip数 + '   全在同一行: ' + d.chip同一行);
    console.log('  卡片直接子元素: ' + JSON.stringify(d.卡片内子元素));
    console.log('  页脚: ' + JSON.stringify(d.页脚) + '  文案: ' + d.页脚文案 + '  下方还有: ' + d.页脚下方还有内容);
    console.log('  文档总高: ' + d.已滚动高度);
  }
  console.log('\n控制台错误: ' + (errs.length?JSON.stringify(errs.slice(0,2)):'(无)'));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
