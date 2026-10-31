/* REQ-70: Guided tour – a step-by-step walk through ALITA along the three mechanisms of the research proposal
   (refresh memory: vertical and horizontal sense-making · make the argument traceable · update schemes), with the
   question "explore or exploit?" as the thread. Each step can switch the page, highlight a part of the interface and
   put an example question into the Graph Chat. Works with the public databases (EU AI Act, Wachter); the step about
   one's own research projects needs the password. Keys: → / Enter next, ← back, Esc close. */
const TOUR={i:0,on:false,box:null,pop:null};

/* clusters of a database (most documents first) – the cluster ids differ per installation */
function tourClusterOf(db){
  const n={};(typeof DOCS!=='undefined'?DOCS:[]).forEach(d=>{if(d.ci!=null&&(d.db||[]).includes(db))n[d.ci]=(n[d.ci]||0)+1});
  const c=Object.entries(n).sort((a,b)=>b[1]-a[1])[0];return c?'C'+c[0]:null;
}
/* research project with the most manuscript versions (for the vertical sense-making step) */
function tourProject(){
  const n={};(typeof DOCS!=='undefined'?DOCS:[]).forEach(d=>{if(d.pn&&d.ro==='manuscript'&&!(d.db||[]).includes('EUAIA'))n[d.pn]=(n[d.pn]||0)+1});
  const p=Object.entries(n).sort((a,b)=>b[1]-a[1])[0];return p&&p[1]>=2?p[0]:null;
}
function tourLaw(){
  const L=(typeof DOCS!=='undefined'?DOCS:[]).filter(d=>d.leg&&d.leg.norm_id==='eu-ai-act');
  return L.find(d=>d.leg.current)||L.sort((a,b)=>(b.leg.seq||0)-(a.leg.seq||0))[0]||null;
}
function tourShow(p){if(typeof showPage==='function'){showPage(p);try{history.replaceState(null,'','#'+(p==='graph'?'b':p))}catch(e){}}}

