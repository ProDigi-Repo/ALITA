/* ALITA, the helper fairy. A click on the info sign above a chat lets a small ALITA morph out of the big avatar in the
   database bar, fly down and land next to the sign. You can ask her a question (it goes to her chat) or let her show
   you around: she flies from function to function, highlights it and explains it. She flies back into the avatar
   when she leaves. Her head is a live copy of the big avatar (hair colours, flowers and all); the body is drawn here. */
(function(){
  const HELLO='Hi, I’m ALITA! I can <b>show you how everything here works</b> – and explain the difference between the two ways to search: <b>RAG</b> and <b>Graph</b>.';
  const DIFF=`<b class="cw-step">RAG vs. Graph</b>
    <span class="cw-ab"><i class="cw-a1">A</i><b>RAG – Document Chat</b>: finds the text passages that fit your question best and answers from them. Good for <i>what</i> a paper or note says – content, details, quotes.</span>
    <span class="cw-ab"><i class="cw-b1">B</i><b>Graph – Graph Chat</b>: follows the connections between people, projects, methods, clusters and document parts. Good for <i>how</i> things are connected – who worked with whom, which methods in which project.</span>
    <span class="cw-tip">Tip: content → A, connections → B. Or just ask me, I pass it on.</span>`;
  const NS='http://www.w3.org/2000/svg',FW=92,FH=118,BW=300;
  const RM=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  const BODY=`
    <ellipse class="cw-disc" cx="60" cy="146" rx="24" ry="4.5" fill="#3df2ff" fill-opacity=".45"/>
    <ellipse cx="60" cy="146" rx="14" ry="2.4" fill="#fff" fill-opacity=".8"/>
    <g class="cw-spark"><path d="M30 138l1.2 2.8 2.8 1.2-2.8 1.2-1.2 2.8-1.2-2.8-2.8-1.2 2.8-1.2Z" fill="#ffd36b"/><path d="M90 132l1 2.2 2.2 1-2.2 1-1 2.2-1-2.2-2.2-1 2.2-1Z" fill="#ff9be6"/><circle cx="84" cy="146" r="1.2" fill="#fff"/><circle cx="36" cy="150" r="1" fill="#fff"/></g>
    <g class="cw-wingL"><path d="M47 98C30 84 14 88 16 100c2 10 18 14 31 6Z" fill="#b9f2ff" fill-opacity=".55" stroke="#3df2ff" stroke-width=".9"/><path d="M46 106C32 108 22 118 30 124c7 4 16-4 18-14Z" fill="#ffd3ea" fill-opacity=".55" stroke="#ff9be6" stroke-width=".9"/></g>
    <g class="cw-wingR"><path d="M73 98C90 84 106 88 104 100c-2 10-18 14-31 6Z" fill="#b9f2ff" fill-opacity=".55" stroke="#3df2ff" stroke-width=".9"/><path d="M74 106C88 108 98 118 90 124c-7 4-16-4-18-14Z" fill="#ffd3ea" fill-opacity=".55" stroke="#ff9be6" stroke-width=".9"/></g>
    <path d="M53.5 118v11M66.5 118v11" stroke="#1b1636" stroke-width="7" stroke-linecap="round"/>
    <ellipse cx="52" cy="132.5" rx="6.6" ry="4" fill="#fff" stroke="#3df2ff" stroke-width="1.2"/><ellipse cx="68" cy="132.5" rx="6.6" ry="4" fill="#fff" stroke="#3df2ff" stroke-width="1.2"/>
    <ellipse cx="50.5" cy="131.3" rx="2" ry="1" fill="#ff9be6"/><ellipse cx="69.5" cy="131.3" rx="2" ry="1" fill="#ff9be6"/>
    <path d="M47 87Q60 82 73 87L79 116Q60 124 41 116Z" fill="url(#avTop)" stroke="#c25bff" stroke-width=".9" stroke-linejoin="round"/>
    <path d="M50 88Q60 95 70 88" fill="none" stroke="#3df2ff" stroke-width="1.6" stroke-linecap="round" filter="url(#avNeon)"/>
    <path d="M60 99l2 4.2 4.6.6-3.4 3.1.9 4.5-4.1-2.3-4.1 2.3.9-4.5-3.4-3.1 4.6-.6Z" fill="#ffd36b"/>
    <path d="M43 113Q60 119 77 113" fill="none" stroke="#ff4fd8" stroke-opacity=".7" stroke-width="1"/>
    <path d="M47 92Q40 100 39 108" fill="none" stroke="#26204a" stroke-width="7" stroke-linecap="round"/><circle cx="39" cy="110" r="4" fill="#f3c3a5"/>`;
  const WAVE=`<g class="cw-wave"><path d="M73 92Q82 88 86 79" fill="none" stroke="#26204a" stroke-width="7" stroke-linecap="round"/><circle cx="87" cy="76" r="4.2" fill="#f3c3a5"/></g>`;
  function figure(){
    const svg=document.createElementNS(NS,'svg');svg.setAttribute('viewBox','0 0 120 154');svg.setAttribute('role','img');svg.setAttribute('aria-label','ALITA');
    svg.innerHTML=BODY;
    const src=document.querySelector('#avatar svg');
    if(src){const head=src.cloneNode(true);head.querySelectorAll('defs').forEach(d=>d.remove());
      const bust=head.querySelector('#avBody');   // drop the big bust (shoulders, top) – the small chibi body replaces it; neck and hair locks stay
      if(bust)[...bust.children].forEach(ch=>{const f=ch.getAttribute('fill')||'',st=ch.getAttribute('stroke')||'';if(f.includes('avTop')||/#3df2ff|#ff4fd8/i.test(st))ch.remove()});
      const halo=head.querySelector('circle[fill="url(#avHalo)"]');if(halo)halo.remove();
      [head,...head.querySelectorAll('[id]')].forEach(e=>e.removeAttribute('id'));
      head.setAttribute('x','0');head.setAttribute('y','-4');head.setAttribute('width','120');head.setAttribute('height','120');head.setAttribute('overflow','visible');head.removeAttribute('aria-hidden');
      svg.appendChild(head);}
    svg.insertAdjacentHTML('beforeend',WAVE);
    return svg;
  }

  /* ---------------- tour stops (only those visible on the current page are used) ---------------- */
  const vis=el=>el&&el.offsetParent!==null&&el.getBoundingClientRect().width>0;
  const STOPS=[
    ['#dbs','Databases','Pick one or more databases here – their <b>flowers</b> appear everywhere they are used. Click again to deselect; <b>Clear selection</b> resets everything.'],
    ['#page-graph .bq-map','Knowledge map','Your whole knowledge at a glance: <b>projects &amp; papers</b> on top, <b>semantic clusters</b> in the middle, <b>documents</b> below. Click a cluster or a project to explore it.'],
    ['#page-graph .v3-reset','Reset view','Zoomed or turned too far? <b>⟲ Reset view</b> brings the map back to the start.'],
    ['#page-graph .bq-cluster','Projects & clusters','What you clicked opens here: descriptions, <b>connected clusters</b> and all <b>documents</b> – without leaving the page.'],
    ['#cviz','Cluster views','Map <b>A</b> filters the Document Chat, graph <b>B</b> the Graph Chat. <b>3D · time</b> lets you walk through the years.'],
    ['#page-chat .why-row','A or B?','<b>A</b> tells you <i>what</i> your documents say, <b>B</b> <i>how</i> things are connected.'],
    ['.tile:not([hidden]) .atoggle','Advanced settings','Filters and the system prompt of a chat live here – open them only when you need them.'],
    ['#graphInput','Ask the knowledge graph','Type your question here – or simply ask me, I pass it on.'],
    ['#page-chat #ragInput','Ask your documents','Questions about the content of your documents go here.'],
    ['.tile:not([hidden]) [data-hist]','History','Earlier conversations – open, download or delete them.'],
  ];
  let A=null;   // the active ALITA {el,fig,say,card,kind,tour,spot}
  function avatarRect(){const av=document.querySelector('#avatar');return av&&vis(av)?av.getBoundingClientRect():null}
  function place(left,top,flip){const el=A.el;el.classList.toggle('flip',!!flip);el.style.left=left+'px';el.style.top=top+'px';el._top=top;fit()}
  function fit(){   // keep ALITA and her bubble fully on screen when the bubble grows
    if(!A)return;const el=A.el,h=el.offsetHeight,t=(el._top??parseFloat(el.style.top))||0,nt=Math.max(6,Math.min(t,innerHeight-h-6));if(nt!==parseFloat(el.style.top))el.style.top=nt+'px'}
  function spot(el){if(A.spot)A.spot.classList.remove('alita-spot');A.spot=el;if(el)el.classList.add('alita-spot')}
  function posNear(r){   // where ALITA stands next to a target rectangle
    const W=FW+BW+8,big=r.height>220;let left,top;
    if(big){left=r.left+14;top=r.top+14}
    else{left=r.left-10;top=r.bottom+8;if(top+FH>innerHeight-6)top=r.top-FH-8}
    top=Math.max(6,Math.min(innerHeight-FH-6,top));
    let flip=false;if(left+W>innerWidth-6){const figLeft=Math.min(r.right-FW+10,innerWidth-FW-6);left=figLeft-BW-4;flip=true}   // bubble on the left, ALITA at the target
    left=Math.max(6,left);return {left,top,flip};
  }
  function morphIn(){   // grow out of the big avatar and fly to the landing spot
    const av=document.querySelector('#avatar'),ar=avatarRect(),fr=A.fig.getBoundingClientRect();
    if(av&&!RM())av.animate([{transform:'scale(1)',filter:'none'},{transform:'scale(.84)',filter:'brightness(1.5) drop-shadow(0 0 14px #3df2ff)',offset:.35},{transform:'scale(1)',filter:'none'}],{duration:900,easing:'ease-out'});
    if(av)setTimeout(()=>av.classList.add('alita-away'),RM()?0:180);   // she has left the avatar – the bar is empty until she comes back
    if(!ar||RM()){A.fig.classList.add('landed');return}
    const dx=ar.left+ar.width/2-(fr.left+fr.width/2),dy=ar.top+ar.height/2-(fr.top+fr.height/2),s0=Math.min(1.3,ar.height/FH);
    const an=A.fig.animate([{transform:`translate(${dx}px,${dy}px) scale(${s0})`,opacity:.15,filter:'brightness(2) blur(2px)'},
      {transform:`translate(${dx*.55}px,${dy*.45-50}px) scale(.8) rotate(-12deg)`,opacity:1,filter:'none',offset:.45},
      {transform:'translate(0,8px) rotate(3deg)',offset:.82},{transform:'none'}],{duration:1250,easing:'cubic-bezier(.3,.75,.3,1)'});
    an.onfinish=()=>A&&A.fig.classList.add('landed');
  }
  function leave(){   // fly back into the avatar
    if(!A)return;const cur=A;A=null;clearTimeout(cur.t);if(cur.spot)cur.spot.classList.remove('alita-spot');cur.say.style.opacity='0';
    const avEl=document.querySelector('#avatar'),ar=avEl&&avEl.offsetParent!==null?avEl.getBoundingClientRect():null,fr=cur.fig.getBoundingClientRect();
    const home=()=>{const av=document.querySelector('#avatar');if(!av)return;av.classList.remove('alita-away');if(!RM())av.animate([{transform:'scale(.6)',opacity:0,filter:'brightness(1.8) drop-shadow(0 0 14px #ff9be6)'},{transform:'scale(1.08)',opacity:1,offset:.6},{transform:'scale(1)',filter:'none'}],{duration:650,easing:'cubic-bezier(.3,1.4,.5,1)'})};
    if(!ar||RM()){cur.el.remove();home();return}
    cur.fig.classList.remove('landed');
    const dx=ar.left+ar.width/2-(fr.left+fr.width/2),dy=ar.top+ar.height/2-(fr.top+fr.height/2);
    const an=cur.fig.animate([{transform:'none',opacity:1},{transform:`translate(${dx*.45}px,${dy*.55-40}px) scale(.85) rotate(10deg)`,offset:.5},{transform:`translate(${dx}px,${dy}px) scale(.35)`,opacity:0,filter:'brightness(2)'}],{duration:900,easing:'ease-in'});
    an.onfinish=()=>{cur.el.remove();home()};
  }
  function arm(ms){if(!A)return;clearTimeout(A.t);if(A.keep||A.tour)return;A.t=setTimeout(leave,ms||9000)}
  function greet(){
    A.say.innerHTML=`<div class="cw-msg">${HELLO}</div><div class="cw-nav"><button type="button" class="cw-diff">RAG vs. Graph?</button><button type="button" class="cw-tour">✨ Show me around</button></div><form class="cw-ask"><input type="text" placeholder="Or ask me something …" aria-label="Your question to ALITA"><button type="submit" title="Send" aria-label="Send">➤</button></form>`;
    const inp=A.say.querySelector('input');
    inp.addEventListener('focus',()=>{A.keep=true;clearTimeout(A.t)});inp.addEventListener('blur',()=>{if(A&&!inp.value.trim()){A.keep=false;arm()}});
    setTimeout(()=>{try{A&&inp.focus({preventScroll:true})}catch(e){}},1250);
    A.say.querySelector('.cw-ask').addEventListener('submit',e=>{e.preventDefault();const q=inp.value.trim();if(!q)return;
      const t=A.kind==='a'?'rag':'graph',ci=document.getElementById(t+'Input'),cf=document.getElementById(t+'Form');if(!ci||!cf)return;
      ci.value=q;cf.requestSubmit();A.keep=true;
      A.say.innerHTML=`<div class="cw-msg">Got it! I’m asking the <b>${A.kind==='a'?'Document Chat':'Graph Chat'}</b> – the answer appears there ↓</div>`;
      const chat=document.getElementById(t+'Chat');if(chat)setTimeout(()=>chat.closest('.tile').scrollIntoView({behavior:'smooth',block:'nearest'}),400);
      clearTimeout(A.t);A.t=setTimeout(leave,2800)});
    A.say.querySelector('.cw-tour').addEventListener('click',startTour);
    A.say.querySelector('.cw-diff').addEventListener('click',showDiff);
    fit();arm();
  }
  function showDiff(){   // RAG vs. Graph – the two ways to search, side by side
    if(!A)return;A.keep=true;clearTimeout(A.t);
    A.say.innerHTML=`<div class="cw-msg">${DIFF}</div><div class="cw-nav"><button type="button" data-d="back">‹ Back</button><button type="button" class="cw-tour">✨ Show me around</button></div>`;
    fit();A.say.querySelector('[data-d="back"]').addEventListener('click',e=>{e.stopPropagation();A.keep=false;greet();fit()});
    A.say.querySelector('.cw-tour').addEventListener('click',e=>{e.stopPropagation();startTour()});
  }
  /* ---------------- tour ---------------- */
  function startTour(){
    const steps=STOPS.map(([sel,title,text])=>({el:[...document.querySelectorAll(sel)].find(vis),title,text})).filter(x=>x.el);
    if(!steps.length)return;A.tour={steps,i:0};clearTimeout(A.t);showStep(0);
  }
  function showStep(i){
    if(!A||!A.tour)return;const T=A.tour,st=T.steps[i];T.i=i;
    st.el.scrollIntoView({behavior:RM()?'auto':'smooth',block:'center',inline:'nearest'});spot(st.el);
    A.say.innerHTML=`<div class="cw-msg"><b class="cw-step">${esc(st.title)}</b> ${st.text}</div><div class="cw-nav"><span class="cw-count">${i+1} / ${T.steps.length}</span>`+
      `${i?'<button type="button" data-tour="back">‹ Back</button>':''}<button type="button" data-tour="next" class="cw-next">${i<T.steps.length-1?'Next ›':'Done ✓'}</button><button type="button" data-tour="end" title="End the tour">✕</button></div>`;
    A.say.querySelectorAll('[data-tour]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();const k=b.dataset.tour;
      if(k==='back')showStep(i-1);else if(k==='next'){if(i<T.steps.length-1)showStep(i+1);else leave()}else leave()}));
    fit();setTimeout(()=>{if(!A||A.tour!==T||T.i!==i)return;const p=posNear(st.el.getBoundingClientRect());A.fig.classList.add('flying');place(p.left,p.top,p.flip);setTimeout(()=>A&&A.fig.classList.remove('flying'),900);
      try{A.say.querySelector('.cw-next').focus({preventScroll:true})}catch(e){}},RM()?0:480);
  }
  /* ---------------- open from an info sign ---------------- */
  function open(btn){
    const card=btn.closest('.chat-why');if(!card)return;
    if(A){const same=A.card===card;leave();if(same)return}
    const kind=card.classList.contains('cw-a')?'a':'b',r=btn.getBoundingClientRect();
    const el=document.createElement('div');el.className='cw-pop cw-'+kind;el.setAttribute('role','dialog');el.setAttribute('aria-label','ALITA');
    const fig=document.createElement('div');fig.className='cw-fig';fig.appendChild(figure());
    const say=document.createElement('div');say.className='cw-say';
    el.append(fig,say);document.body.appendChild(el);
    A={el,fig,say,card,kind,tour:null,spot:null,keep:false};
    let top=r.top-FH+6;if(top<6)top=Math.min(innerHeight-FH-6,r.bottom+4);
    let left=Math.max(6,r.left-14),flip=false;if(left+FW+BW>innerWidth-6){flip=true;left=Math.max(6,r.left-14-BW-4)}
    place(left,top,flip);greet();morphIn();
  }
  document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('.chat-why .cw-tag');if(b){e.preventDefault();open(b);return}
    if(!A||A.tour||A.sticky)return;if(e.composedPath().includes(A.el)||!document.contains(e.target))return;   // clicks inside her bubble (even on buttons replaced meanwhile) keep her
    leave()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&A)leave();if(A&&A.tour&&(e.key==='ArrowRight'||e.key==='ArrowLeft')&&!(e.target&&e.target.tagName==='INPUT')){const i=A.tour.i+(e.key==='ArrowRight'?1:-1);if(i>=0&&i<A.tour.steps.length)showStep(i)}});
  addEventListener('scroll',e=>{if(!A||A.tour||A.keep)return;if(e.target&&e.target.closest&&e.target.closest('.cw-pop'))return;leave()},true);
  /* ALITA with a message of her own (e.g. after an upload): she morphs out of the avatar, lands below the database bar
     and stays until "OK" (or Esc) */
  window.alitaSay=(html,o={})=>{
    if(A){const c=A;A=null;clearTimeout(c.t);if(c.spot)c.spot.classList.remove('alita-spot');c.el.remove()}
    const el=document.createElement('div');el.className='cw-pop cw-b cw-notice';el.setAttribute('role','alertdialog');el.setAttribute('aria-label','ALITA');
    const fig=document.createElement('div');fig.className='cw-fig';fig.appendChild(figure());
    const say=document.createElement('div');say.className='cw-say';
    el.append(fig,say);document.body.appendChild(el);
    A={el,fig,say,card:null,kind:'b',tour:null,spot:null,keep:true,sticky:true};
    const r=avatarRect()||{left:24,right:124,top:24,bottom:124,width:100,height:100};
    let left=Math.max(6,r.left+r.width*.2),top=Math.min(innerHeight-FH-6,r.bottom+6),flip=false;
    if(left+FW+BW>innerWidth-6){flip=true;left=Math.max(6,innerWidth-FW-BW-10)}
    say.innerHTML=`<div class="cw-msg">${html}</div><div class="cw-nav"><button type="button" class="cw-next" data-ok>${o.ok||'Thanks, ALITA!'}</button></div>`;
    say.querySelector('[data-ok]').addEventListener('click',e=>{e.stopPropagation();leave()});
    place(left,top,flip);morphIn();fit();
    setTimeout(()=>{try{A&&A.el===el&&say.querySelector('[data-ok]').focus({preventScroll:true})}catch(e){}},1300);
  };
  window.alitaTour=()=>{const b=[...document.querySelectorAll('.chat-why .cw-tag')].find(vis);if(b){open(b);setTimeout(startTour,1300)}};   // for a "help" entry point
})();
