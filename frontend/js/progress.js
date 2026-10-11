/* ======================================================================
   KNOWLEDGE PROGRESS (REQ-10, REQ-15 – REQ-18)
   Version history of a project divided into knowledge stages: a timeline in the
   project card and a stage table under chat answers about a project's development.
   Every file links to its document (REQ-18).
   ====================================================================== */
const PG_KIND={start:['first version','#495057'],substantive:['substantive change','#d9480f'],reword:['rewording','#868e96'],
  resubmission:['resubmission','#7048e8'],format:['formatting only','#adb5bd'],identical:['identical copy','#ced4da'],unknown:['not comparable (no text)','#ced4da']};
const PG_ROLE={analysis_output:'analysis output',analysis_script:'analysis script',model_file:'model',data:'data'};
const PG_CACHE=new Map();
let PG_K=5;try{PG_K=+localStorage.getItem('pg_k')||5}catch(e){}

function pgFileChip(f,withNo=true){
  const k=PG_KIND[f.kind]||null;
  return `<button type="button" class="pg-file" data-open-doc="${esc(f.doc_id)}" title="${esc([f.filename,f.date,k&&k[0],f.why,f.venue&&('journal: '+f.venue)].filter(Boolean).join(' · '))}">${withNo&&f.n!=null?`<b>${f.n}</b>`:''}${k?`<i style="--k:${k[1]}"></i>`:''}${esc(f.filename||f.doc_id)}</button>`;
}
function pgAnalysisChip(a){
  const sure=a.basis==='journal folder'||a.basis==='date';
  return `<button type="button" class="pg-an${sure?'':' guess'}" data-open-doc="${esc(a.doc_id)}" title="${esc(`${PG_ROLE[a.role]||a.role||'file'} · assigned by ${a.basis||'?'}${sure?'':' (assumed)'}${a.date?' · '+a.date:''}`)}">${esc(a.filename)}<small>${esc(PG_ROLE[a.role]||a.role||'')}${sure?'':' ?'}</small></button>`;
}
/* REQ-16 + REQ-18: the table – stage · knowledge state · files · analyses */
function progressTableHtml(p,o={}){
  if(!p||!(p.stages||[]).length)return `<div class="pg-empty">${esc((p&&p.notes&&p.notes[0])||'No version history found for this project.')}</div>`;
  const fileOf=(s)=>s.files.map(x=>typeof x==='object'?x:(p.versions||[]).find(v=>v.n===x)).filter(Boolean);
  const rows=p.stages.map(s=>{const fs=fileOf(s),an=s.analyses||[];
    return `<tr><td class="pg-st"><b>Stage ${s.n}</b><small>${esc([s.date_from,s.date_to].filter(Boolean).map(d=>d.slice(0,7)).filter((d,i,a)=>a.indexOf(d)===i).join(' – '))}</small>${(s.venues||[]).length?`<small>${esc(s.venues.join(', '))}</small>`:''}</td>
      <td class="pg-kn"><div class="pg-state">${esc(s.state||'–')}</div><div class="pg-chg">${s.n>1?'<b>New:</b> ':''}${esc(s.change||'')}${s.state_source==='llm'?' <span class="pg-ai" title="Formulated by the AI from the first and last version of the stage">AI</span>':''}</div>${s.formal_versions?`<div class="pg-formal">${s.formal_versions} version${s.formal_versions>1?'s':''} without new insight</div>`:''}</td>
      <td class="pg-fl"><details class="pg-files"><summary>${esc(s.label)} <small>(${fs.length})</small></summary>${fs.map(f=>pgFileChip(f)).join('')}</details></td>
      <td class="pg-as">${an.length?an.slice(0,o.maxAn||8).map(pgAnalysisChip).join('')+(an.length>(o.maxAn||8)?`<small>+${an.length-(o.maxAn||8)} more</small>`:''):'<span class="pg-none">–</span>'}</td></tr>`}).join('');
  return `<div class="pg-tablewrap"><table class="pg-table"><thead><tr><th>Stage</th><th>Knowledge state</th><th>Files</th><th>Analyses</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${(p.notes||[]).length?`<ul class="pg-notes">${p.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul>`:''}`;
}
/* REQ-10: timeline – stage bands, one dot per manuscript version (colour = kind of change), analyses below linked to their stage */
function progressTimelineSvg(p){
  const vs=p.versions||[],st=p.stages||[];if(!vs.length)return '';
  const step=Math.max(10,Math.min(26,520/vs.length)),L=66,W=L+step*(vs.length-1)+24,yV=52,yA=100,H=126;
  const X=n=>L+(n-1)*step;
  const bands=st.map((s,i)=>{const x0=X(s.from)-step/2,x1=X(s.to)+step/2;
    return `<rect x="${x0}" y="14" width="${x1-x0}" height="${H-20}" rx="6" class="pg-band${i%2?' alt':''}"/><text x="${x0+5}" y="27" class="pg-bl">Stage ${s.n}</text>`}).join('');
  const line=`<line x1="${X(1)}" y1="${yV}" x2="${X(vs.length)}" y2="${yV}" class="pg-spine"/>`;
  const dots=vs.map(v=>{const k=PG_KIND[v.kind]||PG_KIND.unknown,big=v.kind==='substantive'||v.kind==='start',x=X(v.n);
    const t=`<title>${esc(`${v.n} · ${v.filename}${v.date?' · '+v.date:''}\n${k[0]}${v.why&&v.kind!=='start'?': '+v.why:''}${v.venue?'\njournal: '+v.venue:''}`)}</title>`;
    const shape=v.kind==='resubmission'?`<rect x="${x-4}" y="${yV-4}" width="8" height="8" transform="rotate(45 ${x} ${yV})" fill="${k[1]}"/>`
      :`<circle cx="${x}" cy="${yV}" r="${big?6.5:3.6}" fill="${v.kind==='reword'?'var(--bg,#fff)':k[1]}" stroke="${k[1]}" stroke-width="${v.kind==='reword'?1.6:0}"${v.kind==='unknown'?' stroke-dasharray="2 2"':''}/>`;
    return `<g class="pg-dot" data-open-doc="${esc(v.doc_id)}">${t}${shape}${big?`<text x="${x}" y="${yV+18}" class="pg-n">${v.n}</text>`:''}</g>`}).join('');
  const an=st.map(s=>{const a=s.analyses||[];if(!a.length)return '';const x0=X(s.from),x1=X(s.to),w=Math.max(0,x1-x0);
    return a.map((f,i)=>{const x=a.length===1?(x0+x1)/2:x0+w*i/(a.length-1),sure=f.basis==='journal folder'||f.basis==='date';
      return `<g class="pg-dot" data-open-doc="${esc(f.doc_id)}"><title>${esc(`${f.filename}\n${PG_ROLE[f.role]||f.role} · stage ${s.n} · assigned by ${f.basis}${sure?'':' (assumed)'}`)}</title>
        <line x1="${x}" y1="${yA-6}" x2="${X(s.from)}" y2="${yV+7}" class="pg-link${sure?'':' guess'}"/><rect x="${x-4.5}" y="${yA-4.5}" width="9" height="9" rx="2" class="pg-anbox ${esc(f.role||'')}"/></g>`}).join('')}).join('');
  return `<div class="pg-tl" role="img" aria-label="Version timeline with ${vs.length} manuscript versions in ${st.length} knowledge stages"><svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${bands}${line}
    <text x="4" y="${yV+3}" class="pg-lane">versions</text><text x="4" y="${yA+3}" class="pg-lane">analyses</text>${an}${dots}</svg></div>
    <div class="pg-legend">${['substantive','reword','resubmission','format'].map(k=>`<span><i class="${k}" style="--k:${PG_KIND[k][1]}"></i>${PG_KIND[k][0]}</span>`).join('')}<span><i class="an"></i>analysis · data · model</span><span><i class="guess"></i>assumed link</span></div>`;
}
/* chat: block under the answer */
function progressBlockHtml(p){
  if(!p)return '';
  return `<details class="pg-block" open><summary><b>Knowledge stages</b> · ${esc(p.project||'')} · ${(p.stages||[]).length} stage${(p.stages||[]).length===1?'':'s'}</summary>${progressTableHtml(p,{maxAn:5})}</details>`;
}
/* project card: section with timeline + table, computed on demand */
function cgProgressSection(name){
  return `<section class="pg-sec" data-pg="${esc(name)}"><h6>Knowledge progress <small>version history in stages</small></h6>
    <div class="pg-ctl"><label>Stages <select class="pg-k">${[3,5,10].map(k=>`<option ${k===PG_K?'selected':''}>${k}</option>`).join('')}</select></label>
      <button type="button" class="mini pg-ai-btn" title="Let the AI describe the knowledge reached in each stage (uses your API key, about one request per stage)">✨ Describe stages with AI</button></div>
    <div class="pg-body"><div class="pg-empty">Loading version history…</div></div></section>`;
}
async function pgFetch(name,k,post){
  const key=name+'|'+k;if(!post&&PG_CACHE.has(key))return PG_CACHE.get(key);
  if(!LIVE)throw new Error('needs the running backend');
  const url='api/projects/'+encodeURIComponent(name)+'/progress';
  const r=post?await fetch(url,{method:'POST',headers:headers(),body:JSON.stringify({stages:k,use_llm:true})})
             :await fetch(url+'?stages='+k);
  if(!r.ok)throw new Error(r.status===404||r.status===405?'the backend needs an update (docker compose up -d --build backend)':'HTTP '+r.status);
  const p=await r.json();PG_CACHE.set(key,p);return p;
}
async function wireProgress(box){
  const sec=box.querySelector('.pg-sec');if(!sec)return;const name=sec.dataset.pg,body=sec.querySelector('.pg-body');
  const show=async(post)=>{body.innerHTML=`<div class="pg-empty">${post?'The AI is describing the stages…':'Loading version history…'}</div>`;
    try{const p=await pgFetch(name,PG_K,post);if(!sec.isConnected)return;body.innerHTML=progressTimelineSvg(p)+progressTableHtml(p)}
    catch(e){body.innerHTML=`<div class="pg-empty">Version history not available: ${esc(e.message)}</div>`}};
  sec.querySelector('.pg-k').addEventListener('change',e=>{PG_K=+e.target.value;try{localStorage.setItem('pg_k',PG_K)}catch(x){}show(false)});
  sec.querySelector('.pg-ai-btn').addEventListener('click',()=>show(true));
  show(false);
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-open-doc]');if(!b)return;
  if(e.target.closest('summary'))return;e.preventDefault();
  const id=b.dataset.openDoc;if(DOCS.find(d=>d.id===id))openDoc(id);else toast('This file is not in the current document list')});
