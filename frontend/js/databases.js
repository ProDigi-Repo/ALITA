/* ---------- Databases ---------- */
let DATABASES=['AL','CNN_DM','DL','JSW','LDK','ML','UM','EUAIA','OTH'];
/* Display names (flowers). The IDs above stay the internal keys: folders research/<ID>/, Qdrant payload, API filters, CSS colors. */
const DB_NAME={AL:'Aster',CNN_DM:'Camellia',DL:'Dahlia',JSW:'Jasmine',LDK:'Peony',ML:'Magnolia',UM:'Orchid',EUAIA:'EU AI Act',OTH:'Others'};
const dbName=n=>DB_NAME[n]||n;
const dbNames=l=>(l||[]).map(dbName);
/* Database IDs inside texts that come from the server (cluster labels "JSW · …", cluster titles and
   descriptions, profiles) -> flower names. Short IDs that are also ordinary words or abbreviations
   (AL, DL, ML, UM) are only replaced as a label prefix or after "database(s)". */
function dbRelabel(s){
  if(!s||typeof s!=='string')return s;
  const ids=Object.keys(DB_NAME).sort((a,b)=>b.length-a.length),alt=ids.join('|');
  s=s.replace(new RegExp(`^((?:${alt})(?:/(?:${alt}))*)(\\s·\\s)`),(m,p,sep)=>p.split('/').map(dbName).join('/')+sep);
  s=s.replace(new RegExp(`\\b(databases?)\\s+((?:${alt})(?:\\s*(?:,|\\+|and|und|&)\\s*(?:${alt}))*)\\b`,'gi'),(m,w,l)=>w+' '+l.replace(new RegExp(`\\b(${alt})\\b`,'g'),x=>dbName(x)));
  const safe=ids.filter(i=>i.length>2);
  if(safe.length)s=s.replace(new RegExp(`\\b(${safe.join('|')})\\b`,'g'),x=>dbName(x));
  return s;
}
let SEL_DB=[];
try{SEL_DB=JSON.parse(localStorage.getItem('sel_db')||'[]')}catch(e){}
const DB_ICON='<svg width="22" height="24" viewBox="0 0 22 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="11" cy="5" rx="8" ry="3"/><path d="M3 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M3 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>';
/* Flower icons for the databases (drawn in the database color via currentColor) */
const DB_FLOWER=(()=>{
  const ring=(n,rx,ry,cy,off=0,op=.28)=>Array.from({length:n},(_,i)=>`<ellipse cx="12" cy="${12-cy}" rx="${rx}" ry="${ry}" transform="rotate(${(off+i*360/n).toFixed(1)} 12 12)" fill="currentColor" fill-opacity="${op}"/>`).join('');
  const svg=b=>`<svg class="flw" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round" aria-hidden="true">${b}</svg>`;
  return {
    // Aster: many narrow rays around a large centre
    AL:svg(ring(16,1.1,4.2,6.6,0,.35)+'<circle cx="12" cy="12" r="3" fill="currentColor" fill-opacity=".9"/>'),
    // Camellia: round, overlapping petals in two layers
    CNN_DM:svg(ring(6,4,4.3,5.6,0,.2)+ring(5,2.6,2.8,2.6,36,.35)+'<circle cx="12" cy="12" r="1.4" fill="currentColor"/>'),
    // Dahlia: pointed petals in a strict geometric double ring
    DL:svg(ring(12,1.8,4.6,6.2,0,.22).replace(/<ellipse /g,'<ellipse ')+ring(8,1.5,3,3.2,22.5,.4)+'<circle cx="12" cy="12" r="1.5" fill="currentColor"/>'),
    // Jasmine: five slim star petals, slightly turned like a pinwheel
    JSW:svg(Array.from({length:5},(_,i)=>`<path d="M12 12C10.4 9 10.6 4.6 12.6 2.4C14 4.8 13.8 9 12 12Z" transform="rotate(${i*72} 12 12)" fill="currentColor" fill-opacity=".3"/>`).join('')+'<circle cx="12" cy="12" r="1.3" fill="currentColor"/>'),
    // Peony: full, ruffled bloom seen from the side, with leaves
    LDK:svg('<path d="M4.5 12.5C3.5 8 6.5 5.5 9 6.6C9.8 3.8 14.2 3.8 15 6.6C17.5 5.5 20.5 8 19.5 12.5C18.5 16.2 15.5 17.6 12 17.6S5.5 16.2 4.5 12.5Z" fill="currentColor" fill-opacity=".22"/><path d="M7.4 12.2C7.4 9.6 9.4 8.2 12 8.2S16.6 9.6 16.6 12.2M9.4 11.6C9.8 10.3 10.8 9.9 12 9.9S14.2 10.3 14.6 11.6M6 13.6C8.6 15.4 15.4 15.4 18 13.6" /><path d="M12 17.6V22M12 20C10.2 18.6 8 18.8 6.8 20C8.4 21.2 10.6 21.2 12 20ZM12 20C13.8 18.6 16 18.8 17.2 20C15.6 21.2 13.4 21.2 12 20Z" fill="currentColor" fill-opacity=".35"/>'),
    // Magnolia: tall goblet of three large petals on a branch
    ML:svg('<path d="M12 18C8.4 16.6 6.8 12.4 7.6 6.8C10 8 11.6 11 12 14C12.4 11 14 8 16.4 6.8C17.2 12.4 15.6 16.6 12 18Z" fill="currentColor" fill-opacity=".25"/><path d="M12 15.5C10.4 12.2 10.6 6.8 12 2.8C13.4 6.8 13.6 12.2 12 15.5Z" fill="currentColor" fill-opacity=".45"/><path d="M12 18V22M12 20.5L15.5 19.4"/>'),
    // Orchid: three sepals, two wide petals and a lip
    UM:svg('<path d="M12 11C10.8 8 11 4.6 12 2.6C13 4.6 13.2 8 12 11Z" fill="currentColor" fill-opacity=".25"/><path d="M12 12C9 13.2 5.6 16 4.6 19C7.6 18.6 10.6 15.6 12 12ZM12 12C15 13.2 18.4 16 19.4 19C16.4 18.6 13.4 15.6 12 12Z" fill="currentColor" fill-opacity=".25"/><path d="M12 11.5C9.4 7.8 5.4 7 3 8.4C3.8 11.6 8.4 13.2 12 11.5ZM12 11.5C14.6 7.8 18.6 7 21 8.4C20.2 11.6 15.6 13.2 12 11.5Z" fill="currentColor" fill-opacity=".35"/><path d="M10.2 12.6C10 15.4 10.8 17.6 12 18.4C13.2 17.6 14 15.4 13.8 12.6C12.8 13.4 11.2 13.4 10.2 12.6Z" fill="currentColor" fill-opacity=".7"/>'),
    // EU AI Act: a cornflower (Kornblume) – blue like the EU flag; a ring of fringed, funnel-shaped florets around a dark disc
    EUAIA:svg(Array.from({length:8},(_,i)=>`<path d="M12 9.6L10.6 4.2L11.3 4.9L12 3.4L12.7 4.9L13.4 4.2Z" transform="rotate(${i*45} 12 12)" fill="currentColor" fill-opacity=".35"/>`).join('')
      +Array.from({length:8},(_,i)=>`<path d="M12 10.6L11.2 7.4L12 8L12.8 7.4Z" transform="rotate(${22.5+i*45} 12 12)" fill="currentColor" fill-opacity=".55"/>`).join('')
      +'<circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r=".7" fill="#fff" fill-opacity=".8" stroke="none"/>'),
    // Others: a snapping flytrap – two toothed jaws on a curved stem, ready to catch whatever does not fit elsewhere
    OTH:svg('<path d="M12 22.4C12.6 19.6 11.4 17.2 12 14.6" fill="none"/><path d="M11.9 19.4C9.6 19.6 8 18.4 7.4 16.6C9.4 16.2 11 17.2 11.9 19.4Z" fill="currentColor" fill-opacity=".3"/>'
      +'<path d="M12 14.6C8 14.2 5 10.8 5.4 6.2C8.6 7 11.2 10.2 12 14.6Z" fill="currentColor" fill-opacity=".3"/><path d="M12 14.6C16 14.2 19 10.8 18.6 6.2C15.4 7 12.8 10.2 12 14.6Z" fill="currentColor" fill-opacity=".3"/>'
      +'<path d="M5.4 6.2L4.4 4.6M6.5 6.5L6.1 4.7M7.7 7.1L7.8 5.3M9 8L9.6 6.4M18.6 6.2L19.6 4.6M17.5 6.5L17.9 4.7M16.3 7.1L16.2 5.3M15 8L14.4 6.4" stroke-linecap="round"/>'
      +'<circle cx="9" cy="10.6" r=".7" fill="currentColor"/><circle cx="15" cy="10.6" r=".7" fill="currentColor"/>')
  };
})();
const dbIcon=n=>DB_FLOWER[n]||DB_ICON;
const dbColor=n=>`var(--db-${n},var(--muted))`;
function dbTags(list){return (list&&list.length)?`<div class="dbtags">${list.map(n=>`<span class="dbtag" style="--c:${dbColor(n)}">${esc(dbName(n))}</span>`).join('')}</div>`:'<span class="srcnote">–</span>'}
function renderDbBar(){
  const cnt=n=>DOCS.filter(d=>(d.db||[]).includes(n)).length;
  const pcnt=n=>new Set(DOCS.filter(d=>(d.db||[]).includes(n)&&d.pn).map(d=>d.pn)).size;
  $('#dbs').innerHTML=DATABASES.map(n=>{const c=cnt(n);return `<span class="dbw" style="--c:${dbColor(n)}"><button class="db ${c?'':'empty'}" type="button" data-db="${esc(n)}" aria-pressed="${SEL_DB.includes(n)}" style="--c:${dbColor(n)}" title="Show or hide database ${esc(dbName(n))}">${dbIcon(n)}<span><span class="nm">${esc(dbName(n))}</span><span class="ct">${c} docs · ${pcnt(n)} proj.</span></span></button><button class="dbi" type="button" data-info="${esc(n)}" title="Information about ${esc(dbName(n))}: contents and cluster descriptions" aria-label="Information about database ${esc(dbName(n))}">i</button></span>`}).join('');
  $$('#dbs .dbi').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();openDbInfo(b.dataset.info)}));
  $$('#dbs .db').forEach(b=>b.addEventListener('click',()=>{const n=b.dataset.db;AV.flash(getComputedStyle(b).getPropertyValue('--c').trim()||'#3df2ff');const ic=b.querySelector('svg');setDbSel(SEL_DB.includes(n)?SEL_DB.filter(x=>x!==n):[...SEL_DB,n],ic&&ic.getBoundingClientRect(),getComputedStyle(b).color)}));
  const un=DOCS.filter(d=>!(d.db||[]).length).length;
  $('#dbUnassigned').textContent=un?`${un} document${un===1?'':'s'} without a database`:'';
  $('#dbHint').textContent=(SEL_DB.length?dbNames(SEL_DB).join(' + '):'all (no selection)')+' · for A and B';
  $('#dbClear').hidden=!SEL_DB.length&&!(typeof CV!=='undefined'&&CV.sels.size);
  $('#uDbs').innerHTML=dbPickerButtons([]);wirePick('#uDbs');
  setHair();try{syncHairFlowers()}catch(e){}
  if(window.syncPuppy)syncPuppy();
  if(window.syncVoxel)syncVoxel();
}
/* Avatar hair = colors of the selected databases (none or all selected: rainbow) */
const HAIR_ALL=['#ff3b6b','#ff8a3d','#ffd84d','#52e08a','#36cfff','#6a6cff','#c25bff'];
function setHair(){
  const stops=[...document.querySelectorAll('#avHair stop')];if(!stops.length)return;
  const sel=SEL_DB.filter(n=>DATABASES.includes(n));
  const all=!sel.length||sel.length===DATABASES.length;
  const cs=getComputedStyle(document.getElementById('avatar'));
  const cols=sel.map(n=>cs.getPropertyValue('--db-'+n).trim()||'#3df2ff');
  stops.forEach((st,i)=>{
    let c;
    if(all)c=HAIR_ALL[i%HAIR_ALL.length];
    else if(cols.length===1)c=i%2?`color-mix(in oklab, ${cols[0]} 72%, #fff)`:cols[0];   // one database: its color with highlights
    else c=cols[Math.min(cols.length-1,Math.floor(i*cols.length/stops.length))];
    st.style.stopColor=c;
  });
  const av=document.getElementById('avatar');
  av.setAttribute('aria-label','ALITA avatar: cyberpunk girl with seashell earrings who follows your cursor; hair in '+(all?'all database colors':'the colors of '+dbNames(sel).join(' + ')));
}
/* Selecting a database: its flower flies down into the parameter line of each visible chat and blooms there.
   Deselecting (also "Clear selection"): the flowers in the parameter lines wilt and fly back up to their button. */
