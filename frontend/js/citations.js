/* REQ-35: citation network – which documents of the collection cite which research papers.
   "⇄ Citations" in the header of the knowledge map (B page) switches the map to this view and back.
   Data: GET api/citations (backend app/citations.py – found in the reference lists by DOI or title, no LLM).
   Layout: x = year (older works on the left, so arrows mostly point left), y = a small force simulation;
   size = how often a node is cited inside the collection; shape/colour as in the knowledge map. */
const CI={on:false,data:null,key:'',loading:false,cam:{x:0,y:0,k:1},hover:null,focus:null,showIso:true,nodes:[],edges:[],W:0,H:0};
try{CI.showIso=localStorage.getItem('ci_iso')!=='0'}catch(e){}

function ciCol(n){
  if(typeof CG!=='undefined'&&CG.mode==='db'){const d=(n.databases||[])[0];return d?v3Css(`var(--db-${d})`):'#8d97b3'}
  return v3Css(n.kind==='project'?'var(--t-project)':n.kind==='research_notes'?'var(--t-notes)':'var(--t-paper)');
}
const ciR=n=>4.5+3.2*Math.sqrt(n.cited_by||0)+(n.kind==='project'?1:0);
const CI_VIA={'doi':'DOI','title+author+year':'title, first author and year','title+author':'title and first author','title-start+author+year':'start of the title, first author and year','title+year':'title and year','title':'title only'};

async function ciLoad(force){
  const key=dbScope().join(',');
  if(!force&&CI.data&&CI.key===key)return CI.data;
  if(!LIVE){CI.data={nodes:[],edges:[],stats:{},demo:true};CI.key=key;return CI.data}
  CI.loading=true;ciDraw();
  try{const q=key?'?databases='+encodeURIComponent(key):'';const r=await fetch('api/citations'+q);if(!r.ok)throw new Error('HTTP '+r.status);CI.data=await r.json();CI.key=key;CI.layoutKey=''}
  catch(e){CI.data={nodes:[],edges:[],stats:{},error:e.message}}
  CI.loading=false;return CI.data;
}

/* layout: years on x, force on y (deterministic seed so the picture is stable between visits) */
function ciLayout(W,H){
  const d=CI.data||{nodes:[],edges:[]};
  const iso=n=>!n.cited_by&&!n.cites;
  const nodes=d.nodes.filter(n=>CI.showIso||!iso(n)).map(n=>({...n}));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const edges=d.edges.filter(e=>byId.has(e.source)&&byId.has(e.target)).map(e=>({...e,s:byId.get(e.source),t:byId.get(e.target)}));
  // years as evenly spaced columns (only years that occur) – recent years with many papers do not crowd together
  const years=[...new Set(nodes.map(n=>n.year).filter(Boolean))].sort((p,q)=>p-q);if(!years.length)years.push(new Date().getFullYear());
  const col=new Map(years.map((y,i)=>[y,i])),last=years.length-1;
  const padL=40,padR=60,top=26,bot=34,iw=Math.max(80,W-padL-padR),ih=Math.max(60,H-top-bot);
  const X=y=>padL+(last?(col.has(y)?col.get(y):last)/last:.5)*iw;
  let seed=7;const rnd=()=>(seed=(seed*16807)%2147483647)/2147483647;
  const band=n=>iso(n)?[.80,.97]:[.03,.74];          // connected works above, works without citations in a strip below
  const groups=new Map();nodes.forEach(n=>{const k=(n.year||years[last])+'|'+iso(n);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(n)});
  groups.forEach(g=>{g.sort((p,q)=>(q.cited_by+q.cites)-(p.cited_by+p.cites)||String(p.label).localeCompare(q.label));
    g.forEach((n,i)=>{const [b0,b1]=band(n);n.tx=X(n.year||years[last]);n.x=n.tx+(rnd()-.5)*8;n.y=top+ih*(b0+(b1-b0)*(i+.5)/g.length+(rnd()-.5)*.04);n.vx=0;n.vy=0;n.r=ciR(n)})});
  const mg=document.createElement('canvas').getContext('2d');mg.font='12px '+getComputedStyle(document.body).fontFamily;
  nodes.forEach(n=>{n.lw=iso(n)?0:mg.measureText(n.label||'').width+8;n.left=n.tx+n.r+n.lw>W-4});   // label right of the node, or left at the right edge
  const box=n=>n.left?[n.x-n.r-n.lw,n.x+n.r]:[n.x-n.r,n.x+n.r+n.lw];
  for(let it=0;it<220;it++){
    const a=1-it/220;
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const p=nodes[i],q=nodes[j];if(iso(p)!==iso(q))continue;const dx=q.x-p.x,dy=q.y-p.y,d=Math.hypot(dx,dy)+.01,min=p.r+q.r+22;
      if(d<min){const f=(min-d)/d*.25*a;p.vy-=dy*f;q.vy+=dy*f;p.vx-=dx*f*.15;q.vx+=dx*f*.15}
      // labels: two nodes whose label boxes overlap horizontally need ~16 px vertical distance
      const [p0,p1]=box(p),[q0,q1]=box(q),gap=Math.max(p.r,q.r,7)+9;
      if(p0<q1&&q0<p1&&Math.abs(dy)<gap){const f=(gap-Math.abs(dy))*.18*a*(dy>=0?1:-1);p.vy-=f;q.vy+=f}
    }
    edges.forEach(e=>{const dy=e.t.y-e.s.y,f=dy*.004*a;e.s.vy+=f;e.t.vy-=f});
    nodes.forEach(n=>{const [b0,b1]=band(n);n.vx+=(n.tx-n.x)*.2;n.x+=n.vx;n.y+=n.vy;n.vx*=.5;n.vy*=.5;
      n.y=Math.max(top+ih*b0+n.r,Math.min(top+ih*b1-n.r,n.y))});
  }
  CI.axis={years,X,top,ih};
  CI.nodes=nodes;CI.edges=edges;
}

