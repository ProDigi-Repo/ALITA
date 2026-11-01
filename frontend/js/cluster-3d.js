/* Clusters – 3D views: knowledge map (A) and cluster graph (B) per period, B-page layout and camera, 2D/3D toggle. */
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
  // REQ-59: relations to the clusters of a compared database – one line per relation, between the two cluster nodes
  // that are closest in time (same period if possible)
  const XL=(typeof xcLinks==='function'?xcLinks([...new Set(nodes.map(d=>d.c.id))]):[]).map(l=>{let best=null;
    nodes.filter(d=>d.c.id===l.a).forEach(p=>nodes.filter(d=>d.c.id===l.b).forEach(q=>{const k=Math.abs(p.i-q.i);if(!best||k<best.k)best={k,p,q}}));
    return best?{...l,pa:best.p,pb:best.q}:null}).filter(Boolean);
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
    XL.forEach(l=>{if(l.pa.i!==l.pb.i)return;const p=l.pa,q=l.pb,dx=q.x-p.x,dy=q.y-p.y,dz=q.z-p.z,d=Math.sqrt(dx*dx+dy*dy+dz*dz)+0.01,k=0.008*Math.max(.2,l.s)*(d-44)/d;
      if(!p.pin){p.vx+=dx*k;p.vy+=dy*k;p.vz+=dz*k}if(!q.pin){q.vx-=dx*k;q.vy-=dy*k;q.vz-=dz*k}});
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
    if(XL.length){const anyX=CV.sels.size>0;XL.forEach(l=>{const p=P(l.pa),q=P(l.pb);if(!p||!q)return;const hi=anyX&&cvHas(l.a)&&cvHas(l.b);
      g.globalAlpha=anyX&&!hi&&(cvOff(l.a)||cvOff(l.b))?.25:.9;g.strokeStyle=XC_COL;g.lineWidth=(hi?2:1.2)+l.s*3;g.setLineDash([8,6]);g.beginPath();g.moveTo(p.x,p.y);g.lineTo(q.x,q.y);g.stroke();g.setLineDash([]);
      const mx=(p.x+q.x)/2,my=(p.y+q.y)/2,lab=l.s.toFixed(2);g.font='600 10.5px "IBM Plex Mono",monospace';const w=g.measureText(lab).width+10;
      g.fillStyle=css.getPropertyValue('--panel').trim()||'#fff';g.strokeStyle=XC_COL;g.lineWidth=1;g.beginPath();g.roundRect?g.roundRect(mx-w/2,my-8,w,16,8):g.rect(mx-w/2,my-8,w,16);g.fill();g.stroke();
      g.fillStyle=XC_COL;g.textAlign='center';g.fillText(lab,mx,my+3.5);g.textAlign='left';g.globalAlpha=1;st.hits.push({kind:'xlink',l,x:mx,y:my,r:12})})}
    if(LAY){   // document layer: the cluster's documents below it, joined by a thin stem
      const tc={research_paper:css.getPropertyValue('--t-paper').trim()||'#6b4fa3',research_notes:css.getPropertyValue('--t-notes').trim()||'#2e7d4f',research_project:css.getPropertyValue('--t-project').trim()||'#1f5f8b',
        legal_project:css.getPropertyValue('--t-legal').trim()||'#a23b2a',legal_guideline:css.getPropertyValue('--t-guideline').trim()||'#9a6a00',standard:css.getPropertyValue('--t-standard').trim()||'#3f6f7a',guidance:css.getPropertyValue('--t-guidance').trim()||'#5b6b1f'};
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
      if(h.kind==='xlink'){if(cv)cv.style.cursor='pointer';if(tip)cvTip(tip,box.parentElement,xcTipHtml(h.l,clusterInfo()),e);return}
      if(h.kind==='doc'){const u=h.u;if(cv)cv.style.cursor='pointer';if(tip)cvTip(tip,box.parentElement,`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''}${u.y?' · '+u.y:''} · C${u.ci}${u.pn?' · '+esc(u.pn):''}<br><i>click to open</i>`,e);return}cv.style.cursor='move';showProfile(h.c.id,e)},
    grab:h=>{if(!h.node)return;st.dragging=true;h.node.pin=true;run()},
    pull:(h,dx,dy)=>{const W=box.clientWidth,H=GH,cam=st.cam,f=Math.min(W,H)*1.35,k=cam.dist/f,cy=Math.cos(cam.yaw),sy=Math.sin(cam.yaw),cp=Math.cos(cam.pitch),sp=Math.sin(cam.pitch);
      const rx=dx*k,uy=-dy*k,d=h.node;d.x+=rx*cy-uy*sp*sy;d.y+=uy*cp;d.z+=-rx*sy-uy*sp*cy;keep(d)},
    release:(h,moved)=>{st.dragging=false;if(!moved)h.node.pin=false;run()},
    click:h=>{if(h.kind==='xlink'){xcSelect(h.l);return}if(h.kind==='project'){cvSelectProject(h.p);return}if(h.kind==='doc'){if(h.u.id&&typeof openDoc==='function')openDoc(h.u.id);return}if(key==='graphB'){cgPick(h.c.id);return}cvSelect(h.c.id)},
    reset:()=>{st.cam={...v3Cam(),yaw:0,pitch:LAY?0.12:0.18,dist:DIST,oy:LAY?10:40};st.nodes={};st.fit=null;mountGraph3D(cvUnits(),cvClusters(cvUnits()),box,key,GH)}};
  if(LAY){const fk=BW+'x'+GH+'|'+n+'|'+NT;   // fit once per tile size / data shape – the user's own zoom survives redraws
    if(st.fit!==fk){st.fit=fk;const x0=-spanX/2-R*0.5,x1=spanX/2+R*0.5;
      v3FitCam(st.cam,[[x0,Y_TOP[1]],[x1,Y_TOP[1]],[x0,Y_DOC[0]],[x1,Y_DOC[0]],[x0,Y_SEM[0]],[x1,Y_SEM[1]]],BW,GH)}}
  draw();v3Wire(st,box.querySelector('canvas'),api);box.querySelector('canvas')._api=api;run();
  $('#cvGraphHint').textContent=`Per period: node size = documents in that period · orange = bridges within the period · dotted = the same cluster from period to period${XL.length?' · violet dashed = relation to a cluster of the compared database':''}`;
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
