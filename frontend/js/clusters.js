/* ---------- Cluster analysis band ---------- */
const CV={sels:new Set()};   // selected clusters = search space of both chats (one or more)
const cvHas=id=>CV.sels.has(+id), cvOff=id=>CV.sels.size>0&&!CV.sels.has(+id);
try{if(localStorage.getItem('cviz_hidden')==='1')$('#cviz').classList.add('collapsed')}catch(e){}
function cvSyncToggle(){const c=$('#cviz').classList.contains('collapsed');$$('.cv-toggle').forEach(b=>{b.textContent=c?'Show':'Hide';b.setAttribute('aria-expanded',!c)})}
cvSyncToggle();
$$('.cv-toggle').forEach(b=>b.addEventListener('click',()=>{const c=$('#cviz').classList.toggle('collapsed');try{localStorage.setItem('cviz_hidden',c?'1':'0')}catch(e){}cvSyncToggle();if(!c)renderClusterViz()}));
const cvHue=c=>(c*67)%360, cvCol=(c,l=45)=>`hsl(${cvHue(c)} 60% ${l}%)`;
const CV_TYPE={research_paper:'Paper',research_notes:'Note',research_project:'Project',legal_project:'Law',legal_guideline:'Guideline',standard:'Standard'};
function cvUnits(){
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
function cvClear(){if(typeof CG!=='undefined')CG.proj=null;CV.sels.clear();const r=$('#rCluster');if(r)r.value='';try{syncParams('rag');syncParams('graph')}catch(e){}renderClusterViz()}
function cvSelect(c,only){   // click = add/remove a cluster; only = select just this one
  if(only)CV.sels=new Set([c]);else if(CV.sels.has(c))CV.sels.delete(c);else CV.sels.add(c);
  const sel=$('#rCluster');if(sel)sel.value=CV.sels.size===1?String([...CV.sels][0]):'';
  try{syncParams('rag');syncParams('graph')}catch(e){}
  renderClusterViz();
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
/* ---------- Cluster map (A) and cluster graph (B) in 3D, interactive (v1.5.0) ----------
   Drag the background = rotate · wheel = zoom · drag a cluster = pull it (B: linked clusters follow) ·
   click a cluster = select (A: filter Document Chat, B: ask Graph Chat) · click a point = open document · double-click = reset. */
const V3={on:true,map:null,graph:null};
const V3_HELP={
  map:'<b>Controls</b> · left → right = periods<br>drag = rotate · wheel = zoom<br>drag a cluster = pull it, similar ones follow<br>click clusters = select for the chats · double-click = reset',
  graph:'<b>Controls</b> · left → right = periods<br>drag = rotate · wheel = zoom · dotted = same cluster<br>drag a node = pull it, linked ones follow<br>click clusters = select for the chats · double-click = reset'};
try{V3.on=localStorage.getItem('cv3d')!=='0'}catch(e){}
function v3Cam(){return {yaw:-0.55,pitch:0.32,dist:250}}
function v3Proj(cam,p,W,H){
  const cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
  const x1=p.x*cy-p.z*sy,z1=p.x*sy+p.z*cy,y2=p.y*cp-z1*sp,z2=p.y*sp+z1*cp+cam.dist;
  if(z2<5)return null;const f=Math.min(W,H)*1.35;return {x:W/2+x1*f/z2,y:H/2+(cam.oy||0)-y2*f/z2,z:z2,s:f/z2};
}
function v3Canvas(box,h){
  let cv=box.querySelector('canvas.v3');
  if(!cv){box.innerHTML='';cv=document.createElement('canvas');cv.className='v3';cv.tabIndex=0;box.appendChild(cv);
    const hp=document.createElement('div');hp.className='v3-help';hp.innerHTML=box.id==='cvGraph'?V3_HELP.graph:V3_HELP.map;box.appendChild(hp)}
  const dpr=window.devicePixelRatio||1,W=box.clientWidth||600,H=h;cv.style.height=H+'px';
  if(cv.width!==W*dpr||cv.height!==H*dpr){cv.width=W*dpr;cv.height=H*dpr}
  const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);return {cv,g,W,H};
}
function v3Col(u,ci,l){if(CV.mode==='db'){const n=(u&&u.db||[])[0];return n?`var(--db-${n})`:'#8d97b3'}return cvCol(ci,l||48)}
function v3Css(c){if(!c.startsWith('var('))return c;const n=c.slice(4,-1);return getComputedStyle(document.documentElement).getPropertyValue(n).trim()||'#8d97b3'}
function v3Shape(g,t,x,y,r){g.beginPath();if(LEGAL_T.has(t)){g.moveTo(x,y-r*1.4);g.lineTo(x+r*1.25,y+r*.9);g.lineTo(x-r*1.25,y+r*.9);g.closePath()}else if(t==='research_project'){g.moveTo(x,y-r*1.6);g.lineTo(x+r*1.6,y);g.lineTo(x,y+r*1.6);g.lineTo(x-r*1.6,y);g.closePath()}else if(t==='research_paper')g.rect(x-r,y-r,2*r,2*r);else g.arc(x,y,r,0,Math.PI*2)}
/* generic pointer handling: orbit / drag a handle / click */
function v3Wire(st,cv,api){
  if(cv._v3)return;cv._v3=1;let drag=null;
  cv.addEventListener('pointerdown',e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const hit=api.hit(mx,my);
    drag={x:e.clientX,y:e.clientY,moved:0,hit};cv.setPointerCapture(e.pointerId);if(hit&&hit.kind==='cluster')api.grab&&api.grab(hit)});
  cv.addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
    if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.moved+=Math.abs(dx)+Math.abs(dy);drag.x=e.clientX;drag.y=e.clientY;
      if(drag.hit&&drag.hit.kind==='cluster'&&drag.moved>3){api.pull(drag.hit,dx,dy);hideProfile();return}
      if(!drag.hit||drag.hit.kind!=='cluster'){st.cam.yaw+=dx*0.008;st.cam.pitch=Math.max(-1.45,Math.min(1.45,st.cam.pitch+dy*0.008));api.draw();return}}
    const h=api.hit(mx,my);api.hover(h,e,mx,my)});
  cv.addEventListener('pointerup',()=>{const d=drag;drag=null;if(d&&d.hit&&d.hit.kind==='cluster')api.release&&api.release(d.hit,d.moved>3);if(d&&d.moved<4&&d.hit)api.click(d.hit)});
  cv.addEventListener('pointerleave',()=>{api.hover(null)});
  cv.addEventListener('wheel',e=>{e.preventDefault();st.cam.dist=Math.max(70,Math.min(900,st.cam.dist*(1+Math.sign(e.deltaY)*0.1)));api.draw()},{passive:false});
  cv.addEventListener('dblclick',()=>{api.reset();api.draw()});
}
/* ----- Time slices for A and B: the cluster structure per period, left to right (v1.7.0) -----
   Periods: everything before the second-latest year, the second-latest year, the latest year
   (with the current data: before 2025 · 2025 · 2026). Projects appear in every period they ran. */
function v3Periods(units){
  const ys=units.flatMap(u=>v3Years(u)).filter(Boolean);const Y=ys.length?Math.max(...ys):new Date().getFullYear();
  return [{label:`before ${Y-1}`,lo:-Infinity,hi:Y-2},{label:String(Y-1),lo:Y-1,hi:Y-1},{label:String(Y),lo:Y,hi:Y}];
}
function v3Years(u){
  if(u.t==='research_project'){const p=PROJECTS.find(x=>x.name===u.pn)||{};const a=+String(p.from_||'').slice(0,4),b=+String(p.to||'').slice(0,4);
    const ys=DOCS.filter(d=>d.pn===u.pn&&d.y).map(d=>d.y);const lo=a||(ys.length?Math.min(...ys):0),hi=b||(ys.length?Math.max(...ys):0);return lo&&hi?[lo,hi]:[]}
  return u.y?[u.y,u.y]:[];
}
function v3Slices(units){ // [{label, units:[…]}]; a unit belongs to every period its years overlap
  const P=v3Periods(units);
  return P.map(p=>({...p,units:units.filter(u=>{const r=v3Years(u);return r.length&&r[0]<=p.hi&&r[1]>=p.lo})}));
}
const V3_GAP=2.4;   // distance between the period panels, in map radii

