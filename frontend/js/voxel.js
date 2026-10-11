/* Magnolia's block look: when the database Magnolia (ML) is selected, ALITA turns into a blocky pixel/voxel
   version of herself (square head, pixel face, her visor, seashell earrings and hair in the database colours).
   The pixels assemble row by row while the normal drawing fades out, and scatter again on deselect. */
(function(){
  const av=document.getElementById('avatar');if(!av)return;
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const G=[
'........................',
'........................',
'........HHHHHHHH........',
'......HHHHHHHHHHHH......',
'.....HHHHHHHHHHHHHH.....',
'.....HHHHHHHHHHHHHH.....',
'....HHHHHHHHHHHHHHHH....',
'....HHSSSSSSSSSSSSHH....',
'....HHVVVVVVVVVVVVHH.D..',
'....HHSSSSSSSSSSSSHH.L..',
'....HHSRRSSSSSSRRSHH.L..',
'....HHSWBPSSSSWBPSHH.L..',
'....HHSWBBSSSSWBBSHH....',
'....HHSKSSSSSSSSKSHH....',
'....HHSSSSSMMSSSSSHH....',
'...EHHsSSSSSSSSSSsHHE...',
'....HHssSSSSSSSSssHH....',
'....HHHHHHNNNNHHHHHH....',
'....HHHHHHNNNNHHHHHH....',
'...HHHTTTCCCCCCTTTHHH...',
'...HHTTTTTCCCCTTTTTHH...',
'..LHTTTTTTTLLTTTTTTTHL..',
'..LTTTTTTTTLLTTTTTTTTL..',
'..LTTTTTTTTLLTTTTTTTTL..'];
  const COL={S:'#f6cfb4',s:'#e3ab8c',V:'#3df2ff',W:'#ffffff',B:'#26b8e8',P:'#16285e',R:'#3a2340',K:'#ff9db8',M:'#e0607e',E:'#ffd3ea',N:'#eebc9d',T:'#1d1840',C:'#3df2ff',L:'#c25bff',D:'#ff4fd8'};
  let box=null,on=false;
  function hairCols(){const st=[...av.querySelectorAll('#avHair stop')].map(s=>s.style.stopColor||getComputedStyle(s).stopColor).filter(Boolean);/* target colours, not mid-transition */return st.length?st:['#d892dc','#f0b8f2']}
  function build(){
    const hc=hairCols(),NS='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 120 120');svg.setAttribute('shape-rendering','crispEdges');svg.classList.add('voxel');
    let k=0;
    G.forEach((row,y)=>[...row].forEach((ch,x)=>{if(ch==='.')return;
      let c=COL[ch];if(ch==='H'){c=hc[Math.min(hc.length-1,Math.floor(x/24*hc.length))]}
      const r=document.createElementNS(NS,'rect');if(ch==='H')r.classList.add('vx-hair');r.setAttribute('x',x*5);r.setAttribute('y',y*5);r.setAttribute('width',5.05);r.setAttribute('height',5.05);r.style.fill=c;
      if(ch==='H'&&((x*7+y*3)%5===0))r.setAttribute('fill-opacity','.82');            // a little texture in the hair blocks
      if(ch==='V')r.setAttribute('fill-opacity','.75');
      if('WBP'.includes(ch))r.classList.add('vx-eye');
      r.dataset.y=y;r.dataset.x=x;svg.appendChild(r);k++;}));
    // closed eyelids (skin pixels over the eyes) for blinking
    [[7,11],[8,11],[9,11],[14,11],[15,11],[16,11],[7,12],[8,12],[9,12],[14,12],[15,12],[16,12]].forEach(([x,y])=>{const r=document.createElementNS(NS,'rect');r.setAttribute('x',x*5);r.setAttribute('y',y*5);r.setAttribute('width',5.05);r.setAttribute('height',5.05);r.setAttribute('fill',COL.S);r.classList.add('vx-lid');svg.appendChild(r)});
    const b=document.createElement('div');b.className='voxelbox';b.appendChild(svg);return b;
  }
  function show(){
    if(on)return;on=true;if(box)box.remove();box=build();av.appendChild(box);av.classList.add('is-voxel');
    if(reduce||!Element.prototype.animate)return;
    [...box.querySelectorAll('rect:not(.vx-lid)')].forEach(r=>{const y=+r.dataset.y,x=+r.dataset.x;
      r.animate([{transform:`translate(${(x-12)*1.5}px,${-30-Math.random()*30}px)`,opacity:0},{transform:'translate(0,0)',opacity:1}],
        {duration:420,delay:(23-y)*22+Math.random()*120,easing:'cubic-bezier(.3,1.4,.5,1)',fill:'backwards'});});
  }
  function hide(){
    if(!on)return;on=false;av.classList.remove('is-voxel');const b=box;box=null;if(!b)return;
    if(reduce||!Element.prototype.animate){b.remove();return}
    let last=null;[...b.querySelectorAll('rect')].forEach(r=>{const y=+r.dataset.y||0,x=+r.dataset.x||12;
      last=r.animate([{transform:'translate(0,0)',opacity:1},{transform:`translate(${(x-12)*2+(Math.random()-.5)*20}px,${40+Math.random()*40}px) rotate(${(Math.random()-.5)*90}deg)`,opacity:0}],
        {duration:520,delay:y*14+Math.random()*100,easing:'ease-in',fill:'forwards'});});
    setTimeout(()=>b.remove(),1100);
  }
  function recolor(){if(!box)return;const hc=hairCols();box.querySelectorAll('.vx-hair').forEach(r=>{r.style.fill=hc[Math.min(hc.length-1,Math.floor(+r.dataset.x/24*hc.length))]})}
  // called after every change of the database selection (renderDbBar): block mode while Magnolia is selected
  window.syncVoxel=()=>{try{if(typeof SEL_DB!=='undefined'&&SEL_DB.includes('ML')){if(on)recolor();else show()}else hide()}catch(e){}};
})();
