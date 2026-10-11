/* ---------- Technical Documentation (sub menu per group, first group: Ontology) ---------- */
let TECH_GROUPS=null,TECH_SEL=null,GRAPH_STATUS=null;
try{TECH_SEL=localStorage.getItem('tech_doc')}catch(e){}
async function getTechGroups(){
  if(TECH_GROUPS)return TECH_GROUPS;
  if(LIVE){try{const r=await fetch('api/technical-docs').then(r=>r.json());if(r.groups&&r.groups.length)return TECH_GROUPS=r.groups}catch(e){}
    try{GRAPH_STATUS=await fetch('api/graph/status').then(r=>r.json())}catch(e){}}
  return TECH_GROUPS=TECH_FALLBACK;
}
async function renderTechPage(){
  const groups=await getTechGroups(),all=groups.flatMap(g=>g.docs);
  if(!all.length){$('#techPage').innerHTML='<p class="lead">No technical documentation yet.</p>';return}
  if(!all.find(d=>d.id===TECH_SEL))TECH_SEL=all[0].id;
  const idx=all.findIndex(d=>d.id===TECH_SEL),d=all[idx];
  const status=GRAPH_STATUS?(GRAPH_STATUS.available?`Neo4j: ${(GRAPH_STATUS.nodes||[]).reduce((a,n)=>a+n.n,0)} nodes · ${GRAPH_STATUS.ontology_classes||0} ontology classes`:GRAPH_STATUS.enabled===false?'Graph disabled':'Neo4j not reachable'):(LIVE?'':'Demo: graph simulated from the summaries');
  $('#techToc').innerHTML='<h4>Technical documentation</h4>'+groups.map(g=>`<div class="grp">${esc(g.title)}</div>`+g.docs.map((x,i)=>`<a href="#" class="sub ${x.id===TECH_SEL?'on':''}" data-id="${esc(x.id)}">${i+1}. ${esc(x.title)}</a>`).join('')).join('')+
    `<p class="srcnote" style="margin:10px 8px 2px">Source: <code>docs/technical/</code> · app v${APP_VERSION}${status?'<br>'+esc(status):''}</p>`;
  const prev=all[idx-1],next=all[idx+1];
  $('#techPage').innerHTML=mdRender(d.markdown)+`<div class="docnav">${prev?`<button class="mini" data-id="${esc(prev.id)}">← ${esc(prev.title)}</button>`:'<span></span>'}${next?`<button class="mini" data-id="${esc(next.id)}">${esc(next.title)} →</button>`:''}</div>`;
  const go=id=>{TECH_SEL=id;try{localStorage.setItem('tech_doc',id)}catch(e){}renderTechPage();window.scrollTo({top:0})};
  $$('#techToc a').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();go(a.dataset.id)}));
  $$('#techPage .docnav button').forEach(b=>b.addEventListener('click',()=>go(b.dataset.id)));
}

/* ---------- DEO in the demo: the structured summary fields are discourse elements ---------- */
const SUM_DEO={purpose:['Motivation','ProblemStatement'],design_methodology_approach:['Methods'],findings:['Results'],research_limitations_implications:['Discussion','FutureWork'],originality_value:['Contribution']};
const SUM_LABEL={purpose:'Purpose',design_methodology_approach:'Methods',findings:'Findings',research_limitations_implications:'Limitations',originality_value:'Contribution'};
function deoFields(deo){return Object.keys(SUM_DEO).filter(f=>!deo||!deo.length||SUM_DEO[f].some(c=>deo.includes(c)))}
const DEO_Q=[[/\bmethod|methodolog|design|approach|sample|participants|survey|experiment|interview|regression|methode|vorgehen|stichprobe/i,['Methods','Materials']],
  [/result|finding|effect|outcome|evidence|ergebnis|befund/i,['Results']],[/limitation|weakness|bias|caveat|grenze|einschränkung/i,['Discussion']],
  [/implication|interpret|discuss|bedeutung/i,['Discussion']],[/future|next step|outlook|ausblick/i,['FutureWork']],
  [/\bwhy\b|motivat|purpose|goal|aim|problem|research question|warum|ziel|forschungsfrage/i,['Motivation','ProblemStatement']],
  [/contribut|novel|original|beitrag/i,['Contribution']]];
