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
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=sort#/trending'});
  await sleep(7000);
  console.log('=== 首屏默认状态 ===');
  console.log('  筛选器: ' + await ev("[...document.querySelectorAll('.chip-label')].map(e=>e.textContent).join(' | ')"));
  console.log('  周期:   ' + await ev("(document.querySelector('.model-text')||{textContent:''}).textContent"));
  console.log('  下拉顺序: ' + await ev("[...document.querySelectorAll('.chip select')][2] ? [...[...document.querySelectorAll('.chip select')][2].options].map(o=>o.textContent).join(' / ') : '(无)'"));
  console.log('  悬停说明: ' + await ev("(document.querySelectorAll('.chip')[2]||{title:''}).title.slice(0,70)+'…'"));
  console.log('\n=== 列表顺序（编号 + 本周期新增）===');
  const rows = await ev(`[...document.querySelectorAll('.card-item')].slice(0,8).map(function(c){
      var pos=(c.querySelector('.rank')||{textContent:'-'}).textContent.trim();
      var g=(c.querySelector('.m.gain')||{textContent:'—'}).textContent.trim();
      var name=(c.querySelector('.repo-name')||{textContent:''}).textContent.trim();
      return pos.padStart(2)+'  '+g.padEnd(20)+' '+name;}).join('\\n  ')`);
  console.log('  ' + rows);
  const mono = await ev(`(function(){
      var nums=[...document.querySelectorAll('.card-item .m.gain')].map(function(e){
        var t=e.textContent.replace(/[^0-9.k]/g,'');
        if(t.indexOf('k')>0){ return Math.round(parseFloat(t)*1000); }
        return parseInt(t.replace(/,/g,''),10);}).filter(function(n){return !isNaN(n);});
      for(var i=1;i<nums.length;i++){ if(nums[i]>nums[i-1]) return false; }
      return true;})()`);
  console.log('\n  严格降序: ' + mono + '   （解析后的数值序列: ' + await ev(`(function(){var a=[];document.querySelectorAll('.card-item .m.gain').forEach(function(e){var t=e.textContent.replace(/[^0-9.k]/g,'');a.push(t.indexOf('k')>0?Math.round(parseFloat(t)*1000):parseInt(t.replace(/,/g,''),10));});return a.join(' > ');})()`) + '）');
  console.log('  控制台错误: ' + (errs.length?JSON.stringify(errs.slice(0,2)):'(无)'));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
