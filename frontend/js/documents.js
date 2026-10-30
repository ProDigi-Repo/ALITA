/* ---------- API-Key ---------- */
let apiKey='';
try{apiKey=localStorage.getItem('or_key')||''}catch(e){}
function renderKey(){
  const s=$('#keyStatus');
  if(apiKey){s.className='pill ok';s.innerHTML='<span class="dot"></span>Key …'+esc(apiKey.slice(-4));$('#apiKey').value=apiKey}
  else{s.className='pill';s.innerHTML='<span class="dot"></span>no key'}
}
function renderDbLock(){
  const p=$('#dbPass'),l=$('#dbLock');if(!p)return;
  p.placeholder=DB_UNLOCKED?'all databases unlocked':'show all databases';p.disabled=DB_UNLOCKED;l.hidden=!DB_UNLOCKED;
}
$('#dbLock').addEventListener('click',()=>{try{localStorage.removeItem('db_unlocked')}catch(e){}location.reload()});
renderDbLock();
$('#keyForm').addEventListener('submit',e=>{
  e.preventDefault();
  const pw=$('#dbPass').value;
  if(pw){
    $('#dbPass').value='';
    if(pw===DB_PASSWORD){const k=$('#apiKey').value.trim();try{localStorage.setItem('db_unlocked','1');if(k.startsWith('sk-or-'))localStorage.setItem('or_key',k)}catch(e){}DB_UNLOCKED=true;toast('Password correct · all databases are shown');setTimeout(()=>location.reload(),600);return}
    toast('Wrong password');if(!$('#apiKey').value.trim()||$('#apiKey').value.trim()===apiKey)return;
  }
  const v=$('#apiKey').value.trim();
  if(v && !v.startsWith('sk-or-')){toast('The key should start with "sk-or-"');return}
  apiKey=v;try{v?localStorage.setItem('or_key',v):localStorage.removeItem('or_key')}catch(e){}
  renderKey();toast(v?'Key saved · in this browser only':'Key removed');
});
$('#toggleKey').addEventListener('click',()=>{const i=$('#apiKey');i.type=i.type==='password'?'text':'password'});
const CHAT_MODEL_ID='openai/gpt-6-luna';   // fixed model, no selection (backend: CHAT_MODEL)
renderKey();

/* ======================================================================
   DOCUMENTS
   ====================================================================== */
let DOCS=[], PROJECTS=[];
const D={t:'',sort:'d',dir:-1,shown:100,sel:null};

function normLive(r){ // API-Zeile -> internes Kurzformat
  return {leg:r.legal||null,id:r.doc_id,t:r.doc_type,ti:r.title,fn:r.filename,ft:r.filetype,d:(r.date||'').slice(0,10),ds:r.date_source,y:r.year,sz:r.size_bytes,
    pn:r.project_name,rp:r.rel_path,ro:r.role,ve:r.venue,st:r.stage,v:r.version,la:r.is_latest,ar:r.archived,ix:r.indexed,no:r.index_note,me:r.method_ids||[],lg:r.language,pg:r.pages,db:r.databases||[],doi:r.doi,au:r.authors||[],ed:r.editors||[],ci:r.cluster_id,cl:r.cluster_label,cs:r.cluster_score,cb:r.cluster_basis,cx:r.cluster_x,cy:r.cluster_y,ca:r.cluster_alt_id,cas:r.cluster_alt_score,ct:r.cluster_title,cd:r.cluster_description,cc:r.cluster_contribution,can:r.cluster_anchor};
}
async function loadDocs(){
  if(LIVE){
    try{
      const [docs,projs,gl]=await Promise.all([fetch('api/documents?limit=5000').then(r=>r.json()),fetch('api/projects').then(r=>r.json()),fetch('api/glossary').then(r=>r.json())]);
      DOCS=docs.items.map(normLive);
      PROJECTS=projs.map(p=>({ci:p.cluster_id,cl:p.cluster_label,cs:p.cluster_score,cx:p.cluster_x,cy:p.cluster_y,ca:p.cluster_alt_id,cas:p.cluster_alt_score,name:p.name,title:p.title,files:p.file_count,indexed:p.indexed_count,from_:(p.date_from||'').slice(0,10),to:(p.date_to||'').slice(0,10),venues:p.venues,keywords:p.keywords,summary:p.summary||{},methods:(p.methods||[]).map(m=>[m.id,m.label,m.confidence,m.source]),roles:p.roles,filetypes:p.filetypes,excluded:p.excluded_patterns,exc:p.excluded_count,excBy:p.excluded_by,team:p.authors||[],db:p.databases||[]}));
      (gl.methods||[]).forEach(m=>METHOD_LABEL[m.id]=m.label);
    }catch(e){toast('Could not load documents: '+e.message)}
  }else if(DEMO){
    DOCS=DEMO.docs.map(d=>({...d,ix:false,la:d.la!==false,ar:!!d.ar,me:d.me||[],db:d.db||[]}));
    PROJECTS=[{...DEMO.project,db:DEMO.project.db||[]}];
  }
  
  DOCS=dbGateFilter(DOCS);PROJECTS=dbGateFilter(PROJECTS);
  [...DOCS,...PROJECTS].forEach(x=>{x.cl=dbRelabel(x.cl);if(x.ct)x.ct=dbRelabel(x.ct);if(x.cd)x.cd=dbRelabel(x.cd)});
  if(!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.desc&&!DEMO.clusters._relabeled){Object.values(DEMO.clusters.desc).forEach(v=>{v.title=dbRelabel(v.title);v.description=dbRelabel(v.description)});DEMO.clusters._relabeled=true}
  fillFacetSelects();renderDbBar();renderDocs();renderClusterViz();renderClusterPage();loadClusterProfiles();
}