/* ----- A: cluster map per period (3D scene, panels side by side) ----- */
function mountMap3D(units,cls){
  const box=$('#cvMap');const st=V3.map||(V3.map={cam:{...v3Cam(),yaw:0,pitch:0.18,dist:395,oy:40},off:{}});
  const R=62,S=v3Slices(units),n=S.length,sx=i=>(i-(n-1)/2)*R*V3_GAP;
  const links=cvLinks(units);st.pin=st.pin||new Set();st.vel=st.vel||{};
  const undated=units.filter(u=>!v3Years(u).length).length;
  const pos=(u,i)=>{const o=st.off[u.ci]||{x:0,y:0,z:0};return {x:sx(i)+u.cx*R+o.x*0.6,y:u.cy*R+o.y*0.6,z:o.z*0.6}};
  const draw=()=>{
    const {g,W,H}=v3Canvas(box,350);g.clearRect(0,0,W,H);
    const muted=getComputedStyle(document.documentElement).getPropertyValue('--muted').trim()||'#888',fg=getComputedStyle(document.documentElement).getPropertyValue('--fg').trim()||'#222';
    const P=p=>v3Proj(st.cam,p,W,H);
    const seg=(a,b,col,w,dash)=>{const p=P(a),q=P(b);if(!p||!q)return;g.strokeStyle=col;g.lineWidth=w;if(dash)g.setLineDash(dash);g.beginPath();g.moveTo(p.x,p.y);g.lineTo(q.x,q.y);g.stroke();g.setLineDash([])};
    st.hits=[];const cen={};   // cen[ci][i] = centre of cluster ci in period i
    S.forEach((sl,i)=>{
      // panel frame + period label
      const B=R*1.12,x0=sx(i),fr=[[-B,-B],[B,-B],[B,B],[-B,B]].map(([x,y])=>({x:x0+x,y,z:0}));
      for(let k=0;k<4;k++)seg(fr[k],fr[(k+1)%4],'rgba(128,140,170,.28)',1);
      const lp=P({x:x0-B,y:B,z:0});if(lp){g.fillStyle=fg;g.font='600 12px "IBM Plex Sans",sans-serif';g.fillText(`${sl.label}`,lp.x+4,lp.y-6);
        g.fillStyle=muted;g.font='11px "IBM Plex Sans",sans-serif';g.fillText(`${sl.units.filter(u=>u.on).length} items`,lp.x+4+g.measureText(sl.label).width*1.1+10,lp.y-6)}
      // halos per cluster in this period
      cls.forEach(c=>{const mem=sl.units.filter(u=>u.ci===c.id&&u.on);if(!mem.length)return;const ps=mem.map(u=>pos(u,i));
        const m={x:ps.reduce((a,p)=>a+p.x,0)/ps.length,y:ps.reduce((a,p)=>a+p.y,0)/ps.length,z:ps.reduce((a,p)=>a+p.z,0)/ps.length};
        (cen[c.id]=cen[c.id]||{})[i]={m,n:mem.length};
        const rad=Math.max(8,Math.sqrt(ps.reduce((a,p)=>a+(p.x-m.x)**2+(p.y-m.y)**2,0)/ps.length)*1.4),q=P(m);if(!q)return;
        const dim=cvOff(c.id);g.globalAlpha=dim?.05:.13;g.fillStyle=cvCol(c.id,55);g.beginPath();g.arc(q.x,q.y,rad*q.s,0,Math.PI*2);g.fill();
        g.globalAlpha=dim?.15:.5;g.strokeStyle=cvCol(c.id);g.setLineDash([4,4]);g.stroke();g.setLineDash([]);g.globalAlpha=1});
      // relations inside the period
      const L=cvLinks(sl.units),mx=Math.max(1,...L.map(l=>l.n));
      L.forEach(l=>{const a=cen[l.a]&&cen[l.a][i],b=cen[l.b]&&cen[l.b][i];if(a&&b){g.globalAlpha=.25+.5*l.n/mx;seg(a.m,b.m,muted,1+3*l.n/mx);g.globalAlpha=1}});
    });
    // development of each cluster from period to period
    Object.entries(cen).forEach(([ci,per])=>{const ks=Object.keys(per).map(Number).sort((a,b)=>a-b);
      for(let k=1;k<ks.length;k++){g.globalAlpha=cvOff(+ci)?.15:.6;seg(per[ks[k-1]].m,per[ks[k]].m,cvCol(+ci),1.5,[2,4]);g.globalAlpha=1}});
    // documents
    const pts=[];S.forEach((sl,i)=>sl.units.forEach(u=>{if(!u.on)return;const p=P(pos(u,i));if(p)pts.push({u,p})}));   // only the selected databases
    pts.sort((a,b)=>b.p.z-a.p.z).forEach(({u,p})=>{const dim=!u.on||(cvOff(u.ci)),r=Math.max(2,Math.min(8,p.s*2.6));
      g.globalAlpha=dim?.16:1;g.fillStyle=v3Css(v3Col(u,u.ci));v3Shape(g,u.t,p.x,p.y,r);g.fill();
      if(r>=3.5&&typeof s3Flower==='function'){const img=s3Flower((u.db||[])[0]);if(img){const f=r*(u.t==='research_project'?2:1.7);g.drawImage(img,p.x-f/2,p.y-f/2,f,f)}}g.globalAlpha=1;
      if(st.hov===u){v3Shape(g,u.t,p.x,p.y,r);g.strokeStyle=muted;g.lineWidth=2;g.stroke()}if(!dim)st.hits.push({kind:'doc',u,x:p.x,y:p.y,r:r+3})});
    // cluster labels per period (size = documents in that period)
    Object.entries(cen).forEach(([ci,per])=>Object.entries(per).forEach(([i,{m,n:k}])=>{const q=P(m);if(!q)return;const c=cls.find(x=>x.id===+ci);
      const dim=cvOff(+ci),lab=`C${ci}·${k}`;g.font='600 10px "IBM Plex Mono",monospace';const w=g.measureText(lab).width+10,h=14;
      g.globalAlpha=dim?.35:1;g.fillStyle=cvCol(+ci);g.beginPath();g.roundRect?g.roundRect(q.x-w/2,q.y-h/2,w,h,7):g.rect(q.x-w/2,q.y-h/2,w,h);g.fill();
      if(st.pin.has(+ci)){g.strokeStyle='#0e8fa0';g.lineWidth=2.5;g.stroke()}
      g.fillStyle='#fff';g.textAlign='center';g.fillText(lab,q.x,q.y+3.5);g.textAlign='left';g.globalAlpha=1;st.hits.push({kind:'cluster',c,x:q.x,y:q.y,r:w/2+2})}));
    if(undated){g.fillStyle=muted;g.font='11px "IBM Plex Sans",sans-serif';g.fillText(`${undated} without year not shown`,W-170,H-8)}
  };
  function step(){
    const O=id=>st.off[id]||(st.off[id]={x:0,y:0,z:0}),V=id=>st.vel[id]||(st.vel[id]={x:0,y:0,z:0});let e=0;
    const nMax=Math.max(1,...links.map(x=>x.n));
    links.forEach(l=>{const a=O(l.a),b=O(l.b),k=0.07*(0.3+0.7*(l.s||0.5))*Math.sqrt(l.n/nMax);
      ['x','y','z'].forEach(ax=>{const d=(a[ax]-b[ax])*k;if(!st.pin.has(l.a))V(l.a)[ax]-=d;if(!st.pin.has(l.b))V(l.b)[ax]+=d})});
    cls.forEach(c=>{if(st.pin.has(c.id)){st.vel[c.id]={x:0,y:0,z:0};return}const o=O(c.id),v=V(c.id);
      ['x','y','z'].forEach(ax=>{v[ax]-=o[ax]*0.02;v[ax]*=0.8;o[ax]+=v[ax];e+=Math.abs(v[ax])})});
    return e;
  }
  function run(){cancelAnimationFrame(st.raf);let k=0;const tick=()=>{const e=step();draw();if((e>0.02||st.dragging!=null)&&k++<900&&document.body.contains(box))st.raf=requestAnimationFrame(tick)};st.raf=requestAnimationFrame(tick)}
  const api={draw,
    hit:(mx,my)=>{const hs=st.hits||[];const c=[...hs].reverse().find(h=>h.kind==='cluster'&&Math.hypot(h.x-mx,h.y-my)<h.r);if(c)return c;let b=null,bd=1e9;hs.forEach(h=>{if(h.kind!=='doc')return;const d=Math.hypot(h.x-mx,h.y-my);if(d<h.r&&d<bd){bd=d;b=h}});return b},
    hover:(h,e)=>{const tip=$('#cvTip'),cv=box.querySelector('canvas');if(!h){cvTip(tip,null,'');hideProfile();if(st.hov){st.hov=null;draw()}if(cv)cv.style.cursor='grab';return}
      cv.style.cursor=h.kind==='cluster'?'move':'pointer';if(h.kind==='cluster'){cvTip(tip,null,'');showProfile(h.c.id,e);return}hideProfile();
      const u=h.u;if(st.hov!==u){st.hov=u;draw()}cvTip(tip,box.parentElement,`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''}${u.y?' · '+u.y:''} · C${u.ci} ${esc(u.cl||'')}`,e)},
    grab:h=>{st.dragging=h.c.id;st.pin.add(h.c.id);run()},
    pull:(h,dx,dy)=>{const W=box.clientWidth,H=350,cam=st.cam,f=Math.min(W,H)*1.35,k=cam.dist/f/0.6,cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
      const rx=dx*k,uy=-dy*k,o=st.off[h.c.id]||(st.off[h.c.id]={x:0,y:0,z:0});o.x+=rx*cy-uy*sp*sy;o.y+=uy*cp;o.z+=-rx*sy-uy*sp*cy},
    release:(h,moved)=>{st.dragging=null;if(!moved)st.pin.delete(h.c.id);run()},
    click:h=>{if(h.kind==='cluster')cvSelect(h.c.id);else if(h.u.id&&typeof openDoc==='function')openDoc(h.u.id)},
    reset:()=>{st.cam={...v3Cam(),yaw:0,pitch:0.18,dist:395,oy:40};st.off={};st.vel={};st.pin.clear()}};
  draw();v3Wire(st,box.querySelector('canvas'),api);box.querySelector('canvas')._api=api;
}

