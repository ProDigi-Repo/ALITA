/* ---------- Clusters ---------- */
function clusterTag(d,big){if(d.ci==null)return '<span class="srcnote">–</span>';return `<span class="ctag ${big?'big':''}" style="--h:${(d.ci*67)%360}" title="Cluster ${d.ci}: ${esc(d.cl||'')}"><b>C${d.ci}</b><span>${esc(d.cl||'')}</span></span>`}
function CLUSTER_NOTE(){const c=(!LIVE&&DEMO&&DEMO.clusters)||null;const model=c&&c.model?` (${c.model}, ${c.dim} dimensions)`:'';return `Semantic clustering: k-means on the embeddings${model} of the structured summaries (title, purpose, design/methodology/approach, findings, research limitations/implications, originality/value); cluster count chosen by silhouette. Data points: one per research paper, one per research note and one per research project. Files inside a project inherit the project's cluster. Person names in cluster labels are replaced by Pokémon pseudonyms.`}

/* ---------- Release notes (Quelle: CHANGELOG.md; live über /api/release-notes) ---------- */
function mdInline(t){return esc(t).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')}
const REL_ORDER=['Requirements','Added','Changed','Deprecated','Removed','Fixed','Security','Open points'];
function relSections(r){const sec=r.sections&&Object.keys(r.sections).length?r.sections:{Changed:r.changes||[]};
  return REL_ORDER.filter(k=>sec[k]&&sec[k].length).map(k=>`<div class="relsec"><span class="relkind k-${k.toLowerCase().replace(/\s+/g,'-')}">${k}</span><ul>${sec[k].map(c=>`<li>${mdInline(c)}</li>`).join('')}</ul></div>`).join('')}
function closeRel(){if($('#drawer').hidden&&$('#histPanel').hidden)$('#scrim').hidden=true}
$('#appVersion').addEventListener('click',()=>showPage('release'));
$('#scrim').addEventListener('click',closeRel);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeRel()});



/* ---------- Release Notes page ---------- */
async function getReleases(){
  if(LIVE){try{const r=await fetch('api/release-notes').then(r=>r.json());if(r.releases&&r.releases.length)return r.releases}catch(e){}}
  return RELEASES_FALLBACK;
}
async function renderReleasePage(){
  const rel=await getReleases();
  $('#relToc').innerHTML='<h4>Versions</h4>'+rel.map(r=>`<a href="#rel-${esc(r.version)}" data-v="${esc(r.version)}" class="${r.version===APP_VERSION?'on':''}${r.highlight?' special':''}">${r.highlight?'<i aria-label="special release">★</i>':''}v${esc(r.version)}<small>${esc(r.date||'')}</small></a>`).join('');
  $('#relPage').innerHTML=`<h1>Release notes</h1><p class="lead">Frontend v${APP_VERSION}${BACKEND_VERSION?' · Backend v'+esc(BACKEND_VERSION):''} · format <a href="https://keepachangelog.com/en/1.1.0/" target="_blank" rel="noopener">Keep a Changelog 1.1.0</a> · versions follow <a href="https://semver.org/spec/v2.0.0.html" target="_blank" rel="noopener">Semantic Versioning 2.0.0</a> · source: CHANGELOG.md</p>`+
    rel.map(r=>`<section class="rel ${r.version===APP_VERSION?'cur':''}${r.highlight?' special':''}" id="rel-${esc(r.version)}"><h4><code>v${esc(r.version)}</code><span>${esc(r.date||'')}</span>${r.version===APP_VERSION?'<span class="now">current</span>':''}${r.highlight?'<span class="special-badge">★ special release</span>':''}</h4>${r.highlight?`<div class="rel-highlight">${mdInline(r.highlight)}</div>`:''}${relSections(r)}</section>`).join('');
  $$('#relToc a').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();$$('#relToc a').forEach(x=>x.classList.toggle('on',x===a));const t=document.getElementById('rel-'+a.dataset.v);if(t)t.scrollIntoView({behavior:'smooth',block:'start'})}));
}

