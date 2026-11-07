/* ---------- Header: OpenRouter key, password gate and login per database (3.13.0, REQ-81) ----------
   Moved together from documents.js and core.js. Who may see what is decided by the server when accounts exist
   (REQ-77: GET /api/me, POST /api/login, /api/logout); without accounts the shared password below works in the page. */
/* ---------- API-Key ---------- */
let apiKey='';
// Never persist a bearer key on shared computers; remove the old persisted value.
try{localStorage.removeItem('or_key')}catch(e){}
window.addEventListener('pagehide',()=>{apiKey='';$('#apiKey').value=''});
function renderKey(){
  const s=$('#keyStatus');
  if(apiKey){s.className='pill ok';s.innerHTML='<span class="dot"></span>Key …'+esc(apiKey.slice(-4));$('#apiKey').value=apiKey}
  else{s.className='pill';s.innerHTML='<span class="dot"></span>no key'}
}
function renderDbLock(){
  const p=$('#dbPass'),l=$('#dbLock'),u=$('#dbUser');if(!p)return;
  if(ACCOUNTS_ON){
    p.placeholder=ACCOUNT?(ACCOUNT.all?'all databases unlocked':'logged in · '+dbName(ACCOUNT.database)):'password of this user';
    p.disabled=!!ACCOUNT;l.hidden=!ACCOUNT;if(u){u.disabled=!!ACCOUNT;if(ACCOUNT)u.value=ACCOUNT.user}
    l.textContent=ACCOUNT?'Log out':'Lock';l.title=ACCOUNT?'Log out '+ACCOUNT.user+' – only the public databases stay visible':'';
  }else{p.placeholder=DB_UNLOCKED?'all databases unlocked':'show all databases';p.disabled=DB_UNLOCKED;l.hidden=!DB_UNLOCKED}
  applyPageGate();
}
/* REQ-77: after login or logout the server's view of this browser decides databases, pages and upload rights */
async function accountChanged(msg){
  await refreshMe();
  Store.emit('gate',DB_UNLOCKED);
  if(LOCKED_PAGES.some(x=>!$('#page-'+x).hidden&&!pageOpen(x)))showPage('graph');
  if(msg)toast(msg);
}
async function accountLogin(user,password){
  try{
    const r=await fetch('api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user,password})});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){toast(r.status===401?'Wrong user name or password':(j.detail||'Login failed'));return}
    await accountChanged(j.account.all?'Logged in · all databases are shown':'Logged in as '+j.account.user+' · only the database '+dbName(j.account.database)+' is shown');
  }catch(e){toast('Login failed: '+e.message)}
}
/* lock/unlock without a page reload: the OpenRouter key lives in page memory only and would be lost */
function setDbUnlocked(on){
  DB_UNLOCKED=on;try{on?localStorage.setItem('db_unlocked','1'):localStorage.removeItem('db_unlocked')}catch(e){}
  DATABASES=[...DB_ALL];applyDbGate();Store.emit('gate',on);
  if(!on&&LOCKED_PAGES.some(x=>!$('#page-'+x).hidden))showPage('graph');   // locked while on a hidden tab
}
Store.on('gate',()=>renderDbLock(),10);
Store.on('gate',()=>loadDocs(),20);
$('#dbLock').addEventListener('click',async()=>{
  if(ACCOUNTS_ON){try{await fetch('api/logout',{method:'POST'})}catch(e){}await accountChanged('Logged out · only the public databases are shown');return}
  setDbUnlocked(false);toast('Locked · only the public databases are shown')});
renderDbLock();
$('#keyForm').addEventListener('submit',e=>{
  e.preventDefault();
  const pw=$('#dbPass').value;
  if(pw){
    $('#dbPass').value='';
    if(ACCOUNTS_ON)accountLogin($('#dbUser').value,pw);
    else if(pw===DB_PASSWORD){setDbUnlocked(true);toast('Password correct · all databases are shown')}
    else toast('Wrong password');
    if(!$('#apiKey').value.trim()||$('#apiKey').value.trim()===apiKey)return;
  }
  const v=$('#apiKey').value.trim();
  if(v && !v.startsWith('sk-or-')){toast('The key should start with "sk-or-"');return}
  apiKey=v;
  renderKey();toast(v?'Key set · until this page is closed or reloaded':'Key removed');
  if(typeof adSync==='function'&&!$('#addData').hidden)adSync();   // the upload wizard waits for the key
});
$('#toggleKey').addEventListener('click',()=>{const i=$('#apiKey');i.type=i.type==='password'?'text':'password'});
const CHAT_MODEL_ID='openai/gpt-6-luna';   // fixed model, no selection (backend: CHAT_MODEL)
renderKey();

/* ---------- Identity and login (GET /api/me) ---------- */
/* /api/me: identity, admin rights and – with accounts (REQ-77) – the login and its databases */
function applyMe(user){
  IS_ADMIN=user.is_admin===true;AUTH_MODE=user.auth_mode||'local';
  const logout=$('#logout');logout.hidden=!user.access_enabled;
  logout.title=user.email||(AUTH_MODE==='reviewer'?'Anonymous reviewer':'');
  if(user.accounts){
    ACCOUNTS_ON=true;ACCOUNT=user.account||null;ACCOUNT_DBS=user.databases===undefined?null:user.databases;
    DB_UNLOCKED=!!(ACCOUNT&&ACCOUNT.all);DATABASES=[...DB_ALL];applyDbGate();
  }
  applyUploadRights();
  if(typeof renderDbLock==='function')renderDbLock();
}
/* uploads: admins, and users into their own database */
function applyUploadRights(){
  const may=IS_ADMIN||!!(ACCOUNT&&!ACCOUNT.all);   // REQ-84: every logged-in user uploads into their own database
  const el=$('#openUpload');if(el)el.hidden=!may;
  if(typeof renderUpTile==='function')renderUpTile();
}
async function refreshMe(){try{const r=await fetch('api/me');if(r.ok)applyMe(await r.json())}catch(e){}}
/* user names for the dropdown before the password field */
async function loadAccounts(){
  try{
    const a=await (await fetch('api/accounts')).json(),sel=$('#dbUser');if(!sel||!a.enabled)return;
    sel.innerHTML=a.users.map(u=>`<option value="${esc(u.user)}">${esc(u.all?u.label||'All databases':u.user)}</option>`).join('');
    sel.hidden=false;if(ACCOUNT)sel.value=ACCOUNT.user;
    $('#dbPass').title='Choose your user name and enter its password: each user sees only their own database ("'+esc((a.users.find(u=>u.all)||{}).label||'All databases')+'" shows everything)';
  }catch(e){}
}
$('#logout').addEventListener('click',async()=>{
  if(AUTH_MODE==='reviewer'){
    try{const r=await fetch('api/reviewer/logout',{method:'POST'});if(!r.ok)throw new Error('Logout failed')}catch(e){toast('Logout failed; please try again');return}
    location.replace('/review-login.html');
  }else location.replace('/cdn-cgi/access/logout');
});
// Do not restore credentials or conversations from the back/forward cache after logout.
window.addEventListener('pageshow',e=>{if(e.persisted)location.reload()});
