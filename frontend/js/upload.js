/* "Upload new data" (REQ-84): the wizard, the tile next to the database bar and the polling of upload jobs (REQ-83).
   Loaded after documents.js (uses LEGAL_T, D, loadDocs, uploadReport) and before activity.js/start.js.
   Accounts upload into their own database, admins choose one; the server runs the whole pipeline on every file. */
/* ---------- Upload new data (REQ-84): one wizard for everybody who may upload ----------
   Opened from the tile next to the database bar and from Documents → + Upload. Accounts upload into their own
   database (shown, not choosable), admins choose one. The server runs the whole pipeline on every file: text, LLM
   summary and methods, chunks, embeddings, rhetorical roles, knowledge graph, clustering, citations, legal links. */
const KIND_N=(t,n)=>({research_paper:'paper',research_notes:'note',legal_guideline:'guideline',standard:'standard',guidance:'guidance page',legal_project:'legal project'}[t]||'file')+(n>1?'s':'');
const ZIP_T=t=>t==='research_project'||t==='legal_project';   // one ZIP per project (REQ-38: legal projects too)
const AD_TYPE_DESC={
  research_paper:'Published or own papers – PDF, DOCX, TXT or MD, one or more files. Optionally linked to a project.',
  research_notes:'Notes, minutes, idea collections, web articles – one or more files. Optionally linked to a project.',
  research_project:'A project folder as ZIP – manuscripts, data, analyses, submissions. The folder name becomes the project name, every file is linked to it; the "Literatur" folder is skipped.',
  legal_project:'The folder of a law as ZIP: its versions (proposal, adopted text, consolidated versions) and accompanying documents. A _legal.yaml in the folder gives stages, entry into force and application dates.',
  legal_guideline:'Formally adopted guidelines of authorities, one file each. Versions of the same guideline can be grouped with a _legal.yaml.',
  guidance:'Q&A pages, FAQs, factsheets and explanations of authorities (not binding), one file each, e.g. a web page printed as PDF. ALITA splits them into topics and questions.',
  standard:'ISO, IEC, CEN, DIN … one file per standard. Check that the licence allows storing the full text.'};