function opt(v,l){return `<option value="${esc(v)}">${esc(l)}</option>`}
function fillFacetSelects(){
  const uniq=(k)=>[...new Set(DOCS.flatMap(d=>Array.isArray(d[k])?d[k]:[d[k]]).filter(v=>v!=null&&v!==''))];
  const count=(k,v)=>DOCS.filter(d=>Array.isArray(d[k])?d[k].includes(v):d[k]===v).length;
  const projs=uniq('pn').sort(), fts=uniq('ft').sort((a,b)=>count('ft',b)-count('ft',a)), roles=uniq('ro').sort((a,b)=>count('ro',b)-count('ro',a));
  const meths=uniq('me').sort((a,b)=>count('me',b)-count('me',a)), years=uniq('y').sort();
  for(const id of ['#dProject']) $(id).innerHTML=opt('','All projects')+projs.map(p=>opt(p,p)).join('');
  for(const id of ['#dFiletype','#rFiletype']) $(id).innerHTML=opt('','All file types')+fts.map(f=>opt(f,'.'+f+'  ('+count('ft',f)+')')).join('');
  for(const id of ['#dMethod','#rMethod']) $(id).innerHTML=opt('','All methods')+meths.map(m=>opt(m,(METHOD_LABEL[m]||m)+'  ('+count('me',m)+')')).join('');
  const cl=[...new Set(DOCS.filter(d=>d.ci!=null).map(d=>d.ci))].sort((a,b)=>a-b);
  for(const id of ['#dCluster','#rCluster']) $(id).innerHTML=opt('','All clusters')+cl.map(c=>{const m=DOCS.filter(d=>d.ci===c),own=m.filter(d=>d.cb!=='project'&&d.cb!=='contribution').length,pr=new Set(m.filter(d=>d.cb==='project').map(d=>d.pn)).size;return opt(c,`C${c} · ${(m[0]||{}).cl||''}  (${own}${pr?` + ${pr} project${pr>1?'s':''}`:''})`)}).join('');
  $('#dRole').innerHTML=opt('','All roles')+roles.map(r=>opt(r,(ROLE_LABEL[r]||r)+'  ('+count('ro',r)+')')).join('');
  for(const id of ['#dFrom','#rFrom']) $(id).innerHTML=opt('','Year from')+years.map(y=>opt(y,y)).join('');
  for(const id of ['#dTo','#rTo']) $(id).innerHTML=opt('','Year to')+years.map(y=>opt(y,y)).join('');
  $('#projList').innerHTML=projs.map(p=>`<option value="${esc(p)}">`).join('');
  // counters
  const c=t=>DOCS.filter(d=>d.t===t).length;
  $('#cLegal').textContent=DOCS.filter(d=>LEGAL_T.has(d.t)).length;
  $('#cAll').textContent=DOCS.length;$('#cClusters').textContent=new Set(DOCS.filter(d=>d.ci!=null).map(d=>d.ci)).size;$('#cProject').textContent=c('research_project');$('#cPaper').textContent=c('research_paper');$('#cNotes').textContent=c('research_notes');
  $('#cProjN').textContent=projs.length;$('#navCount').textContent=DOCS.length;
}

