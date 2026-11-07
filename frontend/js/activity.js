/* REQ-87: the "Activity" tile between the database bar and "Upload new data".
   Shows what runs on the server right now: the own uploads (with pipeline step and progress bar) and chats, and the
   other users' uploads and chats anonymously (kind, step, progress – no names, files or databases), plus how busy the
   chat workers are. So a user sees that their upload is running – and, when things are slow, that others are busy too.
   Polls GET /api/activity: every 3 s while something runs, every 15 s otherwise, paused while the tab is hidden. */
const ACT={timer:null,busy:false,last:null};
const ACT_KIND={chat:'Document Chat',graph:'Graph Chat',progress:'Knowledge progress'};
const actSecs=s=>s<60?`${s}s`:s<3600?`${Math.floor(s/60)} min`:`${Math.floor(s/3600)} h`;
function actBar(p,mode){   // mode: 'det' (share known) | 'ind' (running, no share) | 'wait'
  const w=Math.round(Math.max(0,Math.min(1,p||0))*100);
  return `<span class="act-bar ${mode}" role="progressbar" aria-valuemin="0" aria-valuemax="100" ${mode==='det'?`aria-valuenow="${w}"`:''}><i style="width:${mode==='det'?w:mode==='wait'?0:100}%"></i></span>`;
}
function actUpload(j,own){
  const name=own?esc(j.name):(j.kind==='maintenance'?'Recalculation':'Upload');
  let st,mode='det',detail='';
  if(j.status==='queued'){mode='wait';st=j.waiting_for_lock?'waiting for an import':j.position>1?`waiting · ${j.position-1} ahead`:'next in line'}
  else if(j.status==='running'){mode=j.progress==null?'ind':'det';st=mode==='det'?`${Math.round((j.progress||0)*100)}%`:'running';detail=j.step||'processing'}
  else{st=j.status==='done'?'done':j.status==='error'?'failed':'interrupted';if(own&&j.status!=='done')detail=j.error||''}
  return `<li class="act-i s-${esc(j.status)}${own?' own':''}" title="${esc(own?j.name+(detail?' – '+detail:''):detail||st)}">`
    +`<span class="act-n">${own?'⇪ ':''}${name}</span><span class="act-s">${esc(st)}</span>`
    +`${j.status==='done'?'':actBar(j.progress,mode)}${detail?`<span class="act-d">${esc(detail)}</span>`:''}</li>`;
}
function actChat(c,own){
  const label=ACT_KIND[c.kind]||'Chat';
  return `<li class="act-i act-chat s-${c.state==='waiting'?'queued':'running'}${own?' own':''}"><span class="act-n">${own?'✎ ':''}${esc(label)}</span>`
    +`<span class="act-s">${c.state==='waiting'?'waiting':'answering'} · ${actSecs(c.seconds||0)}</span>${actBar(0,c.state==='waiting'?'wait':'ind')}</li>`;
}
function renderActivity(a){
  const tile=$('#actTile');if(!tile)return;
  tile.hidden=!LIVE||!a;if(!a)return;
  const you=[...a.you.uploads.map(j=>actUpload(j,true)),...a.you.chats.map(c=>actChat(c,true))];
  $('#actYou').innerHTML=you.slice(0,3).join('')||'<li class="act-empty">Nothing running</li>';
  const o=a.others,ups=o.uploads.map(j=>actUpload(j,false));
  const chats=o.chats.length?`<li class="act-i act-chat s-running"><span class="act-n">${o.chats.length} chat${o.chats.length===1?'':'s'}</span>`
    +`<span class="act-s">${o.chats.filter(c=>c.state==='answering').length} answering${o.chats.some(c=>c.state==='waiting')?` · ${o.chats.filter(c=>c.state==='waiting').length} waiting`:''}</span>${actBar(0,'ind')}</li>`:'';
  $('#actOthers').innerHTML=(ups.slice(0,2).join('')+(ups.length>2?`<li class="act-more">+ ${ups.length-2} more uploads</li>`:'')+chats)||'<li class="act-empty">No activity</li>';
  const s=a.server,used=s.chats_answering/Math.max(1,s.chat_capacity);
  const level=s.chats_waiting>0||s.uploads_waiting>1?'high':used>.5||s.uploads_running?'mid':'low';
  const lbl={low:'quiet',mid:'busy',high:'very busy'}[level];
  $('#actLoad').className='act-load '+level;
  $('#actLoad').textContent=lbl;
  $('#actLoad').title=`Server: ${s.chats_answering}/${s.chat_capacity} chat workers in use${s.chats_waiting?`, ${s.chats_waiting} waiting`:''} · uploads: ${s.uploads_running} running, ${s.uploads_waiting} waiting (one at a time)`;
}
async function activityTick(){
  clearTimeout(ACT.timer);
  if(!LIVE){renderActivity(null);return}
  let a=null;
  if(document.visibilityState!=='hidden'){
    const r=await fetch('api/activity').catch(()=>null);
    a=r&&r.ok?await r.json().catch(()=>null):null;
    if(a){ACT.last=a;renderActivity(a)}
  }
  const s=(a||ACT.last||{}).server||{};
  ACT.busy=!!(s.chats_answering||s.chats_waiting||s.uploads_running||s.uploads_waiting);
  ACT.timer=setTimeout(activityTick,ACT.busy?3000:15000);
}
let ACT_SOON=null;
function activityNow(){clearTimeout(ACT_SOON);ACT_SOON=setTimeout(activityTick,300)}   // debounced refresh
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')activityNow()});
Store.on('gate',()=>activityNow(),46);