function tourSteps(){
  const law=$('#cgCompare')&&[...$('#cgCompare').options].find(o=>/EUAIA/.test(o.value)&&/WACHTER/.test(o.value));
  const cw=tourClusterOf('WACHTER'),ca=tourClusterOf('EUAIA'),proj=tourProject();
  const pair=cw&&ca&&cw!==ca?`${cw} and ${ca}`:'the Wachter papers and the EU AI Act';
  return [
    {title:'Explore or exploit? A tour through ALITA',
     text:`Research is usually judged by its final version. The way there – ideas proposed, tested, dropped and recombined across drafts – stays scattered and fades. ALITA turns all project material into an ontology-based knowledge graph so that this <b>trajectory</b> becomes visible and can be questioned.<br><br>The tour follows three mechanisms: <b>1 · refresh memory</b> (within a project and across projects), <b>2 · make the argument traceable</b>, <b>3 · update one's schemes</b>. About ten steps; the example questions use the public databases EU AI Act and Wachter.`},
    {page:'graph',target:'#dbs',title:'What is in the collection',
     text:`Every database is a collection – research projects with all their versions, papers, notes, laws. Public here: <b>EU AI Act</b> (the AI Act in four versions from the 2021 proposal to the consolidated text, Commission guidelines, guidance) and <b>Wachter</b> (two papers on trustworthy AI and the AI Act). With the password, your own research projects appear.`},
    {page:'graph',target:'#cgGraph',title:'Where have we been? The knowledge map',
     text:`Each dot is a document, each coloured group a <b>cluster</b> of related content (found from the document summaries). Versions of the same project lie on a line through time. Click a cluster to see its description and members – the map is the memory that otherwise fades.`},
    {page:'graph',target:'#cgCompare',title:'Horizontal sense-making: across collections',
     run:()=>{if(law&&typeof xcChange==='function'){$('#cgCompare').value=law.value;xcChange(law.value)}},
     text:`Every database is clustered on its own. <b>Compare</b> draws the relations between the clusters of two databases as violet lines with their similarity – here ${law?'EU AI Act ↔ Wachter (selected for you)':'pick two databases'}. This is looking beyond one's own research bubble: which other body of work is close to mine?`},
    {page:'graph',target:'#graphForm',title:'Ask about what the map shows',
     prompt:`Describe the link between ${pair}: where do the papers agree with the law, and where do they criticise it?`,
     text:`Name clusters in a question and the Graph Chat searches exactly them – through the ontology: cluster → document → section (its rhetorical role, or the article of a law) → passage. It adds <b>bridging passages</b>: the most similar paragraphs on both sides of the cluster boundary, as evidence for the line on the map.`},
    {page:'graph',target:'#graphForm',title:'Vertical sense-making: a trajectory over versions',
     prompt:'What changed in Article 4 between the proposal and the consolidated version of the AI Act?',
     text:`The AI Act is a well-documented trajectory: proposal (2021), committee amendments (2023), adopted text (2024), consolidated version (2026). ALITA keeps every version of every article and the change between them, and every answer says <b>which version</b> it refers to. The same temporal model is what we want for research projects: which ideas came, changed or disappeared – and when.`},
    {page:'graph',target:'#graphForm',title:'Traceability: explicit relations, not only similarity',
     prompt:'Which papers discuss Article 31 of the AI Act, and what do they argue?',
     text:`References in the papers ("Art. 33(4) AI Act") are edges in the graph: paper –discusses→ article. Papers cite the version they had in front of them – Laux, Wachter &amp; Mittelstadt cite Art. 33 of the 2021 proposal, which is Art. 31 today; ALITA maps this. Under the answer: the <b>graph path</b> and the numbered <b>sources</b> – every statement can be checked in its passage.`},
    {page:'docs',target:'.lg-disc,#drawer',wait:900,
     run:()=>{const d=tourLaw();if(d&&typeof openDoc==='function')openDoc(d.id)},
     title:'The same relation, seen from the law',
     text:`Document details of a law version list, for each article, the papers that discuss it – in the numbering of that version. <b>Ask</b> next to an article puts the question into the Graph Chat. Every document has such details: summary, methods, versions, citations, and for papers the articles they discuss.`},
    {page:'graph',target:'#graphForm',title:'Updating schemes: let ALITA argue back',
     prompt:'Which assumptions of Laux, Wachter & Mittelstadt are no longer valid under the final text of the AI Act? Quote the passages on both sides.',
     text:`Schemes change when we meet information that contradicts them. Ask ALITA to <b>challenge</b> a position rather than confirm it – and then check its sources: click a number and read the passage. An answer you cannot trace is not evidence. This is also how ALITA counters over-reliance on the language model.`},
    proj&&typeof DB_UNLOCKED!=='undefined'&&DB_UNLOCKED?
      {page:'graph',target:'#graphForm',title:'Your own project: explored or exploited?',
       prompt:`How did the knowledge in project ${proj} evolve over time? Which directions were explored and dropped, and which were pursued until the final version?`,
       text:`For a research project ALITA compares each manuscript version with the previous one (substantive change, rewording, resubmission) and forms <b>knowledge stages</b>; the answer shows them as a table. Follow up with "Which constructs were omitted?" or "What did the reviewers ask for and what changed after it?"`}:
      {target:'#dbPass',title:'Your own projects',
       text:`With the password ALITA shows the research projects behind the public collections: manuscripts in all versions, analyses, reviewer responses. Then ask, for example: <i>"How did the knowledge in this project evolve over time? Which directions were explored and dropped?"</i> – the answer shows the knowledge stages of the project as a table.`},
    {title:'Explore or exploit – with the trajectory in view',
     text:`That was ALITA: the map shows where you have been, the graph makes the argument traceable, and the chat helps you question your own schemes – before deciding whether to <b>exploit</b> the path you are on or <b>explore</b> one you once left.<br><br>Limits: answers come from a language model and can be wrong; the sources are there to check them. Planned: why decisions were taken, who contributed what, and an external challenge ("Window to the outside").`}
  ].filter(Boolean);
}