const FLY_OK=()=>!matchMedia('(prefers-reduced-motion: reduce)').matches&&!!Element.prototype.animate;
function flyPath(fly,from,to,k,back){
  const dx=to.left+to.width/2-(from.left+from.width/2),dy=to.top+to.height/2-(from.top+from.height/2),sc=to.width/from.width;
  const sway=(k%2?-1:1)*Math.min(140,Math.abs(dy)*.25+40),steps=14,frames=[];
  for(let i=0;i<=steps;i++){const p=i/steps,e=p<.5?2*p*p:1-Math.pow(-2*p+2,2)/2;
    const x=dx*e+Math.sin(p*Math.PI*2)*sway*(1-p),y=dy*e-Math.sin(p*Math.PI)*30;
    frames.push({transform:`translate(${x.toFixed(1)}px,${y.toFixed(1)}px) rotate(${(p*(back?-360:540)*(k%2?-1:1)).toFixed(0)}deg) scale(${(1+(sc-1)*p+.25*Math.sin(p*Math.PI)).toFixed(3)})`,opacity:back?(1-.6*p):(p>.96?.6:1)});}
  return fly.animate(frames,{duration:(back?850:1100)+k*150,delay:k*100,easing:'linear',fill:'forwards'});
}
function flyer(n,r,color){const fly=document.createElement('div');fly.className='flyflower';fly.innerHTML=dbIcon(n);
  fly.style.cssText=`left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;color:${color}`;document.body.appendChild(fly);return fly}
