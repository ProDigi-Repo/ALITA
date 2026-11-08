/* REQ-97: the three columns of the B page (knowledge map | projects & clusters | Graph Chat) can be made wider or
   narrower – drag a divider with the mouse or a finger, or focus it and use ← / → (Home = original widths, also a
   double-click). Widths are kept per browser. Below 1100 px the page is one column and the dividers are hidden. */
(function(){
  const g=document.querySelector('#page-graph .bgrid');if(!g)return;
  const DEF=[1.3,1,1],MIN=[240,220,260],KEY='alita-bcols';
  let fr=DEF.slice();
  try{const v=JSON.parse(localStorage.getItem(KEY)||'null');if(Array.isArray(v)&&v.length===3&&v.every(x=>x>0.15&&x<6))fr=v}catch(e){}
  const NAMES=['knowledge map','projects & clusters','Graph Chat'];
  const splits=[1,2].map(i=>{
    const d=document.createElement('div');d.className='bsplit';d.dataset.i=i;d.tabIndex=0;
    d.setAttribute('role','separator');d.setAttribute('aria-orientation','vertical');
    d.setAttribute('aria-label',`Resize: ${NAMES[i-1]} | ${NAMES[i]} (← → to change, Home to reset)`);
    d.setAttribute('aria-valuemin','10');d.setAttribute('aria-valuemax','90');
    d.title='Drag to make the columns wider or narrower · double-click: original widths';
    return d;
  });
  g.insertBefore(splits[0],g.querySelector('.bq-cluster'));
  g.insertBefore(splits[1],g.querySelector('.bq-chat'));
  g.classList.add('resizable');
  function apply(save){
    fr.forEach((f,i)=>g.style.setProperty('--bw'+(i+1),f.toFixed(3)+'fr'));
    splits.forEach((d,k)=>d.setAttribute('aria-valuenow',String(Math.round(100*fr[k]/(fr[k]+fr[k+1])))));
    if(save)try{localStorage.setItem(KEY,JSON.stringify(fr))}catch(e){}
    if(typeof onBResize==='function'){clearTimeout(apply.t);apply.t=setTimeout(onBResize,60)}
  }
  function widths(){return ['.bq-map','.bq-cluster','.bq-chat'].map(s=>g.querySelector(s).getBoundingClientRect().width)}
  /* move the divider k (0 or 1) by dx pixels: the two neighbouring columns trade width, both keep their minimum */
  function move(k,dx,base){
    const w=(base||widths()).slice(),sum=w[k]+w[k+1];
    let a=Math.min(Math.max(w[k]+dx,MIN[k]),sum-MIN[k+1]);
    w[k]=a;w[k+1]=sum-a;
    const tot=fr.reduce((s,x)=>s+x,0),px=w.reduce((s,x)=>s+x,0);
    fr=w.map(x=>x/px*tot);apply(false);
  }
  splits.forEach((d,k)=>{
    d.addEventListener('pointerdown',e=>{
      if(e.button>0)return;e.preventDefault();d.setPointerCapture(e.pointerId);
      const x0=e.clientX,base=widths();d.classList.add('drag');document.body.classList.add('bsplitting');
      const mv=ev=>move(k,ev.clientX-x0,base);
      const up=()=>{d.releasePointerCapture(e.pointerId);d.removeEventListener('pointermove',mv);d.removeEventListener('pointerup',up);
        d.removeEventListener('pointercancel',up);d.classList.remove('drag');document.body.classList.remove('bsplitting');apply(true)};
      d.addEventListener('pointermove',mv);d.addEventListener('pointerup',up);d.addEventListener('pointercancel',up);
    });
    d.addEventListener('keydown',e=>{
      const step=e.shiftKey?120:40;
      if(e.key==='ArrowLeft'){move(k,-step);apply(true);e.preventDefault()}
      else if(e.key==='ArrowRight'){move(k,step);apply(true);e.preventDefault()}
      else if(e.key==='Home'){fr=DEF.slice();apply(true);e.preventDefault()}
    });
    d.addEventListener('dblclick',()=>{fr=DEF.slice();apply(true)});
  });
  apply(false);
})();
/* REQ-98: text size per tile – "A−" / "A+" in the header of each tile scale every font of that tile (all sizes are
   calc(… * var(--fs-scale))), kept per browser. Browser zoom still scales the whole page. */
(function(){
  const STEPS=[0.85,1,1.15,1.3,1.5,1.75],KEY='alita-fs';
  const TILES=[['#page-graph .bq-map','.cv-head','map-b','knowledge map'],['#page-graph .bq-cluster','.bq-head','clusters','projects & clusters'],
    ['.tile.t-graph','.tile-head','chat-b','Graph Chat'],['.tile.t-rag','.tile-head','chat-a','Document Chat'],
    ['#cviz .cv.t-rag','.cv-head','map-a','knowledge map A'],['#cviz .cv.t-graph','.cv-head','map-a2','knowledge map B'],['#page-docs','.dtabs','docs','documents']];
  let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')||{}}catch(e){}
  const base=()=>parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--fs-scale'))||1;
  TILES.forEach(([sel,head,key,name])=>{
    const t=document.querySelector(sel),h=t&&t.querySelector(head);if(!t||!h)return;
    let i=Math.max(0,STEPS.indexOf(saved[key]??1));if(i<0)i=1;
    const box=document.createElement('span');box.className='fs-ctl';box.setAttribute('role','group');box.setAttribute('aria-label',`Text size of the ${name}`);
    box.innerHTML='<button type="button" class="fs-dn" aria-label="Smaller text" title="Smaller text in this tile">A−</button><button type="button" class="fs-up" aria-label="Larger text" title="Larger text in this tile">A+</button>';
    h.appendChild(box);
    const set=save=>{
      if(STEPS[i]===1)t.style.removeProperty('--fs-scale');else t.style.setProperty('--fs-scale',(base()*STEPS[i]).toFixed(3));
      box.querySelector('.fs-dn').disabled=i===0;box.querySelector('.fs-up').disabled=i===STEPS.length-1;
      box.title=`Text size ${Math.round(STEPS[i]*100)} %`;
      if(save){saved[key]=STEPS[i];try{localStorage.setItem(KEY,JSON.stringify(saved))}catch(e){}}
    };
    box.querySelector('.fs-dn').addEventListener('click',e=>{e.stopPropagation();if(i>0){i--;set(true)}});
    box.querySelector('.fs-up').addEventListener('click',e=>{e.stopPropagation();if(i<STEPS.length-1){i++;set(true)}});
    set(false);
  });
})();
