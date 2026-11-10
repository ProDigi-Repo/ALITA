/* REQ-96: in the upload wizard, research projects are either a new project (one ZIP each) or new documents and
   versions for an existing project (single files). Used by upload.js (AD is its wizard state, read at call time). */
const ADD=()=>AD.type==='research_project'&&AD.mode==='add';
const NEED_ZIP=t=>ZIP_T(t)&&!ADD();
function adProjects(){return PROJECTS.filter(p=>(p.db||[]).includes(AD.db)).sort((a,b)=>(a.name||'').localeCompare(b.name||''))}
function adProjFiles(name){return DOCS.filter(d=>d.pn===name&&d.t==='research_project'&&d.la!==false&&d.rp).sort((a,b)=>a.rp.localeCompare(b.rp))}
function adSyncMode(files){
  const show=AD.type==='research_project';$('#adMode').hidden=!show;$('#adAdd').hidden=!ADD();
  if(!ADD())return;
  const sel=$('#adExProj'),projs=adProjects(),cur=sel.value;
  sel.innerHTML=projs.length?projs.map(p=>`<option value="${esc(p.name)}">${esc(p.title&&p.title!==p.name?p.title+' ('+p.name+')':p.name)} · ${p.files||0} files</option>`).join('')
    :'<option value="">No project in this database yet – upload a new one first</option>';
  if(projs.some(p=>p.name===cur))sel.value=cur;
  const one=files.length===1&&!!sel.value;$('#adVerWrap').hidden=!one;
  if(one){
    const vs=$('#adVersionOf'),was=vs.value;
    vs.innerHTML='<option value="">a new document of the project</option>'+adProjFiles(sel.value).map(d=>`<option value="${esc(d.rp)}">a new version of ${esc(d.rp)}${d.v?' (now v'+esc(d.v)+')':''}</option>`).join('');
    if([...vs.options].some(o=>o.value===was))vs.value=was;
  }
}
