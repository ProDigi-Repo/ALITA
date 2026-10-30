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
  ${LIVE&&lg.seq>1?`<button class="mini" type="button" data-lgchanges="${esc(lg.norm_id)}|${lg.seq}">Show the changes of this version</button><div class="lg-changes"></div>`:''}</section>`;
}
function wireLegalDoc(root){
  root.querySelectorAll('.lg-vers button').forEach(b=>b.addEventListener('click',()=>openDoc(b.dataset.id)));
  root.querySelectorAll('[data-lgchanges]').forEach(b=>b.addEventListener('click',async()=>{
    const [nid,seq]=b.dataset.lgchanges.split('|'),box=b.nextElementSibling;box.textContent='Loading …';
    try{const r=await fetch(`api/legal/norms/${encodeURIComponent(nid)}/actions?seq=${seq}`).then(r=>r.json());
      box.innerHTML=r.actions.length?`<ul class="lg-acts">${r.actions.slice(0,80).map(a=>`<li><b>${esc(a.component_label)}</b> · ${esc(LG_KIND[a.kind]||a.kind)}<br><small>${esc(a.text.slice(0,300))}${a.text.length>300?' …':''}</small></li>`).join('')}</ul>${r.actions.length>80?`<p class="srcnote">… and ${r.actions.length-80} more</p>`:''}`:'<p class="srcnote">No changes recorded.</p>'}
    catch(e){box.textContent='Could not load the changes: '+e.message}
  }));
}
