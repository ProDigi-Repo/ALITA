/* REQ-99: a little school of herrings swims out of the Send button when a question is sent (both chats).
   Purely decorative: aria-hidden, no clicks caught, skipped with "reduce motion". */
(function(){
  const FISH='<svg viewBox="0 0 64 24" width="44" height="17" aria-hidden="true"><path d="M4 12C14 3 38 2 50 10L60 3V21L50 14C38 22 14 21 4 12Z" fill="#c9d6e3" stroke="#5b7a96" stroke-width="1.4"/><path d="M8 12C18 9 34 8 47 11" stroke="#7e9bb5" stroke-width="1.2" fill="none"/><path d="M22 6.2L27 3.6L30 6" fill="#a9bdd0" stroke="#5b7a96" stroke-width="1"/><circle cx="11" cy="10.4" r="1.6" fill="#1d2d3c"/><path d="M15 8.2C16.4 10.4 16.4 13.6 15 15.8" stroke="#7e9bb5" stroke-width="1.1" fill="none"/></svg>';
  const RM=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function swim(btn){
    if(RM()||!btn)return;
    const r=btn.getBoundingClientRect(),n=6;
    for(let i=0;i<n;i++){
      const f=document.createElement('div');f.className='herring';f.innerHTML=FISH;f.setAttribute('aria-hidden','true');
      const dx=-(220+Math.random()*260),dy=-(60+Math.random()*220),dur=1300+Math.random()*700,delay=i*70;
      f.style.left=(r.left+r.width/2-22)+'px';f.style.top=(r.top+r.height/2-8)+'px';
      document.body.appendChild(f);
      const wob=(Math.random()*16+8)*(Math.random()<.5?-1:1);
      f.animate([{transform:'translate(0,0) scale(.4)',opacity:0},{transform:`translate(${dx*.25}px,${dy*.25+wob}px) scale(1)`,opacity:1,offset:.2},
        {transform:`translate(${dx*.6}px,${dy*.6-wob}px) scale(1)`,opacity:1,offset:.6},{transform:`translate(${dx}px,${dy}px) scale(.9)`,opacity:0}],
        {duration:dur,delay,easing:'cubic-bezier(.3,.6,.4,1)',fill:'both'}).onfinish=()=>f.remove();
    }
  }
  document.addEventListener('submit',e=>{const f=e.target;if(f&&f.classList&&f.classList.contains('composer'))swim(f.querySelector('.send'))},true);
  window.herringSwim=swim;
})();