const AD_PIPE='After the upload ALITA reads every file and runs the full pipeline: summary, methods and keywords (LLM) → chunks and embeddings → rhetorical roles → knowledge graph → sorting into the existing clusters of the database (small databases are clustered anew; “Recompute clusters” does it on request) → citation network and links to legal provisions.';
/* who may upload: admins (any database) and logged-in accounts (their own database) */
function canUpload(){return IS_ADMIN||!!(ACCOUNT&&!ACCOUNT.all&&ACCOUNT.database)}
function ownDb(){return ACCOUNT&&!ACCOUNT.all?ACCOUNT.database:null}
const AD={db:null,type:null};
function adOpen(type){
  if(LIVE&&!canUpload()){toast(ACCOUNTS_ON?'Log in with your user name to upload your own data':'Uploading needs admin rights');return}
  const own=ownDb();
  AD.db=own||(SEL_DB.length===1?SEL_DB[0]:AD.db);
  if(type)AD.type=type;
  const n=db=>DOCS.filter(d=>(d.db||[]).includes(db)).length;
  const choices=own?[own]:DATABASES;
  $('#adDbs').innerHTML=choices.map(db=>`<label class="ad-db" style="--c:${dbColor(db)}"><input type="radio" name="addb" value="${esc(db)}" ${AD.db===db?'checked':''} ${own?'disabled':''}><span class="ad-fl">${dbIcon(db)}</span><b>${esc(dbName(db))}</b><small>${own?'your database · ':''}${n(db)} docs</small></label>`).join('');
  $('#adDbs').closest('fieldset').querySelector('legend').lastChild.textContent=own?' Your documents go into your own database':' Which database should the documents go to?';
  $$('input[name=addb]').forEach(r=>r.addEventListener('change',()=>{AD.db=r.value;adSync()}));
  $('#adType').value=AD.type||'';
  $('#adFiles').value='';$('#adProject').value='';$('#adDate').value='';
  adSync();$('#addData').hidden=false;
  setTimeout(()=>(own?$('#adType'):($('input[name=addb]:checked')||$('input[name=addb]'))).focus(),30);
}
function adSync(){
  const t=AD.type,files=[...$('#adFiles').files];
  $('#adTypeDesc').textContent=t?AD_TYPE_DESC[t]:'Choose what you are uploading – ALITA processes each kind differently.';
  $('#adFiles').accept=ZIP_T(t)?'.zip':'.pdf,.docx,.doc,.txt,.md,.pptx';
  $('#adFiles').multiple=true;
  $('#adProjWrap').hidden=!t||ZIP_T(t)||LEGAL_T.has(t);
  $('#adDateQ').textContent=ZIP_T(t)?'Which overall date should the project get?':t==='research_paper'?'Which date should the papers get (e.g. publication)?':t==='research_notes'?'Which date should the notes get?':'Which overall date should the data get?';
  $('#adDateHint').textContent=ZIP_T(t)?'Optional. Files with their own document date keep it (the version history needs it); files without a reliable date and the project itself get this date.'
    :'Optional. Leave empty to take the dates from the files.';
  $('#adDropText').innerHTML=files.length?`<b>${files.length} file${files.length>1?'s':''}</b>: ${esc(files.slice(0,3).map(f=>f.name).join(', '))}${files.length>3?' …':''}`
    :ZIP_T(t)?'Drop the projects here – <b>one ZIP per project</b> – or <u>choose files</u>':'Drop files here or <u>choose files</u>';
  $('#adPipe').textContent=AD_PIPE;
  const noKey=LIVE&&!apiKey;            // the pipeline needs the user's OpenRouter key (summaries, embeddings, clusters)
  $('#adKey').hidden=!noKey;
  $('#adKey').innerHTML=noKey?'<b>Enter your OpenRouter key at the top first.</b> The pipeline uses it for summaries, embeddings and clustering; without it your documents could not be searched.':'';
  const ok=AD.db&&t&&files.length&&!noKey;$('#adGo').disabled=!ok;
  $('#adGo').textContent=AD.db?`Upload to ${dbName(AD.db)}`:'Upload';
  $('#adSum').textContent=!AD.db?'Choose a database.':!t?'Choose the kind of data.':!files.length?'Choose the files.'
    :`${files.length} ${ZIP_T(t)?(files.length>1?'projects (one ZIP each)':'project (ZIP)'):KIND_N(t,files.length)} → ${dbName(AD.db)}${$('#adDate').value?' · dated '+$('#adDate').value:' · dates from the files'}`;
}
$('#adType').addEventListener('change',e=>{AD.type=e.target.value||null;adSync()});
['change','input'].forEach(ev=>{$('#adFiles').addEventListener(ev,adSync);$('#adDate').addEventListener(ev,adSync)});
$('#adDateClear').addEventListener('click',()=>{$('#adDate').value='';adSync()});
const adDrop=$('#adDrop');
['dragenter','dragover'].forEach(ev=>adDrop.addEventListener(ev,e=>{e.preventDefault();adDrop.classList.add('over')}));
['dragleave','drop'].forEach(ev=>adDrop.addEventListener(ev,()=>adDrop.classList.remove('over')));
adDrop.addEventListener('drop',e=>{e.preventDefault();if(e.dataTransfer.files.length){$('#adFiles').files=e.dataTransfer.files;adSync()}});
$$('[data-adclose]').forEach(b=>b.addEventListener('click',()=>$('#addData').hidden=true));
$('#addData').addEventListener('click',e=>{if(e.target===$('#addData'))$('#addData').hidden=true});
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!$('#adConfirm').hidden){$('#adConfirm').hidden=true;return}$('#addData').hidden=true});
$('#upOpen').addEventListener('click',()=>adOpen());
$('#openUpload').addEventListener('click',()=>adOpen(D.t&&D.t!=='legal'?D.t:null));   // Documents: the type of the open tab
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
          <p class="adc-note">* The final name comes from the folder inside the ZIP${ownDb()?'; if another database already has a project of that name, yours gets “(' + esc(dbName(AD.db)) + ')” added':''}. Date: ${date?esc(date)+' for the project and its files without a date of their own':'taken from the files'}.</p>`}`;
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
  if(!LIVE){$('#addData').hidden=true;toast('Demo mode: uploading requires the running backend');return}
  const fd=new FormData();
  fd.append('doc_type',AD.type);files.forEach(f=>fd.append('files',f));fd.append('databases',AD.db);
  if($('#adDate').value)fd.append('date',$('#adDate').value);
  if(!ZIP_T(AD.type)&&$('#adProject').value.trim())fd.append('project_name',$('#adProject').value.trim());
  fd.append('use_llm',$('#adLlm').checked);
  $('#adGo').disabled=true;$('#adGo').textContent='Uploading…';
  try{
    const r=await fetch('api/ingest',{method:'POST',body:fd,headers:headers(false)});
    if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||r.status);
    const {jobs}=await r.json();$('#addData').hidden=true;toast(`${dbName(AD.db)}: upload received – processing ${jobs.length} job${jobs.length===1?'':'s'}`);
    pollJobs(jobs);upTrack();
    if(typeof oceanParty==='function')oceanParty(`${jobs.length===1?'Upload':jobs.length+' uploads'} received!`);   // REQ-91
  }catch(err){toast('Upload failed: '+err.message);adSync()}
});
/* ---------- The "Upload new data" tile: who may upload where (progress: activity tile, js/activity.js) ---------- */
function renderUpTile(){
  const tile=$('#upTile');if(!tile)return;
  const may=!LIVE||canUpload();
  tile.hidden=!(may||ACCOUNTS_ON);          // anonymous visitors of an instance with accounts see how to get there
  $('#upOpen').disabled=LIVE&&!may;
  const own=ownDb();
  $('#upTarget').innerHTML=!LIVE?'Demo mode – needs the running backend'
    :!may?'Log in with your user name to upload your own files'
    :own?`into your database <b>${esc(dbName(own))}</b>`:'into a database of your choice';
  $('.uptile .up-hint').hidden=!(LIVE&&may);
  $('#upRecluster').hidden=!(LIVE&&may);
}
/* REQ-92: "Recompute clusters" – uploads only sort new documents into the existing clusters; this computes them anew
   (accounts: their own database; admins: the selected databases, or all). */