function deoForQuestion(q){const out=[];DEO_Q.forEach(([rx,c])=>{if(rx.test(q))c.forEach(x=>{if(!out.includes(x))out.push(x)})});return out.slice(0,4)}

function graphPlan(q){
  const chips=$$('#graphFilters .chip[aria-pressed="true"]').map(b=>b.textContent.trim().toLowerCase());
  const deo=$('#gDeo').value?[$('#gDeo').value]:deoForQuestion(q);
  const rel=$('#gRel').value;if(rel==='uses_method'&&!deo.includes('Methods'))deo.unshift('Methods');
  const ql=q.toLowerCase(),names=new Set();DOCS.forEach(d=>(d.au||[]).forEach(a=>names.add(a)));
  const persons=chips.includes('person')?[...names].filter(a=>{const last=a.split(/\s+/).pop();return last.length>2&&new RegExp('\\b'+last.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'\\b','i').test(q)}):[];
  const methods=chips.includes('method')?Object.entries(METHOD_LABEL).filter(([id,l])=>l&&ql.includes(String(l).toLowerCase())).map(([id])=>id):[];
  return {deo,persons,methods,databases:[...SEL_DB],clusters:[...CV.sels],year:+$('#gYear').value||null,hops:+$('#gHops').value||2,relation:rel,entity_types:chips};
}
function demoGraphAnswer(q,prior=[]){
  const plan=graphPlan(q),fields=deoFields(plan.deo);
  const pass=d=>d.su&&!d.du&&(!plan.databases.length||(d.db||[]).some(x=>plan.databases.includes(x)))&&(!(plan.clusters||[]).length||plan.clusters.includes(d.ci))&&(!plan.persons.length||(d.au||[]).some(a=>plan.persons.includes(a)))
    &&(!plan.methods.length||(d.me||[]).some(m=>plan.methods.includes(m)))&&(!plan.year||d.y===plan.year)&&fields.some(f=>(d.su[f]||'').trim());
  let query=q;if(prior.length&&q.split(/\s+/).length<=6){const lq=[...prior].reverse().find(t=>t.role==='user');if(lq)query=lq.content+' '+q}
  const qs=[...new Set(demoTokens(query))];
  const ranked=DOCS.filter(pass).map(d=>{const txt=demoTokens([d.ti,...fields.map(f=>d.su[f]||'')].join(' '));let sc=0;qs.forEach(w=>{sc+=txt.filter(x=>x===w).length});return {d,sc}})
    .sort((a,b)=>b.sc-a.sc||(b.d.y||0)-(a.d.y||0)).slice(0,4).filter((x,i)=>x.sc>0||plan.persons.length||plan.methods.length||i<2);
  const path=[];
  if(!ranked.length)return {answer:`The knowledge graph has no ${plan.deo.length?plan.deo.join('/')+' elements':'documents'} for this question with the current selection. Try another discourse element or clear the filters.`,sources:[],path:plan.deo.map(c=>[c,'DEO']),plan,llm:'extractive'};
  const top=ranked[0].d,info=clusterInfo(),f0=fields.find(f=>(top.su[f]||'').trim());
  if(plan.persons.length)path.push([plan.persons[0],'Person'],'authored');else if((top.au||[])[0])path.push([top.au[0],'Person'],'authored');
  path.push([top.ti.length>60?top.ti.slice(0,58)+'…':top.ti,TYPE_LABEL[top.t]||'Document']);
  if(plan.methods.length)path.push('uses_method',[METHOD_LABEL[plan.methods[0]]||plan.methods[0],'Method']);
  if(f0)path.push('contains',[SUM_LABEL[f0],'deo:'+SUM_DEO[f0][0]]);
  if(top.ci!=null)path.push('in_cluster',[(info[top.ci]&&info[top.ci].title)||'C'+top.ci,'Cluster']);
  const sources=ranked.map((x,i)=>{const d=x.d,f=fields.find(k=>(d.su[k]||'').trim());return {n:i+1,doc_id:d.id,title:d.ti,filename:d.fn,url:'#',locator:f?SUM_LABEL[f]+' · deo:'+SUM_DEO[f][0]:null,score:+(0.9-i*0.07).toFixed(2),
    snippet:firstSentence(d.su[f]||'',260),doc_type:d.t,project_name:d.pn,filetype:d.ft,year:d.y,role:d.ro,methods:d.me||[],databases:d.db||[],cluster_id:d.ci,cluster_label:d.cl}});
  const lowFirst=t=>/^[A-Z][a-z]/.test(t)?t[0].toLowerCase()+t.slice(1):t;
  const sent=ranked.slice(0,3).map((x,i)=>{const f=fields.find(k=>(x.d.su[k]||'').trim());return (i?['Along the same path,','Further,'][i-1]+' ':'')+(i?lowFirst(firstSentence(x.d.su[f])):firstSentence(x.d.su[f])).replace(/[.!?]\s*$/,'')+` [${i+1}].`});
  const answer=`Following the graph via ${plan.deo.length?plan.deo.join(' and '):'all discourse elements'}: `+sent.join(' ');
  const docs=ranked.map((x,i)=>({n:i+1,head:`[${i+1}] ${x.d.ti} (${TYPE_LABEL[x.d.t]||x.d.t}; database ${dbNames(x.d.db).join(', ')||'none'}${x.d.y?'; '+x.d.y:''}; authors ${(x.d.au||[]).slice(0,3).join(', ')||'–'})`,
    body:fields.filter(f=>(x.d.su[f]||'').trim()).map(f=>`${SUM_LABEL[f]} (deo:${SUM_DEO[f].join('/deo:')}): ${x.d.su[f]}`).join('\n')}));
  const cited=new Set([...answer.matchAll(/\[(\d+)\]/g)].map(m=>+m[1]));
  return {answer,sources:sources.filter(x=>cited.has(x.n)),allSources:sources,docs,path,plan,llm:'extractive',
    graphContext:`Graph path: ${path.map(x=>typeof x==='string'?x:`${x[0]} [${x[1]}]`).join(' ')}\nDiscourse elements asked for: ${plan.deo.join(', ')||'any'}`};
}

