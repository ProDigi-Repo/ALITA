/* ---------- Question meta: intent + entities ---------- */
const INTENT_LABEL={progress:'Knowledge progress',find_sources:'Find sources',summarize:'Summarize',explain:'Explain',compare:'Compare',methodology:'Methodology',findings:'Findings',limitations:'Limitations',authorship:'People & authorship',timeline:'Timeline',overview:'Overview',question:'Question'};
const INTENT_RULES=[['progress',/(erkenntnis(stand|fortschritt|stufe)|knowledge (stage|progress|state)|im zeitverlauf|over time|entwickelt|weiterentwick|evolv|evolution|progress|versionshistorie|version history|stufen|stages|(wie|how)\b.{0,40}\banaly\w*\b.{0,30}(durchgeführt|gemacht|conducted|performed|done|carried out))/],['compare',/\b(compare|comparison|differ|difference|versus|vs\.?|vergleich|unterschied)/],['limitations',/\b(limitation|weakness|shortcoming|limitationen|grenzen|einschränk)/],
  ['methodology',/\b(method|methodology|design|approach|sample|data ?set|measure|methode|vorgehen|stichprobe|erhebung)/],['findings',/\b(finding|result|outcome|effect|impact|ergebnis|befund|wirkung)/],
  ['authorship',/\b(who|author|wrote|written by|team|wer|autor)/],['timeline',/\b(when|timeline|since|history|wann|zeitlich|chronolog)/],
  ['find_sources',/\b(source|paper|literature|reference|cite|find|search|quelle|literatur|finde|suche)/],['summarize',/\b(summar|tl;?dr|overview of|key points|zusammenfass|kurzfassung)/],
  ['overview',/\b(list|which|all|overview|landscape|welche|liste|übersicht)/],['explain',/\b(what is|what are|explain|define|definition|why|how does|was ist|erkläre|warum|wie funktioniert)/]];