function ciMount(){
  const box=$('#cgCiteView');if(!box)return null;
  if(!box.querySelector('canvas')){
    box.innerHTML=`<div class="ci-bar"><span class="ci-meta" id="ciMeta"></span>
      <label class="check ci-iso"><input type="checkbox" id="ciIso"> papers without citations</label>
      <button class="mini" type="button" id="ciFit" title="Back to the start view">⟲ Reset view</button>
      <button class="mini" type="button" id="ciRebuild" title="Read the reference lists again and recompute the network (no LLM, no embeddings; takes seconds)">⟳ Recompute</button></div>
      <div class="ci-stage"><canvas></canvas><div class="cv-tip ci-tip" hidden></div><div class="ci-empty" hidden></div></div>
      <div class="cg-legend ci-legend" id="ciLegend"></div>`;
    const cv=box.querySelector('canvas');
    $('#ciIso').checked=CI.showIso;
    $('#ciIso').addEventListener('change',e=>{CI.showIso=e.target.checked;try{localStorage.setItem('ci_iso',CI.showIso?'1':'0')}catch(_){}CI.layoutKey='';ciRender()});
    $('#ciFit').addEventListener('click',()=>{CI.cam={x:0,y:0,k:1};CI.focus=null;ciDraw()});
    $('#ciRebuild').addEventListener('click',ciRebuild);
    ciWire(cv);
  }
  return box;
}

function ciWire(cv){
  let drag=null,moved=false;
  const pt=e=>{const r=cv.getBoundingClientRect();return {x:(e.clientX-r.left-CI.cam.x)/CI.cam.k,y:(e.clientY-r.top-CI.cam.y)/CI.cam.k,sx:e.clientX-r.left,sy:e.clientY-r.top}};
  const hitNode=p=>{let best=null,bd=1e9;CI.nodes.forEach(n=>{const d=Math.hypot(n.x-p.x,n.y-p.y);if(d<n.r+5/CI.cam.k&&d<bd){bd=d;best=n}});return best};
  const hitEdge=p=>{let best=null,bd=6/CI.cam.k;CI.edges.forEach(e=>{const c=ciCtrl(e);for(let t=0;t<=1;t+=.05){const x=(1-t)*(1-t)*e.s.x+2*(1-t)*t*c.x+t*t*e.t.x,y=(1-t)*(1-t)*e.s.y+2*(1-t)*t*c.y+t*t*e.t.y,d=Math.hypot(x-p.x,y-p.y);if(d<bd){bd=d;best=e}}});return best};
  cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,cx:CI.cam.x,cy:CI.cam.y};moved=false;cv.setPointerCapture(e.pointerId)});
  cv.addEventListener('pointermove',e=>{
    if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.abs(dx)+Math.abs(dy)>3)moved=true;if(moved){CI.cam.x=drag.cx+dx;CI.cam.y=drag.cy+dy;ciDraw();return}}
    const p=pt(e),n=hitNode(p),ed=n?null:hitEdge(p);CI.hover=n||ed;cv.style.cursor=n?'pointer':drag?'grabbing':'grab';ciTip(p,n,ed);ciDraw();
  });
  cv.addEventListener('pointerup',e=>{const wasDrag=moved;drag=null;if(wasDrag)return;const n=hitNode(pt(e));
    if(n){CI.focus=CI.focus===n.id?null:n.id;ciDraw();if(CI.focus&&typeof openDoc==='function')openDoc(n.doc_id)}else{CI.focus=null;ciDraw()}});
  cv.addEventListener('pointerleave',()=>{CI.hover=null;const t=$('#cgCiteView .ci-tip');if(t)t.hidden=true;ciDraw()});
  cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect(),sx=e.clientX-r.left,sy=e.clientY-r.top,k0=CI.cam.k,k=Math.max(.4,Math.min(5,k0*Math.exp(-e.deltaY*.0015)));
    CI.cam.x=sx-(sx-CI.cam.x)*k/k0;CI.cam.y=sy-(sy-CI.cam.y)*k/k0;CI.cam.k=k;ciDraw()},{passive:false});
}