const visibleChips=n=>$$(`.psum .pdb[data-db="${n}"]`).filter(t=>t.offsetParent&&t.getBoundingClientRect().width);
function flyFlower(n,from,col){
  if(!FLY_OK())return;
  visibleChips(n).forEach((t,k)=>{
    const ti=t.querySelector('svg');if(!ti)return;
    const fly=flyer(n,from,getComputedStyle(t).color||col);ti.style.opacity='0';
    flyPath(fly,from,ti.getBoundingClientRect(),k,false).onfinish=()=>{fly.remove();ti.style.opacity='';
      ti.animate([{transform:'scale(.2) rotate(-120deg)',opacity:.4},{transform:'scale(1.55) rotate(12deg)',opacity:1,offset:.6},{transform:'scale(1) rotate(0)'}],{duration:650,easing:'cubic-bezier(.2,.9,.3,1.3)'});
      t.animate([{boxShadow:'0 0 0 0 transparent'},{boxShadow:'0 0 0 6px color-mix(in srgb,currentColor 25%,transparent),0 0 18px currentColor',offset:.4},{boxShadow:'0 0 0 0 transparent'}],{duration:900,easing:'ease-out'});
      const burst=document.createElement('span');burst.className='bloomburst';t.appendChild(burst);setTimeout(()=>burst.remove(),800);};
  });
}
/* call BEFORE the selection changes: remembers where the flowers of the removed databases sit */
function chipSpots(names){return names.flatMap(n=>visibleChips(n).map(t=>{const ti=t.querySelector('svg');return ti&&{n,r:ti.getBoundingClientRect(),c:getComputedStyle(t).color}}).filter(Boolean))}
/* call AFTER the bar was re-rendered: the flowers fly back up to their buttons */
function flyBack(spots){
  if(!FLY_OK())return;
  spots.forEach((s,k)=>{const b=$(`#dbs .db[data-db="${s.n}"] svg`);if(!b)return;const to=b.getBoundingClientRect();if(!to.width)return;
    const fly=flyer(s.n,s.r,s.c);fly.animate([{filter:'drop-shadow(0 0 6px currentColor) saturate(1)'},{filter:'drop-shadow(0 0 2px currentColor) saturate(.4)'}],{duration:900,fill:'forwards'});
    flyPath(fly,s.r,to,k,true).onfinish=()=>{fly.remove();b.animate([{transform:'scale(1.35)'},{transform:'scale(1)'}],{duration:350,easing:'ease-out'})};});
}
/* change the selection in one place: parameter lines first, so a failing view never leaves them stale */
function setDbSel(next,from,col){
  const added=next.filter(n=>!SEL_DB.includes(n)),removed=SEL_DB.filter(n=>!next.includes(n));
  const spots=chipSpots(removed);
  SEL_DB=[...next];saveDbSel();
  flyBack(spots);if(from)added.forEach(n=>flyFlower(n,from,col));
}
/* Hair jewellery: the flower of every selected database grows out of ALITA's hair (Peony as a large pink bloom
   above her right temple). Grows with a little vine and opens; wilts away again when deselected. */
