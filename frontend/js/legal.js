/* REQ-37/38: legal texts (laws, guidelines, standards) in the interface.
   - under each chat answer: which version/date of the legal texts it refers to (the disclosed temporal policy) and,
     for questions about changes or the origin of a term, the table from the change history (Action nodes);
   - at each source: component and validity of a legal passage;
   - in the document details: the version of the norm (stage, in force from–to, applicable from, what changed). */
const LG_KIND={enacted:'enacted',added:'added',modified:'new wording',removed:'deleted',applicability_changed:'application date changed',renumbered:'renumbered'};

function legalSrcTag(lg){
  if(!lg)return '';
  if(lg.kind==='action')return `${lg.component||''} · change ${lg.date||''}`;
  const st=lg.valid_from?`in force ${lg.valid_from} – ${lg.valid_to||'today'}`:(lg.stages||[]).map(s=>STAGE_LABEL[s]||s).join(', ')+' (not in force)';
  return `${lg.component||''} · ${st}${lg.applicable_from?' · applies from '+lg.applicable_from:''}`;
}

function legalBlockHtml(a){
  const t=a.temporal;if(!t)return '';
  const lg=a.legal||{};
  let h=`<div class="lg-scope" title="How ALITA chose the versions of laws, guidelines and standards for this answer (policy of the temporal planner)"><span class="lbl">⏱ Legal texts</span>${esc(t.label||'')}${t.source==='settings'?' <i>(date from the settings)</i>':''}</div>`;
  if((lg.texts||[]).length)h+=`<div class="lg-note">Exact text used: ${lg.texts.map(x=>`<b>${esc(x.norm)} ${esc(x.component)}</b> (${esc(x.state)})`).join('; ')}</div>`;
  if((lg.changes||[]).length){
    const rows=lg.changes.slice(0,60).map(c=>`<tr><td>${esc(c.date||'–')}</td><td>${esc(c.norm)}</td><td>${esc(c.component)}</td><td>${esc(LG_KIND[c.kind]||c.kind)}</td><td>${esc(c.source||c.stage||'')}</td></tr>`).join('');
    h+=`<details class="lg-tab" open><summary>Changes from the version history (${lg.changes.length})</summary><table><thead><tr><th>Date</th><th>Norm</th><th>Component</th><th>Change</th><th>By</th></tr></thead><tbody>${rows}</tbody></table></details>`;
  }
  if((lg.provenance||[]).length){
    const rows=lg.provenance.map(p=>`<tr><td>${esc(p.norm)}</td><td>${esc(p.component)}</td><td>version ${p.since} · ${esc(p.stage)}${p.valid_from?' · in force '+esc(p.valid_from):''}</td><td>${esc(LG_KIND[p.action]||p.action||'–')}${p.source?' · '+esc(p.source):''}</td></tr>`).join('');
    h+=`<details class="lg-tab" open><summary>Origin of “${esc(t.term||'')}”</summary><table><thead><tr><th>Norm</th><th>Component</th><th>Since</th><th>Introduced by</th></tr></thead><tbody>${rows}</tbody></table></details>`;
  }
  return h;
}

