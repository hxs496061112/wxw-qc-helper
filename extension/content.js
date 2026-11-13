(()=>{
'use strict';
if(location.hostname!=='v3.wxwerp.com'||globalThis.__wxwQcLiveBooted)return;
globalThis.__wxwQcLiveBooted=true;
const ID='wxw-qc-live';
const onScanPage=()=>/^\/order\/startjob\/?$/.test(location.pathname);
const routeKey=()=>onScanPage()?location.pathname+'?taskId='+new URL(location.href).searchParams.get('taskId'):'';
let activeRoute='',observer=null;
let host=null,shadow=null,bound=null,pending=null,timer=null,lastKey='',renderedKey='',candidate='',candidateTime=0;
const clean=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
function counters(){
 const m=(document.body.innerText||'').match(/累计扫描\s*(\d+)\s*次\s*[,，]\s*成功\s*(\d+)\s*次\s*[,，]\s*失败\s*(\d+)\s*次/);
 return m?{all:+m[1],success:+m[2],fail:+m[3]}:null;
}
function sizeOf(name,spec){
 const a=[...name.matchAll(/[（(]\s*(\d{2}(?:\.\d)?)\s*[)）]/g)].map(x=>x[1]);
 const b=[...spec.matchAll(/(?:尺码|鞋码|码数|size)\s*[:：]?\s*(\d{2}(?:\.\d)?)/gi)].map(x=>x[1]);
 const end=spec.match(/[-－]\s*(\d{2}(?:\.\d)?)\s*$/);if(end)b.push(end[1]);
 const values=[...new Set([...a,...b].filter(v=>+v>=20&&+v<=55))];
 return values.length===1?values[0]:values.length>1?'尺码待核对':'尺码未识别';
}
function readRemarks(root,order,codes){
 const unknown={ready:false,remark:'',picking:''};
 const scope=root.closest('.el-card__body');
 if(!scope)return unknown;
 const headers=Array.from(scope.querySelectorAll(':scope>.listview table.vxe-table--header th'));
 const columns={};
 for(const name of ['平台订单号','运单号','备注','拣货备注']){
  const ids=[...new Set(headers.filter(e=>clean(e)===name).map(e=>Array.from(e.classList).find(c=>/^col_\d+$/.test(c))).filter(Boolean))];
  if(ids.length!==1)return unknown;
  columns[name]=ids[0];
 }
 const tokens=value=>value.split(/[,，;；\s]+/).filter(Boolean);
 const orders=new Set(tokens(order)),currentCodes=new Set(codes.flatMap(tokens));
 const rows=Array.from(scope.querySelectorAll(':scope>.listview table.vxe-table--body tbody tr'));
 const matched=new Map(),coveredOrders=new Set();
 for(const row of rows){
  const cell=name=>row.querySelector(':scope>td.'+columns[name]);
  const orderCell=cell('平台订单号'),trackingCell=cell('运单号');
  if(!orderCell||!trackingCell)continue;
  const ids=tokens(clean(orderCell)),tracking=clean(trackingCell);
  if(!ids.length||!ids.every(id=>orders.has(id))||!currentCodes.has(tracking))continue;
  const noteCell=cell('备注'),pickCell=cell('拣货备注');
  if(!noteCell||!pickCell)return unknown;
  const value=e=>{
   const text=((e.querySelector(':scope>.vxe-cell')||e).textContent||'').replace(/\r\n?/g,'\n').trim();
   return /^[-—–]?$/.test(text)?'':text;
  };
  const notes={remark:value(noteCell),picking:value(pickCell)};
  const key=JSON.stringify([ids.slice().sort(),tracking]);
  if(matched.has(key)&&JSON.stringify(matched.get(key))!==JSON.stringify(notes))return unknown;
  matched.set(key,notes);
  ids.forEach(id=>coveredOrders.add(id));
 }
 if(!matched.size||Array.from(orders).some(id=>!coveredOrders.has(id)))return unknown;
 const values=Array.from(matched.values());
 const join=field=>[...new Set(values.map(v=>v[field]).filter(Boolean))].join('\n\n');
 const notes={ready:true,remark:join('remark'),picking:join('picking')};
 // Avoid showing stale notes while the current banner and table update.
 const normalized=s=>s.replace(/\s+/g,' ').trim();
 const banners=Array.from(scope.querySelectorAll(':scope>.tips')).filter(visible).map(clean).filter(Boolean);
 if(banners.some(t=>![notes.remark,notes.picking].some(v=>normalized(v).includes(t))))return unknown;
 return notes;
}
function read(){
 const roots=Array.from(document.querySelectorAll('.center-body>.body-right')).filter(visible);
 if(roots.length!==1)return null;
 const root=roots[0],centers=Array.from(root.querySelectorAll(':scope>.right-center')).filter(visible),title=root.querySelector(':scope>.right-title');
 if(!centers.length||!title)return null;
 const totalCell=Array.from(title.children).find(e=>clean(e).startsWith('合计数量'));
 const total=clean(totalCell).match(/^合计数量\s*(\d+)$/);
 const order=root.parentElement.querySelector('.body-left .shop .PRIMARY');
 if(!order||!total||!+total[1])return null;
 const signs=centers.flatMap(center=>Array.from(center.querySelectorAll('.select-center :is(.sign,.sign-list)')).filter(visible).map(sign=>({center,sign})));
 if(!signs.length)return null;
 const items=[];
 for(const {center,sign} of signs){
  const n=clean(sign).match(/^[x×]\s*(\d+)$/i);if(!n||+n[1]<1)return null;
  let card=sign.parentElement;
  while(card&&card!==center&&!card.querySelector('.select-image img'))card=card.parentElement;
  if(!card||card===center||card.querySelectorAll('.select-image img').length!==1||card.querySelectorAll('.sign,.sign-list').length!==1)return null;
  const picture=card.querySelector('.select-image img'),names=card.querySelectorAll('.wrap');
  const name=clean(names[0]);if(!name)return null;
  const spec=clean(sign.parentElement.querySelector(':scope>div')).replace(clean(names[names.length-1]),'').trim();
  const raw=picture.currentSrc||picture.src;
  let url;try{url=new URL(raw,location.href);if(url.protocol!=='https:')return null;}catch{return null;}
  items.push({name,spec,qty:+n[1],pic:url.href,size:sizeOf(name,spec)});
 }
 if(items.reduce((n,i)=>n+i.qty,0)!==+total[1])return null;
 const status=Array.from(title.children).map(clean).filter(t=>/已作废|已发货|待发货|配货|异常|取消/.test(t)).join(' / ');
 const codes=Array.from(root.parentElement.querySelectorAll('.body-left .shop')).map(clean);
 return {root,codes,order:clean(order),total:+total[1],status,items,remarks:readRemarks(root,clean(order),codes)};
}
const style='*{box-sizing:border-box}:host{font:14px \"Microsoft YaHei\",sans-serif;color:#203e33}.panel{container-type:inline-size;background:#fff;border:2px solid #28674d;border-radius:10px;overflow:hidden}.details{display:grid;grid-template-columns:minmax(0,1fr) 300px;align-items:start}.details.no-remarks{grid-template-columns:minmax(0,1fr)}.remarks[hidden]{display:none}.remarks{padding:12px 12px 12px 0;display:grid;gap:14px;min-width:0}.remark-box{padding:16px;border:2px solid #d84c42;border-radius:9px;background:#fff1ec;min-width:0}.remark-label{font-size:17px;font-weight:800;color:#a62b22;margin-bottom:10px}.remark-text{font-size:26px;font-weight:800;line-height:1.5;color:#a4231b;white-space:pre-wrap;overflow-wrap:anywhere}@container(max-width:1230px){.details.multiple{grid-template-columns:minmax(0,1fr)}.details.multiple>.remarks{padding:0 12px 12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr))}}@container(max-width:750px){.details{grid-template-columns:minmax(0,1fr)}.remarks{padding:0 12px 12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr))}}.items{padding:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px;align-items:start}.item{min-width:0}.item:only-child{border:0}.item:not(:only-child){border:1px solid #dce8de;border-radius:8px;padding:10px}.photo{width:100%;height:auto;aspect-ratio:1 / 1;max-height:420px;display:block;object-fit:contain;background:#f4f6f2;border-radius:7px}.spec{display:flex;justify-content:center;align-items:center;gap:24px;flex-wrap:wrap;text-align:center;margin:10px 0}.size{font-size:68px;line-height:1.1;font-weight:800;color:#000}.size small{font-size:18px;margin-left:5px}.unknown{font-size:24px;color:#a35d20}.quantity{background:#eef3ed;padding:9px 12px;border-radius:8px;text-align:center}.quantity small{display:block;font-size:12px}.quantity b{display:block;font-size:32px;font-weight:500}.quantity.alert{background:#fff0ef;border:2px solid #d52b2b;color:#bd2020}.quantity.alert b,.quantity.alert small{font-weight:800}.name{text-align:center;font-size:28px;font-weight:800;line-height:1.35;overflow-wrap:anywhere}.name+.props{text-align:center}.props{font-size:12px;color:#6b7c70;line-height:1.5;overflow-wrap:anywhere;margin-top:5px}.empty{padding:38px 18px;text-align:center;color:#8a632f;font-size:16px;line-height:1.8}.failed-image{height:120px;display:grid;place-items:center;color:#a4482d}';
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function mount(root){
 if(bound===root&&host?.isConnected)return;
 if(bound)bound.classList.remove('wxw-qc-layout');
 host?.remove();root.querySelector(':scope>#'+ID)?.remove();bound=root;host=document.createElement('section');host.id=ID;host.dataset.version='0.6.1';host.setAttribute('aria-label','质检放大');
 shadow=host.attachShadow({mode:'open'});const css=el('style');css.textContent=style+'.order-total{margin:12px 12px 0;padding:12px;display:flex;align-items:center;justify-content:center;gap:16px;flex-wrap:wrap}.order-total small{font-size:24px;font-weight:800;line-height:1.2}.order-total b{font-size:36px;font-weight:800;line-height:1.2}';shadow.append(css);
 root.classList.add('wxw-qc-layout');root.append(host);lastKey='';renderedKey='';
}
const productKey=data=>JSON.stringify({order:data.order,total:data.total,items:data.items});
function drawRemarks(details,data){
 const remarks=el('aside','remarks');remarks.dataset.state=data.remarks.ready?'ready':'pending';
 for(const [field,label] of [['remark','备注'],['picking','拣货备注']]){
  const value=data.remarks[field];
  if(!data.remarks.ready||!value.trim())continue;
  const box=el('section','remark-box important');box.dataset.field=field;
  box.append(el('div','remark-label',label),el('div','remark-text',value));remarks.append(box);
 }
 details.classList.toggle('no-remarks',!remarks.childElementCount);
 if(remarks.childElementCount)remarks.setAttribute('aria-label','当前订单备注');
 else {remarks.hidden=true;remarks.setAttribute('aria-hidden','true');}
 const previous=details.querySelector(':scope>.remarks');
 if(previous)previous.replaceWith(remarks);else details.append(remarks);
}
function draw(data,message){
 const currentProductKey=data?productKey(data):'';
 const key=message||JSON.stringify({product:currentProductKey,remarks:data.remarks});
 if(key===lastKey)return;lastKey=key;
 const hasRemarks=!!data?.remarks.ready&&[data.remarks.remark,data.remarks.picking].some(value=>value.trim());
 if(data)host.style.setProperty('--wxw-qc-width',String(Math.min(data.items.length,3)*480+Math.max(0,Math.min(data.items.length,3)-1)*14+(hasRemarks?300:0))+'px');
 const prev=shadow.querySelector('.panel');
 // Late notes must never tear down already rendered SKU cards or images.
 if(!message&&prev&&renderedKey===currentProductKey){drawRemarks(prev.querySelector('.details'),data);return;}
 const panel=el('div','panel');
 if(message)panel.append(el('div','empty',message));
 else{
  const total=el('div','quantity order-total'+(data.total>=2?' alert':''));
  total.append(el('small','','本单合计'),el('b','','× '+data.total));panel.append(total);
  const list=el('div','items');
  data.items.forEach((item,i)=>{
   const card=el('article','item');if(data.items.length>1)card.append(el('div','props','商品 '+(i+1)+' / '+data.items.length+' · 请逐项核对'));
   const img=el('img','photo');img.alt=item.name;img.referrerPolicy='no-referrer';img.src=item.pic;
   img.addEventListener('error',()=>img.replaceWith(el('div','failed-image','图片加载失败，请看原页面')),{once:true});
   const spec=el('div','spec'),size=el('div','size'+(/^\d/.test(item.size)?'':' unknown'),item.size);
   if(/^\d/.test(item.size))size.append(el('small','','码'));
   const qty=el('div','quantity'+(item.qty>=2?' alert':''));qty.append(el('small','','应有数量'),el('b','','× '+item.qty));spec.append(size,qty);
   card.append(img,spec,el('div','name',item.name),el('div','props',item.spec));list.append(card);
  });
  const details=el('div','details'+(data.items.length>1?' multiple':''));
  details.append(list);drawRemarks(details,data);panel.append(details);
 }
 if(prev)prev.replaceWith(panel);else shadow.append(panel);
 renderedKey=message?'':currentProductKey;
}
// Bound the delay: unrelated animations must not postpone rendering forever.
function schedule(){if(timer===null)timer=setTimeout(()=>{timer=null;update();},150);}
function detach(){
 host?.remove();bound?.classList.remove('wxw-qc-layout');
 host=null;shadow=null;bound=null;lastKey='';renderedKey='';candidate='';
}
function syncRoute(){
 const next=routeKey();
 if(next===activeRoute)return;
 observer?.disconnect();observer=null;
 clearTimeout(timer);timer=null;detach();pending=null;candidateTime=0;
 activeRoute=next;
 if(next){
  observer=new MutationObserver(records=>{
   if(records.some(r=>!host?.contains(r.target)))schedule();
  });
  observer.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['src','style','class']});
 }
}
function update(){
 syncRoute();
 if(!activeRoute)return;
 const data=read();
 const root=data?.root||Array.from(document.querySelectorAll('.center-body>.body-right')).find(visible);
 if(!root){detach();return;}
 mount(root);
 host.style.setProperty('--wxw-qc-rows',String(Array.from(root.querySelectorAll(':scope>.right-center')).filter(visible).length||1));
 if(pending){
  const c=counters();
  if(c&&pending.counter&&c.fail>pending.counter.fail){draw(null,'本次扫码失败，请核对原页面');return;}
  if(!c||!pending.counter||c.success<=pending.counter.success){draw(null,'等待本次扫码结果，上一单已清除');return;}
 }
 if(pending?.code&&data&&!data.codes.some(c=>c===pending.code||c.endsWith(' '+pending.code))){draw(null,'等待当前扫描码对应的订单，请核对原页面');return;}
 if(!data){candidate='';draw(null,'当前商品信息不完整，请核对原页面');return;}
 const sig=productKey(data);
 if(sig!==candidate){candidate=sig;candidateTime=Date.now();draw(null,'正在核对当前单…');schedule();return;}
 if(Date.now()-candidateTime<140){schedule();return;}
 pending=null;draw(data);
}
function begin(code){syncRoute();if(!activeRoute)return;pending={counter:counters(),code:code||null};candidate='';lastKey='';if(shadow)draw(null,'等待本次扫码结果，上一单已清除');schedule();}
document.addEventListener('input',e=>{if(e.target.matches('input#scanInput,input[name="scanInput"]')&&e.target.value&&!pending)begin();},true);
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('input#scanInput,input[name="scanInput"]'))begin(e.target.value.trim());},true);
document.addEventListener('click',e=>{const b=e.target.closest('button');if(b&&clean(b)==='扫描')begin(document.getElementById('scanInput')?.value.trim());},true);
// pushState/replaceState do not emit popstate. A small route heartbeat handles
// SPA entry and recovers if the framework replaces the result subtree.
window.addEventListener('popstate',schedule);
window.addEventListener('pageshow',schedule);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)schedule();});
setInterval(()=>{syncRoute();if(activeRoute)schedule();},500);
schedule();
})();