function ciTip(p,n,e){
  const t=$('#cgCiteView .ci-tip');if(!t)return;
  if(!n&&!e){t.hidden=true;return}
  let h;
  if(n){
    const au=(n.authors||[]).slice(0,4).join(', ')+((n.authors||[]).length>4?' et al.':'');
    h=`<b>${esc(n.title||n.label)}</b><br>${n.kind==='project'?`Research project · ${n.files} current file${n.files>1?'s':''}`:esc(au)}${n.year?' · '+n.year:''}`+
      `<br>cited by <b>${n.cited_by}</b> · cites <b>${n.cites}</b> in this collection${(n.databases||[]).length?'<br>'+esc(dbNames(n.databases).join(', ')):''}<br><i>click: highlight and open</i>`;
  }else{
    h=`<b>${esc(e.s.label)}</b> cites <b>${esc(e.t.label)}</b><br>found by ${esc(CI_VIA[e.via]||e.via)}${e.evidence?`<br><span class="ci-ev">“${esc(e.evidence)}”</span>`:''}`;
  }
  t.innerHTML=h;t.hidden=false;
  const W=t.parentElement.clientWidth,sx=p.x*CI.cam.k+CI.cam.x,sy=p.y*CI.cam.k+CI.cam.y;
  t.style.left=Math.min(W-t.offsetWidth-6,sx+14)+'px';t.style.top=(sy+14+t.offsetHeight>t.parentElement.clientHeight?sy-t.offsetHeight-10:sy+14)+'px';
}

function ciCtrl(e){const mx=(e.s.x+e.t.x)/2,my=(e.s.y+e.t.y)/2,dx=e.t.x-e.s.x,dy=e.t.y-e.s.y,l=Math.hypot(dx,dy)||1,b=Math.min(60,l*.18);return {x:mx-dy/l*b,y:my+dx/l*b}}