function currentDocFilter(){
  return {db:SEL_DB,t:D.t,q:$('#dq').value.trim().toLowerCase(),pn:$('#dProject').value,ro:$('#dRole').value,ft:$('#dFiletype').value,me:$('#dMethod').value,ci:$('#dCluster').value===''?null:+$('#dCluster').value,
    yf:+$('#dFrom').value||null,yt:+$('#dTo').value||null,latest:$('#dLatest').checked,nodup:$('#dNoDup').checked};
}
function filterDocs(f){
  return DOCS.filter(d=>(!f.db.length||(d.db||[]).some(x=>f.db.includes(x)))&&(!f.t||d.t===f.t||(f.t==='legal'&&LEGAL_T.has(d.t)))&&(!f.pn||d.pn===f.pn)&&(!f.ro||d.ro===f.ro)&&(!f.ft||d.ft===f.ft)&&(!f.me||(d.me||[]).includes(f.me))&&(f.ci==null||d.ci===f.ci)
    &&(!f.yf||(d.y&&d.y>=f.yf))&&(!f.yt||(d.y&&d.y<=f.yt))&&(!f.latest||d.la)&&(!f.nodup||!d.du)
    &&(!f.q||(d.ti||'').toLowerCase().includes(f.q)||(d.fn||'').toLowerCase().includes(f.q)||(d.rp||'').toLowerCase().includes(f.q)));
}
function verKey(v){if(!v)return -1;const m=/^(\d+)([a-z]?)/.exec(v);return m?+m[1]+(m[2]?(m[2].charCodeAt(0)-96)/100:0):-1}
function sortDocs(rows){
  const k=D.sort,dir=D.dir;
  const val=d=>k==='ci'?(d.ci??999):k==='db'?(d.db||[]).join(','):k==='v'?verKey(d.v):k==='ix'?(d.du?0:d.ix?2:1):k==='d'&&d.ds==='file_mtime'?'0'+(d.d||''):(d[k]??''); // uncertain dates go last
  return rows.sort((a,b)=>{const x=val(a),y=val(b);if(x===y)return (a.rp||a.fn).localeCompare(b.rp||b.fn);return (x>y?1:-1)*dir});
}
function statusOf(d){
  if(d.du)return['dup','Duplicate'];
  if(d.ix)return['ok','Full text'];
  if(d.no&&/metadata only|no text|pyreadstat|binary|not readable|conversion|nur Metadaten|Kein Text|Binär|nicht lesbar|Konvertierung/i.test(d.no))return['meta','Metadata only'];
  return LIVE?['meta','Not embedded']:['meta','Ready'];
}
function renderDocs(){
  const f=currentDocFilter();
  const rows=sortDocs(filterDocs(f));
  $$('.dtab:not(.dstat)').forEach(b=>b.setAttribute('aria-selected',b.dataset.t===D.t));
  $$('.dt th[data-sort]').forEach(th=>th.querySelector('.arr').textContent=th.dataset.sort===D.sort?(D.dir>0?'↑':'↓'):'');
  renderProjectCard(f);
  const body=$('#dbody');
  body.innerHTML=rows.slice(0,D.shown).map(d=>{
    const [sc,sl]=statusOf(d);
    return `<tr data-id="${esc(d.id)}" class="${d.la?'':'old'} ${D.sel===d.id?'sel':''}">
      <td><div class="ttl">${esc(d.ti)}</div><div class="rp">${esc(d.pn?d.pn+' / '+(d.rp||d.fn):d.fn)}</div></td>
      <td>${dbTags(d.db)}</td>
      <td>${clusterTag(d)}</td>
      <td><span class="tbadge" style="--c:${TYPE_COLOR[d.t]}">${TYPE_LABEL[d.t]}</span></td>
      <td>${esc(ROLE_LABEL[d.ro]||d.ro||'–')}${d.ve?`<div class="rp">${esc(d.ve)}${d.st?' · '+esc(STAGE_LABEL[d.st]||d.st):''}</div>`:''}</td>
      <td><span class="ft">${esc(d.ft)}</span></td>
      <td class="num">${esc(d.d||'–')}${d.ds==='file_mtime'?'<span class="unsure" title="Date comes from the file system and may be skewed by copying or unzipping">≈</span>':''}</td>
      <td class="vers">${d.v?'v'+esc(d.v):'–'}${d.la&&d.v?'<span class="latest">latest</span>':''}</td>
      <td><div class="mchips">${(d.me||[]).slice(0,3).map(m=>`<span class="tagl">${esc(METHOD_LABEL[m]||m)}</span>`).join('')}${(d.me||[]).length>3?`<span class="tagl">+${d.me.length-3}</span>`:''}</div></td>
      <td><span class="st ${sc}">${sl}</span></td></tr>`}).join('');
  $('#dMore').hidden=rows.length<=D.shown;
  $('#dMoreBtn').textContent=`Show more (${rows.length-D.shown} of ${rows.length})`;
  const empty=$('#dEmpty');
  if(!rows.length){
    empty.hidden=false;
    const noType=D.t&&!DOCS.some(d=>d.t===D.t);
    empty.innerHTML=noType?`<b>No ${TYPE_LABEL[D.t]} documents yet</b><span>Upload ${D.t==='research_paper'?'papers (PDF, DOCX)':'notes (DOCX, TXT, MD, PDF)'} with "Upload". They get the same metadata: date, file type, summary, and methods.</span><button class="btn" onclick="openUpload('${D.t}')">Upload now</button>`
      :`<b>No matches</b><span>No documents match these filters.</span><button class="btn" onclick="resetDocFilters()">Reset filters</button>`;
  }else empty.hidden=true;
}
function renderProjectCard(f){
  const card=$('#pcard');
  const name=f.pn||(PROJECTS.length===1&&(!f.t||f.t==='research_project')?PROJECTS[0].name:'');
  const p=PROJECTS.find(x=>x.name===name);
  if(!p||(f.t&&f.t!=='research_project')){card.hidden=true;return}
  card.hidden=false;
  const s=p.summary||{};
  const prov=s.source==='parsed'?'taken from the project\'s structured abstract':s.source==='llm'?'generated by the LLM from the latest manuscript':'';
  card.innerHTML=`<div class="left">
      <div class="folder"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>${esc(p.name)}</div>
      <h3>${esc(p.title||p.name)}</h3>
      <div class="stats"><span><b>${p.files}</b> files</span><span><b>${esc(p.from_)}</b> to <b>${esc(p.to)}</b></span><span><b>${(p.venues||[]).length}</b> submissions</span>${p.excluded&&p.excluded.length?`<span title="${esc(p.excluded.join(', '))}">excluded: ${esc(p.excluded[0])}${p.excluded.length>1?' …':''}</span>`:''}</div>
      <div class="venues">${(p.venues||[]).map((v,i)=>`<span class="tagl">${i+1} ${esc(v)}</span>`).join('')}</div>
      <h4 style="margin:6px 0 0;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em">Databases ${(p.db||[]).length?'':'<span class="prov">unassigned</span>'}</h4>
      ${dbPicker('pcDb',p.db)}
      <h4 style="margin:6px 0 0;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em">Methods <span class="prov" title="The methods glossary is a temporary placeholder">Draft glossary</span></h4>
      <div class="mchips">${(p.methods||[]).map(m=>`<span class="mchip">${esc(METHOD_LABEL[m[0]]||m[1])}<i>${Math.round(m[2]*100)}%</i></span>`).join('')||'<span class="srcnote">none yet</span>'}</div>
      ${(p.keywords||[]).length?`<div class="mchips">${p.keywords.map(k=>`<span class="tagl">${esc(k)}</span>`).join('')}</div>`:''}
    </div>
    <div>${sumHtml(s)}${prov?`<div class="srcnote" style="margin-top:8px">Summary ${prov}.</div>`:''}</div>`;
  wireDbPicker('pcDb',dbs=>assignDbs({project:p.name},dbs));
}
function sumHtml(s,emptyNote){
  s=s||{};
  const any=SUM_FIELDS.some(([k])=>s[k]);
  if(!any)return `<dl class="sumgrid">${SUM_FIELDS.map(([,l])=>`<dt>${l}</dt><dd class="empty">–</dd>`).join('')}</dl><div class="srcnote" style="margin-top:6px">${emptyNote||'Generated by the LLM during ingestion when an API key is set.'}</div>`;
  return `<dl class="sumgrid">${SUM_FIELDS.map(([k,l])=>`<dt>${l}</dt><dd${s[k]?'':' class="empty"'}>${esc(s[k]||'not stated in the text')}</dd>`).join('')}</dl>`;
}
function resetDocFilters(){
  $('#dq').value='';['#dProject','#dRole','#dFiletype','#dMethod','#dCluster','#dFrom','#dTo'].forEach(s=>$(s).value='');
  $('#dLatest').checked=false;$('#dNoDup').checked=true;D.t='';D.shown=100;renderDocs();
}
$$('.dtab:not(.dstat)').forEach(b=>b.addEventListener('click',()=>{D.t=b.dataset.t;D.shown=100;renderDocs()}));
$('#cClustersBtn').addEventListener('click',()=>openDbInfo(null,true));
['#dq','#dProject','#dRole','#dFiletype','#dMethod','#dCluster','#dFrom','#dTo','#dLatest','#dNoDup'].forEach(s=>$(s).addEventListener(s==='#dq'?'input':'change',()=>{D.shown=100;renderDocs()}));
$('#dReset').addEventListener('click',resetDocFilters);
$('#dMoreBtn').addEventListener('click',()=>{D.shown+=200;renderDocs()});
$$('.dt th[data-sort]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.sort;D.dir=D.sort===k?-D.dir:(k==='d'||k==='v'?-1:1);D.sort=k;renderDocs()}));
$('#dbody').addEventListener('click',e=>{const tr=e.target.closest('tr');if(tr)openDoc(tr.dataset.id)});

/* ---------- Detail drawer ---------- */
async function openDoc(id){
  let d=DOCS.find(x=>x.id===id);if(!d)return;
  D.sel=id;$$('#dbody tr').forEach(tr=>tr.classList.toggle('sel',tr.dataset.id===id));
  let full=d;
  if(LIVE){try{const r=await fetch('api/documents/'+encodeURIComponent(id)).then(r=>r.json());full={...d,su:r.summary,kw:r.keywords,mfull:r.methods,au:r.authors,ed:r.editors,cr:r.created,mo:r.modified,du:(r.project||{}).duplicate_of,tc:r.text_chars,cites:r.cites,cited_by:r.cited_by}}catch(e){}}
  const p=PROJECTS.find(x=>x.name===d.pn);
  const siblings=d.vg||d.v?DOCS.filter(x=>x.pn===d.pn&&(x.vg?x.vg===d.vg:false)).sort((a,b)=>verKey(b.v)-verKey(a.v)||(b.d||'').localeCompare(a.d||'')):[];
  const hasOwn=full.su&&SUM_FIELDS.some(([k])=>full.su[k]);
  const methods=full.mfull?full.mfull.map(m=>[m.id,m.label,m.confidence,m.source]):(d.me||[]).map(m=>[m,METHOD_LABEL[m]||m,null,'keyword']);
  const [sc,sl]=statusOf(full);
  $('#drTitle').textContent=d.ti;
  $('#drBody').innerHTML=`
    <div class="actions">
      ${LIVE?`<a class="btn" href="files/${encodeURIComponent(id)}" target="_blank" rel="noopener">Open file</a>`:`<button class="btn" type="button" onclick="toast('Opening files requires the running backend')">Open file</button>`}
      <button class="btn" type="button" id="drAsk">Ask in chat</button>
    </div>
    <section><h4>Databases</h4>${dbPicker('drDb',d.db)}
      <div class="srcnote" style="margin-top:6px">${d.pn?`<label class="check"><input type="checkbox" id="drDbAll" checked> apply to the whole project ${esc(d.pn)}</label>`:''}</div>
    </section>
    <section><h4>Cluster</h4>${d.ci!=null?`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${clusterTag(d,true)}${d.cs!=null?`<span class="srcnote">similarity to cluster center ${(+d.cs).toFixed(2)}</span>`:d.cb==='project'?'<span class="srcnote">inherited from its research project</span>':d.cb==='contribution'?`<span class="srcnote">${esc(CONTRIB_LABEL[d.cc]||d.cc||'Contribution')} to ${esc(((DOCS.find(x=>x.id===d.can)||{}).ti)||'the project content')}</span>`:d.du?'<span class="srcnote">inherited from the original file</span>':''}</div><div class="srcnote" style="margin-top:6px">${CLUSTER_NOTE()}</div>`:'<span class="srcnote">Not clustered (no text or not embedded yet).</span>'}</section>
    <section><h4>Belongs to</h4><dl class="kv">
      <dt>Data type</dt><dd><span class="tbadge" style="--c:${TYPE_COLOR[d.t]}">${TYPE_LABEL[d.t]}</span></dd>
      ${d.pn?`<dt>Research Project</dt><dd class="mono">${esc(d.pn)}</dd><dt>Path in project</dt><dd class="mono">${esc(d.rp)}</dd>`:''}
      ${(full.au||[]).length?`<dt>${d.pn?'Project team':'Author'+(full.au.length>1?'s':'')}</dt><dd>${personLinks(full.au)}</dd>`:d.pn?`<dt>Project team</dt><dd class="srcnote">not recorded yet – add it in the project card</dd>`:''}
      ${(full.ed||[]).length?`<dt>Last saved by</dt><dd class="srcnote" title="From the file's metadata – the person who saved the file, not necessarily an author">${esc(full.ed.join(', '))}</dd>`:''}
      <dt>Role</dt><dd>${esc(ROLE_LABEL[d.ro]||d.ro||'–')}</dd>
      ${d.ve?`<dt>Submission</dt><dd>${esc(d.ve)}${d.st?' · '+esc(STAGE_LABEL[d.st]||d.st):''}</dd>`:''}
      ${d.ar?`<dt>Archive</dt><dd>stored in an archive folder</dd>`:''}
    </dl></section>
    <section><h4>File</h4><dl class="kv">
      <dt>File name</dt><dd class="mono">${esc(d.fn)}</dd>
      <dt>File type</dt><dd><span class="ft">${esc(d.ft)}</span></dd>
      <dt>Date</dt><dd>${esc(d.d||'–')} <span class="srcnote">· source: ${esc(DATE_SRC[d.ds]||d.ds||'–')}</span></dd>
      <dt>Size</dt><dd class="mono">${fmtSize(d.sz)}${d.pg?` · ${d.pg} ${d.ft==='pptx'?'slides':'pages'}`:''}</dd>
      ${d.doi?`<dt>DOI</dt><dd class="mono"><a href="https://doi.org/${esc(d.doi)}" target="_blank" rel="noopener">${esc(d.doi)}</a></dd>`:''}
      ${d.lg?`<dt>Language</dt><dd>${d.lg==='de'?'German':d.lg==='en'?'English':esc(d.lg)}</dd>`:''}
      <dt>Index</dt><dd><span class="st ${sc}">${sl}</span>${full.no?` <span class="srcnote">· ${esc(full.no)}</span>`:''}</dd>
    </dl></section>
    <section><h4>Summary</h4>
      ${hasOwn?sumHtml(full.su)+`<div class="srcnote" style="margin-top:6px">${full.su.source==='parsed'?'Read from the structured abstract in the document.':full.su.source==='manual'?'Curated summary (stored in _summaries.yaml next to the file).':'Generated by the LLM.'}</div>`
        :p&&p.summary&&SUM_FIELDS.some(([k])=>p.summary[k])?`<div class="srcnote" style="margin-bottom:8px">No summary of its own${['manuscript','abstract','notes','reviewer_response','questionnaire'].includes(d.ro)&&!d.la?' (older version)':''}. Showing the project summary:</div>`+sumHtml(p.summary)
        :sumHtml(null)}
    </section>
    <section><h4>Methods <span class="prov">Draft glossary</span></h4>
      <div class="mchips">${methods.map(m=>`<span class="mchip" title="Source: ${m[3]==='llm'?'LLM':'keyword'}">${esc(METHOD_LABEL[m[0]]||m[1])}${m[2]!=null?`<i>${Math.round(m[2]*100)}%</i>`:''}</span>`).join('')||'<span class="srcnote">none detected</span>'}</div>
    </section>
    ${full.kw&&full.kw.length?`<section><h4>Keywords</h4><div class="mchips">${full.kw.map(k=>`<span class="tagl">${esc(k)}</span>`).join('')}</div></section>`:''}
    ${typeof legalDocHtml==='function'?legalDocHtml(full):''}
    ${typeof citesHtml==='function'?citesHtml(full):''}
    ${siblings.length>1?`<section><h4>Versions (${siblings.length})</h4><div class="vlist">${siblings.map(s=>`<button type="button" data-id="${esc(s.id)}" class="${s.id===id?'cur':''}"><span><b>v${esc(s.v||'–')}</b>${s.la?'<span class="latest">latest</span>':''}<div class="rp">${esc(s.rp)}</div></span><span class="num">${esc(s.d||'')}</span></button>`).join('')}</div></section>`:''}
  `;
  wireDbPicker('drDb',async dbs=>{const all=d.pn&&$('#drDbAll')&&$('#drDbAll').checked;await assignDbs(all?{project:d.pn}:{doc:id},dbs);openDoc(id)});
  $('#drBody').querySelectorAll('.vlist button').forEach(b=>b.addEventListener('click',()=>openDoc(b.dataset.id)));
  if(typeof wireLegalDoc==='function')wireLegalDoc($('#drBody'));
  $('#drBody').querySelectorAll('.ci-list [data-open]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();openDoc(b.dataset.open)}));   // REQ-35
  const inB=!$('#page-graph').hidden&&$('#cgDocSlot');
  $('#drAsk').addEventListener('click',()=>{
    if(inB){const g=$('#graphInput');g.value=`What is in "${d.fn||d.ti}"${d.pn?` (project ${d.pn})`:''}? `;g.focus();return}   // B page: ask the Graph Chat, stay on the page
    closeDrawer();showPage('chat');$('#ragInput').value=`@project:${d.pn||''} What is in "${d.fn}"? `.replace('@project: ','');$('#ragInput').focus()});
  const dr=$('#drawer');
  if(inB){   // REQ-02: the knowledge map stays visible and usable – details open in the projects & clusters area
    if(dr.parentElement!==$('#cgDocSlot'))$('#cgDocSlot').appendChild(dr);
    dr.classList.add('docked');dr.hidden=false;$('#scrim').hidden=true;$('#page-graph .bq-cluster').classList.add('doc-open');
    $('#page-graph .bq-cluster .bq-body').scrollTop=0;
    if(d.ci!=null&&typeof CG!=='undefined'&&CG.sel!==d.ci){CG.sel=d.ci;try{renderClusterPage()}catch(e){}}   // the map marks the document's cluster
  }else{
    if(dr.classList.contains('docked')){document.body.appendChild(dr);dr.classList.remove('docked')}
    dr.hidden=false;$('#scrim').hidden=false;
  }
}
function closeDrawer(){const dr=$('#drawer');dr.hidden=true;$('#scrim').hidden=true;const q=$('#page-graph .bq-cluster');if(q)q.classList.remove('doc-open');
  if(dr.classList.contains('docked')){document.body.appendChild(dr);dr.classList.remove('docked')}}
$('#drBack').addEventListener('click',closeDrawer);
$('#drClose').addEventListener('click',closeDrawer);$('#scrim').addEventListener('click',closeDrawer);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();$('#upload').hidden=true}});
function fmtSize(b){if(b==null)return '–';return b<1024?b+' B':b<1048576?(b/1024).toFixed(0)+' KB':(b/1048576).toFixed(1)+' MB'}

