const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(t){const el=$('#toast');el.textContent=t;el.classList.add('show');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove('show'),2600)}

const TYPE_LABEL={research_project:'Project',research_paper:'Paper',research_notes:'Notes',legal_project:'Legal project',legal_guideline:'Guideline',standard:'Standard',guidance:'Guidance & FAQ'};
const LEGAL_T=new Set(['legal_project','legal_guideline','standard','guidance']);   /* REQ-38: law, guidelines, standards – drawn as triangles */
const TYPE_COLOR={research_project:'var(--t-project)',research_paper:'var(--t-paper)',research_notes:'var(--t-notes)',legal_project:'var(--t-legal)',legal_guideline:'var(--t-guideline)',standard:'var(--t-standard)',guidance:'var(--t-guidance)'};
const CONTRIB_LABEL={content:'Content',data:'Data contribution',analysis:'Analysis contribution',results:'Results presentation',instrument:'Survey instrument',submission:'Submission material',literature:'Literature',presentation:'Presentation',version:'Earlier version',text:'Supporting text',other:'Other contribution'};
const ROLE_LABEL={manuscript:'Manuscript',abstract:'Abstract',title_page:'Title page',cover_letter:'Cover letter',reviewer_response:'Reviewer response',highlights:'Highlights',appendix:'Appendix',tables:'Tables',figures:'Figures',submission_pdf:'Submission PDF',questionnaire:'Questionnaire',data:'Data',analysis_script:'Analysis script',analysis_output:'Analysis output',model_file:'Model file',notes:'Notes',presentation:'Presentation',image:'Image',reference:'Reference',legal_text:'Legal text',white_paper:'White paper',other:'Other'};
const STAGE_LABEL={initial_submission:'Initial submission',revision_1:'Revision 1',revision_2:'Revision 2',accepted:'Accepted',submission:'Submission',
  proposal:'Proposal',committee:'Committee amendments (Parliament)',position_parliament:'Parliament position',position_council:'Council position',general_approach:'General approach',trilogue_agreement:'Trilogue agreement',adopted:'Adopted text',published:'Published',consolidated:'Consolidated version',corrigendum:'Corrigendum',draft:'Draft',consultation:'Draft for consultation',final:'Final version',revised:'Revised version',withdrawn:'Withdrawn',version:'Version',is:'Published (60.60)',dis:'DIS (40)',fdis:'FDIS (50)',cd:'Committee draft (30)',wd:'Working draft (20)',amendment:'Amendment',edition:'Edition'};
const DATE_SRC={doc_properties:'document properties',pdf_metadata:'PDF metadata',filename:'file name',filename_year:'year in file name',file_mtime:'file system (uncertain)',text:'publication date in the text',curated:'curated (_summaries.yaml)'};
const SUM_FIELDS=[['purpose','Purpose'],['design_methodology_approach','Design / Methodology / Approach'],['findings','Findings'],['research_limitations_implications','Research limitations / implications'],['originality_value','Originality / value']];

