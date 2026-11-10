/* Database information panel: contents, cluster descriptions and excluded files of a database. */
/* ---------- Database information: contents and cluster descriptions ---------- */
function dbClusterCardHtml(c,n,info,dbsAll,openLinks){   // cluster card of the database info panel (own name: cluster-profile.js has clusterCardHtml(ci))
  const has=u=>!n||(u.db||[]).includes(n),mineN=c.all.filter(has).length;
  const i=info[c.id]||{},per=dbsAll.map(x=>({x,k:c.all.filter(u=>(u.db||[]).includes(x)).length})).filter(o=>o.k),tot=per.reduce((a,o)=>a+o.k,0)||1;
  const tag=per.length>1?`<span class="tag shared">shared${n?' with '+esc(per.filter(o=>o.x!==n).map(o=>dbName(o.x)).join(', ')):' · '+esc(per.map(o=>dbName(o.x)).join(', '))}</span>`:`<span class="tag only">only ${esc(per[0]?dbName(per[0].x):'')}</span>`;
  const list=c.all.filter(has);
  return `<div class="ccard" style="--h:${cvHue(c.id)}"><h5><b>C${c.id}</b>${esc(cvName(c))}${tag}</h5>
    ${i.description?`<p>${esc(i.description)}</p>`:`<p class="srcnote">No description yet – with an API key the backend writes one when the clusters are recomputed.</p>`}
    <div class="terms">Distinctive terms: ${esc(c.label)}</div>
    <div class="share"><span class="bar">${per.map(o=>`<i style="--c:var(--db-${esc(o.x)});width:${o.k/tot*100}%" title="${esc(dbName(o.x))}: ${o.k}"></i>`).join('')}</span><span>${n?`${mineN} of ${c.all.length} from ${esc(dbName(n))}`:per.map(o=>`${esc(dbName(o.x))} ${o.k}`).join(' · ')}</span></div>
    <details ${openLinks?'open':''}><summary>${list.length} document${list.length>1?'s':''}${n?' from '+esc(dbName(n)):''}</summary><ul>${list.map(u=>`<li>${openLinks&&u.id?`<a href="#" data-open="${esc(u.id)}">${esc(u.ti||'')}</a>`:esc(u.ti||'')} <span class="srcnote">${CV_TYPE[u.t]||''}${n?'':' · '+esc(dbNames(u.db).join(', '))}</span></li>`).join('')}</ul></details>
    ${openLinks?'':`<div><button class="mini" type="button" data-cl="${c.id}">Filter Document Chat to C${c.id}</button></div>`}</div>`;
}