function ciDraw(){
  const box=$('#cgCiteView');if(!box||box.hidden)return;
  const cv=box.querySelector('canvas'),stage=box.querySelector('.ci-stage');if(!cv)return;
  const W=stage.clientWidth,H=stage.clientHeight,dpr=devicePixelRatio||1;
  if(cv.width!==Math.round(W*dpr)||cv.height!==Math.round(H*dpr)){cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);cv.style.width=W+'px';cv.style.height=H+'px'}
  const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
  const empty=box.querySelector('.ci-empty');
  const d=CI.data;
  const msg=CI.loading?'Loading the citation network …':!d?'':d.demo?'The citation network needs the running backend (it is computed from the reference lists of the indexed papers).':d.error?'Could not load the citation network: '+d.error:
    !d.nodes.length?'No research papers in the current selection.':!d.edges.length?'No citations between documents of this selection found yet. If papers were added before release 2.2.0, press “⟳ Recompute”.':'';
  empty.hidden=!msg;empty.textContent=msg;if(msg&&(!d||!d.nodes.length))return;
  const muted=v3Css('var(--muted)'),line=v3Css('var(--line)'),fg=v3Css('var(--fg)'),acc=v3Css('var(--graph)');
  // year axis (screen space x follows the camera, labels stay at the bottom)
  const A=CI.axis;if(A){g.font='11px '+getComputedStyle(document.body).fontFamily;g.textAlign='center';
    const every=Math.max(1,Math.ceil(A.years.length/Math.max(2,Math.floor(W/56))));
    A.years.forEach((y,i)=>{const x=A.X(y)*CI.cam.k+CI.cam.x;if(x<6||x>W-6)return;
      g.strokeStyle=line;g.globalAlpha=.7;g.beginPath();g.moveTo(x,0);g.lineTo(x,H-18);g.stroke();g.globalAlpha=1;
      if(i%every===0||i===A.years.length-1){g.fillStyle=muted;g.fillText(String(y),x,H-5)}});
    const yb=(A.top+A.ih*.775)*CI.cam.k+CI.cam.y;if(CI.showIso&&CI.nodes.some(n=>!n.cited_by&&!n.cites)&&yb>0&&yb<H-20){g.textAlign='left';g.fillStyle=muted;g.fillText('without citations in this collection',8,yb)}}
  g.save();g.translate(CI.cam.x,CI.cam.y);g.scale(CI.cam.k,CI.cam.k);
  const f=CI.focus,near=new Set();if(f){near.add(f);CI.edges.forEach(e=>{if(e.s.id===f)near.add(e.t.id);if(e.t.id===f)near.add(e.s.id)})}
  CI.edges.forEach(e=>{
    const on=!f||e.s.id===f||e.t.id===f,hov=CI.hover===e,c=ciCtrl(e);
    g.globalAlpha=on?(.35+.55*(e.confidence||.6))*(hov?1.6:1):.08;g.strokeStyle=hov||(f&&on)?acc:fg;g.lineWidth=(hov?2.4:1.3)/CI.cam.k;
    g.setLineDash(e.via&&e.via!=='doi'&&!e.via.includes('author')?[4/CI.cam.k,3/CI.cam.k]:[]);
    g.beginPath();g.moveTo(e.s.x,e.s.y);g.quadraticCurveTo(c.x,c.y,e.t.x,e.t.y);g.stroke();g.setLineDash([]);
    // arrow head at the cited work
    const tx=e.t.x-c.x,ty=e.t.y-c.y,l=Math.hypot(tx,ty)||1,ux=tx/l,uy=ty/l,ex=e.t.x-ux*(e.t.r+2),ey=e.t.y-uy*(e.t.r+2),a=7/CI.cam.k;
    g.fillStyle=g.strokeStyle;g.beginPath();g.moveTo(ex,ey);g.lineTo(ex-ux*a-uy*a*.55,ey-uy*a+ux*a*.55);g.lineTo(ex-ux*a+uy*a*.55,ey-uy*a-ux*a*.55);g.closePath();g.fill();
  });
  g.globalAlpha=1;
  const lbl=CI.nodes.length<=40||CI.cam.k>1.3;
  CI.nodes.forEach(n=>{
    const dim=f&&!near.has(n.id),iso=!n.cited_by&&!n.cites;g.globalAlpha=dim?.18:iso?.55:1;
    g.fillStyle=ciCol(n);v3Shape(g,n.kind==='project'?'research_project':n.kind,n.x,n.y,n.r);g.fill();
    if(CI.hover===n||f===n.id){g.lineWidth=2.4/CI.cam.k;g.strokeStyle=acc;g.stroke()}
    if((lbl&&!iso)||CI.hover===n||f===n.id||n.cited_by>=2){g.font=`${(n.cited_by?12:11)/CI.cam.k}px `+getComputedStyle(document.body).fontFamily;g.textAlign='left';
      g.fillStyle=fg;g.globalAlpha=dim?.25:iso?.6:.95;
      if(n.left){g.textAlign='right';g.fillText(n.label||'',n.x-n.r-4/CI.cam.k,n.y+4/CI.cam.k)}else g.fillText(n.label||'',n.x+n.r+4/CI.cam.k,n.y+4/CI.cam.k)}
  });
  g.restore();g.globalAlpha=1;
}

async function ciRender(force){
  const box=ciMount();if(!box||!CI.on)return;
  await ciLoad(force);
  const st=box.querySelector('.ci-stage'),W=st.clientWidth,H=st.clientHeight,k=`${CI.key}|${W}|${H}|${CI.showIso}`;
  if(CI.layoutKey!==k&&CI.data){ciLayout(W,H);CI.layoutKey=k;CI.cam={x:0,y:0,k:1}}
  const s=(CI.data&&CI.data.stats)||{};
  $('#ciMeta').textContent=CI.data&&!CI.data.demo&&!CI.data.error?`${s.edges||0} citation${s.edges===1?'':'s'} · ${s.nodes||0} papers & projects${SEL_DB.length?' · '+dbNames(SEL_DB).join('+'):''}${s.run?' · computed '+String(s.run).slice(0,10):''}`:'';
  $('#ciLegend').innerHTML=(CG.mode==='db'?`<span>Colour = database</span>`:`<span><i style="--c:var(--t-paper);border-radius:2px"></i>Paper</span><span><i style="--c:var(--t-notes)"></i>Note</span><span><i style="--c:var(--t-project);transform:rotate(45deg);border-radius:1px"></i>Project</span>`)+
    `<span>Arrow = cites (from the reference list) · solid = DOI or title with author · dashed = title only · size = cited by · left → right = year · click a node to open it, drag to pan, wheel to zoom</span>`;
  ciDraw();
}

