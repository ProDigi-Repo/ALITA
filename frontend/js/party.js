/* REQ-91: an ocean party over the whole screen after every upload – a wave washes in, schools of party fish with
   party hats swim across, a disco ball spins, bubbles and confetti rise, fireworks burst, and Ollie, ALITA's own party
   octopus with sunglasses, dances in the middle. About six seconds; never blocks clicks (pointer-events: none),
   Escape ends it early, and with "reduce motion" only a calm banner appears.
   oceanParty(text) starts it; called from upload.js when the server has accepted an upload. */
(function(){
  const NS='http://www.w3.org/2000/svg';
  const rnd=(a,b)=>a+Math.random()*(b-a),pick=a=>a[Math.floor(Math.random()*a.length)];
  const COLORS=['#ff4f8b','#ffd23f','#3df2ff','#7c4dff','#2ee59d','#ff7a2f','#ffffff','#5fd8ff'];
  const DURATION=6200;
  let running=null;

  function el(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e}

  /* a cartoon party fish facing right, with a striped party hat */
  function fishSvg(body,fin,hat){
    const svg=el('svg',{viewBox:'0 0 120 80',width:120,height:80});
    el('path',{d:'M18 40 L0 18 L6 40 L0 62 Z',fill:fin},svg);                                  // tail
    el('ellipse',{cx:62,cy:42,rx:44,ry:28,fill:body},svg);                                     // body
    el('path',{d:'M50 16 Q62 2 76 16',fill:fin},svg);                                          // dorsal fin
    el('path',{d:'M40 30 Q48 42 40 54 M54 26 Q62 42 54 58',stroke:'rgba(255,255,255,.55)','stroke-width':4,fill:'none','stroke-linecap':'round'},svg);
    el('circle',{cx:88,cy:36,r:9,fill:'#fff'},svg);el('circle',{cx:90,cy:36,r:4.5,fill:'#14213d'},svg);
    el('path',{d:'M96 50 Q102 54 106 48',stroke:'#14213d','stroke-width':3,fill:'none','stroke-linecap':'round'},svg);  // smile
    if(hat){const g=el('g',{transform:'translate(70 2) rotate(18)'},svg);
      el('path',{d:'M0 22 L12 -10 L24 22 Z',fill:hat},g);
      el('path',{d:'M4 12 L20 12 M8 2 L16 2',stroke:'#fff','stroke-width':3},g);
      el('circle',{cx:12,cy:-11,r:4,fill:'#fff'},g)}
    return svg;
  }
  /* Ollie, the party octopus: purple, sunglasses, party hat, eight waving arms */
  function octopusSvg(){
    const svg=el('svg',{viewBox:'0 0 240 260',width:240,height:260,class:'party-octo'});
    const arms=el('g',{},svg);
    for(let i=0;i<8;i++){const x=48+i*20,dir=i<4?-1:1;
      el('path',{d:`M${x} 150 C${x+dir*10} 190 ${x-dir*18} 210 ${x+dir*14} 248`,stroke:'#9b5de5','stroke-width':16,fill:'none','stroke-linecap':'round',class:'party-arm',style:`animation-delay:${(i*0.09).toFixed(2)}s`},arms)}
    el('ellipse',{cx:120,cy:110,rx:78,ry:72,fill:'#9b5de5'},svg);
    el('ellipse',{cx:96,cy:70,rx:22,ry:12,fill:'rgba(255,255,255,.25)'},svg);
    [[88,136],[150,140],[120,152]].forEach(([x,y])=>el('circle',{cx:x,cy:y,r:5,fill:'#c39bff'},svg));
    const glasses=el('g',{},svg);                                                              // sunglasses
    el('rect',{x:70,y:96,width:42,height:24,rx:9,fill:'#14213d'},glasses);
    el('rect',{x:128,y:96,width:42,height:24,rx:9,fill:'#14213d'},glasses);
    el('path',{d:'M112 104 L128 104',stroke:'#14213d','stroke-width':5},glasses);
    el('path',{d:'M78 100 L92 100',stroke:'rgba(255,255,255,.6)','stroke-width':3,'stroke-linecap':'round'},glasses);
    el('path',{d:'M98 134 Q120 154 142 134',stroke:'#14213d','stroke-width':5,fill:'#ff4f8b','stroke-linecap':'round'},svg);  // big grin
    const hat=el('g',{transform:'translate(120 8)'},svg);
    el('path',{d:'M-26 44 L0 -18 L26 44 Z',fill:'#ffd23f'},hat);
    el('path',{d:'M-18 26 L18 26 M-10 8 L10 8',stroke:'#ff4f8b','stroke-width':5},hat);
    el('circle',{cx:0,cy:-20,r:8,fill:'#3df2ff'},hat);
    return svg;
  }
  function discoBall(){
    const svg=el('svg',{viewBox:'0 0 100 130',width:100,height:130,class:'party-disco'});
    el('line',{x1:50,y1:0,x2:50,y2:30,stroke:'#cfd8e3','stroke-width':2},svg);
    el('circle',{cx:50,cy:78,r:46,fill:'#b8c4d6'},svg);
    const tiles=el('g',{class:'party-tiles'},svg);
    for(let y=40;y<120;y+=10)for(let x=8;x<96;x+=10){
      if((x-50)**2+(y-78)**2<44**2)el('rect',{x,y,width:8,height:8,fill:pick(['#ffffff','#e3ecf7','#9fb2c9','#3df2ff','#ff4f8b']),opacity:rnd(.6,1)},tiles)}
    return svg;
  }

  function particles(canvas,until){
    const ctx=canvas.getContext('2d'),dpr=Math.min(2,devicePixelRatio||1);
    const W=()=>canvas.width/dpr,H=()=>canvas.height/dpr;
    const fit=()=>{canvas.width=innerWidth*dpr;canvas.height=innerHeight*dpr;ctx.setTransform(dpr,0,0,dpr,0,0)};fit();
    const P=[];
    const rocket=()=>P.push({k:'rocket',x:rnd(.08,.92)*W(),y:H()+10,vx:rnd(-.8,.8),vy:-rnd(13,18)*Math.sqrt(H()/900),c:pick(COLORS),life:1});
    const burst=(x,y,c)=>{const n=110,c2=pick(COLORS);for(let i=0;i<n;i++){const a=i/n*Math.PI*2+rnd(-.05,.05),v=rnd(3,9);
      P.push({k:'spark',x,y,px:x,py:y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,c:Math.random()<.25?'#fff':i%2?c:c2,life:1,decay:rnd(.009,.016),r:rnd(2,3.6)})}
      P.push({k:'glow',x,y,life:1,decay:.04,r:rnd(90,140),c});
      for(let i=0;i<26;i++)P.push({k:'flame',x:x+rnd(-20,20),y:y+rnd(-20,20),vx:rnd(-2.2,2.2),vy:rnd(-3.5,-.8),life:1,decay:rnd(.016,.03),r:rnd(10,22)})};
    for(let i=0;i<180;i++)P.push({k:'confetti',x:rnd(0,1)*W(),y:rnd(-H()*.6,H()*.35),vx:rnd(-1,1),vy:rnd(1.5,3.5),c:pick(COLORS),r:rnd(0,6.28),vr:rnd(-.2,.2),w:rnd(6,11),h:rnd(3,6),life:1});
    for(let i=0;i<70;i++)P.push({k:'bubble',x:rnd(0,1)*W(),y:H()+rnd(0,H()*.6),vy:-rnd(1.2,3.2),r:rnd(3,13),ph:rnd(0,6.28),life:1});
    let last=0,frame,prev=0;
    for(let i=0;i<4;i++)setTimeout(()=>{if(performance.now()<until)rocket()},i*140);   // opening salvo
    /* physics in fixed 60 Hz steps, however fast the screen refreshes – same show on every computer */
    const move=(p,t)=>{
      if(p.k==='rocket'){p.x+=p.vx;p.y+=p.vy;p.vy+=.18;if(p.vy>-1.5){burst(p.x,p.y,p.c);return false}return true}
      if(p.k==='spark'){p.px=p.x;p.py=p.y;p.x+=p.vx;p.y+=p.vy;p.vy+=.06;p.vx*=.982;p.vy*=.99;p.life-=p.decay}
      else if(p.k==='glow')p.life-=p.decay;
      else if(p.k==='flame'){p.x+=p.vx;p.y+=p.vy;p.life-=p.decay}
      else if(p.k==='confetti'){p.x+=p.vx+Math.sin(t/300+p.r)*.6;p.y+=p.vy;p.r+=p.vr;if(p.y>H()+20)p.y=-10}
      else if(p.k==='bubble'){p.y+=p.vy;p.x+=Math.sin(t/400+p.ph)*.5;if(p.y<-20)p.y=H()+20}
      return p.life>0};
    const draw=(p,t)=>{
      if(p.k==='rocket'){ctx.fillStyle=p.c;ctx.beginPath();ctx.arc(p.x,p.y,4,0,7);ctx.fill();
        for(let j=1;j<6;j++){ctx.fillStyle=`rgba(255,${180+j*12},63,${.7-j*.12})`;ctx.beginPath();ctx.arc(p.x-p.vx*j*.8,p.y-p.vy*j*.8,3.5-j*.5,0,7);ctx.fill()}}
      else if(p.k==='spark'){ctx.globalAlpha=Math.max(0,p.life);ctx.strokeStyle=p.c;ctx.lineWidth=p.r;ctx.lineCap='round';
        ctx.beginPath();ctx.moveTo(p.px-p.vx*1.5,p.py-p.vy*1.5);ctx.lineTo(p.x,p.y);ctx.stroke();ctx.globalAlpha=1}
      else if(p.k==='glow'){const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r);
        g.addColorStop(0,`rgba(255,255,255,${Math.max(0,p.life*.55)})`);g.addColorStop(.35,`rgba(255,210,63,${Math.max(0,p.life*.35)})`);g.addColorStop(1,'rgba(255,79,139,0)');
        ctx.fillStyle=g;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,7);ctx.fill()}
      else if(p.k==='flame'){const g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r);
        g.addColorStop(0,`rgba(255,240,170,${Math.max(0,p.life)})`);g.addColorStop(.5,`rgba(255,122,47,${Math.max(0,p.life*.8)})`);g.addColorStop(1,'rgba(255,79,139,0)');
        ctx.fillStyle=g;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,7);ctx.fill()}
      else if(p.k==='confetti'){ctx.save();ctx.translate(p.x,p.y);ctx.rotate(p.r);ctx.fillStyle=p.c;ctx.fillRect(-p.w/2,-p.h/2,p.w,p.h*Math.abs(Math.cos(p.r*2)));ctx.restore()}
      else if(p.k==='bubble'){ctx.strokeStyle='rgba(223,247,255,.75)';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,7);ctx.stroke();
        ctx.fillStyle='rgba(255,255,255,.5)';ctx.beginPath();ctx.arc(p.x-p.r*.35,p.y-p.r*.35,p.r*.25,0,7);ctx.fill()}};
    const tick=t=>{
      if(t>until){ctx.clearRect(0,0,W(),H());return}
      if(t-last>330&&t<until-1400){rocket();if(Math.random()<.6)rocket();last=t}
      const steps=prev?Math.min(6,Math.max(1,Math.round((t-prev)/16.67))):1;prev=t;
      for(let n=0;n<steps;n++)for(let i=P.length-1;i>=0;i--)if(!move(P[i],t))P.splice(i,1);
      ctx.clearRect(0,0,W(),H());
      for(const p of P)draw(p,t);
      frame=requestAnimationFrame(tick)};
    frame=requestAnimationFrame(tick);
    addEventListener('resize',fit);
    return ()=>{cancelAnimationFrame(frame);removeEventListener('resize',fit)};
  }

  function stop(){if(!running)return;const r=running;running=null;r.layer.classList.add('out');r.cleanup();
    removeEventListener('keydown',r.onKey);setTimeout(()=>r.layer.remove(),700)}

  window.oceanParty=function(text){
    const calm=matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(running)stop();
    const layer=document.createElement('div');
    layer.className='party'+(calm?' calm':'');layer.setAttribute('aria-hidden','true');
    const banner=document.createElement('div');banner.className='party-banner';
    banner.innerHTML=`<b>${esc(text||'Upload received!')}</b><span>Ocean party – your data is on its way through the pipeline</span>`;
    if(calm){layer.appendChild(banner);document.body.appendChild(layer);
      running={layer,cleanup:()=>{},onKey:()=>{}};setTimeout(stop,2500);return}
    layer.innerHTML='<div class="party-wave"></div>';
    const canvas=document.createElement('canvas');canvas.className='party-canvas';layer.appendChild(canvas);
    const disco=discoBall();layer.appendChild(disco);
    const school=document.createElement('div');school.className='party-school';layer.appendChild(school);
    for(let i=0;i<16;i++){
      const left=i%2===0,f=document.createElement('div');
      f.className='party-fish'+(left?' rtl':'');
      f.style.top=rnd(8,86)+'%';
      f.style.setProperty('--dur',rnd(3.2,5.2).toFixed(2)+'s');
      f.style.setProperty('--delay',rnd(0,1.6).toFixed(2)+'s');
      f.style.setProperty('--size',rnd(.5,1.15).toFixed(2));
      f.appendChild(fishSvg(pick(COLORS.slice(0,6)),pick(COLORS),Math.random()<.6?pick(['#ff4f8b','#ffd23f','#3df2ff','#2ee59d']):null));
      school.appendChild(f)}
    const octo=document.createElement('div');octo.className='party-center';octo.appendChild(octopusSvg());octo.appendChild(banner);
    layer.appendChild(octo);
    document.body.appendChild(layer);
    const until=performance.now()+DURATION-900;
    const cleanup=particles(canvas,until);
    const onKey=e=>{if(e.key==='Escape')stop()};addEventListener('keydown',onKey);
    running={layer,cleanup,onKey};
    setTimeout(()=>{if(running&&running.layer===layer)stop()},DURATION);
  };
})();
