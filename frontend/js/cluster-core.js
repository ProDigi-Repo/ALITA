/* Clusters – shared state and helpers: selected clusters (CV), clustering units from DOCS, selection, shapes.
   Split from clusters.js in 4.0.0 (REQ-61); load order: cluster-core, cluster-3d, cluster-map2d, cluster-page, database-info. */
/* ---------- Cluster analysis band ---------- */
const CV={sels:new Set()};   // selected clusters = search space of both chats (one or more)
const cvHas=id=>CV.sels.has(+id), cvOff=id=>CV.sels.size>0&&!CV.sels.has(+id);
try{if(localStorage.getItem('cviz_hidden')==='1')$('#cviz').classList.add('collapsed')}catch(e){}
function cvSyncToggle(){const c=$('#cviz').classList.contains('collapsed');$$('.cv-toggle').forEach(b=>{b.textContent=c?'Show':'Hide';b.setAttribute('aria-expanded',!c)})}
cvSyncToggle();
$$('.cv-toggle').forEach(b=>b.addEventListener('click',()=>{const c=$('#cviz').classList.toggle('collapsed');try{localStorage.setItem('cviz_hidden',c?'1':'0')}catch(e){}cvSyncToggle();if(!c)renderClusterViz()}));
const cvHue=c=>(c*67)%360, cvCol=(c,l=45)=>`hsl(${cvHue(c)} 60% ${l}%)`;
const CV_TYPE={research_paper:'Paper',research_notes:'Note',research_project:'Project',legal_project:'Law',legal_guideline:'Guideline',standard:'Standard',guidance:'FAQ'};
function cvUnits(){
  if(typeof DOCS==='undefined'||typeof PROJECTS==='undefined')return [];   // a resize can fire before documents.js has run
  const inDb=x=>!SEL_DB.length||(x.db||[]).some(n=>SEL_DB.includes(n));
  const docs=DOCS.filter(d=>d.cb==='summary'&&d.cx!=null&&d.ci!=null);
  const projs=PROJECTS.filter(p=>p.cx!=null&&p.ci!=null).map(p=>({id:null,t:'research_project',ti:p.title||p.name,pn:p.name,ci:p.ci,cl:p.cl,cx:p.cx,cy:p.cy,ca:p.ca,cas:p.cas,db:p.db||[]}));
  return [...docs,...projs].map(u=>({...u,on:inDb(u)}));
}
function cvClusters(units){
  const m=new Map();
  units.forEach(u=>{if(!m.has(u.ci))m.set(u.ci,{id:u.ci,label:u.cl||'',all:[],on:[]});const c=m.get(u.ci);c.all.push(u);if(u.on)c.on.push(u)});
  return [...m.values()].sort((a,b)=>a.id-b.id);
}
function cvLinks(units){
  const acc={};units.filter(u=>u.on&&u.ca!=null&&u.ca!==u.ci).forEach(u=>{const a=Math.min(u.ci,u.ca),b=Math.max(u.ci,u.ca),k=a+'-'+b;(acc[k]=acc[k]||{a,b,n:0,s:0});acc[k].n++;acc[k].s+=u.cas||0});
  return Object.values(acc).map(l=>({...l,s:l.n?l.s/l.n:0}));
}
function cvTip(el,box,html,ev){
  if(!html){el.hidden=true;return}
  el.innerHTML=html;el.hidden=false;const r=box.getBoundingClientRect();
  let x=ev.clientX-r.left+12,y=ev.clientY-r.top+12;if(x>r.width-290)x=Math.max(4,x-300);el.style.left=x+'px';el.style.top=y+'px';
}
/* After a database change: clusters without documents in the selected databases leave the selection */
function cvPruneSel(){
  const cls=cvClusters(cvUnits()),gone=id=>{const c=cls.find(x=>x.id===id);return !c||(SEL_DB.length&&!c.on.length)};
  let ch=false;[...CV.sels].forEach(id=>{if(gone(id)){CV.sels.delete(id);ch=true}});
  if(ch){const r=$('#rCluster');if(r)r.value=CV.sels.size===1?String([...CV.sels][0]):''}
  if(typeof CG!=='undefined'&&CG.sel!=null&&gone(CG.sel))CG.sel=null;
  return ch;
}
/* "Clear selection" in the database bar: deselect everything – databases and clusters */
function clearAllSel(){CV.sels.clear();if(typeof CG!=='undefined'){CG.sel=null;CG.proj=null}const r=$('#rCluster');if(r)r.value='';setDbSel([])}
/* the cluster selection changed: the cluster dropdown of A, the parameter lines and the map follow (state.js) */
function cvChanged(){Store.emit('clusters')}
function cvSyncSelect(){const r=$('#rCluster');if(r)r.value=CV.sels.size===1?String([...CV.sels][0]):''}
Store.on('clusters',cvSyncSelect,10);
Store.on('databases',()=>cvPruneSel(),10);
function cvClear(){if(typeof CG!=='undefined')CG.proj=null;CV.sels.clear();cvChanged()}
function cvSelect(c,only){   // click = add/remove a cluster; only = select just this one
  if(only)CV.sels=new Set([c]);else if(CV.sels.has(c))CV.sels.delete(c);else CV.sels.add(c);
  cvChanged();
}
/* Shape = type (diamond project, square paper, circle note), white flower inside = database */
function cvFlowerDefs(){
  if(typeof DB_FLOWER==='undefined')return '';
  return '<defs>'+Object.entries(DB_FLOWER).map(([n,svg])=>`<symbol id="cvf-${n}" viewBox="0 0 24 24">${svg.replace(/^<svg[^>]*>/,'<g fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round">').replace(/<\/svg>$/,'</g>').replace(/fill-opacity="\.?\d*"/g,'fill-opacity=".9"')}</symbol>`).join('')+'</defs>';
}
function cvShape(u,x,y,col,dim){
  const op=dim?.16:1,st='stroke="var(--panel)" stroke-width="1.2"',n=(u.db||[])[0];
  const flw=f=>(n&&typeof DB_FLOWER!=='undefined'&&DB_FLOWER[n])?`<use href="#cvf-${n}" x="${x-f/2}" y="${y-f/2}" width="${f}" height="${f}" style="color:#fff" opacity="${op}" pointer-events="none"/>`:'';
  if(u.t==='research_project')return `<path d="M${x} ${y-10}L${x+10} ${y}L${x} ${y+10}L${x-10} ${y}Z" fill="${col}" ${st} opacity="${op}"/>`+flw(11);
  if(u.t==='research_paper')return `<rect x="${x-6}" y="${y-6}" width="12" height="12" rx="2" fill="${col}" ${st} opacity="${op}"/>`+flw(11);
  if(LEGAL_T.has(u.t))return `<path d="M${x} ${y-8}L${x+7.5} ${y+5.5}L${x-7.5} ${y+5.5}Z" fill="${col}" ${st} opacity="${op}"/>`+flw(9);
  return `<circle cx="${x}" cy="${y}" r="6.2" fill="${col}" ${st} opacity="${op}"/>`+flw(10.5);
}
