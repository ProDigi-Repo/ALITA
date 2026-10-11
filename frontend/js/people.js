/* ======================================================================
   PEOPLE (REQ-19) – person scope for both chats + curated project teams.
   File metadata only tells who last saved a file ("Last saved by"); authors of a
   project are its team, entered once in the project card.
   ====================================================================== */
let PERSON=[],PEOPLE=[];
try{PERSON=JSON.parse(localStorage.getItem('sel_person')||'[]').filter(x=>typeof x==='string')}catch(e){}

function personKey(s){return String(s||'').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g,'').replace(/ß/g,'ss').replace(/ue/g,'u').replace(/oe/g,'o').replace(/ae/g,'a').replace(/\./g,' ').trim()}
function personMatch(q,n){ // same rules as the backend: surname alone, full name or initial + surname
  const a=personKey(q).split(/\s+/).filter(Boolean),b=personKey(n).split(/\s+/).filter(Boolean);
  if(!a.length||!b.length)return false;
  if(a.join(' ')===b.join(' '))return true;
  if(a.length===1)return b.includes(a[0]);
  return a[a.length-1]===b[b.length-1]&&(a[0]===b[0]||a[0][0]===b[0][0]&&(a[0].length===1||b[0].length===1));
}
function personDocIds(names){ // demo mode: own papers/notes + all files of projects whose team contains the person
  const hit=l=>names.some(q=>(l||[]).some(n=>personMatch(q,n)));
  const proj=new Set(PROJECTS.filter(p=>hit(p.team)).map(p=>p.name));
  return new Set(DOCS.filter(d=>d.pn?proj.has(d.pn):hit(d.au)).map(d=>d.id));
}
function personLinks(names){return (names||[]).map(n=>`<button type="button" class="plink" data-person="${esc(n)}" title="Ask both chats only about the data of ${esc(n)}">👤 ${esc(n)}</button>`).join(' ')}

async function loadPeople(){
  if(LIVE){
    try{const q=SEL_DB.map(d=>'database='+encodeURIComponent(d)).join('&');const r=await fetch('api/people'+(q?'?'+q:''));PEOPLE=r.ok?await r.json():[]}catch(e){PEOPLE=[]}
  }else{
    const m=new Map(),add=n=>{const k=personKey(n);if(!m.has(k))m.set(k,{name:n,documents:0,projects:[]});return m.get(k)};
    const inDb=x=>!SEL_DB.length||(x.db||[]).some(d=>SEL_DB.includes(d));
    PROJECTS.filter(inDb).forEach(p=>(p.team||[]).forEach(n=>{const e=add(n);e.projects.push(p.name);e.documents+=DOCS.filter(d=>d.pn===p.name).length}));
    DOCS.filter(d=>!d.pn&&inDb(d)).forEach(d=>(d.au||[]).forEach(n=>add(n).documents++));
    PEOPLE=[...m.values()].sort((a,b)=>b.projects.length-a.projects.length||b.documents-a.documents||a.name.localeCompare(b.name));
  }
  let dl=$('#peopleList');if(!dl){dl=document.createElement('datalist');dl.id='peopleList';document.body.appendChild(dl)}
  dl.innerHTML=PEOPLE.map(p=>`<option value="${esc(p.name)}" label="${p.projects.length?esc('team of '+p.projects.join(', ')+' · '):''}${p.documents} document${p.documents===1?'':'s'}"></option>`).join('');
}
function setPerson(list){
  PERSON=[...new Set((list||[]).map(s=>String(s).trim()).filter(Boolean))];
  try{localStorage.setItem('sel_person',JSON.stringify(PERSON))}catch(e){}
  [syncScope,()=>syncParams('rag'),()=>syncParams('graph')].forEach(fn=>{try{fn()}catch(e){}});
}
function personScopeHtml(){
  const chips=PERSON.map(n=>`<span class="sc-person" title="Only documents of ${esc(n)}: own papers and notes, plus every project with ${esc(n)} in its team">👤 ${esc(n)}<button type="button" class="sc-px" data-px="${esc(n)}" aria-label="Remove ${esc(n)} from the scope">×</button></span>`).join(' ');
  return ` <span class="sc-people">${chips}${chips?' – only their data ':''}<button type="button" class="sc-addp" title="Restrict both chats to the data of one person">${PERSON.length?'＋':'👤 restrict to a person'}</button></span>`;
}
document.addEventListener('click',e=>{
  const x=e.target.closest('.sc-px');if(x){setPerson(PERSON.filter(n=>n!==x.dataset.px));return}
  const pl=e.target.closest('.plink');if(pl){setPerson([pl.dataset.person]);toast(`Both chats now answer only from the data of ${pl.dataset.person}`);return}
  const a=e.target.closest('.sc-addp');if(!a)return;
  if(!PEOPLE.length)loadPeople();
  const inp=document.createElement('input');inp.className='sc-pin';inp.setAttribute('list','peopleList');inp.placeholder='Name or surname…';inp.setAttribute('aria-label','Person');
  a.replaceWith(inp);inp.focus();
  const done=ok=>{const v=inp.value.trim();if(ok&&v)setPerson([...PERSON,(PEOPLE.find(p=>personKey(p.name)===personKey(v))||{name:v}).name]);else syncScope()};
  inp.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.preventDefault();done(true)}if(ev.key==='Escape')done(false)});
  inp.addEventListener('change',()=>{if(PEOPLE.some(p=>p.name===inp.value))done(true)});
  inp.addEventListener('blur',()=>setTimeout(()=>{if(inp.isConnected)done(true)},150));
});

