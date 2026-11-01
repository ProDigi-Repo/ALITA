/* Clusters – B page (knowledge map column, Enlarge, resize), cluster selection list and the database overlay mode. */
/* ---------- Cluster Graph page (graph approach only) ---------- */
const CG={sel:null,mode:'type'};
try{CG.mode=localStorage.getItem('cg_mode')==='db'?'db':'type'}catch(e){}
function cgSync(){$$('#cgMode button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.m===CG.mode))}
cgSync();
$$('#cgMode button').forEach(b=>b.addEventListener('click',()=>{CG.mode=b.dataset.m;try{localStorage.setItem('cg_mode',CG.mode)}catch(e){}cgSync();renderClusterPage()}));
/* REQ-02: the B page fills exactly the window height – the four areas scroll inside, the knowledge map never leaves the screen */
/* B page: a click on a cluster works as on the A/B Interaction Interface – it selects the cluster for the chats
   (again = deselect, several possible) and its description appears at the top of "Projects & clusters" */
function cgPick(id){
  cvSelect(id);
  CG.sel=cvHas(id)?id:(CG.sel===id?([...CV.sels].pop()??null):CG.sel);
  renderClusterPage();
  const b=$('#page-graph .bq-cluster .bq-body');if(b)b.scrollTop=0;
}
let B_FIT_H=0;
const B_MAP_MAX_H=1600;   // drawing height cap of the knowledge map (REQ-28: it now fills a full-height column)
function fitBPage(){
  const pg=$('#page-graph'),g=pg&&pg.querySelector('.bgrid');if(!g||pg.hidden)return;
  if(matchMedia('(max-width:1100px)').matches){g.style.removeProperty('--bH');return}
  const top=g.getBoundingClientRect().top+scrollY,h=Math.max(700,Math.floor(innerHeight-top-14));
  if(Math.abs(h-B_FIT_H)<4)return;B_FIT_H=h;g.style.setProperty('--bH',h+'px');try{renderClusterPage()}catch(e){}
}
/* REQ-33: "⤢ Enlarge" – the knowledge map as a large window over the page (Esc, ✕ or a click beside it to go back) */
function cgMax(on){
  const s=$('#page-graph .bq-map'),b=$('#cgMax'),sc=$('#cgMaxScrim');if(!s||!b)return;
  s.classList.toggle('maxed',on);sc.hidden=!on;b.setAttribute('aria-pressed',String(on));
  b.textContent=on?'✕ Close':'⤢ Enlarge';b.title=on?'Back to the normal size (Esc)':'Enlarge the knowledge map';
  try{renderClusterPage()}catch(e){}   // the class change is laid out synchronously, so the map is redrawn at the new size right away
}
/* window resize: new height → fitBPage; new width → lay the map out again (REQ-26) */
function onBResize(){
  fitBPage();const m=$('#page-graph .bq-map');if(!m||$('#page-graph').hidden)return;
  const w=m.clientWidth;if(Math.abs(w-(onBResize.w||0))>8){onBResize.w=w;try{renderClusterPage()}catch(e){}}
}
(function wireBPage(){
  const btn=$('#cgMax'),scrim=$('#cgMaxScrim'),isMax=()=>!!$('#page-graph .bq-map.maxed');
  if(btn)btn.addEventListener('click',()=>cgMax(!isMax()));
  if(scrim)scrim.addEventListener('click',()=>cgMax(false));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&isMax()&&!(typeof S3!=='undefined'&&S3.open))cgMax(false)});
  addEventListener('resize',()=>{clearTimeout(onBResize.t);onBResize.t=setTimeout(onBResize,120)});
})();
addEventListener('load',()=>setTimeout(fitBPage,50));
/* every drawing of the B page is announced, so the citation network and the map window can follow (state.js) */
function renderClusterPage(){const r=renderClusterPageView.apply(this,arguments);Store.emit('cluster-page');return r}
function renderClusterPageView(){
  if(typeof cpRenderSel==='function')cpRenderSel();
  if($('#page-graph').hidden)return;
  const units=cvUnits(),cls=cvClusters(units),info=clusterInfo();
  if(typeof xcRenderSelect==='function'){xcRenderSelect();if(XC.pair&&!XC.data&&!XC.busy)xcLoad().then(()=>{if(XC.data)renderClusterPage()})}   // REQ-59
  if(CG.sel!=null&&!cls.find(c=>c.id===CG.sel))CG.sel=null;
  const box=$('#cgGraph');
  if(units.length<2){box.innerHTML='<div class="cv-empty" style="height:360px">No cluster analysis yet.</div>';$('#cgSide').innerHTML='';$('#cgLegend').innerHTML='';$('#cgMeta').textContent='';return}
  const r=renderClusterGraph(units,cls,{big:true,box});
  if(V3.on)mountGraph3D(units,cls,box,'graphB',Math.round(Math.min(B_MAP_MAX_H,Math.max(240,box.parentElement.clientHeight||480))));   // same 2D/3D switch as on A/B
  const run=(!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.run)||'';
  const nx=typeof xcLinks==='function'?xcLinks(r.act.map(c=>c.id)).length:0;
  $('#cgMeta').textContent=`${r.act.length} clusters · ${units.filter(u=>u.on).length} documents · ${r.links.length} bridges${nx?` · ${nx} cross-database relation${nx>1?'s':''}`:''}${SEL_DB.length?' · '+dbNames(SEL_DB).join('+'):''}${run?' · run '+run.slice(0,10):''}`;
  const dbs=DATABASES.filter(n=>units.some(u=>u.on&&(u.db||[]).includes(n)));
  $('#cgLegend').innerHTML=(CG.mode==='db'?dbs.map(n=>`<span><i style="--c:var(--db-${n})"></i>${esc(dbName(n))}</span>`).join(''):`<span><i style="--c:var(--t-paper);border-radius:2px"></i>Paper</span><span><i style="--c:var(--t-notes)"></i>Note</span><span><i style="--c:var(--t-project);transform:rotate(45deg);border-radius:1px"></i>Project</span>`+[...new Set(units.filter(u=>LEGAL_T.has(u.t)).map(u=>u.t))].map(t=>`<span><i style="--c:${TYPE_COLOR[t]};border-radius:0;clip-path:polygon(50% 0,100% 100%,0 100%)"></i>${esc(CV_TYPE[t])}</span>`).join(''))+
    (dbs.length>1?`<span class="cg-flw">${dbs.map(n=>`<i style="color:var(--db-${n})">${DB_FLOWER[n]||''}</i>${esc(dbName(n))}`).join(' ')}</span>`:'')+
    `<span>Node = cluster (size = documents) · line = documents whose second-closest cluster is the other node (number on the line)${nx?' · <b style="color:#7c4dff">violet dashed</b> = relation between clusters of the compared databases (similarity)':''} · click a cluster for details, a document to open it</span>`;
  const dbsAll=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
  let h=typeof xcSideHtml==='function'?xcSideHtml(info):'';   // REQ-59: cross-database relations first
  // the cluster list always stays (the separate detail view was removed – descriptions of the selected clusters sit above the list)
  h+=`<h4>Clusters (${r.act.length})</h4><p class="srcnote" style="margin:0">Click a cluster to select it for the chats and read its description above. The database selection in the bar above applies here too.</p><div class="cglist">`+
    r.act.map(c=>`<button class="cgitem" type="button" data-c="${c.id}" aria-pressed="${cvHas(c.id)}" style="--h:${cvHue(c.id)}"><b>C${c.id}</b><span>${esc(cvName(c,info))}<br><small>${esc(c.label)}</small></span><small>${c.on.length}</small></button>`).join('')+'</div>';
  const ranked=[...r.links].sort((a,b)=>b.n-a.n).slice(0,5);
  if(ranked.length)h+=`<h4>Strongest bridges</h4><div class="cglist">${ranked.map(l=>`<div class="srcnote">C${l.a} ↔ C${l.b}: ${l.n} document${l.n>1?'s':''} · similarity ${l.s.toFixed(2)}</div>`).join('')}</div>`;
  $('#cgSide').innerHTML=h;
  try{cgRenderProj(units)}catch(e){console.error('project card',e)}
  $$('#cgSide .cgitem').forEach(b=>b.addEventListener('click',()=>cgPick(+b.dataset.c)));
  if(typeof xcWireSide==='function')xcWireSide(info);
  $$('#cgSide [data-cl]').forEach(b=>b.addEventListener('click',()=>{cvSelect(+b.dataset.cl,true);try{toast('C'+b.dataset.cl+' selected for both chats')}catch(e){}}));   // REQ-02: stay on the B page
  $$('#cgSide [data-ask]').forEach(b=>b.addEventListener('click',()=>{const c=cls.find(x=>x.id===+b.dataset.ask);const inp=$('#graphInput');if(inp){inp.value=`What connects the documents in cluster C${c.id} (${cvName(c,info)})?`;inp.focus();inp.scrollIntoView({block:'center',behavior:'smooth'})}}));
  $$('#cgSide details [data-open]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();openDoc(a.dataset.open)}));
}
if(window.ResizeObserver){let t2;new ResizeObserver(()=>{clearTimeout(t2);t2=setTimeout(renderClusterPage,120)}).observe($('#cgGraph'))}
if(window.ResizeObserver){let t;new ResizeObserver(()=>{clearTimeout(t);t=setTimeout(renderClusterViz,120)}).observe($('#cviz'))}
$('#rCluster').addEventListener('change',()=>{const v=$('#rCluster').value;CV.sels=v===''?new Set():new Set([+v]);cvChanged()});


/* ---------- Compare databases: overlay the clusters of each selected database ---------- */
CV.mode='cluster';try{CV.mode=localStorage.getItem('cv_mode')==='db'?'db':'cluster'}catch(e){}
function cvSyncMode(){$$('#cvMode button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.m===CV.mode))}
cvSyncMode();
$$('#cvMode button').forEach(b=>b.addEventListener('click',()=>{CV.mode=b.dataset.m;try{localStorage.setItem('cv_mode',CV.mode)}catch(e){}cvSyncMode();renderClusterViz()}));
function cvDbList(units){const has=n=>units.some(u=>(u.db||[]).includes(n));return (SEL_DB.length?SEL_DB:DATABASES).filter(has)}
function cvHull(pts){
  const P=[...new Map(pts.map(p=>[p[0].toFixed(1)+','+p[1].toFixed(1),p])).values()].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  if(P.length<3)return P;
  const cr=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);const lo=[],up=[];
  for(const p of P){while(lo.length>=2&&cr(lo[lo.length-2],lo[lo.length-1],p)<=0)lo.pop();lo.push(p)}
  for(const p of [...P].reverse()){while(up.length>=2&&cr(up[up.length-2],up[up.length-1],p)<=0)up.pop();up.push(p)}
  return lo.slice(0,-1).concat(up.slice(0,-1));
}
function cvInHull(h,x,y,pad){
  if(h.length>=3){let ins=false;for(let i=0,j=h.length-1;i<h.length;j=i++){const [xi,yi]=h[i],[xj,yj]=h[j];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)ins=!ins}if(ins)return true}
  if(h.length===1)return Math.hypot(x-h[0][0],y-h[0][1])<=pad;
  for(let i=0;i<h.length;i++){const a=h[i],b=h[(i+1)%h.length],dx=b[0]-a[0],dy=b[1]-a[1],L=dx*dx+dy*dy||1;let t=((x-a[0])*dx+(y-a[1])*dy)/L;t=Math.max(0,Math.min(1,t));if(Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy)<=pad)return true}
  return false;
}
function cvDbOverlay(units,cls,X,Y,W,H){
  const dbs=cvDbList(units),PAD=13;
  const layers=dbs.map(n=>({n,col:`var(--db-${n})`,units:units.filter(u=>(u.db||[]).includes(n)),hulls:[]}));
  let g='';
  layers.forEach(L=>{
    const byC={};L.units.forEach(u=>(byC[u.ci]=byC[u.ci]||[]).push([X(u.cx),Y(u.cy)]));
    Object.entries(byC).forEach(([c,pts])=>{
      const h=cvHull(pts);L.hulls.push(h);const dim=cvOff(+c);
      const d=h.length===1?`M${h[0][0]} ${h[0][1]}l0.01 0`:'M'+h.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join('L')+(h.length>2?'Z':'');
      g+=`<path class="pt ov" data-c="${c}" d="${d}" fill="${L.col}" fill-opacity="${dim?.04:.28}" stroke="${L.col}" stroke-opacity="${dim?.04:.28}" stroke-width="${PAD*2}" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
  });
  const shown=units.filter(u=>(u.db||[]).some(n=>dbs.includes(n)));
  shown.forEach(u=>{const n=(u.db||[]).find(x=>dbs.includes(x));const dim=cvOff(u.ci);
    g+=`<g class="pt" data-u="${u.id||''}" data-p="${u.t==='research_project'?esc(u.pn):''}" data-c="${u.ci}">${cvShape(u,X(u.cx),Y(u.cy),`var(--db-${n})`,dim)}</g>`});
  cls.forEach(c=>{const m=shown.filter(u=>u.ci===c.id);if(!m.length)return;const mx=m.reduce((a,u)=>a+X(u.cx),0)/m.length,my=m.reduce((a,u)=>a+Y(u.cy),0)/m.length;const dim=cvOff(c.id);
    g+=`<g class="pt" data-c="${c.id}" opacity="${dim?.3:.92}"><rect x="${mx-14}" y="${my-25}" width="28" height="15" rx="7.5" fill="#3a434c"/><text x="${mx}" y="${my-14}" text-anchor="middle" font-size="10.5" font-weight="700" style="fill:#fff">C${c.id}</text></g>`});
  // area overlap per pair of databases (grid sampling of the padded hulls)
  const cell=5,inside=layers.map(()=>0),both={};
  for(let x=cell/2;x<W;x+=cell)for(let y=cell/2;y<H;y+=cell){
    const hit=layers.map(L=>L.hulls.some(h=>cvInHull(h,x,y,PAD)));
    hit.forEach((v,i)=>{if(v)inside[i]++});
    for(let i=0;i<layers.length;i++)for(let j=i+1;j<layers.length;j++){const k=i+'-'+j;both[k]=both[k]||{and:0,or:0};if(hit[i]&&hit[j])both[k].and++;if(hit[i]||hit[j])both[k].or++}
  }
  const pairs=[];for(let i=0;i<layers.length;i++)for(let j=i+1;j<layers.length;j++){const b=both[i+'-'+j];
    const shared=cls.filter(c=>layers[i].units.some(u=>u.ci===c.id)&&layers[j].units.some(u=>u.ci===c.id)).map(c=>'C'+c.id);
    pairs.push({a:layers[i].n,b:layers[j].n,iou:b&&b.or?Math.round(b.and/b.or*100):0,shared})}
  const key=layers.map(L=>`<span class="dbk" style="--c:${L.col}"><i></i>${esc(L.n)} · ${L.units.length}</span>`).join('');
  const sum=layers.length<2?`<span class="srcnote">Select two or more databases in the bar above to overlay their clusters.</span>`:
    pairs.map(p=>`<span title="Share of the map area covered by either database that both cover (padded cluster areas)"><b>${esc(dbName(p.a))} ∩ ${esc(dbName(p.b))}</b>: area overlap ${p.iou}% · ${p.shared.length?`shared clusters ${p.shared.join(', ')}`:'no shared cluster'}</span>`).join('');
  const rows=cls.map(c=>{
    const per=layers.map(L=>({L,n:L.units.filter(u=>u.ci===c.id).length})),tot=per.reduce((a,x)=>a+x.n,0);if(!tot)return '';
    const present=per.filter(x=>x.n);const tag=present.length>1?'<span class="tag shared">shared</span>':`<span class="tag only">only ${esc(present[0].L.n)}</span>`;
    return `<button type="button" class="row" data-c="${c.id}" aria-pressed="${cvHas(c.id)}" title="${esc(per.map(x=>x.L.n+': '+x.n).join(' · '))} – click to filter the Document Chat"><b>C${c.id}</b><span class="lb">${esc(c.label)}</span><span class="bar">${per.filter(x=>x.n).map(x=>`<i style="--c:${x.L.col};width:${x.n/tot*100}%"></i>`).join('')}</span>${tag}</button>`}).join('');
  return {dbs,svg:`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cluster map: clusters of the selected databases overlaid">${cvFlowerDefs()}${g}</svg>`,
    legend:`<div class="cv-cmp"><div class="sum">${key}</div><div class="sum">${sum}</div><div class="rows">${rows}</div><span class="srcnote">Colored areas = clusters of each database; where colors mix, the databases cover the same topics. ■ paper ● note ◆ project</span></div>`};
}


function cvBasisBadge(){
  const b=$('#cvBasis');if(!b)return;const c=(!LIVE&&DEMO&&DEMO.clusters)||null;
  b.className='cv-basis emb';b.textContent='semantic · embeddings';
  b.title='Clusters computed with k-means on the semantic embeddings of the structured summaries'+(c&&c.model?` (${c.model}, ${c.dim} dimensions)`:' (Qdrant vector "summary")')+'. Cluster names list distinctive terms; the descriptions explain the topic.';
}
/* Recompute button removed from the interface in 1.8.0; clusters are recomputed via `ingest cluster` or POST /api/clusters/recompute. */
Store.on('documents',()=>renderClusterPage(),50);
Store.on('databases',()=>renderClusterPage(),60);
