/* ---------- REQ-63: "⤢ Enlarge" opens the knowledge map in a separate browser window ----------
   The window (same address with ?view=map) shows only the knowledge map, filling the whole window – e.g. on a
   second screen. Both windows share the cluster and database selection over a BroadcastChannel, so clusters picked
   in the map window are the search space of the chats in the main window and vice versa. If the browser blocks the
   pop-up, the map is enlarged over the page as before. */
const MW={child:null,ch:null,last:'',isMap:new URLSearchParams(location.search).get('view')==='map'};
try{MW.ch=new BroadcastChannel('alita-map')}catch(e){}
if(MW.isMap){document.documentElement.classList.add('map-window');document.title='ALITA – Knowledge map'}
function mwState(){return JSON.stringify({sel:[...CV.sels].sort((a,b)=>a-b),db:[...SEL_DB].sort()})}
function mwSync(){const s=mwState();if(s===MW.last)return;MW.last=s;try{MW.ch&&MW.ch.postMessage({type:'state',state:s})}catch(e){}}
if(MW.ch)MW.ch.onmessage=e=>{
  const m=e.data||{};if(m.type!=='state'||m.state===mwState())return;
  MW.last=m.state;const st=JSON.parse(m.state);
  if(JSON.stringify([...SEL_DB].sort())!==JSON.stringify(st.db)){SEL_DB=[...st.db];try{saveDbSel()}catch(_){}}
  CV.sels=new Set(st.sel);cvChanged();try{renderClusterPage()}catch(_){}
};
/* every redraw of the B page reports a changed selection to the other window */
Store.on('cluster-page',()=>mwSync(),10);
function mwOpen(){
  if(MW.child&&!MW.child.closed){MW.child.focus();return true}
  const w=Math.min(screen.availWidth||1600,1700),h=Math.min(screen.availHeight||1000,1100);
  MW.child=window.open(location.pathname+'?view=map#graph','alita-map',`popup,width=${w},height=${h}`);
  if(!MW.child)return false;
  MW.last='';setTimeout(mwSync,1500);try{toast('Knowledge map opened in a separate window')}catch(e){}
  return true;
}
(function(){
  const b=document.getElementById('cgMax');if(!b)return;
  if(MW.isMap){b.hidden=true;return}
  b.title='Open the knowledge map in a separate window (e.g. on a second screen)';
  b.addEventListener('click',e=>{if(b.getAttribute('aria-pressed')==='true')return;if(mwOpen()){e.stopImmediatePropagation()}},true);   // capture: before the old overlay handler
})();