/* the peony as hair jewellery: a full, layered pink bloom (drawn in its own colours, not the database colour) */
const AV_PEONY=(()=>{const ring=(n,r,rx,ry,c,o)=>Array.from({length:n},(_,i)=>`<ellipse cx="12" cy="${12-r}" rx="${rx}" ry="${ry}" fill="${c}" transform="rotate(${(o+i*360/n).toFixed(1)} 12 12)"/>`).join('');
  return ring(8,6.4,4.4,4.6,'#f9b4cf',0)+ring(7,4.4,3.6,3.8,'#f2829f',20)+ring(6,2.6,2.8,3,'#e45c86',8)+ring(5,1.2,1.8,2,'#d2457a',30)+'<circle cx="12" cy="12" r="1.3" fill="#ffd36b"/><path d="M8 7.5q4-2 8 0M7 11q5 2.2 10 0" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width=".5"/>';})();
const AV_SPOTS=[[79,23,-20],[41,26,25],[60,17,0],[87,44,-40],[33,43,40],[70,18,-10],[50,19,12]];
function syncHairFlowers(){
  const g=document.getElementById('avFlowers');if(!g)return;
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sel=SEL_DB.filter(n=>DATABASES.includes(n)&&DB_FLOWER[n]);
  const order=[...sel].sort((a,b)=>(b==='LDK')-(a==='LDK'));          // Peony takes the place of honour
  [...g.children].forEach(el=>{if(!sel.includes(el.dataset.db)&&!el.dataset.going){el.dataset.going=1;
    const fl=el.querySelector('.hf');if(reduce||!fl.animate){el.remove();return}
    fl.animate([{transform:'scale(1) rotate(0)',opacity:1},{transform:'scale(0) rotate(-90deg)',opacity:0}],{duration:450,easing:'ease-in',fill:'forwards'}).onfinish=()=>el.remove();}});
  order.forEach((n,i)=>{
    const [x,y,rot]=AV_SPOTS[i%AV_SPOTS.length],big=n==='LDK',s=(big?24:13)/24;
    let el=g.querySelector(`[data-db="${n}"]:not([data-going])`);
    const tf=`translate(${x} ${y}) rotate(${rot})`;
    if(el){el.setAttribute('transform',tf);return}
    el=document.createElementNS('http://www.w3.org/2000/svg','g');el.dataset.db=n;el.setAttribute('transform',tf);el.style.color=`var(--db-${n})`;
    const inner=big?AV_PEONY:DB_FLOWER[n].replace(/^<svg[^>]*>/,'').replace(/<\/svg>$/,'').replace(/fill-opacity="\.?\d*"/g,'fill-opacity=".88"');
    const L=big?9:6;   // vine from the hair to the flower, with two leaves
    el.innerHTML=`<path class="hv" d="M0 ${L}C${-L*.4} ${L*.55} ${L*.4} ${L*.3} 0 0" fill="none" stroke="#3fae6a" stroke-width="${big?1:.8}" stroke-linecap="round"/>`+
      `<g class="hl"><path d="M0 ${L*.6}q${-L*.55} ${-L*.15} ${-L*.75} ${-L*.6}q${L*.55} 0 ${L*.75} ${L*.6}Z" fill="#46c27a" fill-opacity=".9"/><path d="M0 ${L*.45}q${L*.55} ${-L*.1} ${L*.7} ${-L*.55}q${-L*.5} 0 ${-L*.7} ${L*.55}Z" fill="#3aa86a" fill-opacity=".9"/></g>`+
      `<g class="hf"><g transform="scale(${s}) translate(-12 -12)" stroke="rgb(255 255 255 / .55)" stroke-width="${big?.5:.7}">${inner}</g></g>`;
    g.appendChild(el);
    if(reduce||!el.animate)return;
    const v=el.querySelector('.hv'),len=L*1.4;v.style.strokeDasharray=len;
    v.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:420,easing:'ease-out',fill:'backwards'});
    el.querySelector('.hl').animate([{transform:'scale(0)',opacity:0},{transform:'scale(1)',opacity:1}],{duration:380,delay:280,easing:'ease-out',fill:'backwards'});
    el.querySelector('.hf').animate([{transform:'scale(0) rotate(-140deg)',opacity:0},{transform:'scale(1.35) rotate(10deg)',opacity:1,offset:.65},{transform:'scale(1) rotate(0)'}],{duration:800,delay:420,easing:'cubic-bezier(.2,.9,.3,1.2)',fill:'backwards'});
  });
}
function saveDbSel(){try{localStorage.setItem('sel_db',JSON.stringify(SEL_DB))}catch(e){}
  // every view on its own, so one failing view cannot stop the others (parameter lines first)
  [()=>{if(typeof cvPruneSel==='function')cvPruneSel()},()=>{syncParams('rag');syncParams('graph')},renderDbBar,()=>{D.shown=100;renderDocs()},renderClusterViz,renderClusterPage,()=>{if(typeof loadPeople==='function')loadPeople()}].forEach(fn=>{try{fn()}catch(e){console.error('database selection:',e)}});
}
$('#dbClear').addEventListener('click',()=>typeof clearAllSel==='function'?clearAllSel():setDbSel([]));
function dbPickerButtons(sel){return DATABASES.map(n=>`<button type="button" data-db="${esc(n)}" aria-pressed="${(sel||[]).includes(n)}" style="--c:${dbColor(n)}">${esc(dbName(n))}</button>`).join('')}
function wirePick(sel){$$(sel+' button[data-db]').forEach(b=>b.addEventListener('click',()=>b.setAttribute('aria-pressed',b.getAttribute('aria-pressed')!=='true')))}
function pickedDbs(sel){return $$(sel+' button[data-db][aria-pressed="true"]').map(b=>b.dataset.db)}
function dbPicker(id,sel){return `<div class="dbpick" id="${id}">${dbPickerButtons(sel)}<button type="button" class="apply" data-apply>Save assignment</button></div>`}
function wireDbPicker(id,onSave){const root=document.getElementById(id);if(!root)return;wirePick('#'+id);root.querySelector('[data-apply]').addEventListener('click',()=>onSave(pickedDbs('#'+id)))}
async function assignDbs(target,dbs){
  if(LIVE){
    const url=target.project?`api/projects/${encodeURIComponent(target.project)}/databases`:`api/documents/${encodeURIComponent(target.doc)}/databases`;
    const r=await fetch(url,{method:'PUT',headers:headers(),body:JSON.stringify({databases:dbs})});
    if(!r.ok){toast('Save failed: '+((await r.json()).detail||r.status));return}
  }
  // update locally (demo mode: this browser tab only)
  DOCS.forEach(d=>{if(target.project?d.pn===target.project:d.id===target.doc)d.db=[...dbs]});
  if(target.project){const p=PROJECTS.find(x=>x.name===target.project);if(p)p.db=[...dbs]}
  toast(`${target.project?'Project '+target.project:'Document'}: ${dbs.length?dbNames(dbs).join(', '):'no database'}${LIVE?'':' · demo, not saved'}`);
  renderDbBar();renderDocs();
}