/* document details: section "Legal text" for a version of a law / guideline / standard */
function legalDocHtml(full){
  const lg=full.leg||full.legal;if(!lg)return '';
  const sibl=DOCS.filter(d=>d.leg&&d.leg.norm_id===lg.norm_id).sort((a,b)=>a.leg.seq-b.leg.seq);
  return `<section><h4>Legal text <span class="prov">${lg.kind==='law'?'ELI · LegalResource':lg.kind==='standard'?'standard':lg.kind==='faq'?'guidance & FAQ':'guideline'}</span></h4><dl class="kv">
    <dt>Norm</dt><dd>${esc(lg.norm_title||'')}${lg.eli?` <a class="mono" href="${esc(lg.eli)}" target="_blank" rel="noopener">ELI</a>`:''}</dd>
    <dt>Version</dt><dd>${lg.seq} of ${lg.versions} · ${esc(lg.stage_label||STAGE_LABEL[lg.stage]||lg.stage)}${lg.current?' <span class="latest">current</span>':''}</dd>
    ${(lg.files||[]).length>1?`<dt>Files</dt><dd>${lg.files.map(esc).join(' + ')}</dd>`:''}
    ${(lg.amendments||[]).length?(()=>{const A=lg.amendments,n=k=>A.filter(a=>a.status===k).length,open=A.filter(a=>a.status!=='applied');
      return `<dt>Amendments</dt><dd>generated from the amending act: ${n('applied')} of ${A.length} instructions applied${n('approximate')?`, ${n('approximate')} approximately`:''}${n('not_applied')?`, <b>${n('not_applied')} not applied</b>`:''}${open.length?`<details class="lg-amend"><summary>Show</summary><ul>${open.map(a=>`<li><b>${esc(a.instruction)}</b> ${a.status==='approximate'?'≈':'✗'} ${esc(a.text)}${a.note?` <span class="srcnote">– ${esc(a.note)}</span>`:''}</li>`).join('')}</ul></details>`:''}</dd>`})():''}
    ${lg.partial?`<dt>Scope</dt><dd>only the amended parts <span class="srcnote">(all other parts are taken unchanged from the previous version)</span></dd>`:''}
    <dt>In force</dt><dd>${lg.in_force?esc(lg.in_force)+' – '+esc(lg.valid_to||'today'):'<span class="srcnote">not in force (drafting stage)</span>'}</dd>
    ${lg.applicable?`<dt>Applies from</dt><dd>${esc(lg.applicable)} <span class="srcnote">(some provisions may differ)</span></dd>`:''}
    ${lg.amended_by?`<dt>Amended by</dt><dd>${esc(lg.amended_by.title||lg.amended_by.eli||'')}</dd>`:''}
    <dt>Structure</dt><dd>${lg.components} components${lg.seq>1?` · vs. version ${lg.seq-1}: ${lg.changed} changed, ${lg.added} added, ${lg.removed} removed`:''}</dd>
  </dl>
  ${sibl.length>1?`<div class="vlist lg-vers">${sibl.map(d=>`<button type="button" data-id="${esc(d.id)}" class="${d.id===full.id?'cur':''}"><span><b>${d.leg.seq}</b> ${esc(d.leg.stage_label||d.leg.stage)}${d.leg.current?'<span class="latest">current</span>':''}</span><span class="num">${esc(d.leg.in_force||d.d||'')}</span></button>`).join('')}</div>`:''}
  ${LIVE&&lg.seq>1?`<button class="mini" type="button" data-lgchanges="${esc(lg.norm_id)}|${lg.seq}">Show the changes of this version</button><div class="lg-changes"></div>`:''}</section>
  ${LIVE&&lg.kind==='law'?`<section class="lg-disc" data-norm="${esc(lg.norm_id)}" data-seq="${lg.seq}" data-short="${esc(lg.short||lg.norm_title||'')}" data-stage="${esc(lg.stage_label||STAGE_LABEL[lg.stage]||lg.stage||'')}" data-current="${lg.current?1:0}"><h4>Discussed in papers <span class="prov">references in the text · numbering of this version</span></h4><div class="srcnote">Loading …</div></section>`:''}`;
}
/* REQ-69: per article of this version, the papers that discuss it (papers citing another version are mapped over) */
async function loadLegalDiscussed(box){
  const {norm,seq,short,stage,current}=box.dataset,list=box.querySelector('.srcnote');
  try{
    const r=await fetch(`api/legal/norms/${encodeURIComponent(norm)}/discussed?seq=${seq}`).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()});
    const vis=new Set(DOCS.map(d=>d.id));
    const arts=(r.articles||[]).map(a=>({...a,papers:a.papers.filter(p=>vis.has(p.doc_id))})).filter(a=>a.papers.length);
    if(!arts.length){list.textContent='No paper in the visible databases discusses an article of this version yet.';return}
    const au=p=>p.authors&&p.authors.length?`${esc(String(p.authors[0]).split(',')[0])}${p.authors.length>1?' et al.':''}, `:'';
    const row=a=>`<li><b>${esc(a.label)}</b>${a.title?' '+esc(a.title):''}${current!=='1'&&a.current_label&&a.current_label!==a.label?` <span class="srcnote">(today ${esc(a.current_label)})</span>`:''}
      <button class="mini" type="button" data-lgask="${esc(a.current_label||a.label)}|${esc(a.label)}" title="Ask the Graph Chat what the papers say about this article">Ask</button>
      <ul>${a.papers.map(p=>`<li><a href="#" data-open="${esc(p.doc_id)}">${esc(p.title||'')}</a> <span class="srcnote">(${au(p)}${p.year||'n.d.'}) · ${p.count}×${p.cited_as!==a.label?` · cited as ${esc(p.cited_as)}${p.stage?' of the '+esc((STAGE_LABEL[p.stage]||p.stage).toLowerCase()):''}`:''}${(p.parts||[]).length?' · '+esc(p.parts.slice(0,3).join(', ')):''}</span></li>`).join('')}</ul></li>`;
    list.outerHTML=`<div class="srcnote">${arts.length} article(s), recitals or annexes of the ${esc(short)} (${esc(stage.toLowerCase())}) are discussed by ${new Set(arts.flatMap(a=>a.papers.map(p=>p.doc_id))).size} paper(s).</div><ul class="ci-list lg-disc-list">${arts.slice(0,40).map(row).join('')}</ul>${arts.length>40?`<div class="srcnote">… and ${arts.length-40} more</div>`:''}`;
    box.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',e=>{e.preventDefault();openDoc(b.dataset.open)}));
    box.querySelectorAll('[data-lgask]').forEach(b=>b.addEventListener('click',()=>{
      const [cur,here]=b.dataset.lgask.split('|'),inp=$('#graphInput');if(!inp)return;
      if(typeof showPage==='function'&&$('#page-graph')&&$('#page-graph').hidden)showPage('graph');
      inp.value=`What do the papers say about ${cur} of the ${short}${cur!==here?` (numbered ${here.replace(/^\D+/,'')} in the ${stage.toLowerCase()})`:''}? Compare their reading with the wording of the article.`;
      inp.dispatchEvent(new Event('input'));inp.focus();inp.scrollIntoView({block:'center',behavior:'smooth'});
    }));
  }catch(e){list.textContent='Could not load the papers: '+e.message}
}
function wireLegalDoc(root){
  root.querySelectorAll('.lg-disc').forEach(loadLegalDiscussed);
  root.querySelectorAll('.lg-vers button').forEach(b=>b.addEventListener('click',()=>openDoc(b.dataset.id)));
  root.querySelectorAll('[data-lgchanges]').forEach(b=>b.addEventListener('click',async()=>{
    const [nid,seq]=b.dataset.lgchanges.split('|'),box=b.nextElementSibling;box.textContent='Loading …';
    try{const r=await fetch(`api/legal/norms/${encodeURIComponent(nid)}/actions?seq=${seq}`).then(r=>r.json());
      box.innerHTML=r.actions.length?`<ul class="lg-acts">${r.actions.slice(0,80).map(a=>`<li><b>${esc(a.component_label)}</b> · ${esc(LG_KIND[a.kind]||a.kind)}<br><small>${esc(a.text.slice(0,300))}${a.text.length>300?' …':''}</small></li>`).join('')}</ul>${r.actions.length>80?`<p class="srcnote">… and ${r.actions.length-80} more</p>`:''}`:'<p class="srcnote">No changes recorded.</p>'}
    catch(e){box.textContent='Could not load the changes: '+e.message}
  }));
}