async function ciRebuild(){
  const b=$('#ciRebuild');if(!LIVE){toast('Needs the running backend');return}
  b.disabled=true;b.textContent='⟳ Recomputing …';
  try{const r=await fetch('api/citations/rebuild',{method:'POST'});const j=await r.json();if(!r.ok)throw new Error(j.detail||r.status);
    toast(`Citation network: ${j.citations} citations from ${j.citing} documents to ${j.targets} papers`);await ciRender(true)}
  catch(e){toast('Recompute failed: '+e.message)}
  b.disabled=false;b.textContent='⟳ Recompute';
}

function ciToggle(on){
  CI.on=on;const sec=$('#page-graph .bq-map'),btn=$('#cgCite'),box=$('#cgCiteView');if(!sec||!btn||!box)return;
  sec.classList.toggle('cite-on',on);box.hidden=!on;btn.setAttribute('aria-pressed',String(on));
  btn.title=on?'Back to the knowledge map':'Show which papers cite each other (found in their reference lists)';
  try{localStorage.setItem('ci_on',on?'1':'0')}catch(e){}
  if(on)ciRender();else{CI.focus=null}
}

(function wireCitations(){
  const btn=$('#cgCite');if(!btn)return;
  btn.addEventListener('click',()=>ciToggle(!CI.on));
  // every redraw of the B page (database selection, colour mode) and resizing redraw the network as well
  Store.on('cluster-page',()=>{if(CI.on)ciRender()},20);
  if(window.ResizeObserver){let t;new ResizeObserver(()=>{clearTimeout(t);t=setTimeout(()=>{if(CI.on)ciRender()},120)}).observe($('#cgCiteView'))}
  try{if(localStorage.getItem('ci_on')==='1')setTimeout(()=>ciToggle(true),0)}catch(e){}
})();

/* document details: "Cites" / "Cited by" inside the collection (used by documents.js) */
function citesHtml(full){
  const c=(full.cites||[]),b=(full.cited_by||[]);if(!c.length&&!b.length)return '';
  const row=(id,extra)=>{const x=DOCS.find(d=>d.id===id);return x?`<li><a href="#" data-open="${esc(id)}">${esc(x.ti)}</a>${x.y?` <span class="srcnote">${x.y}</span>`:''}${extra||''}</li>`:''};
  return `<section><h4>Citations in this collection <span class="prov">BIBO · from the reference list</span></h4>
    ${c.length?`<div class="srcnote">Cites (${c.length})</div><ul class="ci-list">${c.map(x=>row(x.doc_id,` <span class="srcnote" title="${esc(x.evidence||'')}">· ${esc(CI_VIA[x.via]||x.via)}</span>`)).join('')}</ul>`:''}
    ${b.length?`<div class="srcnote">Cited by (${b.length})</div><ul class="ci-list">${b.map(id=>row(id)).join('')}</ul>`:''}</section>`;
}

/* REQ-68 document details: articles of a law the paper discusses (number as cited, version, today's number) */
function provisionsHtml(full){
  const a=full.discusses||[];if(!a.length)return '';
  const row=x=>`<li><b>${esc(x.label)}</b>${x.title?' '+esc(x.title):''}${x.parts&&x.parts.length?` <span class="srcnote">${esc(x.parts.slice(0,4).join(', '))}</span>`:''}
    <span class="srcnote">· ${esc(x.law||x.norm_id)}${x.stage?', '+esc((STAGE_LABEL[x.stage]||x.stage).toLowerCase())+(x.stage_date?' '+esc(String(x.stage_date).slice(0,4)):''):''} · ${x.count}×</span>
    ${x.renumbered&&x.current_label?`<div class="srcnote">now ${esc(x.current_label)}${x.current_title?' – '+esc(x.current_title):''}</div>`:''}</li>`;
  return `<section><h4>Discusses <span class="prov">ELI · references in the text</span></h4><ul class="ci-list">${a.slice(0,30).map(row).join('')}</ul>
    ${a.length>30?`<div class="srcnote">… and ${a.length-30} more</div>`:''}</section>`;
}