function tourEl(sel){
  for(const s of String(sel||'').split(',')){const e=s.trim()&&document.querySelector(s.trim());if(e&&e.offsetParent!==null&&e.getBoundingClientRect().width>0)return e}
  return null;
}
function tourPlace(){
  if(!TOUR.on)return;
  const st=TOUR.steps[TOUR.i],el=st&&tourEl(st.target),pop=TOUR.pop,box=TOUR.box,W=innerWidth,H=innerHeight;
  if(el){
    const r=el.getBoundingClientRect(),pad=6;
    Object.assign(box.style,{display:'block',left:(r.left-pad)+'px',top:(r.top-pad)+'px',width:(r.width+2*pad)+'px',height:(r.height+2*pad)+'px'});
    box.classList.remove('center');
    const pw=Math.min(420,W-24),ph=pop.offsetHeight||240;
    let top=r.bottom+14,left=Math.min(Math.max(12,r.left),W-pw-12);
    if(top+ph>H-12)top=r.top-ph-14;
    if(top<12){top=Math.min(Math.max(12,r.top),H-ph-12);left=r.right+14+pw<W?r.right+14:Math.max(12,r.left-pw-14)}
    Object.assign(pop.style,{left:left+'px',top:Math.max(12,top)+'px',width:pw+'px',transform:'none'});
  }else{
    Object.assign(box.style,{display:'block',left:'0',top:'0',width:'0',height:'0'});box.classList.add('center');
    Object.assign(pop.style,{left:'50%',top:'50%',width:Math.min(520,W-24)+'px',transform:'translate(-50%,-50%)'});
  }
}
function tourPut(prompt,send){
  const inp=$('#graphInput');if(!inp)return;
  if($('#page-graph')&&$('#page-graph').hidden)tourShow('graph');
  inp.value=prompt;inp.dispatchEvent(new Event('input'));inp.focus();
  if(send){const f=$('#graphForm');if(f&&f.requestSubmit)f.requestSubmit()}
}
function tourGo(i){
  const S=TOUR.steps;TOUR.i=Math.max(0,Math.min(S.length-1,i));const st=S[TOUR.i];
  if(st.page)tourShow(st.page);
  try{st.run&&st.run()}catch(e){}
  const key=!!(($('#apiKey')||{}).value||'').trim()||(typeof hasKey==='function'&&hasKey());
  TOUR.pop.innerHTML=`<div class="tour-head"><span class="tour-n">${TOUR.i+1} / ${S.length}</span><b>${st.title}</b><button type="button" class="tour-x" data-t="close" aria-label="Close the tour">✕</button></div>
    <div class="tour-text">${st.text}</div>
    ${st.prompt?`<div class="tour-q"><span class="lbl">Try this question</span><div>${esc(st.prompt)}</div>
      <div class="tour-qa"><button type="button" class="mini" data-t="put">Put into Graph Chat</button><button type="button" class="mini tour-ask" data-t="ask"${key?'':' title="Enter your OpenRouter key at the top first"'}>Ask now</button></div></div>`:''}
    <div class="tour-nav"><div class="tour-dots">${S.map((_,k)=>`<i class="${k===TOUR.i?'on':''}"></i>`).join('')}</div>
      <button type="button" class="btn" data-t="prev"${TOUR.i?'':' disabled'}>Back</button>
      <button type="button" class="btn tour-next" data-t="next">${TOUR.i===S.length-1?'Finish':'Next'}</button></div>`;
  TOUR.pop.querySelectorAll('[data-t]').forEach(b=>b.addEventListener('click',()=>{
    const t=b.dataset.t;
    if(t==='close')tourEnd();else if(t==='prev')tourGo(TOUR.i-1);
    else if(t==='next'){if(TOUR.i===S.length-1)tourEnd();else tourGo(TOUR.i+1)}
    else if(t==='put'){tourPut(st.prompt,false);tourPlace()}
    else if(t==='ask'){tourPut(st.prompt,true);tourPlace()}
  }));
  requestAnimationFrame(tourPlace);setTimeout(tourPlace,st.wait||350);if(st.wait)setTimeout(tourPlace,st.wait+600);
  const nx=TOUR.pop.querySelector('.tour-next');if(nx)nx.focus({preventScroll:true});
}
function tourKey(e){
  if(!TOUR.on)return;
  if(e.key==='Escape'){e.preventDefault();tourEnd()}
  else if((e.key==='ArrowRight')&&!/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName||'')){e.preventDefault();TOUR.i<TOUR.steps.length-1?tourGo(TOUR.i+1):tourEnd()}
  else if(e.key==='ArrowLeft'&&!/INPUT|TEXTAREA|SELECT/.test((e.target||{}).tagName||'')){e.preventDefault();tourGo(TOUR.i-1)}
}
function tourStart(){
  if(TOUR.on)tourEnd();
  TOUR.steps=tourSteps();TOUR.on=true;
  TOUR.box=document.createElement('div');TOUR.box.className='tour-spot';
  TOUR.pop=document.createElement('section');TOUR.pop.className='tour-pop';TOUR.pop.setAttribute('role','dialog');TOUR.pop.setAttribute('aria-label','Guided tour');
  document.body.append(TOUR.box,TOUR.pop);
  addEventListener('resize',tourPlace);addEventListener('scroll',tourPlace,true);addEventListener('keydown',tourKey);
  tourGo(0);
}
function tourEnd(){
  TOUR.on=false;[TOUR.box,TOUR.pop].forEach(e=>e&&e.remove());TOUR.box=TOUR.pop=null;
  removeEventListener('resize',tourPlace);removeEventListener('scroll',tourPlace,true);removeEventListener('keydown',tourKey);
  try{localStorage.setItem('tour_seen','1')}catch(e){}
}
(function(){
  if(document.documentElement.classList.contains('map-window'))return;
  const b=$('#tourBtn');if(b)b.addEventListener('click',tourStart);
  if(/[?&]tour=1\b/.test(location.search))setTimeout(tourStart,1200);
})();