/* ---------- Upload ---------- */
const KIND_N=(t,n)=>({research_paper:'paper',research_notes:'note',legal_guideline:'guideline',standard:'standard',guidance:'guidance page',legal_project:'legal project'}[t]||'file')+(n>1?'s':'');
const ZIP_T=t=>t==='research_project'||t==='legal_project';   // one ZIP per project (REQ-38: legal projects too)
const LEGAL_HINT={guidance:'One or more Q&A pages, FAQs or factsheets of authorities (one file each, e.g. a web page printed as PDF). ALITA splits them into topics and questions (Q 2.1). A _legal.yaml can give the date of the snapshot; a later snapshot of the same page becomes a new version.',legal_project:'Upload the folder of a law as a ZIP: its versions (proposal, adopted text, consolidated versions) and accompanying documents. A _legal.yaml in the folder gives stages, entry into force and application dates.',legal_guideline:'One or more guidelines (one file each). Versions of the same guideline can be grouped with a _legal.yaml.',standard:'One or more standards (one file each). Check that the licence allows storing the full text.'};
function openUpload(t){
  if(t)$$('input[name=utype]').forEach(r=>r.checked=r.value===t);
  syncUpload();$('#upload').hidden=false;
}
function syncUpload(){
  const t=$('input[name=utype]:checked').value;
  $('#uProjWrap').hidden=ZIP_T(t)||LEGAL_T.has(t);
  $('#uFiles').accept=ZIP_T(t)?'.zip':'.pdf,.docx,.doc,.txt,.md,.pptx';
  $('#uFiles').multiple=!ZIP_T(t);
  $('#uHint').textContent=ZIP_T(t)
    ?'Upload the project folder as a ZIP. The folder name becomes the project name, and every file inside is linked to the project. The "Literatur" folder is skipped.'
    :LEGAL_HINT[t]||(t==='research_paper'?'One or more papers. Optionally link them to a project.':'Notes, minutes, idea collections. Optionally link them to a project.');
}
$$('input[name=utype]').forEach(r=>r.addEventListener('change',syncUpload));
$('#openUpload').addEventListener('click',()=>openUpload());
/* ---------- "Add new data" (button in the database bar): database · type · overall date · files ---------- */
const AD={db:null,type:null};
function adOpen(){
  AD.db=SEL_DB.length===1?SEL_DB[0]:AD.db;AD.type=AD.type||null;
  const n=db=>DOCS.filter(d=>(d.db||[]).includes(db)).length;
  $('#adDbs').innerHTML=DATABASES.map(db=>`<label class="ad-db" style="--c:${dbColor(db)}"><input type="radio" name="addb" value="${esc(db)}" ${AD.db===db?'checked':''}><span class="ad-fl">${dbIcon(db)}</span><b>${esc(dbName(db))}</b><small>${n(db)} docs</small></label>`).join('');
  $$('input[name=addb]').forEach(r=>r.addEventListener('change',()=>{AD.db=r.value;adSync()}));
  $$('input[name=adtype]').forEach(r=>r.checked=r.value===AD.type);
  $('#adFiles').value='';$('#adProject').value='';$('#adDate').value='';
  adSync();$('#addData').hidden=false;
  setTimeout(()=>($('input[name=addb]:checked')||$('input[name=addb]')).focus(),30);
}
function adSync(){
  const t=AD.type,files=[...$('#adFiles').files];
  $('#adFiles').accept=ZIP_T(t)?'.zip':'.pdf,.docx,.doc,.txt,.md,.pptx';
  $('#adFiles').multiple=true;
  $('#adProjWrap').hidden=!t||ZIP_T(t)||LEGAL_T.has(t);
  $('#adDateQ').textContent=ZIP_T(t)?'Which overall date should the project get?':t==='research_paper'?'Which date should the papers get (e.g. publication)?':t==='research_notes'?'Which date should the notes get?':'Which overall date should the data get?';
  $('#adDateHint').textContent=ZIP_T(t)?'Optional. Files with their own document date keep it (the version history needs it); files without a reliable date and the project itself get this date.'
    :'Optional. Leave empty to take the dates from the files.';
  $('#adDropText').innerHTML=files.length?`<b>${files.length} file${files.length>1?'s':''}</b>: ${esc(files.slice(0,3).map(f=>f.name).join(', '))}${files.length>3?' …':''}`
    :ZIP_T(t)?'Drop the projects here – <b>one ZIP per project</b> – or <u>choose files</u>':'Drop files here or <u>choose files</u>';
  const ok=AD.db&&t&&files.length;$('#adGo').disabled=!ok;
  $('#adGo').textContent=AD.db?`Add to ${dbName(AD.db)}`:'Add data';
  $('#adSum').textContent=!AD.db?'Choose a database.':!t?'Choose the kind of data.':!files.length?'Choose the files.'
    :`${files.length} ${ZIP_T(t)?(files.length>1?'projects (one ZIP each)':'project (ZIP)'):KIND_N(t,files.length)} → ${dbName(AD.db)}${$('#adDate').value?' · dated '+$('#adDate').value:' · dates from the files'}`;
}
$$('input[name=adtype]').forEach(r=>r.addEventListener('change',()=>{AD.type=r.value;adSync()}));
['change','input'].forEach(ev=>{$('#adFiles').addEventListener(ev,adSync);$('#adDate').addEventListener(ev,adSync)});
$('#adDateClear').addEventListener('click',()=>{$('#adDate').value='';adSync()});
const adDrop=$('#adDrop');
['dragenter','dragover'].forEach(ev=>adDrop.addEventListener(ev,e=>{e.preventDefault();adDrop.classList.add('over')}));
['dragleave','drop'].forEach(ev=>adDrop.addEventListener(ev,()=>adDrop.classList.remove('over')));
adDrop.addEventListener('drop',e=>{e.preventDefault();if(e.dataTransfer.files.length){$('#adFiles').files=e.dataTransfer.files;adSync()}});
$$('[data-adclose]').forEach(b=>b.addEventListener('click',()=>$('#addData').hidden=true));
$('#addData').addEventListener('click',e=>{if(e.target===$('#addData'))$('#addData').hidden=true});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!$('#adConfirm').hidden){$('#adConfirm').hidden=true;return}$('#addData').hidden=true});
/* 3.6.0 (REQ-54): the "+ Add new data" button was removed from the database bar; uploads go via Documents → + Upload */
if($('#dbAdd'))$('#dbAdd').addEventListener('click',adOpen);
/* Second window before the upload: confirms the choice; for projects it checks that every project is one ZIP */
$('#addForm').addEventListener('submit',e=>{
  e.preventDefault();const files=[...$('#adFiles').files];
  if(!AD.db||!AD.type||!files.length){adSync();return}
  const t=AD.type,date=$('#adDate').value,zip=f=>/\.zip$/i.test(f.name);
  const list=fs=>`<ul class="adc-files">${fs.map(f=>`<li class="${ZIP_T(t)?(zip(f)?'ok':'bad'):''}"><span>${ZIP_T(t)?(zip(f)?'✓':'✗'):'•'}</span>${esc(f.name)}${ZIP_T(t)&&zip(f)?` <small>→ project “${esc(f.name.replace(/\.zip$/i,''))}”*</small>`:''}</li>`).join('')}</ul>`;
  let body,ok=true,need=false;
  if(ZIP_T(t)){
    const bad=files.filter(f=>!zip(f));ok=!bad.length;need=ok;
    body=`<p class="adc-q"><b>Is every project delivered as its own ZIP file?</b></p>
      <p>Each ZIP becomes <b>one ${t==='legal_project'?'legal project':'research project'}</b> in <b>${esc(dbName(AD.db))}</b>; the folder inside the ZIP gives the project its name. Several projects = several ZIP files, never several projects in one ZIP.</p>
      ${list(files)}
      ${bad.length?`<p class="adc-warn">${bad.length===1?'This file is':'These files are'} not a ZIP: ${esc(bad.map(f=>f.name).join(', '))}. Pack each project folder into its own ZIP, then try again.</p>`
        :`<label class="check adc-check"><input type="checkbox" id="adcSure"> Yes – ${files.length===1?'this ZIP contains exactly one project':`these ${files.length} ZIPs contain one project each`}</label>
          <p class="adc-note">* The final name comes from the folder inside the ZIP. Date: ${date?esc(date)+' for the project and its files without a date of their own':'taken from the files'}.</p>`}`;
  }else{
    const zips=files.filter(zip);
    body=`<p class="adc-q"><b>Upload ${files.length} ${KIND_N(t,files.length)} to ${esc(dbName(AD.db))}?</b></p>${list(files)}
      <p>Date: ${date?esc(date):'taken from the files'}${$('#adProject').value.trim()?` · linked to project ${esc($('#adProject').value.trim())}`:''}</p>
      ${zips.length?`<p class="adc-warn">${esc(zips.map(f=>f.name).join(', '))} ${zips.length>1?'are ZIP files':'is a ZIP file'}. If it is a project folder, go back and choose “Research project”.</p>`:''}`;
  }
  $('#adcBody').innerHTML=body;
  const go=$('#adcGo');go.hidden=!ok;go.disabled=need;go.textContent=ZIP_T(t)?`Upload ${files.length} project${files.length>1?'s':''}`:'Upload';
  const sure=$('#adcSure');if(sure)sure.addEventListener('change',()=>go.disabled=!sure.checked);
  $('#adConfirm').hidden=false;(sure||go.hidden?$('#adcBack'):go).focus();
});
$('#adcBack').addEventListener('click',()=>$('#adConfirm').hidden=true);
$('#adcGo').addEventListener('click',async()=>{
  $('#adConfirm').hidden=true;const files=[...$('#adFiles').files];
  if(!LIVE){$('#addData').hidden=true;toast('Demo mode: adding data requires the running backend');return}
  const fd=new FormData();
  fd.append('doc_type',AD.type);files.forEach(f=>fd.append('files',f));fd.append('databases',AD.db);
  if($('#adDate').value)fd.append('date',$('#adDate').value);
  if(!ZIP_T(AD.type)&&$('#adProject').value.trim())fd.append('project_name',$('#adProject').value.trim());
  fd.append('use_llm',$('#adLlm').checked);
  $('#adGo').disabled=true;$('#adGo').textContent='Uploading…';
  try{
    const r=await fetch('api/ingest',{method:'POST',body:fd,headers:headers(false)});
    if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||r.status);
    const {jobs}=await r.json();$('#addData').hidden=true;toast(`${dbName(AD.db)}: processing started (${jobs.length} job${jobs.length===1?'':'s'})`);
    pollJobs(jobs);
  }catch(err){toast('Upload failed: '+err.message);adSync()}
});