/* ---------- ISO 42001 / EU AI Act docs page ---------- */
let CMP_DOCS=null,CMP_SEL=null;
try{CMP_SEL=localStorage.getItem('cmp_doc')}catch(e){}
function mdInline2(t){return esc(t).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/(^|[\s(])_([^_]+)_(?=[\s).,;:]|$)/g,'$1<i>$2</i>').replace(/\*([^*\s][^*]*)\*/g,'<i>$1</i>').replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>')}
function mdRender(md){
  const L=md.replace(/\r/g,'').split('\n');let out='',i=0;
  const cells=l=>l.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
  while(i<L.length){
    const l=L[i];
    if(!l.trim()){i++;continue}
    if(l.trim().startsWith('```')){let c=[];i++;while(i<L.length&&!L[i].trim().startsWith('```')){c.push(L[i]);i++}i++;out+=`<pre><code>${esc(c.join('\n'))}</code></pre>`;continue}
    let m=l.match(/^(#{1,4})\s+(.*)$/);
    if(m){const n=m[1].length;out+=`<h${n}>${mdInline2(m[2])}</h${n}>`;i++;continue}
    if(l.startsWith('>')){let b=[];while(i<L.length&&L[i].startsWith('>')){b.push(L[i].replace(/^>\s?/,''));i++}out+=`<blockquote><p>${mdInline2(b.join(' '))}</p></blockquote>`;continue}
    if(l.trim().startsWith('|')&&i+1<L.length&&/^\s*\|?\s*:?-{2,}/.test(L[i+1])){
      const head=cells(l);i+=2;let rows=[];while(i<L.length&&L[i].trim().startsWith('|')){rows.push(cells(L[i]));i++}
      out+=`<table><thead><tr>${head.map(h=>`<th>${mdInline2(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${mdInline2(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;continue}
    if(/^\s*([-*]|\d+\.)\s+/.test(l)){
      const ol=/^\s*\d+\./.test(l);let items=[];
      while(i<L.length&&/^\s*([-*]|\d+\.)\s+/.test(L[i])){items.push(L[i].replace(/^\s*([-*]|\d+\.)\s+/,''));i++}
      out+=`<${ol?'ol':'ul'}>${items.map(x=>`<li>${mdInline2(x)}</li>`).join('')}</${ol?'ol':'ul'}>`;continue}
    let p=[];while(i<L.length&&L[i].trim()&&!/^(#|>|\s*\||\s*([-*]|\d+\.)\s)/.test(L[i])){p.push(L[i]);i++}
    if(!p.length){p.push(l);i++}
    out+=`<p>${mdInline2(p.join(' '))}</p>`;
  }
  return out;
}
async function getComplianceDocs(){
  if(CMP_DOCS)return CMP_DOCS;
  if(LIVE){try{const r=await fetch('api/compliance-docs').then(r=>r.json());if(r.docs&&r.docs.length)return CMP_DOCS=r.docs}catch(e){}}
  return CMP_DOCS=COMPLIANCE_FALLBACK;
}
async function renderCompliancePage(){
  const docs=await getComplianceDocs();
  if(!docs.length){$('#cmpPage').innerHTML='<p class="lead">No documents in docs/compliance yet.</p>';return}
  if(!docs.find(d=>d.id===CMP_SEL))CMP_SEL=docs[0].id;
  const idx=docs.findIndex(d=>d.id===CMP_SEL),d=docs[idx];
  $('#cmpToc').innerHTML='<h4>ISO/IEC 42001 · EU AI Act</h4>'+docs.map((x,i)=>`<a href="#" data-id="${esc(x.id)}" class="${x.id===CMP_SEL?'on':''}">${i+1}. ${esc(x.title)}</a>`).join('')+
    `<p class="srcnote" style="margin:10px 8px 2px">Drafts for review, not legal advice. Source: <code>docs/compliance/*.md</code> · app v${APP_VERSION}</p>`;
  const prev=docs[idx-1],next=docs[idx+1];
  $('#cmpPage').innerHTML=mdRender(d.markdown)+`<div class="docnav">${prev?`<button class="mini" data-id="${esc(prev.id)}">← ${esc(prev.title)}</button>`:'<span></span>'}${next?`<button class="mini" data-id="${esc(next.id)}">${esc(next.title)} →</button>`:''}</div>`;
  const go=id=>{CMP_SEL=id;try{localStorage.setItem('cmp_doc',id)}catch(e){}renderCompliancePage();$('#cmpPage').scrollTop=0;window.scrollTo({top:0})};
  $$('#cmpToc a').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();go(a.dataset.id)}));
  $$('#cmpPage .docnav button').forEach(b=>b.addEventListener('click',()=>go(b.dataset.id)));
}