const ENT_LABEL={database:'Database',project:'Project',person:'Person',method:'Method',year:'Year',document:'Document',topic:'Topic',cluster:'Cluster'};
function reEsc(x){return x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}
function analyzeQuery(q,filters){
  const low=q.toLowerCase();
  const intent=(INTENT_RULES.find(([,re])=>re.test(low))||['question'])[0];
  const ents=[],seen=new Set();const add=(type,value)=>{const k=type+'|'+String(value).toLowerCase();if(!seen.has(k)){seen.add(k);ents.push({type,value:String(value)})}};
  const persons=new Set();DOCS.forEach(d=>(d.au||[]).forEach(a=>{persons.add(a);persons.add(a.split(' ').pop())}));
  const vocab={database:DATABASES,project:[...new Set(DOCS.map(d=>d.pn).filter(Boolean))],person:[...persons],method:Object.values(METHOD_LABEL)};
  for(const [t,vals] of Object.entries(vocab))for(const v of vals){if(v&&v.length>2&&new RegExp('(^|[^\\w])'+reEsc(v.toLowerCase())+'($|[^\\w])').test(low))add(t,v)}
  (q.match(/(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)/g)||[]).forEach(y=>add('year',y));
  (q.match(/["“„']([^"”“']{3,80})["”“']/g)||[]).forEach(m=>add('document',m.slice(1,-1)));
  if(filters){(filters.database||[]).forEach(d=>add('database',dbName(d)));(filters.project||[]).forEach(p=>add('project',p));(filters.cluster||[]).forEach(c=>add('cluster','C'+c))}
  (q.match(/\b[A-Z][A-Za-z]*[A-Z][A-Za-z]*(?:\s+[A-Z][\w-]+)*\b/g)||[]).forEach(m=>{if(!ents.some(e=>e.value.toLowerCase()===m.toLowerCase()))add('topic',m)});
  return {intent,entities:ents};
}
function metaHtml(meta){
  if(!meta)return '';
  return `<span class="qintent" title="Intention">${esc(INTENT_LABEL[meta.intent]||meta.intent)}</span>`+(meta.entities||[]).map(e=>`<span class="qent" title="${esc(ENT_LABEL[e.type]||e.type)}"><i>${esc(ENT_LABEL[e.type]||e.type)}</i>${esc(e.value)}</span>`).join('');
}
function setTurnMeta(tile,el,meta){
  const sess=HIST[tile].find(x=>x.id===CUR[tile]);if(!sess)return;
  const t=[...sess.turns].reverse().find(t=>t.role==='user');if(t){t.meta=meta;saveHist()}
  if(el){const m=el.querySelector('.qmeta');if(m)m.innerHTML=metaHtml(meta)}
}
function typing(chat){AV.busy(true);const d=document.createElement('div');d.remove=function(){Element.prototype.remove.call(this);AV.busy(false)};d.className='msg bot';d.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d}
function errMsg(chat,text){const d=document.createElement('div');d.className='msg bot err';d.innerHTML=`<div class="bubble">${esc(text)}</div>`;chat.appendChild(d);chat.scrollTop=chat.scrollHeight}
function mdLite(s){return esc(s).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').split(/\n{2,}/).map(p=>`<p>${p.replace(/\n/g,'<br>')}</p>`).join('')}

/* Cost of a chat turn: the question (input incl. retrieved context, query rewrite and embedding) and the answer (output) */
function costHtml(u,part){
  if(!u||u.tokens==null)return '';
  const n=v=>Math.round(v||0).toLocaleString('en'),est=u.price_source&&u.price_source!=='openrouter'?' · estimated prices':'';
  const tip=`Question: ${n(u.question_tokens)} tokens (${n(u.chat_input)} input incl. sources and context${u.embedding?`, ${n(u.embedding)} embedding`:''}) = ${fmtEur(u.question_eur)}\nAnswer: ${n(u.answer_tokens)} tokens = ${fmtEur(u.answer_eur)}\nTogether: ${fmtEur(u.eur)} (≈ $${(+u.usd||0).toFixed(4)})${est}`;
  if(part==='question')return `<span class="cost cost-q" title="${esc(tip)}">💶 question ${fmtEur(u.question_eur)} <small>${n(u.question_tokens)} tokens</small></span>`;
  return `<span class="cost cost-a" title="${esc(tip)}">💶 answer ${fmtEur(u.answer_eur)} <small>${n(u.answer_tokens)} tokens · turn ${fmtEur(u.eur)}</small></span>`;
}
function botMsg(chat,a){
  const id='m'+(++uid);
  const text=mdLite(a.answer).replace(/\[(\d+)\]/g,(m,n)=>`<sup class="cite" data-t="${id}-${n}">[${n}]</sup>`);
  const pathHtml=a.path?`<div class="path"><span class="lbl">Graph path</span>${a.path.map(p=>Array.isArray(p)?`<span class="node">${esc(p[0])}<i>${esc(p[1])}</i></span>`:`<span class="edge">—${esc(p)}→</span>`).join('')}</div>`:'';
  const srcHtml=a.sources.map(s=>{
    const tags=[TYPE_LABEL[s.doc_type]||s.doc_type,s.project_name,s.filetype&&'.'+s.filetype,s.legal?null:s.year,ROLE_LABEL[s.role]||s.role,s.legal&&typeof legalSrcTag==='function'?legalSrcTag(s.legal):s.locator,...(s.methods||[]).map(m=>METHOD_LABEL[m]||m)].filter(Boolean);
    const href=LIVE?s.url.replace(/^\//,''):'#';
    return `<details class="src" id="${id}-${s.n}"><summary><span class="n">[${s.n}]</span><span class="stt"><a href="${esc(href)}" ${LIVE?'target="_blank" rel="noopener"':'data-demo="1"'}>${esc(s.title)}</a><span class="sub">${esc([TYPE_LABEL[s.doc_type]||s.doc_type,s.project_name,s.year,s.locator].filter(Boolean).join(' · '))}</span></span><span class="score">${(+s.score).toFixed(2)}</span><span class="chev" aria-hidden="true">▸</span></summary><div class="sbody"><div class="tags">${tags.map(t=>`<span>${esc(t)}</span>`).join('')}</div><p class="snip">${esc(s.snippet)}</p></div></details>`}).join('');
  const d=document.createElement('div');d.className='msg bot';
  d.innerHTML=`<div class="bubble">${text}</div>${a.progress&&typeof progressBlockHtml==='function'?progressBlockHtml(a.progress):''}${a.temporal&&typeof legalBlockHtml==='function'?legalBlockHtml(a):''}${pathHtml}
   ${a.sources.length?`<details class="sources"><summary><span class="chev" aria-hidden="true">▸</span><b>${a.sources.length} source${a.sources.length>1?'s':''} used</b><span class="srctoggle"></span><span class="sfilter">Filter: ${esc(filterSummary(a.applied_filters||{}))}</span><span class="speek">${a.sources.map(x=>`[${x.n}] ${esc(x.title)}`).join(' · ')}</span></summary><div class="sbar"><button type="button" class="mini" data-sall="1">Expand all</button><button type="button" class="mini" data-sall="0">Collapse all</button></div>${srcHtml}</details>`:''}
   <div class="actions"><button class="mini" data-copy>Copy</button><span class="meta-line" style="align-self:center">${esc(a.model||CHAT_MODEL_ID)}${LIVE?'':a.llm==='claude-sample'?' · demo without backend (GPT-6 Luna needs the backend)':a.llm==='extractive'?' · extractive demo answer':' · sample answer'}${a.truncated?' · cut short':''}${a.memory_turns!=null?` · <span class="memchip" title="${esc(a.retrieval_query&&a.retrieval_query!==a.question?'Search query with conversation context: '+a.retrieval_query:'Earlier turns sent with this question')}">memory: ${a.memory_turns?a.memory_turns+' earlier turn'+(a.memory_turns>1?'s':''):'none'}</span>`:''}</span></div>`;
  chat.appendChild(d);chat.scrollTop=chat.scrollHeight;
  if(a.usage){   // cost of the question (on the user's message) and of the answer (here)
    const ac=d.querySelector('.actions');if(ac)ac.insertAdjacentHTML('beforeend',costHtml(a.usage,'answer'));
    let q=d.previousElementSibling;while(q&&!q.classList.contains('user'))q=q.previousElementSibling;
    if(q&&!q.querySelector('.cost'))(q.querySelector('.bubble')||q).insertAdjacentHTML('afterend',`<div class="cost-row">${costHtml(a.usage,'question')}</div>`);
  }
  d.querySelectorAll('.cite').forEach(c=>c.addEventListener('click',()=>{
    const el=document.getElementById(c.dataset.t);if(!el)return;d.querySelector('details.sources').open=true;el.open=true;
    el.scrollIntoView({block:'nearest',behavior:'smooth'});el.classList.add('flash');setTimeout(()=>el.classList.remove('flash'),1200);
  }));
  d.querySelectorAll('[data-sall]').forEach(b=>b.addEventListener('click',()=>d.querySelectorAll('details.src').forEach(x=>x.open=b.dataset.sall==='1')));
  d.querySelectorAll('a[data-demo]').forEach(l=>l.addEventListener('click',e=>{e.preventDefault();toast('Opening sources requires the running backend')}));
  d.querySelector('[data-copy]').addEventListener('click',()=>{
    const plain=d.querySelector('.bubble').innerText+'\n\nSources:\n'+a.sources.map(s=>`[${s.n}] ${s.title} – ${s.project_name?s.project_name+' / ':''}${s.filename||''}`).join('\n');
    navigator.clipboard?.writeText(plain).then(()=>toast('Answer copied with sources'),()=>toast('Copying not available'));
  });
}

/* Demo answers built from the sample project's real metadata */
/* Demo retrieval: keyword search (BM25) over ALL documents of ALL databases, using title, structured
   summary and keywords; the database selection narrows it, no selection = every database. */
const DEMO_STOP=new Set('the a an and or of in on for to with by from at as is are was were be been this that these those it its into about which what who how why when where do does did can could should would will may might there their them they we you our your i me my more most less than not no yes also any all each other such use used using based between both one two three study paper research data results result approach article notes note project der die das und oder nicht mit ist für auf den dem des ein eine zu von im in als auch wie bei sich sind wird werden kann über durch nach aus'.split(' '));
function demoTokens(t){return (String(t||'').toLowerCase().match(/[a-zäöüß0-9][a-zäöüß0-9-]{2,}/g)||[]).filter(w=>!DEMO_STOP.has(w))}
let DEMO_IDX=null;
function demoIndex(){
  if(DEMO_IDX&&DEMO_IDX.n===DOCS.length)return DEMO_IDX;
  const items=DOCS.filter(d=>d.su&&Object.values(d.su).some(v=>typeof v==='string'&&v.trim())&&!d.du).map(d=>{
    const su=d.su||{},text=[d.ti,d.ti,su.purpose,su.design_methodology_approach,su.findings,su.research_limitations_implications,su.originality_value,(d.kw||[]).join(' '),(d.me||[]).map(m=>METHOD_LABEL[m]||m).join(' ')].join(' ');
    const tf={};demoTokens(text).forEach(w=>tf[w]=(tf[w]||0)+1);return {d,tf,len:Object.values(tf).reduce((a,b)=>a+b,0)};
  });
  const df={};items.forEach(it=>Object.keys(it.tf).forEach(w=>df[w]=(df[w]||0)+1));
  const avg=items.reduce((a,it)=>a+it.len,0)/Math.max(1,items.length);
  return DEMO_IDX={n:DOCS.length,items,df,avg};
}
function demoPass(d,f){
  if(f.database&&f.database.length&&!(d.db||[]).some(x=>f.database.includes(x)))return false;
  if(f.doc_type&&f.doc_type.length&&!f.doc_type.includes(d.t))return false;
  if(f.filetype&&f.filetype.length&&!f.filetype.includes(d.ft))return false;
  if(f.method&&f.method.length&&!(d.me||[]).some(m=>f.method.includes(m)))return false;
  if(f.cluster&&f.cluster.length&&!f.cluster.includes(d.ci))return false;
  if(f.project&&f.project.length&&!f.project.includes(d.pn))return false;
  if(f.person&&f.person.length&&!personDocIds(f.person).has(d.id))return false;
  if(f.year_from&&(d.y||0)<f.year_from)return false;
  if(f.year_to&&(d.y||9999)>f.year_to)return false;
  if(f.latest_only&&d.la===false)return false;
  if(f.deo&&f.deo.length&&!deoFields(f.deo).some(k=>((d.su||{})[k]||'').trim()))return false;
  return true;
}
function demoSearch(q,f,k){
  const I=demoIndex(),qs=[...new Set(demoTokens(q))],N=I.items.length;
  const scored=I.items.filter(it=>demoPass(it.d,f)).map(it=>{
    let sc=0;qs.forEach(w=>{const tf=it.tf[w]||0;if(!tf)return;const idf=Math.log(1+(N-I.df[w]+.5)/(I.df[w]+.5));sc+=idf*tf*2.2/(tf+1.2*(.25+.75*it.len/I.avg))});
    return {d:it.d,sc};
  }).filter(x=>x.sc>0).sort((a,b)=>b.sc-a.sc);
  const out=[],perProj={};
  for(const x of scored){const pk=x.d.t==='research_project'?x.d.pn:null;if(pk&&(perProj[pk]||0)>=2)continue;if(pk)perProj[pk]=(perProj[pk]||0)+1;out.push(x);if(out.length>=k)break}
  return {hits:out,pool:I.items.filter(it=>demoPass(it.d,f)).length};
}
function firstSentence(t,max=240){t=String(t||'').trim();const m=t.match(/^.+?[.!?](\s|$)/);t=(m?m[0]:t).trim();return t.length>max?t.slice(0,max).replace(/\s\S*$/,'')+' …':t}
function demoAnswer(q,filters,prior=[]){
  const f=filters||{},scope=f.database&&f.database.length?dbNames(f.database).join(' + '):'all databases';
  let query=q;
  if(prior.length&&(q.split(/\s+/).length<=6||/\b(that|this|these|those|it|they|them|their|why|dazu|das|diese|und)\b/i.test(q))){const lastQ=[...prior].reverse().find(t=>t.role==='user');if(lastQ)query=lastQ.content+' '+q}
  const k=Math.max(1,Math.min(+($('#ragK')&&$('#ragK').value)||6,8));
  const {hits,pool}=demoSearch(query,f,k);
  if(!pool)return {answer:`The selected databases (${scope}) contain no documents with a summary that match the current filters. Clear the database selection or loosen the filters.`,sources:[],retrieval_query:query};
  if(!hits.length)return {answer:`I searched ${pool} documents in ${scope} but none of them matches the terms of your question. Try other words, or ask about a topic, method or document title.`,sources:[],retrieval_query:query};
  const max=hits[0].sc;
  const sources=hits.map((h,i)=>{const d=h.d,su=d.su||{};return {n:i+1,doc_id:d.id,title:d.ti,filename:d.fn,url:'#',locator:null,score:+(0.55+0.4*h.sc/max).toFixed(2),
    snippet:firstSentence(su.findings||su.purpose||'',260),doc_type:d.t,project_name:d.pn,filetype:d.ft,year:d.y,role:d.ro,methods:d.me||[],databases:d.db||[],cluster_id:d.ci,cluster_label:d.cl}});
  const subj=d=>({research_paper:'a paper',research_notes:'a note',research_project:'the project material'}[d.t]||'a document')+((d.db||[])[0]?' in '+dbName((d.db||[])[0]):'');
  const lowFirst=t=>/^[A-Z][a-z]/.test(t)?t[0].toLowerCase()+t.slice(1):t;
  const stripEnd=t=>t.replace(/\s*[.!?]\s*$/,'');
  const pf=f.deo&&f.deo.length?deoFields(f.deo):null;
  const claim=(h)=>{const su=h.d.su||{};const pk=pf&&pf.find(k=>(su[k]||'').trim());if(pk)return {txt:stripEnd(firstSentence(su[pk],260)),full:true};const f=su.findings&&firstSentence(su.findings,260);
    if(f)return {txt:stripEnd(f),full:true};const p=firstSentence(su.purpose||'',260);return {txt:`${subj(h.d)} ${lowFirst(stripEnd(p))}`,full:false}};
  const c1=claim(hits[0]);
  let p1=(c1.full?c1.txt:c1.txt[0].toUpperCase()+c1.txt.slice(1))+` [1].`;
  const links=['In the same direction,','From a different angle,','At the same time,','In addition,'];
  hits.slice(1,4).forEach((h,i)=>{const c=claim(h),n=i+2,lk=links[i%links.length];
    p1+=' '+`${lk} ${lowFirst(c.txt)} [${n}].`});
  const info=clusterInfo(),cl=[...new Set(hits.slice(0,4).map(h=>h.d.ci).filter(c=>c!=null))],dbsHit=[...new Set(hits.slice(0,4).flatMap(h=>h.d.db||[]))];
  const nUsed=Math.min(hits.length,4);
  let p2=`Taken together, the answer draws on ${nUsed} document${nUsed>1?'s':''} from ${dbsHit.join(' and ')||scope}`+
    (cl.length>1?`, and arguably touches more than one theme of the collection: ${cl.map(c=>(info[c]&&info[c].title)||('cluster C'+c)).join(', ')}.`:cl.length?` within the theme ${(info[cl[0]]&&info[cl[0]].title)||('cluster C'+cl[0])}.`:'.');
  const lim=hits.slice(0,4).map(h=>(h.d.su||{}).research_limitations_implications).find(x=>x&&x.trim()&&!/^not discussed/i.test(x.trim()));
  if(lim)p2+=` The evidence has limits, though: ${lowFirst(stripEnd(firstSentence(lim,400)))} [${hits.findIndex(h=>(h.d.su||{}).research_limitations_implications===lim)+1}].`;
  const parts=[p1,p2];
  const answer=parts.join('\n\n'),cited=new Set([...answer.matchAll(/\[(\d+)\]/g)].map(m=>+m[1]));
  const docs=hits.map((h,i)=>{const d=h.d,su=d.su||{};return {n:i+1,head:`[${i+1}] ${d.ti} (${TYPE_LABEL[d.t]||d.t}; database ${dbNames(d.db).join(', ')||'none'}${d.y?'; '+d.y:''})`,
    body:[['Purpose',su.purpose],['Design/methodology/approach',su.design_methodology_approach],['Findings',su.findings],['Research limitations/implications',su.research_limitations_implications],['Originality/value',su.originality_value]].filter(x=>x[1]).map(x=>x[0]+': '+x[1]).join('\n')}});
  return {answer,sources:sources.filter(x=>cited.has(x.n)),retrieval_query:query,allSources:sources,docs,llm:'extractive'};
}

/* ---------- Chat history (per tile, stored in this browser) ---------- */
const HIST_KEY='alita_chat_history';
let HIST={rag:[],graph:[]};
try{HIST=Object.assign({rag:[],graph:[]},JSON.parse(localStorage.getItem(HIST_KEY)||'{}'))}catch(e){}
const CUR={rag:null,graph:null};
const CHAT_EL={rag:()=>$('#ragChat'),graph:()=>$('#graphChat')};
const TILE_NAME={rag:'Document Chat',graph:'Graph Chat'};
function saveHist(){try{localStorage.setItem(HIST_KEY,JSON.stringify(HIST))}catch(e){}renderHistCounts();renderGraphSide()}
function renderHistCounts(){$$('[data-hcount]').forEach(el=>{const n=HIST[el.dataset.hcount].length;el.textContent=n||''})}
function recordTurn(tile,turn){
  let sess=HIST[tile].find(x=>x.id===CUR[tile]);
  if(!sess){
    sess={id:'s'+Date.now().toString(36)+Math.random().toString(36).slice(2,6),ts:Date.now(),title:'',turns:[]};
    HIST[tile].unshift(sess);CUR[tile]=sess.id;
    HIST[tile]=HIST[tile].slice(0,50);
  }
  if(!sess.title&&turn.role==='user')sess.title=turn.text.slice(0,120);
  sess.turns.push(turn);sess.updated=Date.now();saveHist();syncMem(tile);
}
function historyFor(tile){ // Gedächtnis: der ganze bisherige Verlauf der aktuellen Unterhaltung (neueste 40 Wechsel)
  if(!memOn(tile))return[];
  const sess=HIST[tile].find(x=>x.id===CUR[tile]);if(!sess)return[];
  return sess.turns.filter(t=>!t.err).slice(-40).map(t=>{
    if(t.role==='user')return {role:'user',content:t.text};
    const a=t.a||{};const src=(a.sources||[]).map(x=>`[${x.n}] ${x.title}`).join('; ');
    return {role:'assistant',content:(a.answer||'')+(src?`\n(Sources of this answer: ${src})`:'')};
  }).filter(t=>t.content&&t.content!=='(filters only)');
}
function newChat(tile){CUR[tile]=null;CHAT_EL[tile]().innerHTML='';renderHistPanel();syncMem(tile);renderGraphSide()}
function loadSession(tile,id){
  const sess=HIST[tile].find(x=>x.id===id);if(!sess)return;
  const chat=CHAT_EL[tile]();chat.innerHTML='';CUR[tile]=id;
  sess.turns.forEach(t=>t.role==='user'?userMsg(chat,t.text,t.filters||[],t.meta,t.sp):t.err?errMsg(chat,t.err):botMsg(chat,t.a));
  chat.scrollTop=chat.scrollHeight;syncMem(tile);renderGraphSide();
}
let HIST_TILE='rag';
/* B page: right column = your side of the conversation (questions + input), left = only the answers */
function renderGraphSide(){
  const box=document.getElementById('graphSide');if(!box||typeof HIST==='undefined')return;
  const sess=(HIST.graph||[]).find(x=>x.id===CUR.graph),qs=sess?sess.turns.filter(t=>t.role==='user'):[];
  let html=`<div class="gs-head"><b>Your questions</b><span class="srcnote">${qs.length||''}</span><button class="mini" type="button" data-gs-hist title="Open an earlier conversation">History</button><button class="mini" type="button" data-gs-new>+ New</button></div>`;
  const turns=sess?sess.turns:[],costOf=t=>{const i=turns.indexOf(t),b=turns.slice(i+1).find(x=>x.role!=='user');return b&&b.a&&b.a.usage};
  html+=qs.length?`<div class="gs-qs">${qs.map((t,k)=>{const u=costOf(t);return `<button type="button" class="gs-q" data-gs-q="${k}" title="Show the answer to this question"><span>${esc(t.text)}</span>${u?costHtml(u,'question'):''}</button>`}).join('')}</div>`
    :'<div class="gs-empty">Type your question below. Your questions collect here, the answers appear in the answer area.</div>';
  box.innerHTML=html;box.scrollTop=box.scrollHeight;
  box.querySelector('[data-gs-new]').addEventListener('click',()=>newChat('graph'));
  box.querySelector('[data-gs-hist]').addEventListener('click',()=>openHist('graph'));
  box.querySelectorAll('[data-gs-q]').forEach(b=>b.addEventListener('click',()=>{
    box.querySelectorAll('.gs-q.on').forEach(x=>x.classList.remove('on'));b.classList.add('on');
    const u=CHAT_EL.graph().querySelectorAll('.msg.user')[+b.dataset.gsQ];if(!u)return;
    let m=u.nextElementSibling;while(m&&m.classList.contains('user'))m=m.nextElementSibling;const tgt=m||u;
    tgt.scrollIntoView({behavior:'smooth',block:'start'});tgt.classList.add('gs-flash');setTimeout(()=>tgt.classList.remove('gs-flash'),1200)}));
}
function fmtWhen(ts){const d=new Date(ts);return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})+' · '+d.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit'})}
function renderHistPanel(){
  if($('#histPanel').hidden)return;
  const tile=HIST_TILE,list=HIST[tile];
  $('#histTitle').textContent='Chat history · '+TILE_NAME[tile];
  let html=`<div class="hist-tools"><span class="srcnote">${list.length} conversation${list.length===1?'':'s'} · saved in this browser only</span><span style="display:flex;gap:6px">${list.length?'<button class="btn" type="button" id="histDlAll" title="Download all conversations of this tile as a text file">⤓ All as .txt</button>':''}<button class="btn" type="button" id="histNew">New chat</button></span></div>`;
  if(!list.length)html+=`<div class="empty-state"><b>No conversations yet</b><span>Questions you ask in the ${TILE_NAME[tile]} show up here.</span></div>`;
  let day='';
  html+='<div class="hist-list">'+list.map(sx=>{
    const d=new Date(sx.updated||sx.ts).toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'});
    const head=d!==day?`<div class="hist-day">${esc(d)}</div>`:'';day=d;
    const q=sx.turns.filter(t=>t.role==='user').length;
    const spc=sx.turns.some(t=>t.sp&&t.sp.src==='custom');
    const f=(sx.turns.find(t=>t.a&&t.a.applied_filters)||{}).a;
    return head+`<div class="hist-item ${sx.id===CUR[tile]?'cur':''}" role="button" tabindex="0" data-sid="${esc(sx.id)}"><b>${esc(sx.title||'(untitled)')}</b><span class="hacts"><button class="dl" type="button" data-dl="${esc(sx.id)}" title="Download this conversation as .txt" aria-label="Download conversation as text file">⤓ .txt</button><button class="del" type="button" data-del="${esc(sx.id)}" aria-label="Delete conversation">✕</button></span><span class="meta">${fmtWhen(sx.updated||sx.ts)} · ${q} question${q===1?'':'s'}${spc?' · ⚙ custom system prompt':''}${f?' · filters: '+esc(filterSummary(f.applied_filters)):''}</span><div class="qmeta">${sessionMeta(sx)}</div></div>`;
  }).join('')+'</div>';
  if(list.length)html+=`<div><button class="reset" type="button" id="histClear" style="border:0;background:none;color:var(--rec);cursor:pointer;padding:0">Delete all ${TILE_NAME[tile]} history</button></div>`;
  $('#histBody').innerHTML=html;
  $('#histNew').addEventListener('click',()=>{newChat(tile);closeHist()});
  $$('#histBody .hist-item').forEach(el=>{
    const open=()=>{loadSession(tile,el.dataset.sid);closeHist()};
    el.addEventListener('click',e=>{if(e.target.closest('[data-del],[data-dl]'))return;open()});
    el.addEventListener('keydown',e=>{if(e.key==='Enter')open()});
  });
  $$('#histBody [data-del]').forEach(b=>b.addEventListener('click',()=>{const id=b.dataset.del;HIST[tile]=HIST[tile].filter(x=>x.id!==id);if(CUR[tile]===id)CUR[tile]=null;saveHist();renderHistPanel()}));
  $$('#histBody [data-dl]').forEach(b=>b.addEventListener('click',()=>{const sx=HIST[tile].find(x=>x.id===b.dataset.dl);if(sx)saveTxt(histFilename(tile,sx),histTxt(tile,[sx]))}));
  const da=$('#histDlAll');if(da)da.addEventListener('click',()=>saveTxt(histFilename(tile,null),histTxt(tile,HIST[tile])));
  const c=$('#histClear');if(c)c.addEventListener('click',()=>{if(c.dataset.armed){HIST[tile]=[];CUR[tile]=null;saveHist();renderHistPanel()}else{c.dataset.armed='1';c.textContent='Click again to delete all'}});
}
function sessionMeta(sx){
  const intents=[...new Set(sx.turns.filter(t=>t.meta).map(t=>t.meta.intent))];
  const ents=[];const seen=new Set();
  sx.turns.forEach(t=>(t.meta&&t.meta.entities||[]).forEach(e=>{const k=e.type+'|'+e.value.toLowerCase();if(!seen.has(k)){seen.add(k);ents.push(e)}}));
  if(!intents.length&&!ents.length)return '';
  return intents.map(i=>`<span class="qintent" title="Intention">${esc(INTENT_LABEL[i]||i)}</span>`).join('')+ents.slice(0,8).map(e=>`<span class="qent" title="${esc(ENT_LABEL[e.type]||e.type)}"><i>${esc(ENT_LABEL[e.type]||e.type)}</i>${esc(e.value)}</span>`).join('')+(ents.length>8?`<span class="qent">+${ents.length-8}</span>`:'');
}
function openHist(tile){HIST_TILE=tile;$('#histPanel').hidden=false;$('#scrim').hidden=false;renderHistPanel()}
function closeHist(){$('#histPanel').hidden=true;if($('#drawer').hidden)$('#scrim').hidden=true}
$$('[data-hist]').forEach(b=>b.addEventListener('click',()=>openHist(b.dataset.hist)));
$$('[data-new]').forEach(b=>b.addEventListener('click',()=>{newChat(b.dataset.new);toast('New chat started · the previous one is in History')}));
$('#histClose').addEventListener('click',closeHist);
$('#scrim').addEventListener('click',closeHist);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeHist()});
renderHistCounts();