$('#uCancel').addEventListener('click',()=>$('#upload').hidden=true);
$('#uploadForm').addEventListener('submit',async e=>{
  e.preventDefault();
  const files=$('#uFiles').files;
  if(!files.length){toast('Please choose a file');return}
  if(!LIVE){$('#upload').hidden=true;toast('Demo mode: uploading requires the running backend');return}
  const fd=new FormData();
  fd.append('doc_type',$('input[name=utype]:checked').value);
  [...files].forEach(f=>fd.append('files',f));
  if($('#uProject').value.trim())fd.append('project_name',$('#uProject').value.trim());
  fd.append('use_llm',$('#uLlm').checked);
  const udb=pickedDbs('#uDbs');if(udb.length)fd.append('databases',udb.join(','));
  try{
    const r=await fetch('api/ingest',{method:'POST',body:fd,headers:headers(false)});
    if(!r.ok)throw new Error((await r.json()).detail||r.status);
    const {jobs}=await r.json();$('#upload').hidden=true;toast(`Processing started (${jobs.length} job${jobs.length===1?'':'s'})`);
    pollJobs(jobs);
  }catch(err){toast('Upload failed: '+err.message)}
});
async function pollJobs(ids){
  const open=new Set(ids),done=[];
  while(open.size){
    await new Promise(r=>setTimeout(r,2500));
    for(const id of [...open]){
      const j=await fetch('api/jobs/'+id).then(r=>r.json()).catch(()=>null);
      if(!j||j.status==='done'||j.status==='error'){open.delete(id);done.push(j||{status:'error',name:id,error:'job not found'});
        toast(j&&j.status==='error'?`Error in ${j.name}: ${j.error}`:`Done: ${j?j.name:id}`)}
    }
  }
  loadDocs();
  try{uploadReport(done)}catch(e){console.error('upload report',e)}
}
/* After an upload: ALITA tells how many tokens it took and what that cost in euro */
function uploadReport(jobs){
  if(!jobs.length)return;
  const u=jobs.map(j=>j.usage).filter(Boolean),sum=k=>u.reduce((a,x)=>a+(+x[k]||0),0);
  const ok=jobs.filter(j=>j.status==='done').length,bad=jobs.length-ok;
  const n=v=>Math.round(v).toLocaleString('en');
  const tok=sum('tokens'),eur=sum('eur'),usd=sum('usd'),cin=sum('chat_input'),cout=sum('chat_output'),req=sum('chat_requests'),emb=sum('embedding');
  const est=u.some(x=>x.embedding_estimated),src=u.some(x=>x.price_source==='openrouter')?'live OpenRouter prices':'estimated prices',rate=(u[0]||{}).usd_to_eur;
  const head=`<b class="cw-step">Upload done! 🎉</b> ${ok} of ${jobs.length} ${jobs.length>1?'jobs':'job'} finished${bad?` · <span class="cw-bad">${bad} with errors</span>`:''}.`;
  let body;
  if(!u.length)body='<br>I could not count the tokens this time – the backend did not report them (it may need an update).';
  else if(!tok)body='<br>No AI tokens used – the files were only indexed, without the LLM. Cost: <b>€0.00</b> 🌱';
  else body=`<br>You burned through <b class="cw-big">${n(tok)} tokens</b>:
    <span class="cw-ab"><i class="cw-a1">✎</i>reading &amp; summarizing: ${n(cin)} in · ${n(cout)} out <small>(${n(req)} request${req===1?'':'s'}, ${fmtEur(sum('chat_eur'))})</small></span>
    <span class="cw-ab"><i class="cw-b1">∿</i>embeddings: ${n(emb)}${est?' <small>(estimated)</small>':''} <small>(${fmtEur(sum('embedding_eur'))})</small></span>
    That’s about <b class="cw-big">${fmtEur(eur)}</b> <small>(≈ $${usd.toFixed(usd<0.01?4:2)})</small>.
    <span class="cw-tip">${src}${rate?` · 1 USD ≈ ${rate} EUR`:''}</span>`;
  if(typeof window.alitaSay==='function')window.alitaSay(head+body);
  else toast(`Upload done – ${n(tok)} tokens ≈ ${fmtEur(eur)}`);
}