/* ---------- Avatar: follows the pointer ---------- */
const AV=(()=>{
  const el=$('#avatar');if(!el)return{busy(){},flash(){}};
  const head=$('#avHead'),face=$('#avFace'),eyes=$('#avEyes'),hair=$('#avHairG'),halo=$('#avHaloC');
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(reduce)el.querySelectorAll('animate,animateTransform').forEach(a=>a.remove());
  let tx=0,ty=0,x=0,y=0,last=performance.now();
  function aim(px,py){
    const r=el.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height*.45;
    const dx=px-cx,dy=py-cy,dist=Math.hypot(dx,dy)||1,k=Math.min(1,dist/260);
    tx=dx/dist*k;ty=dy/dist*k;last=performance.now();
  }
  addEventListener('pointermove',e=>aim(e.clientX,e.clientY),{passive:true});
  addEventListener('pointerdown',e=>aim(e.clientX,e.clientY),{passive:true});
  addEventListener('focusin',e=>{const r=e.target.getBoundingClientRect&&e.target.getBoundingClientRect();if(r&&r.width)aim(r.left+r.width/2,r.top+r.height/2)});
  function frame(t){
    if(t-last>3500){tx=Math.sin(t/1700)*.45;ty=Math.sin(t/2300)*.18}  // look around calmly when the mouse is idle
    const f=reduce?1:.12;x+=(tx-x)*f;y+=(ty-y)*f;
    head.setAttribute('transform',`translate(${x*3} ${y*2.2}) rotate(${x*4} 60 60)`);
    hair.setAttribute('transform',`translate(${x*-1.2} ${y*-.8})`);
    face.setAttribute("transform",`translate(${x*1.8} ${y*1.5})`);
    eyes.setAttribute("transform",`translate(${x*1.7} ${y*1.1})`);
    halo.setAttribute('cx',60+x*6);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  if(!reduce)(function blink(){setTimeout(()=>{el.classList.add('blink');setTimeout(()=>{el.classList.remove('blink');blink()},180)},2600+Math.random()*3400)})();
  return{
    busy(on){el.classList.toggle('busy',!!on)},
    flash(color){const g=$('#avVisorGlow');g.setAttribute('fill',color);setTimeout(()=>g.setAttribute('fill','#3df2ff'),650)}
  };
})();