/* ----- B: cluster graph per period (spring layout per panel, same clusters joined through time) ----- */
/* Database flowers in the 3D knowledge map: which database a cluster, project, paper or document comes from */
const CV_FLW={};
function cvFlowerImg(n){
  if(!n||typeof DB_FLOWER==='undefined'||!DB_FLOWER[n])return null;
  if(!CV_FLW[n]){const col=getComputedStyle(document.documentElement).getPropertyValue('--db-'+n).trim()||'#666',img=new Image();
    img.onload=()=>{['#cgGraph','#cvGraph'].forEach(sel=>{const cv=document.querySelector(sel+' canvas.v3');if(cv&&cv._api&&cv._api.draw)cv._api.draw()})};
    img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(DB_FLOWER[n].replace(/^<svg /,'<svg xmlns="http://www.w3.org/2000/svg" ').replace(/currentColor/g,col).replace(/fill-opacity="\.?\d*"/g,'fill-opacity=".6"'));CV_FLW[n]=img}
  const i=CV_FLW[n];return i.complete&&i.naturalWidth?i:null;
}
function cvFlowerBadge(g,n,x,y,r){const img=cvFlowerImg(n);g.fillStyle='#fff';g.beginPath();g.arc(x,y,r,0,Math.PI*2);g.fill();
  g.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--db-'+n).trim()||'#888';g.lineWidth=1;g.stroke();if(img)g.drawImage(img,x-r*.82,y-r*.82,r*1.64,r*1.64)}
setTimeout(()=>{try{DATABASES.forEach(cvFlowerImg)}catch(e){}},0);
/* REQ-26/29 – B page layout that fills its tile.
   v3Proj scales with min(W,H) only, so a wide or tall tile would leave empty margins. Instead the world layout is
   stretched to the tile: periods (GAPX), cluster spread (SPREAD), project row (spanX) grow with the width,
   the layer bands grow with the height (KY). Elsewhere (A/B page) everything keeps the fixed defaults. */
function v3BLayout(BW,GH,n,R,DIST,lay){
  const base=R*V3_GAP;
  if(!lay)return {BW,visW:0,GAPX:base,SPREAD:1,KY:1,sx:i=>(i-(n-1)/2)*base,spanX:(n-1)*base+R*2.4};
  const visW=BW*DIST/(Math.min(BW,GH)*1.35);                                    // world units visible across the tile at the start distance
  const GAPX=n>1?Math.max(base,Math.min(base*6,(visW*0.86-R*3.4)/(n-1))):base;  // distance between period columns
  const SPREAD=Math.min(2.2,Math.max(1,n>1?GAPX/base:visW/(R*5)));              // clusters inside a period spread wider too
  const contentW=n>1?(n-1)*GAPX+R*3.4:visW*0.9;
  const KY=Math.max(1,Math.min(2.6,contentW*GH/BW*0.9/(R*6.2)));                // vertical stretch from the tile's aspect ratio
  return {BW,visW,GAPX,SPREAD,KY,sx:i=>(i-(n-1)/2)*GAPX,spanX:Math.max((n-1)*GAPX+R*2.4,visW*0.86-R)};
}
/* B page layer bands (y up): projects & papers on top, semantic clusters in the middle, documents below –
   stretched by KY; the document band is only as deep as its rows of document marks */
function v3BBands(R,KY,docRows,docSp){
  const Y_PJ=R*2.55*KY,Y_SEM=[-R*1.3*KY,R*1.55*KY],top=Y_SEM[0]-R*0.45;
  return {Y_PJ,Y_TOP:[Y_PJ-R*0.5,Y_PJ+R*0.55],Y_SEM,Y_DOC:[top-Math.max(R*0.7,8+docRows*docSp),top]};
}
/* REQ-29 – zoom (cam.dist) and shift (cam.oy) the camera until the given world points fill W×H (a few fixed-point steps) */
function v3FitCam(cam,pts,W,H,fx=0.96,fy=0.9){
  for(let it=0;it<6;it++){const q=pts.map(([x,y])=>v3Proj(cam,{x,y,z:0},W,H));if(q.some(v=>!v))return;
    const xs=q.map(v=>v.x),ys=q.map(v=>v.y),bw=Math.max(...xs)-Math.min(...xs),bh=Math.max(...ys)-Math.min(...ys);
    cam.dist*=Math.max(bw/(W*fx),bh/(H*fy));cam.oy=(cam.oy||0)+H/2-(Math.max(...ys)+Math.min(...ys))/2}
}
function mountGraph3D(units,cls,box=$('#cvGraph'),key='graph',GH=350){ // key/GH: own camera state and height for the B page
  const S=v3Slices(units),n=S.length,R=58;
  const LAY=key==='graphB',DIST=LAY?560:345;   // B page: three layers – projects & papers / semantic clusters / documents
  const {BW,GAPX,SPREAD,KY,sx,spanX}=v3BLayout(box.clientWidth||600,GH,n,R,DIST,LAY);
  const st=V3[key]||(V3[key]={cam:{...v3Cam(),yaw:0,pitch:0.12,dist:DIST,oy:LAY?10:40},nodes:{}});
  const nodes=[],inSlice=[];
  S.forEach((sl,i)=>{const on=sl.units.filter(u=>u.on);inSlice[i]=on;
    cls.forEach(c=>{const mem=on.filter(u=>u.ci===c.id);if(!mem.length)return;const key=c.id+'|'+i;
      const mx=mem.reduce((s,u)=>s+u.cx,0)/mem.length*R*0.9,my=mem.reduce((s,u)=>s+u.cy,0)/mem.length*R*0.9;   // semantic position
      if(!st.nodes[key])st.nodes[key]={x:sx(i)+mx*SPREAD,y:my*KY,z:((c.id%3)-1)*12,vx:0,vy:0,vz:0,pin:false};
      const nd=st.nodes[key];Object.assign(nd,{key,c,i,mem,ax:sx(i)+(SPREAD>1?mx*SPREAD:0),ay:KY>1?my*KY:0});nodes.push(nd)})});   // ax/ay = anchors the layout pulls towards
  if(!nodes.length){box.innerHTML='<div class="cv-empty">No dated, clustered documents for the current database selection.</div>';return}
  const byKey=Object.fromEntries(nodes.map(d=>[d.key,d]));
  const L=S.map((sl,i)=>cvLinks(inSlice[i]).map(l=>({...l,i,a:byKey[l.a+'|'+i],b:byKey[l.b+'|'+i]})).filter(l=>l.a&&l.b)).flat();
  const T=[];cls.forEach(c=>{const ks=nodes.filter(d=>d.c.id===c.id).sort((a,b)=>a.i-b.i);for(let k=1;k<ks.length;k++)T.push({a:ks[k-1],b:ks[k],c})});
  const rad=d=>5+Math.sqrt(d.mem.length)*3.4;
  const docsOf=d=>d.mem.filter(u=>u.t!=='research_paper');
  const DOCSP=3.4,DCOLS=8,{Y_PJ,Y_TOP,Y_SEM,Y_DOC}=v3BBands(R,KY,Math.ceil(Math.max(1,...nodes.map(d=>docsOf(d).length))/DCOLS),DOCSP);
  // project level above the periods (B page): fixed nodes, linked to the cluster nodes that hold their files
  const PJ=key==='graphB'?cvProjects(units,new Set(nodes.map(d=>d.c.id))):[];
  const PA=LAY?nodes.flatMap(d=>d.mem.filter(u=>u.t==='research_paper').map(u=>({u,d}))):[];   // papers = works of their own (top layer)
  const NT=PJ.length+PA.length,slot=k=>(k-(NT-1)/2)*spanX/Math.max(NT,1);
  PJ.forEach((p,k)=>Object.assign(p,{x:slot(k),y:Y_PJ,z:0,
    to:nodes.map(d=>({d,cnt:d.mem.filter(u=>u.t==='research_project'&&u.pn===p.pn).length})).filter(x=>x.cnt)}));
  PA.forEach((a,k)=>Object.assign(a,{x:slot(PJ.length+k),y:Y_PJ,z:0}));
  // REQ-34: a node may be moved, but only inside its own period column (and the cluster band) – the time axis stays true
  const halfCol=n>1?GAPX/2-R*0.3:(LAY?spanX/2:R*1.5);
  const keep=d=>{const c=sx(d.i);d.x=Math.max(c-halfCol,Math.min(c+halfCol,d.x));if(LAY)d.y=Math.max(Y_SEM[0]+R*0.2,Math.min(Y_SEM[1]-R*0.2,d.y))};
  const step=()=>{
    for(let a=0;a<nodes.length;a++)for(let b=a+1;b<nodes.length;b++){const p=nodes[a],q=nodes[b];if(p.i!==q.i)continue;let dx=p.x-q.x,dy=p.y-q.y,dz=p.z-q.z,d2=dx*dx+dy*dy+dz*dz+0.01,d=Math.sqrt(d2),f=900/d2;
      dx/=d;dy/=d;dz/=d;if(!p.pin){p.vx+=dx*f;p.vy+=dy*f;p.vz+=dz*f}if(!q.pin){q.vx-=dx*f;q.vy-=dy*f;q.vz-=dz*f}}
    const mx=Math.max(1,...L.map(l=>l.n));
    L.forEach(l=>{const p=l.a,q=l.b,dx=q.x-p.x,dy=q.y-p.y,dz=q.z-p.z,d=Math.sqrt(dx*dx+dy*dy+dz*dz)+0.01,k=0.02*(0.4+0.6*l.n/mx)*(d-34)/d;
      if(!p.pin){p.vx+=dx*k;p.vy+=dy*k;p.vz+=dz*k}if(!q.pin){q.vx-=dx*k;q.vy-=dy*k;q.vz-=dz*k}});
    T.forEach(t=>{const p=t.a,q=t.b,k=0.008;['y','z'].forEach(ax=>{const d=(q[ax]-p[ax])*k;if(!p.pin)p['v'+ax]+=d;if(!q.pin)q['v'+ax]-=d})});
    let e=0;nodes.forEach(p=>{if(p.pin){p.vx=p.vy=p.vz=0;return}p.vx-=(p.x-p.ax)*0.02;p.vy-=(p.y-(p.ay||0))*0.01;p.vz-=p.z*0.01;
      p.vx*=0.8;p.vy*=0.8;p.vz*=0.8;p.x+=p.vx;p.y+=p.vy;p.z+=p.vz;keep(p);e+=Math.abs(p.vx)+Math.abs(p.vy)+Math.abs(p.vz)});
    return e;
  };
  const draw=()=>{
    const {g,W,H}=v3Canvas(box,GH);g.clearRect(0,0,W,H);const css=getComputedStyle(document.documentElement),muted=css.getPropertyValue('--muted').trim()||'#888',fg=css.getPropertyValue('--fg').trim()||'#222';
    const P=p=>v3Proj(st.cam,p,W,H);st.hits=[];
    S.forEach((sl,i)=>{const lp=P({x:sx(i)-R*1.1,y:R*1.15,z:0});if(lp){g.fillStyle=fg;g.font='600 12px "IBM Plex Sans",sans-serif';g.fillText(sl.label,lp.x,lp.y)}
      const a=P({x:sx(i)+R*1.2,y:-R*1.1,z:0}),b=P({x:sx(i)+R*1.2,y:R*1.1,z:0});if(a&&b&&i<n-1){g.strokeStyle='rgba(128,140,170,.25)';g.lineWidth=1;g.beginPath();g.moveTo(a.x,a.y);g.lineTo(b.x,b.y);g.stroke()}});
    if(LAY){const x0=-spanX/2-R*0.5,x1=spanX/2+R*0.5,band=(y0,y1,lab,col,right)=>{const c=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]].map(([x,y])=>P({x,y,z:0}));if(c.some(v=>!v))return;
        g.fillStyle=col;g.beginPath();c.forEach((v,k)=>k?g.lineTo(v.x,v.y):g.moveTo(v.x,v.y));g.closePath();g.fill();g.strokeStyle='rgba(128,140,170,.35)';g.setLineDash([4,5]);g.lineWidth=1;g.beginPath();g.moveTo(c[0].x,c[0].y);g.lineTo(c[1].x,c[1].y);g.stroke();g.setLineDash([]);
        const l=P({x:right?x1:x0,y:y1,z:0});if(l){g.fillStyle=muted;g.font='600 10.5px "IBM Plex Sans",sans-serif';g.textAlign=right?'right':'left';g.fillText(lab,l.x+(right?-6:6),l.y+13);g.textAlign='left'}};
      band(Y_TOP[0],Y_TOP[1],'PROJECTS & PAPERS','rgba(31,95,139,.06)');band(Y_SEM[0],Y_SEM[1],'SEMANTIC CLUSTERS','rgba(217,72,15,.04)',true);band(Y_DOC[0],Y_DOC[1],'DOCUMENTS','rgba(110,120,140,.06)',true)}
    T.forEach(t=>{const p=P(t.a),q=P(t.b);if(!p||!q)return;g.globalAlpha=cvOff(t.c.id)?.15:.55;g.strokeStyle=cvCol(t.c.id);g.lineWidth=1.5;g.setLineDash([2,4]);g.beginPath();g.moveTo(p.x,p.y);g.lineTo(q.x,q.y);g.stroke();g.setLineDash([]);g.globalAlpha=1});
    const mx=Math.max(1,...L.map(l=>l.n));
    L.forEach(l=>{const p=P(l.a),q=P(l.b);if(!p||!q)return;g.strokeStyle='rgba(217,72,15,.45)';g.lineWidth=1+3*l.n/mx;g.beginPath();g.moveTo(p.x,p.y);g.lineTo(q.x,q.y);g.stroke()});
    if(LAY){   // document layer: the cluster's documents below it, joined by a thin stem
      const tc={research_paper:css.getPropertyValue('--t-paper').trim()||'#6b4fa3',research_notes:css.getPropertyValue('--t-notes').trim()||'#2e7d4f',research_project:css.getPropertyValue('--t-project').trim()||'#1f5f8b',
        legal_project:css.getPropertyValue('--t-legal').trim()||'#a23b2a',legal_guideline:css.getPropertyValue('--t-guideline').trim()||'#9a6a00',standard:css.getPropertyValue('--t-standard').trim()||'#3f6f7a'};
      nodes.forEach(d=>{const ds=docsOf(d);if(!ds.length)return;const dim=cvOff(d.c.id),top=P({x:d.x,y:Y_DOC[1]-1,z:d.z}),q=P(d);if(top&&q){g.globalAlpha=dim?.12:.35;g.strokeStyle=cvCol(d.c.id);g.lineWidth=1;g.beginPath();g.moveTo(q.x,q.y);g.lineTo(top.x,top.y);g.stroke()}
        ds.forEach((u,k)=>{const col=k%DCOLS,row=Math.floor(k/DCOLS),w=P({x:d.x+(col-(Math.min(DCOLS,ds.length)-1)/2)*DOCSP,y:Y_DOC[1]-3-row*DOCSP,z:d.z});if(!w)return;
          const r=Math.max(1.6,1.25*w.s);g.globalAlpha=dim?.2:.9;g.fillStyle=CG.mode==='db'&&(u.db||[])[0]?(getComputedStyle(document.documentElement).getPropertyValue('--db-'+u.db[0]).trim()||muted):(tc[u.t]||muted);g.beginPath();
          if(u.t==='research_project'){g.moveTo(w.x,w.y-r*1.3);g.lineTo(w.x+r*1.3,w.y);g.lineTo(w.x,w.y+r*1.3);g.lineTo(w.x-r*1.3,w.y);g.closePath()}else if(LEGAL_T.has(u.t)){g.moveTo(w.x,w.y-r*1.4);g.lineTo(w.x+r*1.25,w.y+r*.9);g.lineTo(w.x-r*1.25,w.y+r*.9);g.closePath()}else g.arc(w.x,w.y,r,0,Math.PI*2);g.fill();
          st.hits.push({kind:'doc',u,x:w.x,y:w.y,r:r+2})});g.globalAlpha=1});
      if(PA.length){const pp=tc.research_paper;PA.forEach(a=>{const t=P(a),q=P(a.d);if(!t||!q)return;g.globalAlpha=cvOff(a.d.c.id)?.1:.45;g.strokeStyle=pp;g.lineWidth=1.2;g.beginPath();g.moveTo(t.x,t.y);g.lineTo(q.x,q.y);g.stroke();g.globalAlpha=1;
        const r=Math.max(4,5.5*t.s);g.fillStyle=pp;g.fillRect(t.x-r,t.y-r,2*r,2*r);g.strokeStyle='rgba(255,255,255,.9)';g.lineWidth=1.5;g.strokeRect(t.x-r,t.y-r,2*r,2*r);
        (a.u.db||[]).filter(n=>DB_FLOWER[n]).slice(0,2).forEach((n,k)=>cvFlowerBadge(g,n,t.x+(k-((Math.min(2,(a.u.db||[]).length))-1)/2)*11,t.y-r-7,5.5));
        st.hits.push({kind:'doc',u:a.u,x:t.x,y:t.y,r:r+3})})}
    }
    if(PJ.length){const pc=css.getPropertyValue('--t-project').trim()||'#1f5f8b',mxp=Math.max(1,...PJ.flatMap(p=>p.to.map(t=>t.cnt))),anyS=CV.sels.size>0;
      PJ.forEach(p=>{const a=P(p);if(!a)return;p.to.forEach(t=>{const b=P(t.d);if(!b)return;g.globalAlpha=anyS&&!cvHas(t.d.c.id)?.1:.5;g.strokeStyle=pc;g.lineWidth=1+5*t.cnt/mxp;g.beginPath();g.moveTo(a.x,a.y);g.lineTo(b.x,b.y);g.stroke()});g.globalAlpha=1});
      PJ.forEach(p=>{const a=P(p);if(!a)return;const r=Math.max(8,11*a.s);g.fillStyle=pc;g.beginPath();g.arc(a.x,a.y,r,0,Math.PI*2);g.fill();g.strokeStyle='rgba(255,255,255,.9)';g.lineWidth=2;g.stroke();
        g.fillStyle='#fff';g.beginPath();g.moveTo(a.x,a.y-r*.45);g.lineTo(a.x+r*.45,a.y);g.lineTo(a.x,a.y+r*.45);g.lineTo(a.x-r*.45,a.y);g.closePath();g.fill();
        const nx=[...PJ,...PA].map(q=>P(q)).filter(q=>q&&q.x>a.x+1).reduce((m,q)=>Math.min(m,q.x-8),W),room=nx-a.x-r-14;   // name fits up to the next project or paper
        g.fillStyle=fg;g.font='600 12px "IBM Plex Sans",sans-serif';let nm=p.pn;while(nm.length>4&&g.measureText(nm).width>room)nm=nm.slice(0,-2)+'…';if(nm!==p.pn&&!nm.endsWith('…'))nm+='…';g.fillText(nm,a.x+r+5,a.y-1);g.fillStyle=muted;g.font='10.5px "IBM Plex Sans",sans-serif';const sub=`${p.n} docs · ${p.by.size} clusters`;if(g.measureText(sub).width<=room)g.fillText(sub,a.x+r+5,a.y+12);
        const pr=PROJECTS.find(x=>x.name===p.pn);((pr&&pr.db)||[]).filter(n=>DB_FLOWER[n]).forEach((n,k)=>cvFlowerBadge(g,n,a.x-r*.8-k*11,a.y-r*.8,5.5));
        st.hits.push({kind:'project',p,x:a.x,y:a.y,r:r+3})})}
    nodes.map(d=>({d,p:P(d)})).filter(x=>x.p).sort((a,b)=>b.p.z-a.p.z).forEach(({d,p})=>{const dim=cvOff(d.c.id),r=Math.max(6,rad(d)*p.s*1.1);
      g.globalAlpha=dim?.35:1;g.fillStyle=cvCol(d.c.id);g.beginPath();g.arc(p.x,p.y,r,0,Math.PI*2);g.fill();g.strokeStyle=d.pin?'#0e8fa0':'rgba(255,255,255,.9)';g.lineWidth=d.pin?3:1.5;g.stroke();
      g.fillStyle='#fff';g.font=`600 ${r>11?11:9}px "IBM Plex Mono",monospace`;g.textAlign='center';g.fillText('C'+d.c.id,p.x,p.y+3.5);g.textAlign='left';g.globalAlpha=1;
      g.fillStyle=muted;g.font='10px "IBM Plex Mono",monospace';g.fillText(String(d.mem.length),p.x+r+2,p.y-r+4);
      // one flower per database that contributes documents to this cluster node (arc over its top left)
      const dbs=[...new Set(d.mem.flatMap(u=>u.db||[]))].filter(n=>DB_FLOWER[n]);g.globalAlpha=dim?.35:1;
      dbs.forEach((n,k)=>{const an=(-150+k*34)*Math.PI/180,rr=r+3;cvFlowerBadge(g,n,p.x+Math.cos(an)*rr,p.y+Math.sin(an)*rr,5.5)});g.globalAlpha=1;
      st.hits.push({kind:'cluster',c:d.c,node:d,x:p.x,y:p.y,r:r+2})});
  };
  const run=()=>{cancelAnimationFrame(st.raf);let k=0;const tick=()=>{const e=step();draw();if((e>0.05||st.dragging)&&k++<900&&document.body.contains(box))st.raf=requestAnimationFrame(tick)};st.raf=requestAnimationFrame(tick)};
  const api={draw,
    hit:(mx,my)=>[...(st.hits||[])].reverse().find(h=>Math.hypot(h.x-mx,h.y-my)<h.r)||null,
    hover:(h,e)=>{const cv=box.querySelector('canvas'),tip=key==='graphB'?$('#cgTip'):null;if(tip)cvTip(tip,null,'');if(!h){hideProfile();if(cv)cv.style.cursor='grab';return}
      if(h.kind==='project'){if(cv)cv.style.cursor='pointer';if(tip)cvTip(tip,box.parentElement,cvProjTipHtml(h.p),e);return}
      if(h.kind==='doc'){const u=h.u;if(cv)cv.style.cursor='pointer';if(tip)cvTip(tip,box.parentElement,`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''}${u.y?' · '+u.y:''} · C${u.ci}${u.pn?' · '+esc(u.pn):''}<br><i>click to open</i>`,e);return}cv.style.cursor='move';showProfile(h.c.id,e)},
    grab:h=>{st.dragging=true;h.node.pin=true;run()},
    pull:(h,dx,dy)=>{const W=box.clientWidth,H=GH,cam=st.cam,f=Math.min(W,H)*1.35,k=cam.dist/f,cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
      const rx=dx*k,uy=-dy*k,d=h.node;d.x+=rx*cy-uy*sp*sy;d.y+=uy*cp;d.z+=-rx*sy-uy*sp*cy;keep(d)},
    release:(h,moved)=>{st.dragging=false;if(!moved)h.node.pin=false;run()},
    click:h=>{if(h.kind==='project'){cvSelectProject(h.p);return}if(h.kind==='doc'){if(h.u.id&&typeof openDoc==='function')openDoc(h.u.id);return}if(key==='graphB'){cgPick(h.c.id);return}cvSelect(h.c.id)},
    reset:()=>{st.cam={...v3Cam(),yaw:0,pitch:LAY?0.12:0.18,dist:DIST,oy:LAY?10:40};st.nodes={};st.fit=null;mountGraph3D(cvUnits(),cvClusters(cvUnits()),box,key,GH)}};
  if(LAY){const fk=BW+'x'+GH+'|'+n+'|'+NT;   // fit once per tile size / data shape – the user's own zoom survives redraws
    if(st.fit!==fk){st.fit=fk;const x0=-spanX/2-R*0.5,x1=spanX/2+R*0.5;
      v3FitCam(st.cam,[[x0,Y_TOP[1]],[x1,Y_TOP[1]],[x0,Y_DOC[0]],[x1,Y_DOC[0]],[x0,Y_SEM[0]],[x1,Y_SEM[1]]],BW,GH)}}
  draw();v3Wire(st,box.querySelector('canvas'),api);box.querySelector('canvas')._api=api;run();
  $('#cvGraphHint').textContent=`Per period: node size = documents in that period · orange = bridges within the period · dotted = the same cluster from period to period`;
}
function v3Toggle(){
  $$('.v3-toggle').forEach(b=>{b.textContent=V3.on?'2D':'3D';b.title=V3.on?'Show the flat 2D views':'Show the cluster views in 3D (rotate, drag clusters)'});
}
$$('.v3-toggle').forEach(b=>b.addEventListener('click',()=>{V3.on=!V3.on;try{localStorage.setItem('cv3d',V3.on?'1':'0')}catch(e){}v3Toggle();renderClusterViz();renderClusterPage()}));
v3Toggle();
/* "⟲ Reset view" next to 2D/3D: back to the start view of that panel (same as a double-click on the 3D view) */
$$('.v3-reset').forEach(b=>b.addEventListener('click',()=>{
  const panel=b.closest('.cv, .cg-main');const cv=panel&&panel.querySelector('canvas.v3');
  if(cv&&cv._api&&cv._api.reset){cv._api.reset();cv._api.draw&&cv._api.draw()}
  if(panel&&panel.closest('#page-graph'))renderClusterPage();else renderClusterViz();
  try{toast('View reset')}catch(e){}
}));