async function askRag(q){
  const {clean,f}=parsePromptFilters(q);if(!clean&&!f.length)return;
  const filters=ragFilters();const meta=analyzeQuery(clean||q,filters);
  const chat=$('#ragChat');const sp=spSnapshot('rag');const um=userMsg(chat,clean||'(filters only)',f,meta,sp);
  const prior=historyFor('rag');recordTurn('rag',{role:'user',text:clean||'(filters only)',filters:f,meta,sp});const t=typing(chat);
  const body={message:q,filters,top_k:+$('#ragK').value,history:prior,system_prompt:sysPrompt('rag'),overview:chatScope().overview};
  const finish=data=>{
    if(data.intent){const ents=[...meta.entities];(data.entities||[]).forEach(e=>{if(!ents.some(x=>x.type===e.type&&x.value.toLowerCase()===String(e.value).toLowerCase()))ents.push(e)});setTurnMeta('rag',um,{intent:data.intent,entities:ents})}
    botMsg(chat,data);recordTurn('rag',{role:'bot',a:data});
  };
  const fail=m=>{errMsg(chat,m);recordTurn('rag',{role:'bot',err:m})};
  if(LIVE){
    try{
      const res=await streamChat(body,chat,t);
      if(res.fallback){ // backend without streaming endpoint
        const r=await fetch('api/chat',{method:'POST',headers:headers(),body:JSON.stringify(body)});const data=await r.json();t.remove();
        if(!r.ok)return fail(data.detail||('Error '+r.status));return finish(data);
      }
      if(res.error)return fail(res.error+(res.partial?`\n\nPartial answer: ${res.partial}`:''));
      finish(res.data);
    }catch(e){t.remove();fail('Backend not reachable: '+e.message)}
  }else{
    const base={...demoAnswer(clean,filters,prior),applied_filters:filters,memory_turns:prior.length,model:'no language model (demo)'};
    llmDemoAnswer(chat,t,clean||q,base,prior,a=>{const {docs,allSources,...keep}=a;finish(keep)});
  }
}
$('#ragForm').addEventListener('submit',e=>{e.preventDefault();const v=$('#ragInput').value.trim();if(v){askRag(v);$('#ragInput').value=''}});
$('#ragInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#ragForm').requestSubmit()}});

