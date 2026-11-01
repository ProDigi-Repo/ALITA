/* Clusters – names and labels, the 2D cluster map (A band) and the cluster graph with the project level (B). */
/* Cluster label for the legend chips: a leading database name ("Magnolia · …" or "ML · …") is shown as its flower icon */
/* REQ-04 – descriptive cluster names: the title from clustering (LLM, or built from the cluster's most distinctive
   word pairs), else a readable name made from the distinctive terms; the term list itself is only shown as a detail. */
function cvDbPrefix(label){const m=String(label||'').match(/^([^·]+?)\s*·\s*/);if(!m)return null;const k=m[1].trim(),id=DB_FLOWER[k]?k:Object.keys(DB_NAME).find(i=>DB_NAME[i]===k);return id&&DB_FLOWER[id]?{id,rest:String(label).slice(m[0].length)}:null}
function cvTermsName(label){
  const p=cvDbPrefix(label),t=(p?p.rest:String(label||'')).split(' · ').map(x=>x.trim()).filter(Boolean).slice(0,3);
  const tc=w=>/^(ai|llm|pls|sem|hr|it|esg|csr|ux|ui|qca|nlp|rag)$/i.test(w)?w.toUpperCase():w[0].toUpperCase()+w.slice(1);
  if(!t.length)return '';const w=t.map(tc);return w.length===1?w[0]:w.slice(0,-1).join(', ')+' and '+w[w.length-1];
}
function cvName(c,info){const i=(info||clusterInfo()||{})[c.id];return (i&&i.title&&dbRelabel(i.title))||cvTermsName(c.label)||('Cluster '+c.id)}
function cvChipHtml(c,info){const p=cvDbPrefix(c.label);return (p?`<i class="cv-flw" style="color:${dbColor(p.id)}" title="${esc(dbName(p.id))}">${DB_FLOWER[p.id]}</i>`:'')+esc(cvName(c,info))}
function cvLabelHtml(label){
  const s=String(label||''),m=s.match(/^([^·]+?)\s*·\s*/);
  if(m){const k=m[1].trim(),id=DB_FLOWER[k]?k:Object.keys(DB_NAME).find(i=>DB_NAME[i]===k);
    if(id&&DB_FLOWER[id])return `<i class="cv-flw" style="color:${dbColor(id)}" title="${esc(dbName(id))}">${DB_FLOWER[id]}</i>${esc(s.slice(m[0].length))}`}
  return esc(s);
}
function renderClusterViz(){
  if(typeof cpRenderSel==='function')cpRenderSel();   // descriptions of the selected clusters below the views
  cvBasisBadge();
  const band=$('#cviz');if(!band||band.classList.contains('collapsed')||$('#page-chat').hidden)return;
  const units=cvUnits(),cls=cvClusters(units);
  if(!CV.sels.size&&$('#rCluster')&&$('#rCluster').value!=='')CV.sels.add(+$('#rCluster').value);
  [...CV.sels].forEach(id=>{if(!cls.find(c=>c.id===id))CV.sels.delete(id)});
  if(typeof cpRenderSel==='function')cpRenderSel();
  const run=(DEMO&&!LIVE&&DEMO.clusters&&DEMO.clusters.run)||'';
  if(units.length<2){
    const msg='<div class="cv-empty">No cluster analysis yet.<br>Papers, notes and projects need a structured summary and a summary vector; clustering runs automatically after ingestion.</div>';
    $('#cvMap').innerHTML=msg;$('#cvGraph').innerHTML=msg;$('#cvLegend').innerHTML='';$('#cvMapMeta').textContent='';$('#cvGraphMeta').textContent='';$('#cvGraphHint').textContent='';return;
  }
  const nOn=units.filter(u=>u.on).length;
  $('#cvMapMeta').textContent=`${SEL_DB.length?cls.filter(c=>c.on.length).length:cls.length} clusters · ${nOn}${SEL_DB.length?'':'/'+units.length} data points${SEL_DB.length?' in '+dbNames(SEL_DB).join('+'):''}${run?' · run '+run.slice(0,10):''}`;
  // ---- map
  const box=$('#cvMap'),W=Math.max(320,box.clientWidth||600),H=230,P=18;
  const X=v=>P+(v+1)/2*(W-2*P),Y=v=>P+(1-(v+1)/2)*(H-2*P);
  let g='';
  const only=SEL_DB.length>0;   // a database selection shows only its own point clouds
  cls.forEach(c=>{
    if(only&&!c.on.length)return;
    const pts=(c.on.length?c.on:c.all).map(u=>[X(u.cx),Y(u.cy)]);
    const mx=pts.reduce((a,p)=>a+p[0],0)/pts.length,my=pts.reduce((a,p)=>a+p[1],0)/pts.length;
    const sx=Math.sqrt(pts.reduce((a,p)=>a+(p[0]-mx)**2,0)/pts.length),sy=Math.sqrt(pts.reduce((a,p)=>a+(p[1]-my)**2,0)/pts.length);
    c.mx=mx;c.my=my;const dim=(cvOff(c.id))||!c.on.length;
    g+=`<ellipse class="pt" data-c="${c.id}" cx="${mx}" cy="${my}" rx="${Math.min(W*.2,Math.max(16,sx*1.7+10))}" ry="${Math.min(H*.42,Math.max(14,sy*1.7+10))}" fill="${cvCol(c.id,55)}" fill-opacity="${dim?.03:.12}" stroke="${cvCol(c.id)}" stroke-opacity="${dim?.15:.55}" stroke-dasharray="4 3"/>`;
  });
  units.forEach(u=>{if(only&&!u.on)return;const dim=!u.on||(cvOff(u.ci));g+=`<g class="pt" data-u="${u.id||''}" data-p="${u.t==='research_project'?esc(u.pn):''}" data-c="${u.ci}">${cvShape(u,X(u.cx),Y(u.cy),cvCol(u.ci),dim)}</g>`});
  cls.forEach(c=>{if(only&&!c.on.length)return;const dim=(cvOff(c.id))||!c.on.length;g+=`<g class="pt" data-c="${c.id}" opacity="${dim?.3:1}"><rect x="${c.mx-14}" y="${c.my-27}" width="28" height="15" rx="7.5" fill="${cvCol(c.id)}"/><text x="${c.mx}" y="${c.my-16}" text-anchor="middle" font-size="10.5" font-weight="700" style="fill:#fff">C${c.id}</text></g>`});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cluster map: papers, notes and projects positioned by similarity of their structured summaries">${cvFlowerDefs()}${g}</svg>`;
  const cvInfo=clusterInfo();
  $('#cvLegend').innerHTML=cls.filter(c=>!only||c.on.length).map(c=>`<button type="button" data-c="${c.id}" aria-pressed="${cvHas(c.id)}" style="--h:${cvHue(c.id)}" title="Add or remove cluster ${c.id} from the search space of both chats"><b>C${c.id}</b><span title="Distinctive terms: ${esc(cvTermsName(c.label)?(cvDbPrefix(c.label)||{rest:c.label}).rest:c.label)}">${cvChipHtml(c,cvInfo)} · ${c.on.length}</span></button>`).join('')+
    `<span class="srcnote" style="align-self:center;margin-left:4px">■ paper ● note ◆ project · flower = database · click clusters to select them for both chats${CV.sels.size?` · <a href="#" data-clear-cl>clear selection (${[...CV.sels].map(x=>'C'+x).join(', ')})</a>`:''}</span>`;
  if(CV.mode==='db'){const r=cvDbOverlay(units,cls,X,Y,W,H);box.innerHTML=r.svg;$('#cvLegend').innerHTML=r.legend;
    $('#cvMapMeta').textContent=r.dbs.length?`comparing ${r.dbs.join(' · ')}${run?' · run '+run.slice(0,10):''}`:'no database with clustered documents';}
  $$('#cvLegend button[data-c]').forEach(b=>b.addEventListener('click',()=>cvSelect(+b.dataset.c)));
  wireProfileHover('#cvLegend button[data-c]');
  $$('#cvLegend [data-clear-cl]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();cvClear()}));
  const tip=$('#cvTip');
  $$('#cvMap .pt').forEach(el=>{
    const u=el.dataset.u!==undefined&&(el.dataset.u||el.dataset.p)?units.find(x=>(el.dataset.u&&x.id===el.dataset.u)||(el.dataset.p&&x.t==='research_project'&&x.pn===el.dataset.p)):null;
    const c=cls.find(x=>x.id===+el.dataset.c);
    el.addEventListener('mousemove',ev=>!u&&el.dataset.c?(cvTip(tip,null,''),showProfile(+el.dataset.c,ev)):cvTip(tip,box.parentElement,u?`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''} · C${u.ci} ${esc(u.cl||'')}${u.ca!=null?`<br>also close to C${u.ca}`:''}${u.on?'':'<br><i>outside the selected databases</i>'}`:`<b>C${c.id}</b> ${esc(c.label)}<br>${c.on.length} data points`,ev));
    el.addEventListener('mouseleave',()=>{cvTip(tip,null,'');hideProfile()});
    el.addEventListener('click',()=>{if(u&&u.id&&typeof openDoc==='function')openDoc(u.id);else cvSelect(+el.dataset.c)});
  });
  renderClusterGraph(units,cls);
  if(V3.on){mountMap3D(units,cls);mountGraph3D(units,cls)}
}
/* Project level above the clusters (B page): one node per research project, linked to every cluster that holds
   files of the project (line width = number of files). A click selects all clusters of the project for the chats. */
function cvProjects(units,ids){
  const m=new Map();units.forEach(u=>{if(!u.on||u.t!=='research_project'||!u.pn||(ids&&!ids.has(u.ci)))return;
    const p=m.get(u.pn)||{pn:u.pn,n:0,by:new Map()};p.n++;p.by.set(u.ci,(p.by.get(u.ci)||0)+1);m.set(u.pn,p)});
  return [...m.values()].sort((a,b)=>a.pn.localeCompare(b.pn));
}
function cvProjTitle(pn){const p=(typeof PROJECTS!=='undefined'?PROJECTS:[]).find(x=>x.name===pn);return (p&&p.title)||pn}
function cvProjTipHtml(p){const cl=[...p.by.entries()].sort((a,b)=>b[1]-a[1]),pr=(typeof PROJECTS!=='undefined'?PROJECTS:[]).find(x=>x.name===p.pn),tot=pr&&pr.files;
  return `<b>Project ${esc(p.pn)}</b><br>${esc(cvProjTitle(p.pn))}<br>${p.n} document${p.n>1?'s':''} on the map${tot?` (of ${tot} files – those with their own summary)`:''}, in ${cl.length} cluster${cl.length>1?'s':''}: ${cl.slice(0,8).map(([c,n])=>`C${c} (${n})`).join(', ')}${cl.length>8?' …':''}<br><i>click to select these clusters</i>`}
function cvSelectProject(p){
  const ids=[...p.by.keys()];const all=ids.every(id=>CV.sels.has(id));
  CV.sels=all?new Set([...CV.sels].filter(id=>!ids.includes(id))):new Set(ids);   // click again = deselect
  CG.sel=CV.sels.size?[...p.by.entries()].sort((a,b)=>b[1]-a[1])[0][0]:null;
  CG.proj=all?null:p.pn;   // REQ-09: the project card opens top right (closes again on the second click)
  cvChanged();renderClusterPage();const b=$('#page-graph .bq-cluster .bq-body');if(b)b.scrollTop=0;
}
/* REQ-09: project card at the top of "Projects & clusters" – what the project contains and how it relates to the clusters */
function cgRenderProj(units){
  const box=$('#cgProjCard');if(!box)return;
  const p=CG.proj&&PROJECTS.find(x=>x.name===CG.proj);
  if(!p){box.hidden=true;box.innerHTML='';return}
  const mine=units.filter(u=>u.t==='research_project'&&u.pn===p.name&&u.on),by=new Map();mine.forEach(u=>by.set(u.ci,(by.get(u.ci)||0)+1));
  const cls=cvClusters(units),info=clusterInfo();
  const roles=Object.entries(p.roles||{}).filter(([k])=>k!=='other').sort((a,b)=>b[1]-a[1]).slice(0,6).map(([k,v])=>`${esc((typeof ROLE_LABEL!=='undefined'&&ROLE_LABEL[k])||k.replace(/_/g,' '))} ${v}`).join(' · ');
  const purpose=(p.summary&&p.summary.purpose)||'';
  box.innerHTML=`<div class="cpd-bar"><span>Project</span><span class="cpd-state">${esc(p.name)} · its clusters are selected below</span><button type="button" class="cpd-x" data-pclose title="Close the project and deselect its clusters">✕</button></div>
    <div class="bpcard"><div class="pc-h"><i aria-hidden="true">◆</i><b>${esc(p.title||p.name)}</b></div>
      ${purpose?`<p class="cp-d">${esc(purpose.length>320?purpose.slice(0,319).replace(/\s+\S*$/,'')+'…':purpose)}</p>`:''}
      <dl class="kv"><dt>Folder</dt><dd>${esc(p.name)}${(p.db||[]).length?' · '+(p.db||[]).map(n=>`<span class="pdbi" style="color:${dbColor(n)}" title="${esc(dbName(n))}">${dbIcon(n)}</span>${esc(dbName(n))}`).join(', '):''}</dd>
        ${teamRowHtml(p)}
        <dt>Files</dt><dd>${p.files||0} (${p.indexed||0} with full text) · ${mine.length} on the map</dd>
        <dt>Period</dt><dd>${p.from_?p.from_.slice(0,4):'–'} – ${p.to?p.to.slice(0,4):'–'}</dd>
        ${(p.keywords||[]).length?`<dt>Keywords</dt><dd>${esc(p.keywords.slice(0,6).join(', '))}</dd>`:''}
        ${roles?`<dt>Contents</dt><dd>${roles}</dd>`:''}</dl>
      ${typeof cgProgressSection==='function'?cgProgressSection(p.name):''}
      <h6>Clusters of this project</h6><div class="cp-conn">${[...by.entries()].sort((a,b)=>b[1]-a[1]).map(([ci,n])=>{const c=cls.find(k=>k.id===ci)||{id:ci,label:''};
        return `<button type="button" data-cc="${ci}" style="--h:${cvHue(ci)}" aria-pressed="${cvHas(ci)}" title="${n} document${n>1?'s':''} of the project in C${ci}"><b>C${ci}</b><span>${esc(cvName(c,info))}</span><small>${n}</small></button>`}).join('')}</div>
      ${cpDocListHtml(mine,'project')}</div>`;
  box.hidden=false;
  box.querySelector('[data-pclose]').addEventListener('click',()=>{const pj=cvProjects(units).find(x=>x.pn===p.name);CG.proj=null;if(pj&&[...pj.by.keys()].every(id=>CV.sels.has(id)))cvSelectProject(pj);else renderClusterPage()});
  cpWireConn(box);wireTeam(box,()=>cgRenderProj(units));if(typeof wireProgress==='function')wireProgress(box);
}
function renderClusterGraph(units,cls,o={}){
  const big=!!o.big,box=o.box||$('#cvGraph');
  const W=Math.max(320,box.clientWidth||600),H=big?Math.max(240,box.clientHeight||380):230;
  const isSel=id=>big?CG.sel===id:cvHas(id),anyS=big?CG.sel!=null:CV.sels.size>0,colorDb=big?CG.mode==='db':CV.mode==='db',showDocs=true;
  const links=cvLinks(units),act=cls.filter(c=>c.on.length),info=clusterInfo();
  const XL=typeof xcLinks==='function'?xcLinks(act.map(c=>c.id)):[];   // REQ-59: relations to the clusters of a compared database
  if(!big){
    $('#cvGraphMeta').textContent=`${act.length} cluster nodes · ${links.length} bridges`;
    $('#cvGraphHint').textContent='Node size = data points · line = documents whose second-closest cluster is the other node · click a node to ask the Graph Chat';
  }
  if(!act.length){box.innerHTML='<div class="cv-empty">No clustered documents for the current database selection.</div>';return {act,links}}
  const K=big?Math.min(1.9,Math.max(1.15,Math.min(W,H)/320)):1;
  const R=c=>(9+Math.sqrt(c.on.length)*4.2)*K;
  // deterministic force layout
  const N=act.map((c,i)=>({c,x:W/2+Math.cos(i/act.length*2*Math.PI)*W*.3,y:H/2+Math.sin(i/act.length*2*Math.PI)*H*.3,vx:0,vy:0}));
  const idx=new Map(N.map((n,i)=>[n.c.id,i]));
  for(let it=0;it<320;it++){
    for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){const a=N[i],b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy)||.01;const f=5200*K*K/(d*d);dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
    links.forEach(l=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||.01,f=(d-(R(a.c)+R(b.c)+(big?120:60)*K))*.02*Math.min(3,1+l.n/4);a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f});
    XL.forEach(l=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||.01,f=(d-(R(a.c)+R(b.c)+(big?150:70)*K))*.012*Math.max(.2,l.s);a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f});
    N.forEach(n=>{n.vx+=(W/2-n.x)*.01;n.vy+=(H/2-n.y)*.02;n.x+=n.vx*.5;n.y+=n.vy*.5;n.vx*=.6;n.vy*=.6});
  }
  // fit into the box
  const PJ=big?cvProjects(units,new Set(act.map(c=>c.id))):[],band=PJ.length?78:0;   // project level on top
  const pad=big?90:40,minX=Math.min(...N.map(n=>n.x-R(n.c))),maxX=Math.max(...N.map(n=>n.x+R(n.c))),minY=Math.min(...N.map(n=>n.y-R(n.c))),maxY=Math.max(...N.map(n=>n.y+R(n.c)));
  const sc=Math.min((W-2*pad)/Math.max(1,maxX-minX),(H-band-2*pad)/Math.max(1,maxY-minY),1.6);
  N.forEach(n=>{n.x=W/2+(n.x-(minX+maxX)/2)*sc;n.y=band+(H-band)/2+(n.y-(minY+maxY)/2)*sc});
  let g='';const maxN=Math.max(1,...links.map(l=>l.n));
  links.forEach(l=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const hi=anyS&&(isSel(l.a)||isSel(l.b)),dim=anyS&&!hi;
    g+=`<line class="cnode" data-l="${l.a}-${l.b}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="var(--c2)" stroke-width="${(1.2+l.n/maxN*6)*(big?1.4:1)}" stroke-linecap="round" opacity="${dim?.12:hi?.85:.45}"/>`;
    if(big&&!dim){const mx=(a.x+b.x)/2,my=(a.y+b.y)/2;g+=`<g><rect x="${mx-11}" y="${my-9}" width="22" height="16" rx="8" fill="var(--panel)" stroke="var(--c2)" stroke-opacity=".5"/><text x="${mx}" y="${my+3}" text-anchor="middle" font-size="10.5" class="muted">${l.n}</text></g>`}
  });
  XL.forEach((l,k)=>{const a=N[idx.get(l.a)],b=N[idx.get(l.b)];if(!a||!b)return;const hi=anyS&&(isSel(l.a)||isSel(l.b)),dim=anyS&&!hi;
    g+=`<line class="cnode xlink" data-x="${k}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#7c4dff" stroke-width="${(1+l.s*4)*(big?1.3:1)}" stroke-dasharray="7 5" stroke-linecap="round" opacity="${dim?.15:hi?.95:.7}" style="cursor:pointer"/>`;
    if(big&&!dim){const mx=(a.x+b.x)/2,my=(a.y+b.y)/2;g+=`<g class="cnode xlink" data-x="${k}" style="cursor:pointer"><rect x="${mx-17}" y="${my-9}" width="34" height="16" rx="8" fill="var(--panel)" stroke="#7c4dff"/><text x="${mx}" y="${my+3}" text-anchor="middle" font-size="10.5" style="fill:#7c4dff">${l.s.toFixed(2)}</text></g>`}
  });
  if(PJ.length){
    const mxp=Math.max(1,...PJ.flatMap(p=>[...p.by.values()])),py=30;
    PJ.forEach((p,k)=>{p.x=W*(k+1)/(PJ.length+1);p.y=py});
    PJ.forEach(p=>p.by.forEach((cnt,ci)=>{const nd=N[idx.get(ci)];if(!nd)return;const dim=anyS&&!isSel(ci);
      g+=`<line class="cproj-l" x1="${p.x}" y1="${p.y+12}" x2="${nd.x}" y2="${nd.y-R(nd.c)}" stroke="var(--t-project)" stroke-width="${1+cnt/mxp*7}" stroke-linecap="round" opacity="${dim?.1:.45}"/>`}));
    const maxCh=Math.max(6,Math.floor((W/(PJ.length+1)-34)/7));   // name fits up to the next project
    PJ.forEach(p=>{const nm=p.pn.length>maxCh?p.pn.slice(0,maxCh-1)+'…':p.pn;
      g+=`<g class="cproj" data-pn="${esc(p.pn)}" style="cursor:pointer"><circle cx="${p.x}" cy="${p.y}" r="13" fill="var(--t-project)" stroke="var(--panel)" stroke-width="2"/>`+
        `<path d="M${p.x} ${p.y-6}L${p.x+6} ${p.y}L${p.x} ${p.y+6}L${p.x-6} ${p.y}Z" fill="#fff" opacity=".9"/>`+
        `<text x="${p.x+19}" y="${p.y-1}" font-size="12.5" font-weight="600">${esc(nm)}</text><text x="${p.x+19}" y="${p.y+13}" font-size="10.5" class="muted">${p.n} docs · ${p.by.size} clusters</text></g>`});
    g+=`<text x="10" y="14" font-size="10.5" class="muted" style="letter-spacing:.06em">PROJECTS</text><line x1="0" y1="${band-6}" x2="${W}" y2="${band-6}" stroke="var(--line)" stroke-dasharray="3 4"/>`;
  }
  N.forEach(n=>{
    const c=n.c,r=R(c),dim=anyS&&!isSel(c.id),op=dim?.25:1;
    if(showDocs)c.on.forEach((u,i)=>{const a=i/c.on.length*2*Math.PI-Math.PI/2,ring=r+(big?14:7),ux=n.x+Math.cos(a)*ring,uy=n.y+Math.sin(a)*ring;
      const col=colorDb?`var(--db-${(u.db||[])[0]||'none'},var(--muted))`:(TYPE_COLOR[u.t]||'var(--t-project)');
      const sz=big?5.5:2.6,attrs=big?` class="cnode doc" data-u="${esc(u.id||'')}" data-pn="${u.t==='research_project'?esc(u.pn):''}" data-c="${c.id}"`:'';
      g+=`<g${attrs} opacity="${op}">`+(u.t==='research_project'?`<path d="M${ux} ${uy-sz*1.6}L${ux+sz*1.6} ${uy}L${ux} ${uy+sz*1.6}L${ux-sz*1.6} ${uy}Z" fill="${col}" stroke="var(--panel)"/>`:LEGAL_T.has(u.t)?`<path d="M${ux} ${uy-sz*1.5}L${ux+sz*1.35} ${uy+sz}L${ux-sz*1.35} ${uy+sz}Z" fill="${col}" stroke="var(--panel)"/>`:u.t==='research_paper'&&big?`<rect x="${ux-sz}" y="${uy-sz}" width="${sz*2}" height="${sz*2}" rx="1.5" fill="${col}" stroke="var(--panel)"/>`:`<circle cx="${ux}" cy="${uy}" r="${sz}" fill="${col}" stroke="var(--panel)" stroke-width="${big?1:0}"/>`)+'</g>'});
    const nm=cvName(c,info),title=big||nm.length<=26?nm:nm.slice(0,25).replace(/\s+\S*$/,'')+'…';
    const words=(c.label||'').split(' · ').slice(0,2).join(' · ');   // distinctive terms as a detail line (big graph)
    const ly=n.y+r+(big?(showDocs?34:22):19);
    g+=`<g class="cnode" data-c="${c.id}" opacity="${op}"><circle cx="${n.x}" cy="${n.y}" r="${r}" fill="${cvCol(c.id)}" stroke="${isSel(c.id)?'var(--c2)':'var(--panel)'}" stroke-width="${isSel(c.id)?(big?5:3):1.5}"/>`+
      `<text x="${n.x}" y="${n.y+(big?6:4)}" text-anchor="middle" font-size="${big?17:11.5}" font-weight="700" style="fill:#fff">C${c.id}</text>`+
      (big?`<text x="${n.x}" y="${n.y+22}" text-anchor="middle" font-size="11" style="fill:#fff;opacity:.9">${c.on.length} docs</text>`:'')+
      `<text x="${n.x}" y="${ly}" text-anchor="middle" font-size="${big?13:10.5}" ${big?'font-weight="600"':'class="muted"'}>${esc(title)}</text>`+
      (big&&title!==words?`<text x="${n.x}" y="${ly+15}" text-anchor="middle" font-size="11" class="muted">${esc(words)}</text>`:'')+`</g>`;
  });
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cluster graph: clusters as nodes, bridges between clusters as edges">${g}</svg>`;
  const tip=big?$('#cgTip'):$('#cvTip2');
  box.querySelectorAll('.cproj').forEach(el=>{const p=PJ.find(x=>x.pn===el.dataset.pn);if(!p)return;
    el.addEventListener('mousemove',ev=>cvTip(tip,box.parentElement,cvProjTipHtml(p),ev));el.addEventListener('mouseleave',()=>cvTip(tip,null,''));
    el.addEventListener('click',e=>{e.stopPropagation();cvTip(tip,null,'');cvSelectProject(p)})});
  box.querySelectorAll('.cnode').forEach(el=>{
    let html='';
    if(el.classList.contains('xlink')){const l=XL[+el.dataset.x];if(!l)return;html=xcTipHtml(l,info);
      el.addEventListener('click',e=>{e.stopPropagation();xcSelect(l)});
    }else if(el.classList.contains('doc')){
      const u=units.find(x=>(el.dataset.u&&x.id===el.dataset.u)||(el.dataset.pn&&x.t==='research_project'&&x.pn===el.dataset.pn));if(!u)return;
      html=`<b>${esc(u.ti||'')}</b><br>${CV_TYPE[u.t]||''} · ${esc(dbNames(u.db).join(', '))}${u.cs!=null?' · similarity '+(+u.cs).toFixed(2):''}${u.ca!=null?`<br>also close to C${u.ca}`:''}<br><i>click to open</i>`;
      el.addEventListener('click',e=>{e.stopPropagation();if(u.id&&typeof openDoc==='function')openDoc(u.id);else{CG.sel=u.ci;renderClusterPage()}});
    }else if(el.dataset.c){const c=cls.find(x=>x.id===+el.dataset.c);const t={};c.on.forEach(u=>t[u.t]=(t[u.t]||0)+1);
      html=`<b>C${c.id}</b> ${esc(cvName(c,info))}<br>${Object.entries(t).map(([k,v])=>`${v} ${CV_TYPE[k]||k}${v>1?'s':''}`).join(', ')}`;
      el.addEventListener('click',()=>{if(big){cgPick(c.id);return}
        cvSelect(c.id)});
    }else{const [a,b]=el.dataset.l.split('-').map(Number),l=links.find(x=>x.a===a&&x.b===b);html=`<b>C${a} ↔ C${b}</b><br>${l.n} document${l.n>1?'s':''} bridge these clusters · mean similarity ${l.s.toFixed(2)}`}
    const isC=!el.classList.contains('doc')&&!el.classList.contains('xlink')&&el.dataset.c&&!el.dataset.l;
    el.addEventListener('mousemove',ev=>isC?showProfile(+el.dataset.c,ev):cvTip(tip,box.parentElement,html,ev));
    el.addEventListener('mouseleave',()=>{cvTip(tip,null,'');hideProfile()});
  });
  return {act,links};
}
/* the A band follows data, database and cluster selection (state.js) */
Store.on('clusters',()=>renderClusterViz(),30);
Store.on('documents',()=>renderClusterViz(),40);
Store.on('databases',()=>renderClusterViz(),50);