/* ---------- Backend or demo ---------- */
const APP_VERSION='3.9.0';let LIVE=false;let BACKEND_VERSION='';let IS_ADMIN=false;let AUTH_MODE='local';
const DEMO = window.DEMO_DATA || null;
let METHOD_LABEL={lab_experiment:'Lab experiment',simulation_game:'Simulation / business game',survey:'Survey',interview:'Qualitative interviews',case_study:'Case study',literature_review:'Literature review',regression:'Regression analysis',multilevel:'Multilevel analysis (HLM)',sem:'Structural equation modeling',interrater_reliability:'Interrater reliability',mental_model_elicitation:'Mental model elicitation',system_dynamics:'System dynamics',qualitative_content_analysis:'Qualitative content analysis'};
async function detectBackend(){
  try{
    const ctl=new AbortController();setTimeout(()=>ctl.abort(),2500);
    const r=await fetch('api/health',{signal:ctl.signal});
    if(!r.ok&&r.status>=500)setTimeout(()=>toast(`Backend not reachable (HTTP ${r.status}) – showing the demo. Restart the frontend container: docker compose restart frontend`),800);
    if(r.ok && (r.headers.get('content-type')||'').includes('json')){LIVE=true;const h=await r.json();BACKEND_VERSION=h.version||'';if(Array.isArray(h.databases)&&h.databases.length)DATABASES=h.databases;if(typeof applyDbGate==='function')applyDbGate();if(h.database_names&&typeof h.database_names==='object')Object.assign(DB_NAME,h.database_names)}
  }catch(e){}
  if(LIVE){
    try{
      const r=await fetch('api/me');
      if(r.status===401){
        const problem=await r.json();
        if(problem.login_url==='/review-login.html'){location.replace(problem.login_url);return false}
      }
      if(!r.ok)throw new Error('Login required');
      const user=await r.json();IS_ADMIN=user.is_admin===true;AUTH_MODE=user.auth_mode||'local';
      const logout=$('#logout');logout.hidden=!user.access_enabled;
      logout.title=user.email||(AUTH_MODE==='reviewer'?'Anonymous reviewer':'');
    }catch(e){IS_ADMIN=false}
    ['#dbAdd','#openUpload'].forEach(s=>{const el=$(s);if(el)el.hidden=!IS_ADMIN});   // #dbAdd removed in 3.5.1
  }
  const m=$('#mode');
  m.textContent=LIVE?'Live':'Demo';
  if(LIVE&&BACKEND_VERSION)$('#appVersion').title=(DB_UNLOCKED?'Release notes · ':'')+'Frontend v'+APP_VERSION+' · Backend v'+BACKEND_VERSION;m.classList.toggle('live',LIVE);
  m.title=LIVE?'Connected to the backend':'No backend reachable: the document list shows real metadata from the sample project (without LLM enrichment); chat answers are examples.';
}
$('#logout').addEventListener('click',async()=>{
  if(AUTH_MODE==='reviewer'){
    try{const r=await fetch('api/reviewer/logout',{method:'POST'});if(!r.ok)throw new Error('Logout failed')}catch(e){toast('Logout failed; please try again');return}
    location.replace('/review-login.html');
  }else location.replace('/cdn-cgi/access/logout');
});
// Do not restore credentials or conversations from the back/forward cache after logout.
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload()});

function headers(json=true){const h={};if(json)h['Content-Type']='application/json';if(apiKey)h['X-OpenRouter-Key']=apiKey;return h}

/* filter summary text, e.g. "db=ML · type=Paper" (used by the chats and the parameter lines) */
/* euro amounts of token costs: below one cent with four decimals */
function fmtEur(x){return x==null?'–':x>0&&x<0.01?'€'+x.toFixed(4):'€'+x.toFixed(2)}
function filterSummary(f){
  const o=[];
  if(f.database&&f.database.length)o.push('db='+f.database.map(d=>typeof dbName==='function'?dbName(d):d).join('|'));
  if(f.doc_type&&f.doc_type.length)o.push('type='+f.doc_type.map(t=>TYPE_LABEL[t]).join('|'));
  if(f.project&&f.project.length)o.push('project='+f.project.join('|'));
  if(f.person&&f.person.length)o.push('person='+f.person.join('|'));
  if(f.deo&&f.deo.length)o.push('deo='+f.deo.join('|'));
  if(f.filetype&&f.filetype.length)o.push('filetype='+f.filetype.join('|'));
  if(f.cluster&&f.cluster.length)o.push('cluster='+f.cluster.join('|'));
  if(f.method&&f.method.length)o.push('method='+f.method.join('|'));
  if(f.role&&f.role.length)o.push('role='+f.role.join('|'));
  if(f.year_from||f.year_to)o.push('year='+(f.year_from||'')+'–'+(f.year_to||''));
  if(f.latest_only)o.push('latest versions');
  return o.length?o.join(' · '):'none';
}