/* ======================================================================
   CHAT – tile 1
   ====================================================================== */
$$('.chip').forEach(c=>c.addEventListener('click',()=>c.setAttribute('aria-pressed',c.getAttribute('aria-pressed')!=='true')));
$('#ragK').addEventListener('input',e=>$('#ragKOut').textContent=e.target.value);
$('#gHops').addEventListener('input',e=>$('#gHopsOut').textContent=e.target.value);

function parsePromptFilters(text){const f=[];const clean=text.replace(/@([\wäöüß]+):(?:"([^"]+)"|([^\s,;]+))/gi,(m,k,a,b)=>{f.push(k.toLowerCase()+':'+(a||b));return ''}).replace(/\s{2,}/g,' ').trim();return {clean,f}}

let uid=0;
function spChip(sp){if(!sp)return '';return `<span class="qsp ${sp.src}" title="${esc((sp.src==='custom'?'Custom':'Default')+' system prompt:\n'+sp.text)}">⚙ ${sp.src==='custom'?'custom':'default'} system prompt</span>`}
function userMsg(chat,text,filters,meta,sp){
  const d=document.createElement('div');d.className='msg user';
  d.innerHTML=`<div class="bubble">${esc(text)}</div>`+(filters.length?`<div class="meta-line">${filters.map(f=>`<span class="applied">@${esc(f)}</span>`).join('')}</div>`:'')+`<div class="qmeta">${metaHtml(meta)}</div>`+(sp?`<div class="qspline">${spChip(sp)}</div>`:'');
  chat.appendChild(d);chat.scrollTop=chat.scrollHeight;return d;
}