/* ---------- Project team (shown in the project card) ---------- */
function projectEditors(name){
  const c=new Map();DOCS.filter(d=>d.pn===name).forEach(d=>(d.ed||[]).forEach(n=>c.set(n,(c.get(n)||0)+1)));
  return [...c.entries()].sort((a,b)=>b[1]-a[1]);
}
function teamRowHtml(p){
  const ed=projectEditors(p.name).slice(0,4).map(([n,k])=>`${esc(n)} (${k})`).join(', ');
  return `<dt>Team</dt><dd class="pteam" data-team="${esc(p.name)}">${(p.team||[]).length?personLinks(p.team):'<span class="srcnote">not recorded yet</span>'}
    <button type="button" class="pteam-edit" title="Who works on this project? Answers name only these people">✎ ${(p.team||[]).length?'edit':'add team'}</button>
    ${ed?`<div class="srcnote">Last saved by (file metadata, not authors): ${ed}</div>`:''}</dd>`;
}
function wireTeam(box,rerender){
  const dd=box.querySelector('.pteam');if(!dd)return;
  dd.querySelector('.pteam-edit').addEventListener('click',()=>{
    const p=PROJECTS.find(x=>x.name===dd.dataset.team);if(!p)return;
    dd.innerHTML=`<form class="pteam-form"><input list="peopleList" value="${esc((p.team||[]).join(', '))}" placeholder="e.g. Jürgen Strohecker, Sabrina …" aria-label="Team members, separated by commas">
      <button class="btn primary" type="submit">Save</button><button class="btn" type="button" data-cancel>Cancel</button>
      <div class="srcnote">Comma-separated. Becomes the author list of every file in ${esc(p.name)} and the project's people in the knowledge graph.</div></form>`;
    const f=dd.querySelector('form'),inp=f.querySelector('input');inp.focus();
    f.querySelector('[data-cancel]').addEventListener('click',rerender);
    f.addEventListener('submit',async ev=>{ev.preventDefault();
      const team=inp.value.split(/[,;]/).map(s=>s.trim()).filter(Boolean);
      if(LIVE){try{const r=await fetch('api/projects/'+encodeURIComponent(p.name)+'/team',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({team})});
          if(!r.ok)throw new Error(r.status===404||r.status===405?'the backend needs an update (docker compose up -d --build backend)':'HTTP '+r.status);
          const j=await r.json();p.team=j.team;toast(`Team of ${p.name} saved – ${j.documents} files updated${j.graph?'':' (knowledge graph not reachable)'}`)}
        catch(e){toast('Team not saved: '+e.message);return}}
      else{p.team=team;toast('Team saved in this demo session')}
      DOCS.filter(d=>d.pn===p.name).forEach(d=>d.au=[...p.team]);
      loadPeople();rerender();
    });
  });
}
loadPeople();
