/* ===== "Window to the outside" (REQ-20 · REQ-24 · REQ-25) =====
   Not a fixed area any more: a small button below the database bar shows a live mini copy of the desert
   construction-site animation and opens the full window (#bOutside) as a pop-up. */

/* Mini scene: copy the window's SVG with its own ids – the window is hidden (display:none), and gradients or
   filters referenced from inside a hidden SVG would not render in the copy. The view box zooms in on the excavator. */
(()=>{
  const src=$('#bOutside svg.dz'),dst=$('#bOutsideScene');if(!src||!dst)return;
  dst.innerHTML=src.outerHTML.replace(/id="dz/g,'id="bdz').replace(/url\(#dz/g,'url(#bdz').replace(/role="img"|aria-label="[^"]*"/g,'');
  const sv=dst.querySelector('svg');
  sv.setAttribute('aria-hidden','true');sv.setAttribute('focusable','false');
  sv.setAttribute('viewBox','150 214 540 144');sv.setAttribute('preserveAspectRatio','xMidYMid slice');
})();

/* Open / close: button toggles, ✕, a click on the backdrop or Esc closes; focus moves into the window and back */
function bOutside(open){
  const w=$('#bOutside'),s=$('#bOutsideScrim'),b=$('#bOutsideBtn');if(!w)return;
  w.hidden=s.hidden=!open;b.setAttribute('aria-expanded',String(open));
  (open?$('#bOutsideClose'):b).focus();
}
$('#bOutsideBtn').addEventListener('click',()=>bOutside($('#bOutside').hidden));
$('#bOutsideClose').addEventListener('click',()=>bOutside(false));
$('#bOutsideScrim').addEventListener('click',()=>bOutside(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#bOutside').hidden)bOutside(false)});