/* ======================================================================
   VOICE – tile 2 (mockup, will reuse the same RAG service)
   ====================================================================== */
const GRAPH_ANSWER={answer:'The Mental Model Processes project was written by three authors and submitted to eleven journals [1]. Methodologically, it combines a lab experiment with a multilevel analysis [2].',
  path:[['M. Leyer','Person'],'authored',['11-MentalModelProcesses','Project'],'uses_method',['Multilevel analysis','Method']],
  sources:[{n:1,title:'Title page',filename:'Title page.docx',url:'#',score:.9,snippet:'Measurement and performance impact of team mental models on process performance …',doc_type:'research_project',project_name:'11-MentalModelProcesses',filetype:'docx',year:2022,role:'title_page'},
           {n:2,title:'Abstract',filename:'Abstract.docx',url:'#',score:.82,snippet:'We use laboratory observations with 159 participants in 10 teams …',doc_type:'research_project',project_name:'11-MentalModelProcesses',filetype:'docx',year:2021,role:'abstract'}]};
async function askGraph(q){
  if(!q.trim())return;const chat=$('#graphChat');const ut=q;const meta=analyzeQuery(q,{database:[...SEL_DB],cluster:[...CV.sels]});const sp=spSnapshot('graph');const priorG=historyFor('graph');userMsg(chat,ut,[],meta,sp);recordTurn('graph',{role:'user',text:ut,meta,sp});
  const t=typing(chat);
  const finish=a=>{const {docs,allSources,graphContext,...keep}=a;botMsg(chat,keep);recordTurn('graph',{role:'bot',a:keep})};
  const plan=graphPlan(q);
  if(LIVE){
    const sc=chatScope();
    const body={message:q,history:priorG,system_prompt:sysPrompt('graph'),databases:plan.databases,clusters:sc.kind==='project'?[]:plan.clusters,projects:sc.project,persons:sc.person,overview:sc.overview,deo:$('#gDeo').value?[$('#gDeo').value]:[],
      entity_types:plan.entity_types,relation:plan.relation||null,year_from:plan.year,year_to:plan.year,hops:plan.hops,as_of:($('#gAsOf')&&$('#gAsOf').value)||null};
    try{
      const res=await streamChat(body,chat,t,'api/graph/stream');
      if(res.fallback){const a={...demoGraphAnswer(q,priorG),memory_turns:priorG.length,model:'graph endpoint missing'};return finish(a)}
      if(res.error){errMsg(chat,res.error);recordTurn('graph',{role:'bot',err:res.error});return}
      finish(res.data);
    }catch(e){t.remove();errMsg(chat,'Backend not reachable: '+e.message);recordTurn('graph',{role:'bot',err:'Backend not reachable: '+e.message})}
  }else{
    const base={...demoGraphAnswer(q,priorG),memory_turns:priorG.length,model:'no language model (demo)'};
    llmDemoAnswer(chat,t,q,base,priorG,finish,'graph');
  }
}
$('#graphInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#graphForm').requestSubmit()}});
$('#graphForm').addEventListener('submit',e=>{e.preventDefault();const v=$('#graphInput').value.trim();if(v){askGraph(v);$('#graphInput').value=''}});
try{renderGraphSide()}catch(e){}
