/* REQ-90: deleting data in the Documents tab – a bin in every row the user may delete, "Delete" in the document drawer
   and "Delete project" on the project card. Accounts delete in their own database only (documents shared with other
   databases just lose the own database), admins delete completely, legal texts go with their whole law. The server
   says beforehand what will happen (GET …/deletion); the deletion itself runs in the job queue (activity tile).
   Loaded after upload.js (uses ownDb, canUpload). */
function canDelete(d){
  if(!LIVE||!d)return false;
  if(IS_ADMIN)return true;
  const own=typeof ownDb==='function'?ownDb():null;
  return !!own&&(d.db||[]).includes(own);
}
function canDeleteProject(p){return !!p&&canDelete({db:p.db})}
const DEL={target:null};
const delUrl=t=>t.kind==='project'?`api/projects/${encodeURIComponent(t.name)}`:`api/documents/${encodeURIComponent(t.id)}`;
async function askDelete(target){
  DEL.target=target;
  const r=await fetch(delUrl(target)+'/deletion').catch(()=>null);
  const plan=r&&r.ok?await r.json():null;
  if(!plan){toast(r&&r.status===403?(await r.json().catch(()=>({}))).detail||'Not allowed':'This document cannot be deleted');return}
  DEL.plan=plan;
  const own=typeof ownDb==='function'?ownDb():null,others=(plan.databases||[]).filter(x=>x!==own);
  const title=`<b>${esc(plan.title||plan.project||'')}</b>`;
  let body;
  if(plan.action==='untag')body=`<p class="adc-q">Remove ${title} from your database <b>${esc(dbName(own))}</b>?</p>
    <p>It also belongs to ${others.map(x=>esc(dbName(x))).join(', ')} and stays there for the other users; only your database lets go of it${plan.kind==='project'?` (with its ${plan.documents} file${plan.documents===1?'':'s'})`:''}.</p>`;
  else if(plan.kind==='norm')body=`<p class="adc-q">Delete the legal text ${title} with all its versions?</p>
    <p>${plan.documents} document${plan.documents===1?'':'s'} of this law, its parsed articles and its history are removed – a single version cannot be taken out of the legal model.</p>`;
  else if(plan.kind==='project')body=`<p class="adc-q">Delete the project ${title} with all ${plan.documents} file${plan.documents===1?'':'s'}?</p>
    <p>Its files, passages, summaries and uploaded originals are removed for good.</p>`;
  else body=`<p class="adc-q">Delete ${title}?</p><p>The document, its passages, its summary and the uploaded original are removed for good.</p>`;
  $('#delBody').innerHTML=body+`<p class="del-after">Afterwards ALITA recomputes the clusters, the citation network and the links to legal provisions${!apiKey?' (cluster descriptions need your OpenRouter key)':''}.</p>`;
  $('#delGo').textContent=plan.action==='untag'?'Remove from my database':'Delete';
  $('#delConfirm').hidden=false;$('#delBack').focus();
}
async function waitForJob(job){
  for(;;){await new Promise(r=>setTimeout(r,2000));
    const j=await fetch('api/jobs/'+job.id).then(r=>r.json());
    if(j.status==='done')return j.result;
    if(j.status==='error'||j.status==='interrupted')throw new Error(j.error||j.status)}
}
async function runDelete(){
  const t=DEL.target,plan=DEL.plan;$('#delConfirm').hidden=true;if(!t)return;
  toast(plan.action==='untag'?'Removing from your database …':'Deleting …');
  if(typeof activityNow==='function')setTimeout(activityNow,300);
  try{
    const r=await fetch(delUrl(t),{method:'DELETE',headers:headers(false)});
    let res=await r.json().catch(()=>({}));
    if(!r.ok&&r.status!==202)throw new Error(res.detail||r.status);
    if(r.status===202)res=await waitForJob(res);
    const n=(res.documents_deleted||0)+(res.documents_untagged||0);
    toast(plan.action==='untag'?`Removed from your database (${n} document${n===1?'':'s'})`:`Deleted: ${plan.title||plan.project} (${n} document${n===1?'':'s'})`);
    closeDrawer();await loadDocs();
  }catch(e){toast('Delete failed: '+e.message)}
  if(typeof activityNow==='function')activityNow();
}
$('#delBack').addEventListener('click',()=>$('#delConfirm').hidden=true);
$('#delGo').addEventListener('click',runDelete);
$('#delConfirm').addEventListener('click',e=>{if(e.target===$('#delConfirm'))$('#delConfirm').hidden=true});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#delConfirm').hidden)$('#delConfirm').hidden=true});
