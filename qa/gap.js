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
  await send('Page.enable');await send('Runtime.enable');
  await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
  await send('Emulation.setDeviceMetricsOverride',{width:1560,height:1008,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:8080/?v=G1#/trending'});
  await sleep(5000);
  console.log(await ev(`(function(){
    function R(e){var b=e.getBoundingClientRect();return {l:Math.round(b.left),r:Math.round(b.right),t:Math.round(b.top),b:Math.round(b.bottom)};}
    var card=document.querySelector('.card'), chips=[...document.querySelectorAll('.chip')];
    var model=document.querySelector('.model'), att=document.querySelector('.attach'), send=document.querySelector('.send');
    var nav=document.querySelector('.nav')||document.querySelector('header');
    var h1=document.querySelector('.h1');
    var c=R(card), lastChip=R(chips[chips.length-1]), m=R(model);
    var out=[];
    out.push('【工具栏这一行，水平方向】');
    out.push('  卡片        '+c.l+' .. '+c.r+'   (宽 '+(c.r-c.l)+')');
    out.push('  三个选项    '+R(chips[0]).l+' .. '+lastChip.r+'   (占 '+(lastChip.r-R(chips[0]).l)+')');
    out.push('  周期文案    '+m.l+' .. '+m.r);
    out.push('  刷新键      '+R(send).l+' .. '+R(send).r);
    out.push('  → 选项右边到周期左边，中间空档 = '+(m.l-lastChip.r)+' px  (占整条 '+
      Math.round((m.l-lastChip.r)/(c.r-c.l)*100)+'%)');
    out.push('  → 整条左端到选项 = '+(R(chips[0]).l-c.l)+' px，刷新键到右端 = '+(c.r-R(send).r)+' px');
    out.push('');
    out.push('【首屏，垂直方向】(视口高 '+window.innerHeight+')');
    var n=R(nav);
    out.push('  导航底      '+n.b);
    out.push('  标题        '+R(h1).t+' .. '+R(h1).b);
    out.push('  工具栏      '+c.t+' .. '+c.b);
    out.push('  → 导航底到标题之间空 = '+(R(h1).t-n.b)+' px');
    out.push('  → 标题底到工具栏之间空 = '+(c.t-R(h1).b)+' px');
    out.push('  → 工具栏底到首屏底空 = '+(window.innerHeight-c.b)+' px');
    out.push('  → 首屏被内容占据的比例 ≈ '+Math.round(((c.b-n.b)/(window.innerHeight-n.b))*100)+'%');
    return out.join('\\n');})()`));
  process.exit(0);
})().catch(e=>{console.error('FAILED',e.message);process.exit(1);});