function reclusterTargets(){const own=ownDb();return own?[own]:SEL_DB.length?[...SEL_DB]:[]}
$('#upRecluster').addEventListener('click',()=>{
  const dbs=reclusterTargets(),names=dbs.length?dbs.map(d=>`<b>${esc(dbName(d))}</b>`).join(', '):'<b>all databases</b>';
  $('#rcBody').innerHTML=`<p class="adc-q">Compute the clusters of ${names} completely anew?</p>
    <p>New uploads are only sorted into the existing clusters, so the clusters stay stable. Recomputing groups all documents afresh – cluster numbers, names, descriptions and positions in the map can change. Each database is clustered on its own.</p>
    ${apiKey?'':'<p class="adc-warn">Without your OpenRouter key the clusters get only automatic titles, no written descriptions.</p>'}`;
  $('#rcConfirm').hidden=false;$('#rcBack').focus();
});
$('#rcBack').addEventListener('click',()=>$('#rcConfirm').hidden=true);
$('#rcConfirm').addEventListener('click',e=>{if(e.target===$('#rcConfirm'))$('#rcConfirm').hidden=true});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#rcConfirm').hidden)$('#rcConfirm').hidden=true});
$('#rcGo').addEventListener('click',async()=>{
  $('#rcConfirm').hidden=true;const dbs=reclusterTargets();
  const q=ownDb()?'':dbs.map(d=>'database='+encodeURIComponent(d)).join('&');
  toast('Recomputing the clusters …');if(typeof activityNow==='function')setTimeout(activityNow,300);
  try{
    const r=await fetch('api/clusters/rebuild'+(q?'?'+q:''),{method:'POST',headers:headers(false)});
    let res=await r.json().catch(()=>({}));
    if(!r.ok&&r.status!==202)throw new Error(res.detail||r.status);
    if(r.status===202)res=await waitForJob(res);
    toast(`Clusters recomputed: ${res.k} cluster${res.k===1?'':'s'} for ${res.documents} documents`);
    await loadDocs();
  }catch(e){toast('Recomputing failed: '+e.message)}
  if(typeof activityNow==='function')activityNow();
});
function upTrack(){if(typeof activityNow==='function')activityNow()}   // a job changed: refresh the activity tile
Store.on('gate',()=>renderUpTile(),45);
/* REQ-83: uploads wait in one queue on the server (one job at a time). Finished: done | error | interrupted. */
const JOB_FINISHED=new Set(['done','error','interrupted']),POLLING=new Set();
async function pollJobs(ids){
  ids=ids.filter(id=>!POLLING.has(id));if(!ids.length)return;
  ids.forEach(id=>POLLING.add(id));
  const open=new Set(ids),done=[],told={};
  while(open.size){
    await new Promise(r=>setTimeout(r,2500));
    for(const id of [...open]){
      const r=await fetch('api/jobs/'+id).catch(()=>null);
      const j=r&&r.ok?await r.json().catch(()=>null):(r&&r.status===404?null:{status:'unknown'});
      if(j&&j.id)upTrack(j);
      if(j&&j.status==='queued'){        // say once how many jobs are ahead – other people's uploads count too
        const ahead=(j.position||1)-1,key=j.waiting_for_lock?'lock':ahead;
        if(told[id]!==key){told[id]=key;
          if(j.waiting_for_lock)toast(`${j.name}: waiting for an import on the server to finish`);
          else if(ahead>0)toast(`${j.name}: waiting in line – ${ahead} job${ahead===1?'':'s'} ahead`)}
        continue}
      if(!j||JOB_FINISHED.has(j.status)){open.delete(id);POLLING.delete(id);done.push(j||{status:'error',name:id,error:'job not found'});
        toast(j&&j.status!=='done'?`Error in ${j.name}: ${j.error}`:`Done: ${j?j.name:id}`)}
    }
  }
  loadDocs();
  try{uploadReport(done)}catch(e){console.error('upload report',e)}
}
/* After a reload or login: follow the own uploads that are still waiting or running. */
async function resumeJobs(){
  if(!LIVE)return;
  const r=await fetch('api/jobs?mine=true&limit=20').catch(()=>null);if(!r||!r.ok)return;
  const {jobs=[]}=await r.json().catch(()=>({}));
  renderUpTile();
  const open=jobs.filter(j=>j.status==='queued'||j.status==='running').map(j=>j.id);
  if(open.length){toast(`${open.length} upload${open.length===1?' is':'s are'} still being processed`);pollJobs(open)}
}
Store.on('gate',()=>resumeJobs(),40);
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
