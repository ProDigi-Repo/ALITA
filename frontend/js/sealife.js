/* Deep-sea life in the underwater scene of the header and the database bar.
   Every now and then a creature passes behind the content: Ryūgū no tsukai (oarfish),
   anglerfish with a glowing lure, a school of lanternfish, hatchetfish, and jellyfish
   that pulse and drift. Pure decoration: SVG in a clipped layer (.ofbox) behind the
   content, no pointer events, nothing at all when the system asks for reduced motion.
   Console: seaLife('jelly'|'oarfish'|'angler'|'lantern'|'hatchet') spawns one now. */
(function(){
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const NS='http://www.w3.org/2000/svg';
  const el=(t,a,p)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;};
  const P=a=>a.map(([x,y],i)=>(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)).join('');
  const rnd=(a,b)=>a+Math.random()*(b-a);
  let uid=0, alive=0;
  const grad=(svg,stops,o={})=>{const id='sl'+(++uid);const defs=svg.querySelector('defs')||el('defs',{},svg);
    const g=el(o.radial?'radialGradient':'linearGradient',o.radial?{id}:{id,x1:0,y1:0,x2:0,y2:1},defs);
    stops.forEach(([off,c,op])=>el('stop',{offset:off,'stop-color':c,'stop-opacity':op??1},g));return `url(#${id})`;};

  /* ---------- species: each draws facing right (head at +x) in its own box ---------- */
  const SPECIES={
    oarfish:{weight:1,speed:[38,52],size:[.75,1.1],box:s=>[Math.round(460*s)+60,90],make(svg,s){
      const L=Math.round(460*s),T=13*s,N=60;svg.setAttribute('viewBox',`-50 -45 ${L+60} 90`);
      const body_g=grad(svg,[['0','#f4fbff'],['.45','#b9cfdd'],['1','#5f7f96']]);
      const fin=el('path',{fill:'none',stroke:'#ff5a4e','stroke-width':1.2*s,'stroke-opacity':.85},svg);
      const rays=el('path',{fill:'none',stroke:'#ff7a6a','stroke-width':.7,'stroke-opacity':.6},svg);
      const body=el('path',{fill:body_g,stroke:'#dff1ff','stroke-opacity':.35,'stroke-width':.6},svg);
      const spots=el('path',{fill:'none',stroke:'#3d5a70','stroke-width':.8,'stroke-opacity':.45,'stroke-dasharray':'1 7'},svg);
      const oars=el('path',{fill:'none',stroke:'#ff6b5c','stroke-width':.9,'stroke-linecap':'round','stroke-opacity':.8},svg);
      const crest=el('path',{fill:'none',stroke:'#ff4f45','stroke-width':1.1,'stroke-linecap':'round','stroke-opacity':.9},svg);
      const eye=el('circle',{r:1.8*s,fill:'#0b1a26'},svg);
      return t=>{
        const top=[],bot=[],mid=[];
        for(let i=0;i<=N;i++){const u=i/N,X=L*(1-u),amp=(2+10*u*u)*s;
          const Y=amp*Math.sin(u*9-t*3.2)+3*s*Math.sin(t*.7);
          const th=T*(u<.06?.55+u/.06*.45:1-.93*Math.pow((u-.06)/.94,.8));
          mid.push([X,Y]);top.push([X,Y-th/2]);bot.push([X,Y+th/2]);}
        const hx=L+6*s,hy=mid[0][1];
        body.setAttribute('d',P(top)+`Q${hx} ${hy-T*.35} ${hx} ${hy}Q${hx} ${hy+T*.35} `+P(bot.slice().reverse()).replace(/^M/,'')+'Z');
        fin.setAttribute('d',P(top.map(([x,y],i)=>[x,y-(3.5-2.5*i/N)*s])));
        let r='';for(let i=1;i<N;i+=2){const [x,y]=top[i];r+=`M${x.toFixed(1)} ${y.toFixed(1)}l${(1.2*s).toFixed(1)} ${(-(4-3*i/N)*s).toFixed(1)}`;}
        rays.setAttribute('d',r);spots.setAttribute('d',P(mid.slice(4,N-6)));
        let c='';for(let k=0;k<6;k++){const bx=L-(2+k*2.5)*s,by=top[1][1]-1,len=(16+k*4)*s,w=Math.sin(t*2.4+k*.9)*4*s;
          c+=`M${bx.toFixed(1)} ${by.toFixed(1)}q${(-len*.4).toFixed(1)} ${(-10*s+w).toFixed(1)} ${(-len).toFixed(1)} ${(-4*s+w*1.6).toFixed(1)}`;}
        crest.setAttribute('d',c);
        let o='';for(let k=0;k<2;k++){const bx=L-9*s,by=bot[3][1],w=Math.sin(t*1.8+k*1.3)*5*s;
          o+=`M${bx.toFixed(1)} ${by.toFixed(1)}q${(-14*s).toFixed(1)} ${(10*s+w).toFixed(1)} ${(-(34+k*8)*s).toFixed(1)} ${(14*s+w*1.5).toFixed(1)}`;}
        oars.setAttribute('d',o);eye.setAttribute('cx',(L-2*s).toFixed(1));eye.setAttribute('cy',(hy-1.2*s).toFixed(1));
      };}},

    angler:{weight:2,speed:[16,24],size:[.8,1.15],box:s=>[110*s,80*s],make(svg,s){
      svg.setAttribute('viewBox','-10 -45 110 80');
      const glow=grad(svg,[['0','#eaffff',1],['.25','#7ff6ff',.9],['1','#3df2ff',0]],{radial:true});
      const skin=grad(svg,[['0','#3a3240'],['1','#120e16']]);
      const g=el('g',{},svg);
      const tail=el('path',{fill:'#1a1520',stroke:'#4a4052','stroke-width':.6},g);
      const body=el('path',{d:'M14 0C14 -22 40 -30 62 -24C76 -20 84 -10 86 -2L70 2L86 6C82 16 70 24 52 24C30 24 14 14 14 0Z',fill:skin,stroke:'#5a4f63','stroke-width':.7},g);
      el('path',{d:'M70 2L73 -3L75 3L77 -3L79 3L81 -2L84 4M71 4L73 8L75 4L77 9L79 4L81 8',fill:'none',stroke:'#e9eef2','stroke-width':.7,'stroke-opacity':.9},g);
      el('circle',{cx:66,cy:-12,r:2.2,fill:'#9fb7c6'},g);el('circle',{cx:66.4,cy:-12.3,r:1,fill:'#0b0f14'},g);
      el('path',{d:'M38 6q6 6 2 12M30 -10q8 -4 14 2',fill:'none',stroke:'#4d4357','stroke-width':.8},g);
      const rod=el('path',{fill:'none',stroke:'#6c5f78','stroke-width':1.2,'stroke-linecap':'round'},g);
      const halo=el('circle',{r:11,fill:glow},g);const lure=el('circle',{r:2.4,fill:'#dfffff'},g);
      return t=>{
        const wag=Math.sin(t*3)*5;
        tail.setAttribute('d',`M16 0L${-2} ${-12+wag}L2 0L${-2} ${12+wag}Z`);
        const lx=90+Math.sin(t*1.3)*3,ly=-34+Math.sin(t*1.9)*3;
        rod.setAttribute('d',`M58 -24Q66 -44 ${lx} ${ly}`);
        lure.setAttribute('cx',lx);lure.setAttribute('cy',ly);halo.setAttribute('cx',lx);halo.setAttribute('cy',ly);
        const pulse=.6+.4*Math.sin(t*2.2)**2;halo.setAttribute('opacity',pulse.toFixed(2));halo.setAttribute('r',(9+3*pulse).toFixed(1));
        g.setAttribute('transform',`translate(0 ${(Math.sin(t*.8)*3).toFixed(1)})`);
      };}},

    lantern:{weight:3,speed:[55,75],size:[1.2,1.5],box:s=>[200*s,70*s],make(svg,s){
      svg.setAttribute('viewBox','0 -35 200 70');
      const silver=grad(svg,[['0','#dcebf5'],['.5','#8fa9bb'],['1','#2f4658']]);
      const fish=[...Array(7)].map((_,i)=>{
        const g=el('g',{},svg),x=20+Math.random()*150,y=-24+Math.random()*48,k=.7+Math.random()*.5,ph=Math.random()*6;
        const tail=el('path',{fill:'#6f8ba0'},g);
        el('path',{d:'M0 0C3 -4 10 -4.5 15 -2C17 -1 18 0 18 0C18 0 17 1 15 2C10 4.5 3 4 0 0Z',fill:silver},g);
        el('circle',{cx:14.5,cy:-.8,r:1.4,fill:'#0b141c'},g);
        [3,6,9,12].forEach(px=>el('circle',{cx:px,cy:2.3,r:.7,fill:'#7ff0ff'},g));
        el('circle',{cx:16.5,cy:1,r:.9,fill:'#9ff7ff'},g);
        return {g,tail,x,y,k,ph};});
      return t=>fish.forEach(f=>{
        const w=Math.sin(t*9+f.ph)*2.4;
        f.tail.setAttribute('d',`M1 0L-5 ${-3.5+w}L-4 0L-5 ${3.5+w}Z`);
        f.g.setAttribute('transform',`translate(${(f.x+Math.sin(t*.9+f.ph)*6).toFixed(1)} ${(f.y+Math.sin(t*1.3+f.ph)*3).toFixed(1)}) scale(${f.k})`);});}},

    hatchet:{weight:2,speed:[30,42],size:[.9,1.2],box:s=>[120*s,70*s],make(svg,s){
      svg.setAttribute('viewBox','0 -35 120 70');
      const silver=grad(svg,[['0','#f2f8fc'],['.55','#a7bccb'],['1','#3c5263']]);
      const fish=[[20,-10,1],[64,8,.85],[92,-16,.7]].slice(0,2+Math.floor(Math.random()*2)).map(([x,y,k],i)=>{
        const g=el('g',{},svg),tail=el('path',{fill:'#8aa2b3'},g);
        el('path',{d:'M0 -3L16 -6L20 -2L18 3L10 12L4 9Z',fill:silver,stroke:'#e6f2fa','stroke-opacity':.4,'stroke-width':.4},g);
        el('circle',{cx:16,cy:-3,r:2.1,fill:'#cfe0ea'},g);el('circle',{cx:16.3,cy:-3.2,r:1.1,fill:'#081018'},g);
        [5,7.5,10,12.5].forEach((px,j)=>el('circle',{cx:px,cy:8.5-j*.6,r:.75,fill:'#7ff0ff'},g));
        return {g,tail,x,y,k,ph:i*1.7};});
      return t=>fish.forEach(f=>{
        const w=Math.sin(t*7+f.ph)*2;
        f.tail.setAttribute('d',`M1 -2L-5 ${-5+w}L-4 0L-5 ${5+w}L1 3Z`);
        f.g.setAttribute('transform',`translate(${f.x} ${(f.y+Math.sin(t*1.1+f.ph)*4).toFixed(1)}) scale(${f.k}) rotate(${(Math.sin(t*.9+f.ph)*4).toFixed(1)})`);});}},

    jelly:{weight:3,speed:[10,16],size:[.55,.8],drift:true,box:s=>[80*s,110*s],make(svg,s){
      svg.setAttribute('viewBox','-40 -40 80 110');
      const hue=[['#ff9ad9','#b05cff'],['#8ff4ff','#3d8bff'],['#c9a6ff','#6a4dff'],['#ffd0a0','#ff6a8a']][Math.floor(Math.random()*4)];
      const bellG=grad(svg,[['0',hue[0],.75],['.6',hue[1],.35],['1',hue[1],.08]],{radial:true});
      const glowG=grad(svg,[['0',hue[0],.35],['1',hue[0],0]],{radial:true});
      el('circle',{cx:0,cy:-8,r:36,fill:glowG},svg);
      const tent=el('path',{fill:'none',stroke:hue[0],'stroke-width':.8,'stroke-opacity':.55,'stroke-linecap':'round'},svg);
      const arms=el('path',{fill:'none',stroke:hue[0],'stroke-width':2.2,'stroke-opacity':.35,'stroke-linecap':'round'},svg);
      const bell=el('path',{fill:bellG,stroke:hue[0],'stroke-opacity':.6,'stroke-width':.7},svg);
      const rim=el('path',{fill:'none',stroke:'#ffffff','stroke-opacity':.35,'stroke-width':.6,'stroke-dasharray':'1.5 3'},svg);
      return t=>{
        const c=Math.sin(t*2.1),w=20*(1+.12*c),h=17*(1-.1*c),fl=6+3*c;   // pulse: contract and relax
        bell.setAttribute('d',`M${-w} 0C${-w} ${-h*1.5} ${w} ${-h*1.5} ${w} 0C${w*.7} ${fl*.4} ${w*.35} ${fl*.2} 0 ${fl*.35}C${-w*.35} ${fl*.2} ${-w*.7} ${fl*.4} ${-w} 0Z`);
        rim.setAttribute('d',`M${-w*.95} 1C${-w*.5} ${fl*.5} ${w*.5} ${fl*.5} ${w*.95} 1`);
        let d='';for(let k=0;k<9;k++){const x0=-w*.85+k*(w*1.7/8);d+=`M${x0.toFixed(1)} 2`;
          for(let j=1;j<=6;j++){const y=2+j*9,x=x0+Math.sin(t*1.6-j*.7+k)*(1.5+j*.9);d+=`L${x.toFixed(1)} ${y}`;}}
        tent.setAttribute('d',d);
        let a='';for(let k=0;k<4;k++){const x0=-6+k*4;a+=`M${x0} 4Q${(x0+Math.sin(t*1.2+k)*6).toFixed(1)} 22 ${(x0+Math.sin(t*1.2+k+1)*4).toFixed(1)} ${36+k*3}`;}
        arms.setAttribute('d',a);
      };}},
  };

  function spawn(kind){
    const bars=[...document.querySelectorAll('.top,.dbbar')].filter(b=>b.offsetParent);
    if(!bars.length||document.hidden||alive>=2) return false;
    if(!kind){const ks=Object.keys(SPECIES),tot=ks.reduce((a,k)=>a+SPECIES[k].weight,0);let r=Math.random()*tot;kind=ks.find(k=>(r-=SPECIES[k].weight)<0)||ks[0];}
    const sp=SPECIES[kind]; if(!sp) return false;
    const bar=bars[Math.floor(Math.random()*bars.length)];
    const W=bar.clientWidth,H=bar.clientHeight;
    const s=rnd(...sp.size),[bw,bh]=sp.box(s),ltr=Math.random()<.5,v=rnd(...sp.speed);
    const svg=el('svg',{class:'seacreature '+kind,width:bw,height:bh,'aria-hidden':'true'});
    const update=sp.make(svg,s);
    const y0=sp.drift? rnd(0,Math.max(0,H-bh*.8)) : H*rnd(.3,.7)-bh/2;
    const vy=sp.drift? rnd(-.6,-.2) : 0;                     // jellyfish rise very slowly
    const box=document.createElement('div');box.className='ofbox';box.appendChild(svg);bar.appendChild(box);
    const dist=W+bw, t0=performance.now(); alive++;
    (function frame(now){
      const t=(now-t0)/1000, x=ltr? -bw+v*t : W-v*t;
      if((ltr?x>W:x<-bw)||!box.isConnected){box.remove();alive--;return;}
      const y=y0+vy*t+(sp.drift?Math.sin(t*.6)*5-Math.max(0,Math.sin(t*2.1))*2:0);
      svg.style.transform=`translate(${x.toFixed(1)}px,${y.toFixed(1)}px)${ltr||sp.drift?'':' scaleX(-1)'}`;
      update(t); requestAnimationFrame(frame);
    })(t0);
    return true;
  }
  (function loop(first){setTimeout(()=>{spawn();loop()}, first?4000:rnd(9000,26000));})(true);
  window.seaLife=k=>spawn(k);
})();
