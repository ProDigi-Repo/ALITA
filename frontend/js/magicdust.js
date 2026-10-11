/* Magic dust: clicking ALITA's avatar lets glittering dust rain down from her.
   One full-window canvas while the dust falls, removed afterwards; colors = the avatar's hair
   (selected databases) mixed with silver and gold. Reduced motion: a single soft glow instead. */
(function(){
  const av=document.getElementById('avatar');if(!av)return;
  av.style.cursor='pointer';av.title='Click for magic dust';
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cv=null,g=null,parts=[],raf=0,last=0;
  const hairColors=()=>{const c=[...av.querySelectorAll('#avHair stop')].map(s=>getComputedStyle(s).stopColor).filter(x=>x&&x!=='rgba(0, 0, 0, 0)');return c.length?c:['#ff3b6b','#ffd84d','#52e08a','#36cfff','#c25bff']};
  function ensure(){if(cv)return;cv=document.createElement('canvas');cv.className='magicdust';document.body.appendChild(cv);g=cv.getContext('2d');size();addEventListener('resize',size)}
  function size(){if(!cv)return;const d=devicePixelRatio||1;cv.width=innerWidth*d;cv.height=innerHeight*d;g.setTransform(d,0,0,d,0,0)}
  function star(x,y,r,rot){g.beginPath();for(let i=0;i<8;i++){const a=rot+i*Math.PI/4,rr=i%2?r*.32:r;g.lineTo(x+Math.cos(a)*rr,y+Math.sin(a)*rr)}g.closePath();g.fill()}
  function burst(ev){
    const r=av.getBoundingClientRect(),cols=[...hairColors(),'#ffffff','#fff3b0','#e6f6ff'];
    const ox=ev&&ev.clientX?ev.clientX:r.left+r.width/2,oy=r.top+r.height*.35;
    for(let i=0;i<140;i++){const big=Math.random()<.18;
      parts.push({x:ox+(Math.random()-.5)*r.width*.8,y:oy+(Math.random()-.5)*r.height*.5,
        vx:(Math.random()-.5)*2.6,vy:-Math.random()*2.4-.4,          // puff up a little, then fall
        r:big?2.6+Math.random()*2.4:.7+Math.random()*1.4,star:big||Math.random()<.25,
        c:cols[Math.floor(Math.random()*cols.length)],rot:Math.random()*6,vr:(Math.random()-.5)*.2,
        ph:Math.random()*6,life:0,max:3400+Math.random()*2800,sway:.4+Math.random()*1.2});}
    ensure();if(!raf){last=performance.now();raf=requestAnimationFrame(tick)}
  }
  function tick(now){
    const dt=Math.min(40,now-last);last=now;g.clearRect(0,0,innerWidth,innerHeight);g.globalCompositeOperation='lighter';
    parts=parts.filter(p=>{p.life+=dt;if(p.life>p.max||p.y>innerHeight+20)return false;
      const k=dt/16;p.vy=Math.min(2.4,p.vy+.05*k);p.vx*=.985;                 // gentle gravity, air drag
      p.x+=(p.vx+Math.sin(p.life/380+p.ph)*.35*p.sway)*k;p.y+=p.vy*k;p.rot+=p.vr*k;
      const fade=Math.min(1,(p.max-p.life)/700),tw=.55+.45*Math.sin(p.life/90+p.ph*3);   // twinkle
      g.globalAlpha=fade*tw;g.fillStyle=p.c;g.shadowColor=p.c;g.shadowBlur=p.r*4;
      if(p.star)star(p.x,p.y,p.r*1.8,p.rot);else{g.beginPath();g.arc(p.x,p.y,p.r,0,7);g.fill()}
      return true;});
    g.globalAlpha=1;g.shadowBlur=0;
    if(parts.length)raf=requestAnimationFrame(tick);else{raf=0;cv.remove();cv=null;removeEventListener('resize',size)}
  }
  av.addEventListener('click',ev=>{
    if(reduce){av.animate([{filter:'drop-shadow(0 0 0 #fff)'},{filter:'drop-shadow(0 0 14px #fff3b0)'},{filter:'drop-shadow(0 0 0 #fff)'}],{duration:900});return}
    burst(ev);try{AV.flash('#fff3b0')}catch(e){}
  });
  window.magicDust=()=>burst();
})();
