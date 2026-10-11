/* ---------- Cluster space 3D: walk through the cluster map, time axis = years (v1.3.0) ----------
   x/y = 2D cluster map (PCA of the summary embeddings), depth = publication year.
   No library: a small perspective renderer on <canvas>. */
const S3={open:false,cam:{x:0,y:8,z:-40,yaw:0,pitch:-0.12},keys:new Set(),until:null,from:null,mode:'cluster',hidden:new Set(),pts:[],raf:0,play:0,hover:null,dirty:true};
const S3_XY=55, S3_YEAR=22;
/* Database flower drawn inside each mark: shape = type (square paper, circle note, diamond project), flower = database */
const S3_FLW={};
function s3Flower(n){
  if(!n||typeof DB_FLOWER==='undefined'||!DB_FLOWER[n])return null;
  if(!S3_FLW[n]){const img=new Image();
    const svg=DB_FLOWER[n].replace(/^<svg /,'<svg xmlns="http://www.w3.org/2000/svg" ').replace(/currentColor/g,'#fff').replace(/fill-opacity="\.?\d*"/g,'fill-opacity=".9"');
    img.onload=()=>{S3.dirty=true};img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);S3_FLW[n]=img}
  const img=S3_FLW[n];return img.complete&&img.naturalWidth?img:null;
}
/* preload so the flowers are ready when the cluster views first draw */
setTimeout(()=>{try{(typeof DATABASES!=='undefined'?DATABASES:[]).forEach(s3Flower)}catch(e){}},0);
function s3DrawFlower(g,i,x,y,r){if(r<5)return;const img=s3Flower((i.db||[])[0]);if(img){const f=r*(i.t==='research_paper'?1.55:1.4);g.drawImage(img,x-f/2,y-f/2,f,f)}}
function s3Data(){
  const all=cvUnits(),units=SEL_DB.length?all.filter(u=>u.on):all;   // a database selection shows only its own data
  const pyears=p=>{const a=+String(p.from_||'').slice(0,4),b=+String(p.to||'').slice(0,4);
    const ys=DOCS.filter(d=>d.pn===p.pn&&d.y).map(d=>d.y);return [a||(ys.length?Math.min(...ys):null),b||(ys.length?Math.max(...ys):null)]};
  const items=[];
  units.forEach(u=>{
    if(u.t==='research_project'){const p=PROJECTS.find(x=>x.name===u.pn)||{};const [a,b]=pyears({...p,pn:u.pn});if(a&&b)items.push({...u,y0:a,y1:b,proj:true});return}
    if(u.y)items.push({...u,y0:u.y,y1:u.y});
  });
  const years=items.flatMap(i=>[i.y0,i.y1]);
  const ymin=years.length?Math.min(...years):2020,ymax=years.length?Math.max(...years):2026;
  return {items,ymin,ymax,undated:units.filter(u=>u.t!=='research_project'&&!u.y).length};
}
function s3World(i,year){return {x:i.cx*S3_XY,y:i.cy*S3_XY,z:(year-S3.D.ymin)*S3_YEAR}}
function s3Proj(p,W,H){
  const c=S3.cam,dx=p.x-c.x,dy=p.y-c.y,dz=p.z-c.z,cy=Math.cos(c.yaw),sy=Math.sin(c.yaw),cp=Math.cos(c.pitch),sp=Math.sin(c.pitch);
  const x1=dx*cy-dz*sy,z1=dx*sy+dz*cy,y2=dy*cp-z1*sp,z2=dy*sp+z1*cp;
  if(z2<0.6)return null;const f=H*0.95;return {x:W/2+x1*f/z2,y:H/2-y2*f/z2,z:z2,s:f/z2};
}
function s3Color(i,l){
  if(S3.mode==='db'){const n=(i.db||[])[0];return (n&&S3.dbc[n])||'#8d97b3'}
  return `hsl(${cvHue(i.ci)} 70% ${l||60}%)`;
}
function s3Render(){
  const cv=$('#s3Canvas'),dpr=window.devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;
  if(cv.width!==W*dpr||cv.height!==H*dpr){cv.width=W*dpr;cv.height=H*dpr}
  const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
  const D=S3.D,until=S3.until??D.ymax,from=Math.min(S3.from??D.ymin,until),fade=z=>Math.max(0.12,Math.min(1,1.25-z/520));
  const line=(a,b,col,w)=>{const p=s3Proj(a,W,H),q=s3Proj(b,W,H);if(!p||!q)return;g.strokeStyle=col;g.lineWidth=w;g.beginPath();g.moveTo(p.x,p.y);g.lineTo(q.x,q.y);g.stroke()};
  // year planes
  const B=S3_XY*1.15;
  for(let y=D.ymin;y<=D.ymax;y++){
    const z=(y-D.ymin)*S3_YEAR,cur=y===until||y===from,past=y<=until&&y>=from;
    const col=cur?'rgba(61,242,255,.55)':past?'rgba(141,151,179,.22)':'rgba(141,151,179,.08)';
    const c=[[-B,-B],[B,-B],[B,B],[-B,B]].map(([x,yy])=>({x,y:yy,z}));
    for(let k=0;k<4;k++)line(c[k],c[(k+1)%4],col,cur?1.6:1);
    const lp=s3Proj({x:-B,y:B,z},W,H);
    if(lp){g.fillStyle=cur?'#3df2ff':past?'rgba(232,236,246,.75)':'rgba(232,236,246,.3)';g.font=`${Math.max(10,Math.min(22,lp.s*2.4))}px "IBM Plex Mono",monospace`;g.fillText(String(y),lp.x+4,lp.y-4)}
  }
  // time axis
  line({x:-B,y:-B,z:-S3_YEAR*0.5},{x:-B,y:-B,z:(D.ymax-D.ymin+0.5)*S3_YEAR},'rgba(61,242,255,.35)',1.2);
  // cluster trails: centroid per year, connected through time
  const byC=new Map();S3.cpts=[];S3.labs=[];
  D.items.filter(i=>!i.proj&&i.on&&!S3.hidden.has(i.ci)&&i.y0<=until&&i.y0>=from).forEach(i=>{if(!byC.has(i.ci))byC.set(i.ci,new Map());const m=byC.get(i.ci);const a=m.get(i.y0)||{x:0,y:0,n:0};a.x+=i.cx;a.y+=i.cy;a.n++;m.set(i.y0,a)});
  byC.forEach((m,ci)=>{
    const ys=[...m.keys()].sort((a,b)=>a-b);let prev=null;
    ys.forEach(y=>{const a=m.get(y),p={x:a.x/a.n*S3_XY,y:a.y/a.n*S3_XY,z:(y-D.ymin)*S3_YEAR};
      if(prev)line(prev,p,`hsl(${cvHue(ci)} 70% 60% / .55)`,2.2);
      const q=s3Proj(p,W,H);if(q){g.strokeStyle=`hsl(${cvHue(ci)} 70% 60% / .7)`;g.lineWidth=1.2;g.beginPath();g.arc(q.x,q.y,Math.max(3,Math.min(40,q.s*(1.2+a.n*0.5))),0,Math.PI*2);g.stroke()}
      prev=p});
    if(prev){const q0=s3Proj(prev,W,H);if(q0)S3.cpts.push({ci,x:q0.x,y:q0.y,r:Math.max(10,Math.min(40,q0.s*2))})}
    if(prev){const q=s3Proj(prev,W,H),info=S3.info[ci];if(q&&q.z<420){g.fillStyle=`hsl(${cvHue(ci)} 80% 72%)`;g.font=`600 ${Math.max(11,Math.min(18,q.s*1.8))}px "IBM Plex Sans",sans-serif`;const lab=`C${ci} ${(info&&info.title)||''}`.trim(),fs=Math.max(11,Math.min(18,q.s*1.8));g.fillText(lab,q.x+8,q.y-10);S3.labs.push({ci,x:q.x+6,y:q.y-10-fs,w:g.measureText(lab).width+4,h:fs+6})}}
  });
  // projects: a bar through the years they ran
  S3.ppts=[];
  D.items.filter(i=>i.proj&&!S3.hidden.has(i.ci)).forEach(i=>{
    if(i.y0>until||i.y1<from)return;const a=s3World(i,Math.max(i.y0,from)),b=s3World(i,Math.min(i.y1,until));
    g.globalAlpha=i.on?1:.5;line(a,b,s3Color(i,62),4);g.globalAlpha=1;
    const q=s3Proj(a,W,H);if(q){const r=Math.max(4,Math.min(30,q.s*2.2));g.globalAlpha=i.on?1:.5;g.fillStyle=s3Color(i);g.beginPath();g.moveTo(q.x,q.y-r);g.lineTo(q.x+r,q.y);g.lineTo(q.x,q.y+r);g.lineTo(q.x-r,q.y);g.closePath();g.fill();s3DrawFlower(g,i,q.x,q.y,r*.75);g.globalAlpha=1;S3.ppts.push({i,x:q.x,y:q.y,r,z:q.z,off:!i.on})}
  });
  // documents: sorted far to near
  S3.pts=[];
  const vis=D.items.filter(i=>!i.proj&&!S3.hidden.has(i.ci)).map(i=>{const p=s3Proj(s3World(i,i.y0),W,H);return p&&{i,p}}).filter(Boolean).sort((a,b)=>b.p.z-a.p.z);
  vis.forEach(({i,p})=>{
    const future=i.y0>until||i.y0<from,r=Math.max(3,Math.min(30,p.s*(i.t==='research_paper'?2.1:1.8)));
    g.globalAlpha=(future?0.1:i.on?1:0.5)*fade(p.z);g.fillStyle=s3Color(i);
    g.beginPath();if(i.t==='research_paper')g.rect(p.x-r,p.y-r,2*r,2*r);else g.arc(p.x,p.y,r,0,Math.PI*2);g.fill();s3DrawFlower(g,i,p.x,p.y,r);
    g.beginPath();if(i.t==='research_paper')g.rect(p.x-r,p.y-r,2*r,2*r);else g.arc(p.x,p.y,r,0,Math.PI*2);
    if(S3.hover===i){g.globalAlpha=1;g.strokeStyle='#fff';g.lineWidth=2;g.stroke()}
    g.globalAlpha=1;S3.pts.push({i,x:p.x,y:p.y,r,z:p.z,future,off:!i.on});
  });
  S3.dirty=false;
}
function s3Loop(){
  if(!S3.open)return;const c=S3.cam,k=S3.keys,sp=(k.has('shift')?2.6:1)*1.1;
  const fx=Math.sin(c.yaw),fz=Math.cos(c.yaw);let moved=false;
  const mv=(dx,dy,dz)=>{c.x+=dx;c.y+=dy;c.z+=dz;moved=true};
  if(k.has('w')||k.has('arrowup'))mv(fx*sp,0,fz*sp);
  if(k.has('s')||k.has('arrowdown'))mv(-fx*sp,0,-fz*sp);
  if(k.has('a')||k.has('arrowleft'))mv(-fz*sp,0,fx*sp);
  if(k.has('d')||k.has('arrowright'))mv(fz*sp,0,-fx*sp);
  if(k.has('e'))mv(0,sp,0);if(k.has('q'))mv(0,-sp,0);
  if(S3.play){const D=S3.D,f0=S3.from??D.ymin,t=(performance.now()-S3.play)/1600,y=Math.min(D.ymax,f0+Math.floor(t));
    if(y!==S3.until){S3.until=y;$('#s3Year').value=y;s3YearLabel()}
    const zt=(f0+t-D.ymin)*S3_YEAR-34;c.z+=(zt-c.z)*0.06;moved=true;if(t>D.ymax-f0+1.2)s3Stop()}
  if(moved||S3.dirty)s3Render();
  S3.raf=requestAnimationFrame(s3Loop);
}
function s3YearLabel(){const D=S3.D,f=S3.from??D.ymin,u=S3.until??D.ymax;$('#s3YearOut').textContent=(f<=D.ymin&&u>=D.ymax)?`${D.ymin}–${D.ymax} (all)`:f===u?`${f}`:`${f}–${u}`;
  const fl=$('#s3From'),tr=$('#s3Fill');if(tr&&D.ymax>D.ymin){tr.style.left=((f-D.ymin)/(D.ymax-D.ymin)*100)+'%';tr.style.right=((D.ymax-u)/(D.ymax-D.ymin)*100)+'%'}}