/* ---------- Navigation ---------- */
const PAGES=['chat','docs','graph','release','compliance','tech'];
function placeGraphTile(p){   // the Graph Chat tile moves between the A/B page and the B page
  const tile=$('.tile.t-graph');if(!tile)return;
  if(p==='graph'){if(tile.parentElement!==$('#bTileSlot'))$('#bTileSlot').appendChild(tile)}
  else if(tile.parentElement!==$('#page-chat .tiles'))$('#page-chat .tiles').appendChild(tile);
}
function showPage(p){
  if(!PAGES.includes(p))p='chat';
  if(p!=='graph'&&$('#drawer').classList.contains('docked')&&typeof closeDrawer==='function')closeDrawer();
  if(p==='graph')setTimeout(()=>{if(typeof fitBPage==='function')fitBPage()},0);
  $$('.nav button').forEach(b=>b.setAttribute('aria-selected',b.dataset.page===p));
  PAGES.forEach(x=>{$('#page-'+x).hidden=x!==p});
  if(p==='release')renderReleasePage();
  if(p==='compliance')renderCompliancePage();
  if(p==='tech')renderTechPage();
  if(p==='chat')requestAnimationFrame(renderClusterViz);
  placeGraphTile(p);
  if(p==='graph')requestAnimationFrame(renderClusterPage);
  try{localStorage.setItem('page',p)}catch(e){}
  if(location.hash!=='#'+p)history.replaceState(null,'','#'+p);
}
$$('.nav button').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.page)));
