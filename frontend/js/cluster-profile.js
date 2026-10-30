/* ---------- Cluster profile on hover: key insights, analyses, theories (v1.4.0) ----------
   Live: /api/clusters (LLM statements from clustering + heuristics over the structured summaries, backend/app/cluster_profile.py).
   Demo: the same heuristics here over the summaries in the page. */
let CL_API=null;
async function loadClusterProfiles(){if(!LIVE)return;try{CL_API=await fetch('api/clusters').then(r=>r.ok?r.json():null)}catch(e){CL_API=null}}
const CP_AN=[[/pls[- ]?sem|smart ?pls|partial least squares/,'PLS-SEM'],[/structural equation|\bsem\b|strukturgleichung/,'Structural equation modeling'],[/multi-?level|hierarchical linear|mehrebenen/,'Multilevel analysis'],[/regression/,'Regression analysis'],[/(confirmatory|exploratory) factor|factor analysis|faktorenanalyse/,'Factor analysis'],[/\banova\b|\bmanova\b|varianzanalyse|t-test/,'ANOVA / t-tests'],[/meta-?analys/,'Meta-analysis'],[/systematic (literature )?review|literature review|literaturanalyse|semi-systematic/,'Literature review'],[/vignette/,'Vignette study'],[/experiment/,'Experiment'],[/survey|questionnaire|fragebogen|umfrage/,'Survey'],[/interview/,'Interviews'],[/focus group|fokusgruppe/,'Focus groups'],[/case stud|fallstudie/,'Case study'],[/delphi/,'Delphi study'],[/grounded theory/,'Grounded theory'],[/thematic analysis|qualitative content analysis|inhaltsanalyse|coding/,'Qualitative content analysis'],[/eye[- ]?tracking/,'Eye tracking'],[/simulation|system dynamics model/,'Simulation'],[/process mining|event log/,'Process mining'],[/design science/,'Design science'],[/action research|aktionsforschung/,'Action research'],[/mixed[- ]method/,'Mixed methods'],[/field study|feldstudie/,'Field study'],[/text mining|topic model|clustering|embedding/,'Text mining / clustering'],[/conceptual|konzeptionell/,'Conceptual analysis']];
const CP_TH=[[/signal(l)?ing theory|signaling perspective/,'Signaling theory'],[/status quo bias/,'Status quo bias'],[/technology acceptance model|\btam\b/,'Technology acceptance model'],[/\butaut\b|unified theory of acceptance/,'UTAUT'],[/diffusion of innovation/,'Diffusion of innovations'],[/cognitive load/,'Cognitive load theory'],[/cognitive fit/,'Cognitive fit theory'],[/need for (cognitive )?closure/,'Need for closure'],[/mental models?|shared mental model|team mental model/,'Mental models'],[/system dynamics|stock[- ]and[- ]flow|stock-flow/,'System dynamics'],[/organi[sz]ational learning/,'Organizational learning'],[/knowledge management|wissensmanagement/,'Knowledge management'],[/job characteristics model|hackman/,'Job characteristics model'],[/job demands[- ]resources/,'Job demands-resources model'],[/self-determination/,'Self-determination theory'],[/(procedural|organi[sz]ational) justice|justice theory/,'Organizational justice'],[/instrumental-symbolic/,'Instrumental-symbolic framework'],[/ability,? benevolence,? (and )?integrity|trust factors|integrative model of (organizational )?trust/,'Trust model (ability, benevolence, integrity)'],[/anthropomorphi/,'Anthropomorphism'],[/socio-?technical/,'Sociotechnical systems'],[/institutional theory/,'Institutional theory'],[/resource-based view/,'Resource-based view'],[/dynamic capabilit/,'Dynamic capabilities'],[/lean (management|production|principles)|\blean\b/,'Lean management'],[/\bagile\b|agilit/,'Agile'],[/theory of planned behavio/,'Theory of planned behavior'],[/affective events/,'Affective events theory'],[/emotion/,'Emotion theories'],[/routine/,'Organizational routines'],[/stakeholder theory/,'Stakeholder theory'],[/legitimacy/,'Legitimacy theory'],[/sustainab|nachhaltig/,'Sustainability management'],[/gamification/,'Gamification'],[/bounded rationality|heuristics and biases/,'Bounded rationality']];
function cpFirst(t,n=170){t=String(t||'').replace(/\s+/g,' ').trim();const m=t.match(/^(.+?[.!?])(\s|$)/);const s=m?m[1]:t;return s.length<=n?s:s.slice(0,n-1).replace(/\s+\S*$/,'')+'…'}
function clusterProfileLocal(ci){
  const mem=cvUnits().filter(u=>u.ci===ci&&u.on).map(u=>{if(u.t==='research_project'){const p=PROJECTS.find(x=>x.name===u.pn)||{};return {...u,su:p.summary||p.su||{},me:p.methods||[]}}return u});
  const an={},th={},inc=(o,k)=>o[k]=(o[k]||0)+1;
  mem.forEach(d=>{const su=d.su||{},txt=['purpose','design_methodology_approach','findings','research_limitations_implications','originality_value'].map(k=>su[k]||'').join(' ');
    const low=txt.toLowerCase(),des=(su.design_methodology_approach||'').toLowerCase()||low;
    const f=new Set(CP_AN.filter(([re])=>re.test(des)).map(x=>x[1]));(d.me||[]).forEach(m=>f.add(Array.isArray(m)?(m[1]||m[0]):(METHOD_LABEL[m]||String(m).replace(/_/g,' '))));f.forEach(k=>inc(an,k));
    const t=new Set(CP_TH.filter(([re])=>re.test(low)).map(x=>x[1]));
    (txt.match(/\b[A-Z][\w-]+(?:[ -][A-Za-z][\w-]+){0,2}\s+(?:theory|Theorie)\b/g)||[]).forEach(m=>{if(!/^(The|A|An|This|Our|Grounded|New)\b/.test(m))t.add(m.replace(/\s+Theorie$/,' theory'))});t.forEach(k=>inc(th,k))});
  const top=o=>Object.entries(o).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([name,n])=>({name,n}));
  const seen=new Set(),typical=mem.filter(d=>d.su&&d.su.findings).sort((a,b)=>(b.cs||0)-(a.cs||0)).filter(d=>{const k=cpFirst(d.su.findings);if(seen.has(k))return false;seen.add(k);return true}).slice(0,3);
  const ys=mem.map(d=>d.y).filter(Boolean);
  return {analyses:top(an),theories:top(th),insights:typical.map(d=>({text:cpFirst(d.su.findings),title:d.ti,doc_id:d.id})),documents:mem.length,years:ys.length?[Math.min(...ys),Math.max(...ys)]:null,source:'summaries'};
}
function clusterProfile(ci){
  if(LIVE&&CL_API){const c=(CL_API.clusters||[]).find(x=>x.cluster_id===ci);if(c&&c.profile)return {...c.profile,scope:'all databases'}}
  return clusterProfileLocal(ci);
}
/* Connected clusters: clusters that documents of this cluster are second-closest to (bridges), strongest first */
function cpConnHtml(ci){
  const units=cvUnits(),cls=cvClusters(units),info=clusterInfo()||{};
  const nb=cvLinks(units).filter(l=>l.a===ci||l.b===ci).map(l=>({o:l.a===ci?l.b:l.a,n:l.n,s:l.s})).sort((x,y)=>y.n-x.n||y.s-x.s);
  if(!nb.length)return '<h6>Connected clusters</h6><div class="cp-none">no bridges to other clusters</div>';
  return `<h6>Connected clusters</h6><div class="cp-conn">${nb.map(x=>{const c=cls.find(k=>k.id===x.o)||{id:x.o,label:''};
    return `<button type="button" data-cc="${x.o}" style="--h:${cvHue(x.o)}" aria-pressed="${typeof cvHas==='function'&&cvHas(x.o)}" title="${x.n} document${x.n>1?'s':''} of C${ci} are second-closest to C${x.o} · average similarity ${x.s.toFixed(2)} – click to select C${x.o} as well"><b>C${x.o}</b><span>${esc(cvName(c,info))}</span><small>${x.n} · ${x.s.toFixed(2)}</small></button>`}).join('')}</div>`;
}
/* REQ-09: the elements of a cluster/project – a collapsible list of its documents; a click opens the document (top right on the B page) */
const CP_TYPE_MARK={research_paper:'■',research_notes:'●',research_project:'◆',legal_project:'▲',legal_guideline:'▲',standard:'▲',guidance:'▲'};
function cpDocListHtml(list,label,open){
  if(!list.length)return '';
  const role=u=>u.ro&&typeof ROLE_LABEL!=='undefined'&&ROLE_LABEL[u.ro]?ROLE_LABEL[u.ro]:'';
  const rows=[...list].sort((a,b)=>(b.y||0)-(a.y||0)||String(a.ti||'').localeCompare(String(b.ti||''))).map(u=>
    `<li><button type="button" ${u.id?`data-doc="${esc(u.id)}"`:''} title="${esc((u.rp||u.ti||'')+(u.id?' – click to open':''))}"><i class="m-${esc(u.t||'')}">${CP_TYPE_MARK[u.t]||'•'}</i><span>${esc(u.ti||u.fn||'(untitled)')}</span><small>${[CV_TYPE[u.t]||'',role(u),u.y||'',u.pn&&label!=='project'?u.pn:''].filter(Boolean).map(esc).join(' · ')}</small></button></li>`).join('');
  return `<details class="cp-docs"${open?' open':''}><summary><h6>Documents (${list.length})</h6></summary><ul>${rows}</ul></details>`;
}
function cpWireDocs(root){root.querySelectorAll('[data-doc]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();if(typeof openDoc==='function')openDoc(b.dataset.doc)}))}
function cpWireConn(root){cpWireDocs(root);root.querySelectorAll('[data-cc]').forEach(b=>b.addEventListener('click',()=>{const id=+b.dataset.cc;
  if(!$('#page-graph').hidden&&typeof cgPick==='function')cgPick(id);else cvSelect(id);
  // 3D · time view: the description below must follow the click – show the connected cluster and keep it there
  const d=cpS3();if(d&&root===d){d.dataset.pin=String(id);cpS3Render(d,id)}}))}
function clusterCardHtml(ci){
  const p=clusterProfile(ci),info=(clusterInfo()||{})[ci]||{},label=(cvClusters(cvUnits()).find(c=>c.id===ci)||{}).label||'';
  const chips=a=>a.length?`<div class="cp-chips">${a.map(x=>`<span>${esc(x.name)}${x.n>1?` <i>×${x.n}</i>`:''}</span>`).join('')}</div>`:'<div class="cp-none">none named in the summaries</div>';
  return `<div class="cp-h" style="--h:${cvHue(ci)}"><b>C${ci}</b><span>${esc(cvName({id:ci,label},clusterInfo()))}</span></div>`+
    (info.description?`<p class="cp-d">${esc(dbRelabel(info.description))}</p>`:'')+
    `<h6>Key insights</h6>`+(p.insights&&p.insights.length?`<ul>${p.insights.map(x=>`<li>${esc(dbRelabel(x.text))}${x.title?` <i>— ${esc(x.title)}</i>`:''}</li>`).join('')}</ul>`:'<div class="cp-none">no findings in the summaries yet</div>')+
    `<h6>Analyses used</h6>${chips(p.analyses||[])}<h6>Theories &amp; frameworks</h6>${chips(p.theories||[])}`+cpConnHtml(ci)+cpDocListHtml(cvUnits().filter(u=>u.ci===ci&&u.on),'cluster')+
    `<div class="cp-f">${p.documents||0} documents${p.years?` · ${p.years[0]===p.years[1]?p.years[0]:p.years[0]+'–'+p.years[1]}`:''}${p.scope?' · '+esc(dbRelabel(p.scope)):SEL_DB.length?' · '+dbNames(SEL_DB).join(' + '):''} · from ${p.source==='llm+summaries'?'language model + summaries':'the structured summaries'}</div>`;
}
/* Cluster descriptions in a panel BELOW the views, driven by the cluster selection:
   nothing selected = no panel · each selected cluster = one description, side by side.
   In the 3D·time view (no selection there) the panel at the bottom follows hover; a click keeps it. */
let CP_HOV=null,CP_SIG='';
function cpRenderSel(){
  try{syncScope()}catch(e){}
  const dc=$('#dbClear');if(dc&&typeof CV!=='undefined')dc.hidden=!SEL_DB.length&&!CV.sels.size;
  const ids=(typeof CV!=='undefined'&&CV.sels)?[...CV.sels].sort((a,b)=>a-b):[];
  const sig=ids.join(',')+'|'+(typeof SEL_DB!=='undefined'?SEL_DB.join(','):'')+'|'+(CL_API?1:0);
  ['#cvDock','#cgDock'].forEach(sel=>{const d=$(sel);if(!d)return;
    if(!ids.length){d.hidden=true;d.innerHTML='';d.dataset.sig='';return}
    if(d.dataset.sig===sig&&!d.hidden)return;d.dataset.sig=sig;
    d.innerHTML=`<div class="cpd-bar"><span>Cluster description${ids.length>1?'s':''}</span><span class="cpd-state">${ids.map(c=>'C'+c).join(', ')} selected · click a cluster to add or remove it</span><button type="button" class="cpd-x cpd-clear" title="Deselect all clusters">✕ Clear cluster selection</button></div>`+
      `<div class="cpd-grid${ids.length>1?' multi':''}">${ids.map(ci=>`<div class="cprof cprof-docked">${clusterCardHtml(ci)}</div>`).join('')}</div>`;
    d.hidden=false;d.querySelector('.cpd-x').addEventListener('click',()=>cvClear());cpWireConn(d);
  });
}
function cpS3Render(dock,ci){
  const pin=dock.dataset.pin===String(ci);
  dock.innerHTML=`<div class="cpd-bar"><span>Cluster description</span><span class="cpd-state">${pin?'kept open · click the cluster again or ✕ to release':'hover a cluster to preview · click it to keep it here'}</span><button type="button" class="cpd-x" aria-label="Close the cluster description">✕</button></div><div class="cprof cprof-docked">${clusterCardHtml(ci)}</div>`;
  dock.dataset.c=ci;dock.classList.toggle('pinned',pin);dock.hidden=false;cpWireConn(dock);
  dock.querySelector('.cpd-x').addEventListener('click',()=>{delete dock.dataset.pin;dock.dataset.c='';dock.hidden=true;dock.classList.remove('pinned')});
}
const cpS3=()=>(typeof S3!=='undefined'&&S3.open)?$('#s3Dock'):null;
function showProfile(ci,ev){CP_HOV=ci;const d=cpS3();if(!d||d.dataset.pin)return;if(d.dataset.c!==String(ci)||d.hidden)cpS3Render(d,ci)}
function hideProfile(){CP_HOV=null}
document.addEventListener('click',ev=>{
  const d=cpS3();if(!d||d.contains(ev.target))return;
  const hit=ev.target.closest&&ev.target.closest('#s3Canvas');if(!hit)return;
  if((S3.lastMoved||0)>=5)return;                                                   // end of a rotate drag, not a click
  const ci=typeof S3.clusterAt==='function'?S3.clusterAt(ev.clientX,ev.clientY):CP_HOV;   // the cluster under the pointer now
  if(ci==null)return;
  if(d.dataset.pin===String(ci))delete d.dataset.pin;else d.dataset.pin=String(ci);cpS3Render(d,ci);
},true);
document.addEventListener('keydown',ev=>{const d=cpS3();if(ev.key==='Escape'&&d&&d.dataset.pin){delete d.dataset.pin;cpS3Render(d,+d.dataset.c)}});
function wireProfileHover(sel){$$(sel).forEach(b=>{if(b._cp)return;b._cp=1;b.addEventListener('mousemove',ev=>showProfile(+b.dataset.c,ev));b.addEventListener('mouseleave',hideProfile)})}