function s3Stop(){S3.play=0;$('#s3Play').textContent='▶ Fly through time';$('#s3Play').setAttribute('aria-pressed','false')}
function s3Reset(){const D=S3.D;Object.assign(S3.cam,{x:0,y:10,z:-48,yaw:0,pitch:-0.14});S3.until=D.ymax;S3.from=D.ymin;$('#s3Year').value=D.ymax;$('#s3From').value=D.ymin;s3YearLabel();S3.dirty=true}
function s3Legend(){
  const ids=new Set(S3.D.items.map(i=>i.ci)),cls=cvClusters(cvUnits()).filter(c=>!SEL_DB.length||ids.has(c.id));
  $('#s3Legend').innerHTML=cls.map(c=>`<button type="button" data-c="${c.id}" aria-pressed="${!S3.hidden.has(c.id)}" style="--h:${cvHue(c.id)}"><b>C${c.id}</b><span>${esc(cvName(c,S3.info))}</span><i>${c.on.length}</i></button>`).join('');
  wireProfileHover('#s3Legend button');
  $$('#s3Legend button').forEach(b=>b.addEventListener('click',()=>{const c=+b.dataset.c;S3.hidden.has(c)?S3.hidden.delete(c):S3.hidden.add(c);b.setAttribute('aria-pressed',!S3.hidden.has(c));S3.dirty=true}));
}
function open3D(){
  S3.D=s3Data();S3.info=clusterInfo();const D=S3.D;
  $('#s3').hidden=false;const cs=getComputedStyle($('#s3'));S3.dbc={};DATABASES.forEach(n=>S3.dbc[n]=cs.getPropertyValue('--db-'+n).trim());S3.open=true;document.body.style.overflow='hidden';
  const yr=$('#s3Year'),fr=$('#s3From');yr.min=fr.min=D.ymin;yr.max=fr.max=D.ymax;
  s3Legend();s3Reset();
  const hp=$('#s3Help');if(hp&&hp.offsetParent)$('#s3Legend').style.top=(hp.offsetTop+hp.offsetHeight+8)+'px';
  $('#s3Meta').textContent=`${D.items.filter(i=>!i.proj).length} documents · ${D.items.filter(i=>i.proj).length} projects · ${D.ymin}–${D.ymax}${SEL_DB.length?' · '+dbNames(SEL_DB).join(' + '):''}${D.undated?` · ${D.undated} without year not shown`:''}`;
  cancelAnimationFrame(S3.raf);S3.raf=requestAnimationFrame(s3Loop);$('#s3Canvas').focus();
}
function close3D(){S3.open=false;s3Stop();cancelAnimationFrame(S3.raf);S3.keys.clear();$('#s3').hidden=true;document.body.style.overflow='';$('#s3Tip').hidden=true}
(function(){
  const cv=$('#s3Canvas');if(!cv)return;let drag=null;
  cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,moved:0};cv.setPointerCapture(e.pointerId)});
  cv.addEventListener('pointermove',e=>{
    if(drag){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.moved+=Math.abs(dx)+Math.abs(dy);drag.x=e.clientX;drag.y=e.clientY;
      S3.cam.yaw+=dx*0.004;S3.cam.pitch=Math.max(-1.3,Math.min(1.3,S3.cam.pitch-dy*0.004));S3.dirty=true;return}
    const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
    const lab=(S3.labs||[]).find(l=>mx>=l.x&&mx<=l.x+l.w&&my>=l.y&&my<=l.y+l.h);
    if(lab){if(S3.hover){S3.hover=null;S3.dirty=true}$('#s3Tip').hidden=true;cv.style.cursor='help';showProfile(lab.ci,e);return}
    let best=null,bd=1e9;[...S3.pts,...(S3.ppts||[])].forEach(p=>{const d=Math.hypot(p.x-mx,p.y-my)+((p.future||p.off)?6:0);if(d<Math.max(p.r,4)+6+((p.future||p.off)?6:0)&&d<bd){bd=d;best=p}});
    const h=best&&best.i;S3.hoverWhy=best?(best.future?'outside the selected time range':best.off?'outside the selected databases':''):'';if(h!==S3.hover){S3.hover=h;S3.dirty=true}
    const tip=$('#s3Tip');if(!h){tip.hidden=true;const c=(S3.cpts||[]).find(p=>Math.hypot(p.x-mx,p.y-my)<p.r);if(c){showProfile(c.ci,e);cv.style.cursor='help'}else{hideProfile();cv.style.cursor='grab'}return}
    hideProfile();
    cv.style.cursor='pointer';const yrs=h.proj?(h.y0===h.y1?h.y0:h.y0+'–'+h.y1):h.y0,flw=(h.db||[]).map(n=>`<span class="s3-db" style="color:${S3.dbc[n]||'#555'}">${typeof dbIcon==='function'?dbIcon(n):''}${esc(dbName(n))}</span>`).join(' ');
    tip.innerHTML=`<b>${esc(h.ti||h.pn||'')}</b><br>${CV_TYPE[h.t]||''} · ${yrs} · C${h.ci} ${esc((S3.info[h.ci]&&S3.info[h.ci].title)||h.cl||'')}<br>${flw}${S3.hoverWhy?`<br><i>faded: ${S3.hoverWhy}</i>`:''}${h.id&&!h.proj?'<br><small>click to open</small>':''}`;
    tip.hidden=false;tip.style.left=Math.min(mx+14,r.width-300)+'px';tip.style.top=(my+14)+'px';
  });
  cv.addEventListener('pointerup',e=>{const was=drag;drag=null;if(was&&was.moved<5&&S3.hover&&S3.hover.id&&!S3.hover.proj){const id=S3.hover.id;close3D();openDoc(id)}});
  cv.addEventListener('wheel',e=>{e.preventDefault();const c=S3.cam,s=-e.deltaY*0.06;c.x+=Math.sin(c.yaw)*Math.cos(c.pitch)*s;c.y+=Math.sin(c.pitch)*s;c.z+=Math.cos(c.yaw)*Math.cos(c.pitch)*s;S3.dirty=true},{passive:false});
  window.addEventListener('keydown',e=>{if(!S3.open)return;const k=e.key.toLowerCase();
    if(k==='escape'){close3D();return}
    if(['w','a','s','d','q','e','shift','arrowup','arrowdown','arrowleft','arrowright'].includes(k)){S3.keys.add(k);e.preventDefault()}});
  window.addEventListener('keyup',e=>{S3.keys.delete(e.key.toLowerCase());if(e.key==='Shift')S3.keys.delete('shift')});
  window.addEventListener('blur',()=>S3.keys.clear());
  window.addEventListener('resize',()=>{S3.dirty=true});
  $('#s3Year').addEventListener('input',e=>{s3Stop();let v=+e.target.value;if(v<S3.from){v=S3.from;e.target.value=v}S3.until=v;s3YearLabel();S3.dirty=true});
  $('#s3From').addEventListener('input',e=>{s3Stop();let v=+e.target.value;if(v>S3.until){v=S3.until;e.target.value=v}S3.from=v;s3YearLabel();
    const z=(v-S3.D.ymin)*S3_YEAR-48;if(S3.cam.z<z-60||S3.cam.z>z+40)S3.cam.z=z;S3.dirty=true});   // walk to the start of the window
  $('#s3Play').addEventListener('click',()=>{if(S3.play){s3Stop();return}S3.until=S3.from??S3.D.ymin;S3.cam.z=((S3.from??S3.D.ymin)-S3.D.ymin)*S3_YEAR-40;S3.cam.yaw=0;S3.cam.pitch=-0.12;S3.cam.x=0;S3.play=performance.now();$('#s3Play').textContent='■ Stop';$('#s3Play').setAttribute('aria-pressed','true')});
  $('#s3Reset').addEventListener('click',()=>{s3Stop();s3Reset()});
  $('#s3Close').addEventListener('click',close3D);
  $$('#s3Mode button').forEach(b=>b.addEventListener('click',()=>{S3.mode=b.dataset.m;$$('#s3Mode button').forEach(x=>x.setAttribute('aria-pressed',x===b));S3.dirty=true}));
  // touch / mouse walk pad
  $$('#s3Pad button').forEach(b=>{const k=b.dataset.k;const on=e=>{e.preventDefault();S3.keys.add(k)},off=()=>S3.keys.delete(k);
    b.addEventListener('pointerdown',on);b.addEventListener('pointerup',off);b.addEventListener('pointerleave',off);b.addEventListener('pointercancel',off)});
  $$('[data-open3d]').forEach(b=>b.addEventListener('click',open3D));
})();