function clusterInfo(){
  const info={};
  if(!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.desc){Object.entries(DEMO.clusters.desc).forEach(([k,v])=>info[+k]={...v,source:DEMO.clusters.desc_source||''});return info}
  DOCS.forEach(d=>{if(d.ci==null||!(d.ct||d.cd))return;const o=info[d.ci];if(!o)info[d.ci]={title:d.ct,description:d.cd,source:d.cd?'LLM, names pseudonymized':''};else{if(!o.title&&d.ct)o.title=d.ct;if(!o.description&&d.cd){o.description=d.cd;o.source='LLM, names pseudonymized'}}});
  return info;
}
/* REQ-08: files of the database's projects that the exclusion rules skip (e.g. literature folders), with the reason */
const EXCL_REASON={'*Literatur*/*':'literature folders','**/~$*':'Office temp files','**/.DS_Store':'system files','**/Thumbs.db':'system files'};
function dbExcludedHtml(projNames){
  const ps=PROJECTS.filter(p=>projNames.includes(p.name));if(!ps.length)return '';
  if(ps.every(p=>p.exc==null))return `<dt>Excluded files</dt><dd class="srcnote">not counted yet – needs the current backend</dd>`;
  const n=ps.reduce((a,p)=>a+(p.exc||0),0),by={};ps.forEach(p=>Object.entries(p.excBy||{}).forEach(([k,v])=>{const r=EXCL_REASON[k]||k;by[r]=(by[r]||0)+v}));
  const files=ps.reduce((a,p)=>a+(p.files||0),0);
  return `<dt>Excluded files</dt><dd title="Files in the project folders that are not loaded on purpose (setting PROJECT_EXCLUDE). ${files} files loaded + ${n} excluded = ${files+n} files in the folders.">${n?`${n} – ${esc(Object.entries(by).sort((a,b)=>b[1]-a[1]).map(([r,v])=>`${r} (${v})`).join(', '))}`:'none'}<br><small class="srcnote">${files} loaded + ${n} excluded = ${files+n} files in the folders</small></dd>`;
}
function openDbInfo(n,allDbs){
  const units=cvUnits(),cls=cvClusters(units),info=clusterInfo();
  const dbsAll=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
  const has=u=>!n||(u.db||[]).includes(n);
  const mine=units.filter(has);
  let h='';
  if(n){
    const docs=DOCS.filter(d=>(d.db||[]).includes(n));const ct=t=>docs.filter(d=>d.t===t).length;
    const years=docs.map(d=>d.y).filter(Boolean),langs=[...new Set(docs.map(d=>d.lg).filter(Boolean))];
    const meth={};docs.forEach(d=>(d.me||[]).forEach(m=>meth[m]=(meth[m]||0)+1));
    const topM=Object.entries(meth).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([m,c])=>`${esc(METHOD_LABEL[m]||m)} (${c})`).join(', ');
    const projs=[...new Set(docs.map(d=>d.pn).filter(Boolean))].filter(p=>docs.some(d=>d.pn===p&&d.t==='research_project'));
    h+=`<div class="dbp-head" style="--c:var(--db-${esc(n)})"><span class="sw"></span><span class="srcnote">${SEL_DB.includes(n)?'selected for chat':'not selected'}</span></div>`;
    h+=docs.length?`<section><h4>Contents</h4><dl class="kv">
      <dt>Research papers</dt><dd>${ct('research_paper')}</dd><dt>Research notes</dt><dd>${ct('research_notes')}</dd>
      <dt>Research projects</dt><dd>${projs.length?esc(projs.join(', '))+` (${ct('research_project')} files)`:'–'}</dd>
      <dt>Years</dt><dd>${years.length?Math.min(...years)+' – '+Math.max(...years):'–'}</dd>
      <dt>Languages</dt><dd>${langs.length?esc(langs.join(', ')):'–'}</dd>
      <dt>Main methods</dt><dd>${topM||'–'}</dd>${dbExcludedHtml(projs)}</dl></section>`:`<p class="srcnote">No documents are assigned to ${esc(dbName(n))} yet.</p>`;
    h+=`<div class="dbp-actions"><button class="btn ${SEL_DB.includes(n)?'':'primary'}" type="button" data-act="chat">${SEL_DB.includes(n)?'Remove from chat selection':'Use for chat'}</button>${dbsAll.length>1&&docs.length?`<button class="btn" type="button" data-act="compare">Compare on cluster map</button>`:''}</div>`;
  }else{
    const nd=DATABASES.filter(x=>units.some(u=>(u.db||[]).includes(x)));
    h+=`<p class="srcnote">All ${cls.length} clusters of the latest run across all databases (${esc(dbNames(nd).join(', '))}), with the share of each database. Data points: ${units.length} papers, notes and projects, represented by their structured summaries (semantic embeddings).</p>`;
  }
  const rel=cls.map(c=>({c,mineN:c.all.filter(has).length})).filter(x=>x.mineN).sort((a,b)=>b.mineN-a.mineN||a.c.id-b.c.id);
  h+=`<section><h4>${n?`Clusters with ${esc(dbName(n))} documents`:'Clusters'} (${rel.length})</h4>`;
  h+=rel.length?rel.map(({c})=>dbClusterCardHtml(c,n,info,dbsAll)).join(''):`<p class="srcnote">No clustered documents${n?' in '+esc(dbName(n)):''} yet.</p>`;
  h+=`</section>`;
  const src=Object.values(info)[0];
  if(src&&src.source)h+=`<p class="srcnote">Descriptions: ${esc(src.source)}.${!LIVE&&DEMO&&DEMO.clusters&&DEMO.clusters.model?' Clusters: semantic embeddings ('+esc(DEMO.clusters.model)+').':''}</p>`;
  $("#dbpTitle").textContent=n?`Database ${dbName(n)} (${n})`:'Cluster descriptions';
  $('#dbpBody').innerHTML=h;
  $$('#dbpBody [data-cl]').forEach(b=>b.addEventListener('click',()=>{showPage('chat');cvSelect(+b.dataset.cl,true);closeDbInfo()}));
  const act=a=>$(`#dbpBody [data-act="${a}"]`);
  if(act('chat'))act('chat').addEventListener('click',()=>{const ic=$(`#dbs .db[data-db="${n}"] svg`);setDbSel(SEL_DB.includes(n)?SEL_DB.filter(x=>x!==n):[...SEL_DB,n],ic&&ic.getBoundingClientRect(),ic&&getComputedStyle(ic).color);openDbInfo(n)});
  if(act('compare'))act('compare').addEventListener('click',()=>{if(!SEL_DB.includes(n)){const ic=$(`#dbs .db[data-db="${n}"] svg`);setDbSel([...SEL_DB,n],ic&&ic.getBoundingClientRect(),ic&&getComputedStyle(ic).color)}CV.mode='db';try{localStorage.setItem('cv_mode','db')}catch(e){}cvSyncMode();showPage('chat');renderClusterViz();closeDbInfo()});
  $('#dbPanel').hidden=false;$('#scrim').hidden=false;
}
function closeDbInfo(){$('#dbPanel').hidden=true;if($('#drawer').hidden&&$('#histPanel').hidden)$('#scrim').hidden=true}
$('#dbpClose').addEventListener('click',closeDbInfo);
$('#scrim').addEventListener('click',closeDbInfo);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDbInfo()});
$('#dbInfoAll').addEventListener('click',()=>openDbInfo(null));
