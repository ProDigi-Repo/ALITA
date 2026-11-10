/* ---------- 3.7.0 (REQ-59): compare the clusters of two databases ----------
   Every database is clustered on its own, so the knowledge map has no lines between, e.g., EU AI Act and Wachter.
   The dropdown "Compare" on the B page asks the backend (/api/clusters/relations) how similar the clusters of two
   databases are (centroid of their summary vectors, documents whose closest cluster in the other database is the
   partner) and draws these relations as violet dashed lines on the map (2D and 3D). Clicking a relation selects both
   clusters, so the Graph Chat re-queries inside them across both databases. */
const XC={pair:'',data:null,key:'',busy:false};
try{XC.pair=localStorage.getItem('xc_pair')||''}catch(e){}
const XC_COL='#7c4dff';
/* databases that have clustered units right now (visible ones only, see the password gate) */
function xcDbs(){const u=typeof cvUnits==='function'?cvUnits():[];return DATABASES.filter(n=>u.some(x=>(x.db||[]).includes(n)))}
function xcPairs(){
  const d=xcDbs(),pub=typeof PUBLIC_DBS!=='undefined'?PUBLIC_DBS:[],out=[];
  for(let i=0;i<d.length;i++)for(let j=i+1;j<d.length;j++)out.push([d[i],d[j]]);
  return out.sort((a,b)=>(b.filter(x=>pub.includes(x)).length-a.filter(x=>pub.includes(x)).length));   // EU AI Act ↔ Wachter first
}
function xcRenderSelect(){
  const sel=$('#cgCompare');if(!sel)return;
  const pairs=xcPairs(),val=pairs.some(p=>p.join('|')===XC.pair)?XC.pair:'';
  if(val!==XC.pair){XC.pair=val;XC.data=null}
  sel.innerHTML=`<option value="">No comparison</option>`+pairs.map(p=>`<option value="${esc(p.join('|'))}">${esc(dbName(p[0]))} ↔ ${esc(dbName(p[1]))}</option>`).join('');
  sel.value=XC.pair;sel.disabled=!pairs.length;
  sel.title=pairs.length?'Draw the relations between the clusters of two databases on the map':'Needs clustered documents in at least two visible databases';
}
/* demo / no backend: approximate the relations from the 2D map positions of the units */
function xcApprox(dbs){
  const units=cvUnits().filter(u=>(u.db||[]).some(n=>dbs.includes(n))),by={};
  units.forEach(u=>{const db=dbs.find(n=>(u.db||[]).includes(n));const c=by[u.ci]||(by[u.ci]={cluster_id:u.ci,database:db,size:0,x:0,y:0,m:[]});c.size++;c.x+=u.cx;c.y+=u.cy;c.m.push(u)});
  const cl=Object.values(by);cl.forEach(c=>{c.x/=c.size;c.y/=c.size});
  const sim=(a,b)=>Math.max(0,1-Math.hypot(a.x-b.x,a.y-b.y)/2.83),links=[];
  cl.forEach(a=>cl.forEach(b=>{if(a.cluster_id<b.cluster_id&&a.database!==b.database)links.push({source:a.cluster_id,target:b.cluster_id,similarity:+sim(a,b).toFixed(3),bridges:0,databases:[a.database,b.database]})}));
  const keep=new Set();cl.forEach(c=>{const best=links.filter(l=>l.source===c.cluster_id||l.target===c.cluster_id).sort((x,y)=>y.similarity-x.similarity)[0];if(best)keep.add(best)});
  links.filter(l=>l.similarity>=0.55).forEach(l=>keep.add(l));
  return {databases:dbs,clusters:cl.map(({m,x,y,...c})=>c),links:[...keep].sort((x,y)=>y.similarity-x.similarity),approx:true};
}
async function xcLoad(){
  if(!XC.pair){XC.data=null;XC.key='';return}
  const dbs=XC.pair.split('|'),key=XC.pair+'|'+(DOCS.length);
  if(XC.key===key&&XC.data)return;
  XC.busy=true;
  try{
    if(LIVE){const r=await fetch('api/clusters/relations?databases='+encodeURIComponent(dbs.join(',')));if(!r.ok)throw new Error('HTTP '+r.status);XC.data=await r.json()}
    else XC.data=xcApprox(dbs);
    XC.key=key;
  }catch(e){XC.data=null;try{toast('Cluster comparison not available: '+e.message)}catch(_){}}
  XC.busy=false;
}
/* relations between clusters that are on the map now: [{a,b,s,n,dbs}] */
function xcLinks(ids){
  if(!XC.pair||!XC.data)return [];
  const on=ids?new Set(ids):null;
  return (XC.data.links||[]).map(l=>({a:l.source,b:l.target,s:l.similarity,n:l.bridges||0,dbs:l.databases||[]})).filter(l=>!on||(on.has(l.a)&&on.has(l.b)));
}
function xcDbOf(id){const c=((XC.data||{}).clusters||[]).find(x=>x.cluster_id===id);return c?c.database:null}
function xcTipHtml(l,info){
  const nm=id=>{const c=(typeof cvClusters==='function'?cvClusters(cvUnits()):[]).find(x=>x.id===id);return `C${id} ${esc(c?cvName(c,info):'')} <small>(${esc(dbName(xcDbOf(id)||''))})</small>`};
  return `<b>${nm(l.a)}<br>↔ ${nm(l.b)}</b><br>similarity ${l.s.toFixed(2)}${l.n?` · ${l.n} document${l.n>1?'s':''} closest to the other cluster`:''}${XC.data&&XC.data.approx?'<br><i>approximate (demo)</i>':''}<br><i>click to select both clusters for the Graph Chat</i>`;
}
/* click on a relation: both clusters become the search space of the chats (across both databases) */
function xcSelect(l){
  CV.sels=new Set([l.a,l.b]);
  if(typeof CG!=='undefined'){CG.sel=null;CG.proj=null}   // a project scope would hide the other database
  cvChanged();renderClusterPage();   // both databases stay selected by the comparison
  try{toast(`C${l.a} and C${l.b} selected – the Graph Chat now searches both clusters`)}catch(e){}
}
function xcAsk(l,info){
  xcSelect(l);
  const inp=$('#graphInput');if(!inp)return;
  const cl=typeof cvClusters==='function'?cvClusters(cvUnits()):[],nm=id=>{const c=cl.find(x=>x.id===id);return c?cvName(c,info):'C'+id};
  inp.value=`Compare C${l.a} (${nm(l.a)}, ${dbName(xcDbOf(l.a)||'')}) with C${l.b} (${nm(l.b)}, ${dbName(xcDbOf(l.b)||'')}): where do they agree, where do they differ?`;
  inp.focus();inp.scrollIntoView({block:'center',behavior:'smooth'});
}
/* side panel section of the B page */
function xcSideHtml(info){
  if(!XC.pair)return '';
  const dbs=XC.pair.split('|'),links=xcLinks();
  if(XC.busy)return `<h4>${esc(dbName(dbs[0]))} ↔ ${esc(dbName(dbs[1]))}</h4><p class="srcnote">Loading …</p>`;
  if(!XC.data)return `<h4>${esc(dbName(dbs[0]))} ↔ ${esc(dbName(dbs[1]))}</h4><p class="srcnote">No comparison available.</p>`;
  const cl=cvClusters(cvUnits()),nm=id=>{const c=cl.find(x=>x.id===id);return c?cvName(c,info):''};
  return `<h4>Cluster relations ${esc(dbName(dbs[0]))} ↔ ${esc(dbName(dbs[1]))}</h4><p class="srcnote" style="margin:0">Violet dashed lines on the map${XC.data.approx?' (approximate in the demo)':''}. Select a pair to ask the Graph Chat inside both clusters.</p><div class="cglist">`+
    (links.length?links.map((l,k)=>`<div class="xc-item"><span><b>C${l.a}</b> ${esc(nm(l.a))} <small>${esc(dbName(xcDbOf(l.a)||''))}</small> ↔ <b>C${l.b}</b> ${esc(nm(l.b))} <small>${esc(dbName(xcDbOf(l.b)||''))}</small><br><small>similarity ${l.s.toFixed(2)}${l.n?` · ${l.n} bridging document${l.n>1?'s':''}`:''}</small></span><span class="xc-act"><button class="mini" type="button" data-xc-sel="${k}">Select</button><button class="mini" type="button" data-xc-ask="${k}">Ask</button></span></div>`).join(''):'<p class="srcnote">No clusters with a summary vector in both databases.</p>')+'</div>';
}
function xcWireSide(info){
  const links=xcLinks();
  $$('#cgSide [data-xc-sel]').forEach(b=>b.addEventListener('click',()=>xcSelect(links[+b.dataset.xcSel])));
  $$('#cgSide [data-xc-ask]').forEach(b=>b.addEventListener('click',()=>xcAsk(links[+b.dataset.xcAsk],info)));
}
async function xcChange(v){
  XC.pair=v;XC.data=null;try{v?localStorage.setItem('xc_pair',v):localStorage.removeItem('xc_pair')}catch(e){}
  if(v){const dbs=v.split('|');if(dbs.some(n=>!SEL_DB.includes(n))||SEL_DB.length!==dbs.length)setDbSel(dbs)}   // both databases on the map and in the chats
  renderClusterPage();await xcLoad();renderClusterPage();
}
(function(){const sel=$('#cgCompare');if(sel)sel.addEventListener('change',()=>xcChange(sel.value))})();