/* Cluster label for the legend chips: a leading database name ("Magnolia · …" or "ML · …") is shown as its flower icon */
/* REQ-04 – descriptive cluster names: the title from clustering (LLM, or built from the cluster's most distinctive
   word pairs), else a readable name made from the distinctive terms; the term list itself is only shown as a detail. */
function cvDbPrefix(label){const m=String(label||'').match(/^([^·]+?)\s*·\s*/);if(!m)return null;const k=m[1].trim(),id=DB_FLOWER[k]?k:Object.keys(DB_NAME).find(i=>DB_NAME[i]===k);return id&&DB_FLOWER[id]?{id,rest:String(label).slice(m[0].length)}:null}
function cvTermsName(label){
  const p=cvDbPrefix(label),t=(p?p.rest:String(label||'')).split(' · ').map(x=>x.trim()).filter(Boolean).slice(0,3);
  const tc=w=>/^(ai|llm|pls|sem|hr|it|esg|csr|ux|ui|qca|nlp|rag)$/i.test(w)?w.toUpperCase():w[0].toUpperCase()+w.slice(1);
  if(!t.length)return '';const w=t.map(tc);return w.length===1?w[0]:w.slice(0,-1).join(', ')+' and '+w[w.length-1];
}
function cvName(c,info){const i=(info||clusterInfo()||{})[c.id];return (i&&i.title&&dbRelabel(i.title))||cvTermsName(c.label)||('Cluster '+c.id)}
function cvChipHtml(c,info){const p=cvDbPrefix(c.label);return (p?`<i class="cv-flw" style="color:${dbColor(p.id)}" title="${esc(dbName(p.id))}">${DB_FLOWER[p.id]}</i>`:'')+esc(cvName(c,info))}
function cvLabelHtml(label){
  const s=String(label||''),m=s.match(/^([^·]+?)\s*·\s*/);
  if(m){const k=m[1].trim(),id=DB_FLOWER[k]?k:Object.keys(DB_NAME).find(i=>DB_NAME[i]===k);
    if(id&&DB_FLOWER[id])return `<i class="cv-flw" style="color:${dbColor(id)}" title="${esc(dbName(id))}">${DB_FLOWER[id]}</i>${esc(s.slice(m[0].length))}`}
  return esc(s);
}
function renderClusterViz(){
  if(typeof cpRenderSel==='function')cpRenderSel();   // descriptions of the selected clusters below the views
  cvBasisBadge();
  const band=$('#cviz');if(!band||band.classList.contains('collapsed')||$('#page-chat').hidden)return;
  const units=cvUnits(),cls=cvClusters(units);
  if(!CV.sels.size&&$('#rCluster')&&$('#rCluster').value!=='')CV.sels.add(+$('#rCluster').value);
  [...CV.sels].forEach(id=>{if(!cls.find(c=>c.id===id))CV.sels.delete(id)});
  if(typeof cpRenderSel==='function')cpRenderSel();
  const run=(DEMO&&!LIVE&&DEMO.clusters&&DEMO.clusters.run)||'';
  if(units.length<2){
    const msg='<div class="cv-empty">No cluster analysis yet.<br>Papers, notes and projects need a structured summary and a summary vector; clustering runs automatically after ingestion.</div>';
    $('#cvMap').innerHTML=msg;$('#cvGraph').innerHTML=msg;$('#cvLegend').innerHTML='';$('#cvMapMeta').textContent='';$('#cvGraphMeta').textContent='';$('#cvGraphHint').textContent='';return;
  }
  const nOn=units.filter(u=>u.on).length;
  $('#cvMapMeta').textContent=`${SEL_DB.length?cls.filter(c=>c.on.length).length:cls.length} clusters · ${nOn}${SEL_DB.length?'':'/'+units.length} data points${SEL_DB.length?' in '+dbNames(SEL_DB).join('+'):''}${run?' · run '+run.slice(0,10):''}`;
  // ---- map
  const box=$('#cvMap'),W=Math.max(320,box.clientWidth||600),H=230,P=18;
  const X=v=>P+(v+1)/2*(W-2*P),Y=v=>P+(1-(v+1)/2)*(H-2*P);
  let g='';
  const only=SEL_DB.length>0;   // a database selection shows only its own point clouds
  cls.forEach(c=>{
    if(only&&!c.on.length)return;
    const pts=(c.on.length?c.on:c.all).map(u=>[X(u.cx),Y(u.cy)]);
    const mx=pts.reduce((a,p)=>a+p[0],0)/pts.length,my=pts.reduce((a,p)=>a+p[1],0)/pts.length;
    const sx=Math.sqrt(pts.reduce((a,p)=>a+(p[0]-mx)**2,0)/pts.length),sy=Math.sqrt(pts.reduce((a,p)=>a+(p[1]-my)**2,0)/pts.length);
    c.mx=mx;c.my=my;const dim=(cvOff(c.id))||!c.on.length;
    g+=`<ellipse class="pt" data-c="${c.id}" cx="${mx}" cy="${my}" rx="${Math.min(W*.2,Math.max(16,sx*1.7+10))}" ry="${Math.min(H*.42,Math.max(14,sy*1.7+10))}" fill="${cvCol(c.id,55)}" fill-opacity="${dim?.03:.12}" stroke="${cvCol(c.id)}" stroke-opacity="${dim?.15:.55}" stroke-dasharray="4 3"/>`;
  });
  units.forEach(u=>{if(only&&!u.on)return;const dim=!u.on||(cvOff(u.ci));g+=`<g class="pt" data-u="${u.id||''}" data-p="${u.t==='research_project'?esc(u.pn):''}" data-c="${u.ci}">${cvShape(u,X(u.cx),Y(u.cy),cvCol(u.ci),dim)}</g>`});
  cls.forEach(c=>{if(only&&!c.on.length)return;const dim=(cvOff(c.id))||!c.on.length;g+=`<g class="pt" data-c="${c.id}" opacity="${dim?.3:1}"><rect x="${c.mx-14}" y="${c.my-27}" width="28" height="15" rx="7.5" fill="${cvCol(c.id)}"/><text x="${c.mx}" y="${c.my-16}" text-anchor="middle" font-size="10.5" font-weight="700" style="fill:#fff">C${c.id}</text></g>`});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cluster map: papers, notes and projects positioned by similarity of their structured summaries">${cvFlowerDefs()}${g}</svg>`;
  const cvInfo=clusterInfo();
  $('#cvLegend').innerHTML=cls.filter(c=>!only||c.on.length).map(c=>`<button type="button" data-c="${c.id}" aria-pressed="${cvHas(c.id)}" style="--h:${cvHue(c.id)}" title="Add or remove cluster ${c.id} from the search space of both chats"><b>C${c.id}</b><span title="Distinctive terms: ${esc(cvTermsName(c.label)?(cvDbPrefix(c.label)||{rest:c.label}).rest:c.label)}">${cvChipHtml(c,cvInfo)} · ${c.on.length}</span></button>`).join('')+
    `<span class="srcnote" style="align-self:center;margin-left:4px">■ paper ● note ◆ project · flower = database · click clusters to select them for both chats${CV.sels.size?` · <a href="#" data-clear-cl>clear selection (${[...CV.sels].map(x=>'C'+x).join(', ')})</a>`:''}</span>`;
  if(CV.mode==='db'){const r=cvDbOverlay(units,cls,X,Y,W,H);box.innerHTML=r.svg;$('#cvLegend').innerHTML=r.legend;
    $('#cvMapMeta').textContent=r.dbs.length?`comparing ${r.dbs.join(' · ')}${run?' · run '+run.slice(0,10):''}`:'no database with clustered documents';}
  $$('#cvLegend button[data-c]').forEach(b=>b.addEventListener('click',()=>cvSelect(+b.dataset.c)));
  wireProfileHover('#cvLegend button[data-c]');
  $$('#cvLegend [data-clear-cl]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();cvClear()}));
  const tip=$('#cvTip');
  $$('#cvMap .pt').forEach(el=>{
    const u=el.dataset.u!==undefined&&(el.dataset.u||el.dataset.p)?units.find(x=>(el.dataset.u&&x.id===el.dataset.u)||(el.dataset.p&&x.t==='research_project'&&x.pn===el.dataset.p)):null;
    const c=cls.find(x=>x.id===+el.dataset.c);
    el.addEventListener('mousemove',ev=>!u&&el.dataset.c?(cvTip(tip,null,''),showProfile(+el.dataset.c,ev)):cvTip(tip,box.parentElement,u?`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''} · C${u.ci} ${esc(u.cl||'')}${u.ca!=null?`<br>also close to C${u.ca}`:''}${u.on?'':'<br><i>outside the selected databases</i>'}`:`<b>C${c.id}</b> ${esc(c.label)}<br>${c.on.length} data points`,ev));
    el.addEventListener('mouseleave',()=>{cvTip(tip,null,'');hideProfile()});
    el.addEventListener('click',()=>{if(u&&u.id&&typeof openDoc==='function')openDoc(u.id);else cvSelect(+el.dataset.c)});
  });
  renderClusterGraph(units,cls);
  if(V3.on){mountMap3D(units,cls);mountGraph3D(units,cls)}
}
/* Project level above the clusters (B page): one node per research project, linked to every cluster that holds
   files of the project (line width = number of files). A click selects all clusters of the project for the chats. */
function cvProjects(units,ids){
  const m=new Map();units.forEach(u=>{if(!u.on||u.t!=='research_project'||!u.pn||(ids&&!ids.has(u.ci)))return;
    const p=m.get(u.pn)||{pn:u.pn,n:0,by:new Map()};p.n++;p.by.set(u.ci,(p.by.get(u.ci)||0)+1);m.set(u.pn,p)});
  return [...m.values()].sort((a,b)=>a.pn.localeCompare(b.pn));
}
function cvProjTitle(pn){const p=(typeof PROJECTS!=='undefined'?PROJECTS:[]).find(x=>x.name===pn);return (p&&p.title)||pn}
function cvProjTipHtml(p){const cl=[...p.by.entries()].sort((a,b)=>b[1]-a[1]),pr=(typeof PROJECTS!=='undefined'?PROJECTS:[]).find(x=>x.name===p.pn),tot=pr&&pr.files;
  return `<b>Project ${esc(p.pn)}</b><br>${esc(cvProjTitle(p.pn))}<br>${p.n} document${p.n>1?'s':''} on the map${tot?` (of ${tot} files – those with their own summary)`:''}, in ${cl.length} cluster${cl.length>1?'s':''}: ${cl.slice(0,8).map(([c,n])=>`C${c} (${n})`).join(', ')}${cl.length>8?' …':''}<br><i>click to select these clusters</i>`}
function cvSelectProject(p){
  const ids=[...p.by.keys()];const all=ids.every(id=>CV.sels.has(id));
  CV.sels=all?new Set([...CV.sels].filter(id=>!ids.includes(id))):new Set(ids);   // click again = deselect
  const r=$('#rCluster');if(r)r.value=CV.sels.size===1?String([...CV.sels][0]):'';
  try{syncParams('rag');syncParams('graph')}catch(e){}
  CG.sel=CV.sels.size?[...p.by.entries()].sort((a,b)=>b[1]-a[1])[0][0]:null;
  CG.proj=all?null:p.pn;   // REQ-09: the project card opens top right (closes again on the second click)
  renderClusterViz();renderClusterPage();const b=$('#page-graph .bq-cluster .bq-body');if(b)b.scrollTop=0;
}
/* REQ-09: project card at the top of "Projects & clusters" – what the project contains and how it relates to the clusters */
function cgRenderProj(units){
  const box=$('#cgProjCard');if(!box)return;
  const p=CG.proj&&PROJECTS.find(x=>x.name===CG.proj);
  if(!p){box.hidden=true;box.innerHTML='';return}
  const mine=units.filter(u=>u.t==='research_project'&&u.pn===p.name&&u.on),by=new Map();mine.forEach(u=>by.set(u.ci,(by.get(u.ci)||0)+1));
  const cls=cvClusters(units),info=clusterInfo();
  const roles=Object.entries(p.roles||{}).filter(([k])=>k!=='other').sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,v])=>`${esc((typeof ROLE_LABEL!=='undefined'&&ROLE_LABEL[k])||k.replace(/_/g,' '))} ${v}`).join(' · ');
  const purpose=(p.summary&&p.summary.purpose)||'';
  box.innerHTML=`<div class="cpd-bar"><span>Project</span><span class="cpd-state">${esc(p.name)} · its clusters are selected below</span><button type="button" class="cpd-x" data-pclose title="Close the project and deselect its clusters">✕</button></div>
    <div class="bpcard"><div class="pc-h"><i aria-hidden="true">◆</i><b>${esc(p.title||p.name)}</b></div>
      ${purpose?`<p class="cp-d">${esc(purpose.length>320?purpose.slice(0,319).replace(/\s+\S*$/,'')+'…':purpose)}</p>`:''}
      <dl class="kv"><dt>Folder</dt><dd>${esc(p.name)}${(p.db||[]).length?' · '+(p.db||[]).map(n=>`<span class="pdbi" style="color:${dbColor(n)}" title="${esc(dbName(n))}">${dbIcon(n)}</span>${esc(dbName(n))}`).join(', '):''}</dd>
        ${teamRowHtml(p)}
        <dt>Files</dt><dd>${p.files||0} (${p.indexed||0} with full text) · ${mine.length} on the map</dd>
        <dt>Period</dt><dd>${p.from_?p.from_.slice(0,4):'–'} – ${p.to?p.to.slice(0,4):'–'}</dd>
        ${(p.keywords||[]).length?`<dt>Keywords</dt><dd>${esc(p.keywords.slice(0,6).join(', '))}</dd>`:''}
        ${roles?`<dt>Contents</dt><dd>${roles}</dd>`:''}</dl>
      ${typeof cgProgressSection==='function'?cgProgressSection(p.name):''}
      <h6>Clusters of this project</h6><div class="cp-conn">${[...by.entries()].sort((a,b)=>b[1]-a[1]).map(([ci,n])=>{const c=cls.find(k=>k.id===ci)||{id:ci,label:''};
        return `<button type="button" data-cc="${ci}" style="--h:${cvHue(ci)}" aria-pressed="${cvHas(ci)}" title="${n} document${n>1?'s':''} of the project in C${ci}"><b>C${ci}</b><span>${esc(cvName(c,info))}</span><small>${n}</small></button>`}).join('')}</div>
      ${cpDocListHtml(mine,'project')}</div>`;
  box.hidden=false;
  box.querySelector('[data-pclose]').addEventListener('click',()=>{const pj=cvProjects(units).find(x=>x.pn===p.name);CG.proj=null;if(pj&&[...pj.by.keys()].every(id=>CV.sels.has(id)))cvSelectProject(pj);else renderClusterPage()});
  cpWireConn(box);wireTeam(box,()=>cgRenderProj(units));if(typeof wireProgress==='function')wireProgress(box);
}
function renderClusterGraph(units,cls,o={}){
  const big=!!o.big,box=o.box||$('#cvGraph');
  const W=Math.max(320,box.clientWidth||600),H=big?Math.max(240,box.clientHeight||380):230;
  const isSel=id=>big?CG.sel===id:cvHas(id),anyS=big?CG.sel!=null:CV.sels.size>0,colorDb=big?CG.mode==='db':CV.mode==='db',showDocs=true;
  const links=cvLinks(units),act=cls.filter(c=>c.on.length),info=clusterInfo();
  if(!big){
    $('#cvGraphMeta').textContent=`${act.length} cluster nodes · ${links.length} bridges`;
    $('#cvGraphHint').textContent='Node size = data points · line = documents whose second-closest cluster is the other node · click a node to ask the Graph Chat';
  }
  if(!act.length){box.innerHTML='<div class="cv-empty">No clustered documents for the current database selection.</div>';return {act,links}}
  const K=big?Math.min(1.9,Math.max(1.15,Math.min(W,H)/320)):1;
  const R=c=>(9+Math.sqrt(c.on.length)*4.2)*K;
  // deterministic force layout
  const N=act.map((c,i)=>({c,x:W/2+Math.cos(i/act.length*2*Math.PI)*W*.3,y:H/2+Math.sin(i/act.length*2*Math.PI)*H*.3,vx:0,vy:0}));
  const idx=new Map(N.map((n,i)=>[n.c.id,i]));
  for(let it=0;it<320;it++){
    for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){const a=N[i],b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy)||.01;const f=5200*K*K/(d*d);dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
    links.forEach(l=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||.01,f=(d-(R(a.c)+R(b.c)+(big?120:60)*K))*.02*Math.min(3,1+l.n/4);a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f});
    N.forEach(n=>{n.vx+=(W/2-n.x)*.01;n.vy+=(H/2-n.y)*.02;n.x+=n.vx*.5;n.y+=n.vy*.5;n.vx*=.6;n.vy*=.6});
  }
  // fit into the box
  const PJ=big?cvProjects(units,new Set(act.map(c=>c.id))):[],band=PJ.length?78:0;   // project level on top
  const pad=big?90:40,minX=Math.min(...N.map(n=>n.x-R(n.c))),maxX=Math.max(...N.map(n=>n.x+R(n.c))),minY=Math.min(...N.map(n=>n.y-R(n.c))),maxY=Math.max(...N.map(n=>n.y+R(n.c)));
  const sc=Math.min((W-2*pad)/Math.max(1,maxX-minX),(H-band-2*pad)/Math.max(1,maxY-minY),1.6);
  N.forEach(n=>{n.x=W/2+(n.x-(minX+maxX)/2)*sc;n.y=band+(H-band)/2+(n.y-(minY+maxY)/2)*sc});
  let g='';const maxN=Math.max(1,...links.map(l=>l.n));
  links.forEach(l=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const hi=anyS&&(isSel(l.a)||isSel(l.b)),dim=anyS&&!hi;
    g+=`<line class="cnode" data-l="${l.a}-${l.b}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="var(--c2)" stroke-width="${(1.2+l.n/maxN*6)*(big?1.4:1)}" stroke-linecap="round" opacity="${dim?.12:hi?.85:.45}"/>`;
    if(big&&!dim){const mx=(a.x+b.x)/2,my=(a.y+b.y)/2;g+=`<g><rect x="${mx-11}" y="${my-9}" width="22" height="16" rx="8" fill="var(--panel)" stroke="var(--c2)" stroke-opacity=".5"/><text x="${mx}" y="${my+3}" text-anchor="middle" font-size="10.5" class="muted">${l.n}</text></g>`}
  });
  if(PJ.length){
    const mxp=Math.max(1,...PJ.flatMap(p=>[...p.by.values()])),py=30;
    PJ.forEach((p,k)=>{p.x=W*(k+1)/(PJ.length+1);p.y=py});
    PJ.forEach(p=>p.by.forEach((cnt,ci)=>{const nd=N[idx.get(ci)];if(!nd)return;const dim=anyS&&!isSel(ci);
      g+=`<line class="cproj-l" x1="${p.x}" y1="${p.y+12}" x2="${nd.x}" y2="${nd.y-R(nd.c)}" stroke="var(--t-project)" stroke-width="${1+cnt/mxp*7}" stroke-linecap="round" opacity="${dim?.1:.45}"/>`}));
    const maxCh=Math.max(6,Math.floor((W/(PJ.length+1)-34)/7));   // name fits up to the next project
    PJ.forEach(p=>{const nm=p.pn.length>maxCh?p.pn.slice(0,maxCh-1)+'…':p.pn;
      g+=`<g class="cproj" data-pn="${esc(p.pn)}" style="cursor:pointer"><circle cx="${p.x}" cy="${p.y}" r="13" fill="var(--t-project)" stroke="var(--panel)" stroke-width="2"/>`+
        `<path d="M${p.x} ${p.y-6}L${p.x+6} ${p.y}L${p.x} ${p.y+6}L${p.x-6} ${p.y}Z" fill="#fff" opacity=".9"/>`+
        `<text x="${p.x+19}" y="${p.y-1}" font-size="12.5" font-weight="600">${esc(nm)}</text><text x="${p.x+19}" y="${p.y+13}" font-size="10.5" class="muted">${p.n} docs · ${p.by.size} clusters</text></g>`});
    g+=`<text x="10" y="14" font-size="10.5" class="muted" style="letter-spacing:.06em">PROJECTS</text><line x1="0" y1="${band-6}" x2="${W}" y2="${band-6}" stroke="var(--line)" stroke-dasharray="3 4"/>`;
  }
  N.forEach(n=>{
    const c=n.c,r=R(c),dim=anyS&&!isSel(c.id),op=dim?.25:1;
    if(showDocs)c.on.forEach((u,i)=>{const a=i/c.on.length*2*Math.PI-Math.PI/2,ring=r+(big?14:7),ux=n.x+Math.cos(a)*ring,uy=n.y+Math.sin(a)*ring;
      const col=colorDb?`var(--db-${(u.db||[])[0]||'none'},var(--muted))`:(TYPE_COLOR[u.t]||'var(--t-project)');
      const sz=big?5.5:2.6,attrs=big?` class="cnode doc" data-u="${esc(u.id||'')}" data-pn="${u.t==='research_project'?esc(u.pn):''}" data-c="${c.id}"`:'';
      g+=`<g${attrs} opacity="${op}">`+(u.t==='research_project'?`<path d="M${ux} ${uy-sz*1.6}L${ux+sz*1.6} ${uy}L${ux} ${uy+sz*1.6}L${ux-sz*1.6} ${uy}Z" fill="${col}" stroke="var(--panel)"/>`:LEGAL_T.has(u.t)?`<path d="M${ux} ${uy-sz*1.5}L${ux+sz*1.35} ${uy+sz}L${ux-sz*1.35} ${uy+sz}Z" fill="${col}" stroke="var(--panel)"/>`:u.t==='research_paper'&&big?`<rect x="${ux-sz}" y="${uy-sz}" width="${sz*2}" height="${sz*2}" rx="1.5" fill="${col}" stroke="var(--panel)"/>`:`<circle cx="${ux}" cy="${uy}" r="${sz}" fill="${col}" stroke="var(--panel)" stroke-width="${big?1:0}"/>`)+'</g>'});
    const nm=cvName(c,info),title=big||nm.length<=26?nm:nm.slice(0,25).replace(/\s+\S*$/,'')+'…';
    const words=(c.label||'').split(' · ').slice(0,2).join(' · ');   // distinctive terms as a detail line (big graph)
    const ly=n.y+r+(big?(showDocs?34:22):19);
    g+=`<g class="cnode" data-c="${c.id}" opacity="${op}"><circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${cvCol(c.id)}" stroke="${isSel(c.id)?'var(--c2)':'var(--panel)'}" stroke-width="${isSel(c.id)?(big?5:3):1.5}"/>`+
      `<text x="${n.x}" y="${n.y+(big?6:4)}" text-anchor="middle" font-size="${big?17:11.5}" font-weight="700" style="fill:#fff">C${c.id}</text>`+
      (big?`<text x="${n.x}" y="${n.y+22}" text-anchor="middle" font-size="11" style="fill:#fff;opacity:.9">${c.on.length} docs</text>`:'')+
      `<text x="${n.x}" y="${ly}" text-anchor="middle" font-size="${big?13:10.5}" ${big?'font-weight="600"':'class="muted"'}>${esc(title)}</text>`+
      (big&&title!==words?`<text x="${n.x}" y="${ly+15}" text-anchor="middle" font-size="11" class="muted">${esc(words)}</text>`:'')+`</g>`;
  });
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cluster graph: clusters as nodes, bridges between clusters as edges">${g}</svg>`;
  const tip=big?$('#cgTip'):$('#cvTip2');
  box.querySelectorAll('.cproj').forEach(el=>{const p=PJ.find(x=>x.pn===el.dataset.pn);if(!p)return;
    el.addEventListener('mousemove',ev=>cvTip(tip,box.parentElement,cvProjTipHtml(p),ev));el.addEventListener('mouseleave',()=>cvTip(tip,null,''));
    el.addEventListener('click',e=>{e.stopPropagation();cvTip(tip,null,'');cvSelectProject(p)})});
  box.querySelectorAll('.cnode').forEach(el=>{
    let html='';
    if(el.classList.contains('doc')){
      const u=units.find(x=>(el.dataset.u&&x.id===el.dataset.u)||(el.dataset.pn&&x.t==='research_project'&&x.pn===el.dataset.pn));if(!u)return;
      html=`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''} · ${esc(dbNames(u.db).join(', '))}${u.cs!=null?' · similarity '+(+u.cs).toFixed(2):''}${u.ca!=null?`<br>also close to C${u.ca}`:''}<br><i>click to open</i>`;
      el.addEventListener('click',e=>{e.stopPropagation();if(u.id&&typeof openDoc==='function')openDoc(u.id);else{CG.sel=u.ci;renderClusterPage()}});
    }else if(el.dataset.c){const c=cls.find(x=>x.id===+el.dataset.c);const t={};c.on.forEach(u=>t[u.t]=(t[u.t]||0)+1);
      html=`<b>C${c.id}</b> ${esc(cvName(c,info))}<br>${Object.entries(t).map(([k,v])=>`${v} ${CV_TYPE[k]||k}${v>1?'s':''}`).join(', ')}`;
      el.addEventListener('click',()=>{if(big){cgPick(c.id);return}
        cvSelect(c.id)});
    }else{const [a,b]=el.dataset.l.split('-').map(Number),l=links.find(x=>x.a===a&&x.b===b);html=`<b>C${a} ↔ C${b}</b><br>${l.n} document${l.n>1?'s':''} bridge these clusters · mean similarity ${l.s.toFixed(2)}`}
    const isC=!el.classList.contains('doc')&&el.dataset.c&&!el.dataset.l;
    el.addEventListener('mousemove',ev=>isC?showProfile(+el.dataset.c,ev):cvTip(tip,box.parentElement,html,ev));
    el.addEventListener('mouseleave',()=>{cvTip(tip,null,'');hideProfile()});
  });
  return {act,links};
}

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
function renderClusterPage(){
  if(typeof cpRenderSel==='function')cpRenderSel();
  if($('#page-graph').hidden)return;
  const units=cvUnits(),cls=cvClusters(units),info=clusterInfo();
  if(CG.sel!=null&&!cls.find(c=>c.id===CG.sel))CG.sel=null;
  const box=$('#cgGraph');
  if(units.length<2){box.innerHTML='<div class="cv-empty" style="height:360px">No cluster analysis yet.</div>';$('#cgSide').innerHTML='';$('#cgLegend').innerHTML='';$('#cgMeta').textContent='';return}
  const r=renderClusterGraph(units,cls,{big:true,box});
  if(V3.on)mountGraph3D(units,cls,box,'graphB',Math.round(Math.min(B_MAP_MAX_H,Math.max(240,box.parentElement.clientHeight||480))));   // same 2D/3D switch as on A/B
  const run=(!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.run)||'';
  $('#cgMeta').textContent=`${r.act.length} clusters · ${units.filter(u=>u.on).length} documents · ${r.links.length} bridges${SEL_DB.length?' · '+dbNames(SEL_DB).join('+'):''}${run?' · run '+run.slice(0,10):''}`;
  const dbs=DATABASES.filter(n=>units.some(u=>u.on&&(u.db||[]).includes(n)));
  $('#cgLegend').innerHTML=(CG.mode==='db'?dbs.map(n=>`<span><i style="--c:var(--db-${n})"></i>${esc(dbName(n))}</span>`).join(''):`<span><i style="--c:var(--t-paper);border-radius:2px"></i>Paper</span><span><i style="--c:var(--t-notes)"></i>Note</span><span><i style="--c:var(--t-project);transform:rotate(45deg);border-radius:1px"></i>Project</span>`+[...new Set(units.filter(u=>LEGAL_T.has(u.t)).map(u=>u.t))].map(t=>`<span><i style="--c:${TYPE_COLOR[t]};border-radius:0;clip-path:polygon(50% 0,100% 100%,0 100%)"></i>${esc(CV_TYPE[t])}</span>`).join(''))+
    (dbs.length>1?`<span class="cg-flw">${dbs.map(n=>`<i style="color:var(--db-${n})">${DB_FLOWER[n]||''}</i>${esc(dbName(n))}`).join(' ')}</span>`:'')+
    `<span>Node = cluster (size = documents) · line = documents whose second-closest cluster is the other node (number on the line) · click a cluster for details, a document to open it</span>`;
  const dbsAll=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
  let h='';
  // the cluster list always stays (the separate detail view was removed – descriptions of the selected clusters sit above the list)
  h+=`<h4>Clusters (${r.act.length})</h4><p class="srcnote" style="margin:0">Click a cluster to select it for the chats and read its description above. The database selection in the bar above applies here too.</p><div class="cglist">`+
    r.act.map(c=>`<button class="cgitem" type="button" data-c="${c.id}" aria-pressed="${cvHas(c.id)}" style="--h:${cvHue(c.id)}"><b>C${c.id}</b><span>${esc(cvName(c,info))}<br><small>${esc(c.label)}</small></span><small>${c.on.length}</small></button>`).join('')+'</div>';
  const ranked=[...r.links].sort((a,b)=>b.n-a.n).slice(0,5);
  if(ranked.length)h+=`<h4>Strongest bridges</h4><div class="cglist">${ranked.map(l=>`<div class="srcnote">C${l.a} ↔ C${l.b}: ${l.n} document${l.n>1?'s':''} · similarity ${l.s.toFixed(2)}</div>`).join('')}</div>`;
  $('#cgSide').innerHTML=h;
  try{cgRenderProj(units)}catch(e){console.error('project card',e)}
  $$('#cgSide .cgitem').forEach(b=>b.addEventListener('click',()=>cgPick(+b.dataset.c)));
  $$('#cgSide [data-cl]').forEach(b=>b.addEventListener('click',()=>{cvSelect(+b.dataset.cl,true);try{toast('C'+b.dataset.cl+' selected for both chats')}catch(e){}}));   // REQ-02: stay on the B page
  $$('#cgSide [data-ask]').forEach(b=>b.addEventListener('click',()=>{const c=cls.find(x=>x.id===+b.dataset.ask);const inp=$('#graphInput');if(inp){inp.value=`What connects the documents in cluster C${c.id} (${cvName(c,info)})?`;inp.focus();inp.scrollIntoView({block:'center',behavior:'smooth'})}}));
  $$('#cgSide details [data-open]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();openDoc(a.dataset.open)}));
}
if(window.ResizeObserver){let t2;new ResizeObserver(()=>{clearTimeout(t2);t2=setTimeout(renderClusterPage,120)}).observe($('#cgGraph'))}
if(window.ResizeObserver){let t;new ResizeObserver(()=>{clearTimeout(t);t=setTimeout(renderClusterViz,120)}).observe($('#cviz'))}
$('#rCluster').addEventListener('change',()=>{const v=$('#rCluster').value;CV.sels=v===''?new Set():new Set([+v]);try{syncParams('graph')}catch(e){}renderClusterViz()});


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


/* ---------- Database information: contents and cluster descriptions ---------- */
function dbClusterCardHtml(c,n,info,dbsAll,openLinks){   // cluster card of the database info panel (own name: cluster-profile.js has clusterCardHtml(ci))
  const has=u=>!n||(u.db||[]).includes(n),mineN=c.all.filter(has).length;
  const i=info[c.id]||{},per=dbsAll.map(x=>({x,k:c.all.filter(u=>(u.db||[]).includes(x)).length})).filter(o=>o.k),tot=per.reduce((a,o)=>a+o.k,0)||1;
  const tag=per.length>1?`<span class="tag shared">shared${n?' with '+esc(per.filter(o=>o.x!==n).map(o=>dbName(o.x)).join(', ')):' · '+esc(per.map(o=>dbName(o.x)).join(', '))}</span>`:`<span class="tag only">only ${esc(per[0]?dbName(per[0].x):'')}</span>`;
  const list=c.all.filter(has);
  return `<div class="ccard" style="--h:${cvHue(c.id)}"><h5><b>C${c.id}</b>${esc(cvName(c))}${tag}</h5>
    ${i.description?`<p>${esc(i.description)}</p>`:`<p class="srcnote">No description yet – with an API key the backend writes one when the clusters are recomputed.</p>`}
    <div class="terms">Distinctive terms: ${esc(c.label)}</div>
    <div class="share"><span class="bar">${per.map(o=>`<i style="--c:var(--db-${esc(o.x)});width:${o.k/tot*100}%" title="${esc(dbName(o.x))}: ${o.k}"></i>`).join('')}</span><span>${n?`${mineN} of ${c.all.length} from ${esc(dbName(n))}`:per.map(o=>`${esc(dbName(o.x))} ${o.k}`).join(' · ')}</span></div>
    <details ${openLinks?'open':''}><summary>${list.length} document${list.length>1?'s':''}${n?' from '+esc(dbName(n)):''}</summary><ul>${list.map(u=>`<li>${openLinks&&u.id?`<a href="#" data-open="${esc(u.id)}">${esc(u.ti||'')}</a>`:esc(u.ti||'')} <span class="srcnote">${CV_TYPE[u.t]||''}${n?'':' · '+esc(dbNames(u.db).join(', '))}</span></li>`).join('')}</ul></details>
    ${openLinks?'':`<div><button class="mini" type="button" data-cl="${c.id}">Filter Document Chat to C${c.id}</button></div>`}</div>`;
}

function clusterInfo(){
  const info={};
  if(!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.desc){Object.entries(DEMO.clusters.desc).forEach(([k,v])=>info[+k]={...v,source:DEMO.clusters.desc_source||''});return info}
  DOCS.forEach(d=>{if(d.ci==null||!(d.ct||d.cd))return;const o=info[d.ci];if(!o)info[d.ci]={title:d.ct,description:d.cd,source:d.cd?'LLM, names pseudonymized':''};else{if(!o.title&&d.ct)o.title=d.ct;if(!o.description&&d.cd){o.description=d.cd;o.source='LLM, names pseudonymized'}}});
  return info;
}
/* REQ-08: files of the database's projects that the exclusion rules skip (e.g. literature folders), with the reason */
const EXCL_REASON={'*Literatur*/*':'literature folders','**/~$*':'Office temp files','**/.DS_Store':'system files','**/Thumbs.db':'system files'};
function dbExcludedHtml(projNames){
  const ps=PROJECTS.filter(p=>projNames.includes(p.name));if(!ps.length)return '';
  if(ps.every(p=>p.exc==null))return `<dt>Excluded files</dt><dd class="srcnote">not counted yet – needs the current backend</dd>`;
  const n=ps.reduce((a,p)=>a+(p.exc||0),0),by={};ps.forEach(p=>Object.entries(p.excBy||{}).forEach(([k,v])=>{const r=EXCL_REASON[k]||k;by[r]=(by[r]||0)+v}));
  const files=ps.reduce((a,p)=>a+(p.files||0),0);
  return `<dt>Excluded files</dt><dd title="Files in the project folders that are not loaded on purpose (setting PROJECT_EXCLUDE). ${files} files loaded + ${n} excluded = ${files+n} files in the folders.">${n?`${n} – ${esc(Object.entries(by).sort((a,b)=>b[1]-a[1]).map(([r,v])=>`${r} (${v})`).join(', '))}`:'none'}<br><small class="srcnote">${files} loaded + ${n} excluded = ${files+n} files in the folders</small></dd>`;
}
function openDbInfo(n,allDbs){
  const units=cvUnits(),cls=cvClusters(units),info=clusterInfo();
  const dbsAll=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
  const has=u=>!n||(u.db||[]).includes(n);
  const mine=units.filter(has);
  let h='';
  if(n){
    const docs=DOCS.filter(d=>(d.db||[]).includes(n));const ct=t=>docs.filter(d=>d.t===t).length;
    const years=docs.map(d=>d.y).filter(Boolean),langs=[...new Set(docs.map(d=>d.lg).filter(Boolean))];
    const meth={};docs.forEach(d=>(d.me||[]).forEach(m=>meth[m]=(meth[m]||0)+1));
    const topM=Object.entries(meth).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([m,c])=>`${esc(METHOD_LABEL[m]||m)} (${c})`).join(', ');
    const projs=[...new Set(docs.map(d=>d.pn).filter(Boolean))].filter(p=>docs.some(d=>d.pn===p&&d.t==='research_project'));
    h+=`<div class="dbp-head" style="--c:var(--db-${esc(n)})"><span class="sw"></span><span class="srcnote">${SEL_DB.includes(n)?'selected for chat':'not selected'}</span></div>`;
    h+=docs.length?`<section><h4>Contents</h4><dl class="kv">
      <dt>Research papers</dt><dd>${ct('research_paper')}</dd><dt>Research notes</dt><dd>${ct('research_notes')}</dd>
      <dt>Research projects</dt><dd>${projs.length?esc(projs.join(', '))+` (${ct('research_project')} files)`:'–'}</dd>
      <dt>Years</dt><dd>${years.length?Math.min(...years)+' – '+Math.max(...years):'–'}</dd>
      <dt>Languages</dt><dd>${langs.length?esc(langs.join(', ')):'–'}</dd>
      <dt>Main methods</dt><dd>${topM||'–'}</dd>${dbExcludedHtml(projs)}</dl></section>`:`<p class="srcnote">No documents are assigned to ${esc(dbName(n))} yet.</p>`;
    h+=`<div class="dbp-actions"><button class="btn ${SEL_DB.includes(n)?'':'primary'}" type="button" data-act="chat">${SEL_DB.includes(n)?'Remove from chat selection':'Use for chat'}</button>${dbsAll.length>1&&docs.length?`<button class="btn" type="button" data-act="compare">Compare on cluster map</button>`:''}</div>`;
  }else{
    const nd=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
    h+=`<p class="srcnote">All ${cls.length} clusters of the latest run across all databases (${esc(dbNames(nd).join(', '))}), with the share of each database. Data points: ${units.length} papers, notes and projects, represented by their structured summaries (semantic embeddings).</p>`;
  }
  const rel=cls.map(c=>({c,mineN:c.all.filter(has).length})).filter(x=>x.mineN).sort((a,b)=>b.mineN-a.mineN||a.c.id-b.c.id);
  h+=`<section><h4>${n?`Clusters with ${esc(dbName(n))} documents`:'Clusters'} (${rel.length})</h4>`;
  h+=rel.length?rel.map(({c})=>dbClusterCardHtml(c,n,info,dbsAll)).join(''):`<p class="srcnote">No clustered documents${n?' in '+esc(dbName(n)):''} yet.</p>`;
  h+=`</section>`;
  const src=Object.values(info)[0];
  if(src&&src.source)h+=`<p class="srcnote">Descriptions: ${esc(src.source)}.${!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.model?' Clusters: semantic embeddings ('+esc(DEMO.clusters.model)+').':''}</p>`;
  $("#dbpTitle").textContent=n?`Database ${dbName(n)} (${n})`:'Cluster descriptions';
  $('#dbpBody').innerHTML=h;
  $$('#dbpBody [data-cl]').forEach(b=>b.addEventListener('click',()=>{showPage('chat');cvSelect(+b.dataset.cl,true);closeDbInfo()}));
  const act=a=>$(`#dbpBody [data-act="${a}"]`);
  if(act('chat'))act('chat').addEventListener('click',()=>{const ic=$(`#dbs .db[data-db="${n}"] svg`);setDbSel(SEL_DB.includes(n)?SEL_DB.filter(x=>x!==n):[...SEL_DB,n],ic&&ic.getBoundingClientRect(),ic&&getComputedStyle(ic).color);openDbInfo(n)});
  if(act('compare'))act('compare').addEventListener('click',()=>{if(!SEL_DB.includes(n)){const ic=$(`#dbs .db[data-db="${n}"] svg`);setDbSel([...SEL_DB,n],ic&&ic.getBoundingClientRect(),ic&&getComputedStyle(ic).color)}CV.mode='db';try{localStorage.setItem('cv_mode','db')}catch(e){}cvSyncMode();showPage('chat');renderClusterViz();closeDbInfo()});
  $('#dbPanel').hidden=false;$('#scrim').hidden=false;
}
function closeDbInfo(){$('#dbPanel').hidden=true;if($('#drawer').hidden&&$('#histPanel').hidden)$('#scrim').hidden=true}
$('#dbpClose').addEventListener('click',closeDbInfo);
$('#scrim').addEventListener('click',closeDbInfo);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDbInfo()});
$('#dbInfoAll').addEventListener('click',()=>openDbInfo(null));

