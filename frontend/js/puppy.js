/* Dahlia's puppy: when the database Dahlia (DL) is selected, a little dog hops onto ALITA's head,
   sits there wagging its tail, blinks and follows her head movements; deselecting Dahlia lets it hop off.
   Own SVG drawing; sits in the database bar above the avatar (the avatar itself clips its overflow). */
(function(){
  const av=document.getElementById('avatar'),bar=document.querySelector('.dbbar');if(!av||!bar)return;
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let dog=null,raf=0,leaving=false;
  const W=46,H=40;   // px
  const SVG=`<svg viewBox="0 0 46 40" width="${W}" height="${H}" aria-hidden="true">
    <defs><radialGradient id="pupFur" cx=".45" cy=".35" r=".75"><stop offset="0" stop-color="#fff1dc"/><stop offset=".7" stop-color="#f3cf9f"/><stop offset="1" stop-color="#d9a46a"/></radialGradient></defs>
    <g class="pup-tail"><path d="M33 29q8-3 9-11q1 5-2 9q-3 4-7 4Z" fill="#e2b077" stroke="#b9824a" stroke-width=".6"/></g>
    <ellipse cx="23" cy="31" rx="11" ry="7.5" fill="url(#pupFur)" stroke="#c38f57" stroke-width=".6"/>
    <ellipse cx="17" cy="37" rx="3.2" ry="2.2" fill="#fff4e4" stroke="#c38f57" stroke-width=".5"/><ellipse cx="29" cy="37" rx="3.2" ry="2.2" fill="#fff4e4" stroke="#c38f57" stroke-width=".5"/>
    <g class="pup-head">
      <path class="pup-earL" d="M12 9q-7 1-7 10q0 6 4 7q3-6 5-13Z" fill="#b97a44"/>
      <path class="pup-earR" d="M34 9q7 1 7 10q0 6-4 7q-3-6-5-13Z" fill="#b97a44"/>
      <circle cx="23" cy="16" r="11.5" fill="url(#pupFur)" stroke="#c38f57" stroke-width=".6"/>
      <ellipse cx="23" cy="21" rx="6.2" ry="4.6" fill="#fff6ea"/>
      <ellipse cx="29" cy="11" rx="3.2" ry="2.6" fill="#e0a868" opacity=".7"/>
      <g class="pup-eyes"><ellipse cx="18.5" cy="15.5" rx="1.9" ry="2.2" fill="#2a1a12"/><ellipse cx="27.5" cy="15.5" rx="1.9" ry="2.2" fill="#2a1a12"/>
        <circle cx="19.1" cy="14.7" r=".7" fill="#fff"/><circle cx="28.1" cy="14.7" r=".7" fill="#fff"/></g>
      <ellipse cx="14.5" cy="19.5" rx="2" ry="1.2" fill="#ff9ab0" opacity=".55"/><ellipse cx="31.5" cy="19.5" rx="2" ry="1.2" fill="#ff9ab0" opacity=".55"/>
      <path d="M21.2 19.2q1.8-1.2 3.6 0q-.4 1.6-1.8 1.8q-1.4-.2-1.8-1.8Z" fill="#2a1a12"/>
      <path d="M23 21v1.2M20.6 22.4q1.2 1.4 2.4 0q1.2 1.4 2.4 0" fill="none" stroke="#2a1a12" stroke-width=".6" stroke-linecap="round"/>
      <path class="pup-tongue" d="M22 23.3q1 2.8 2 0Z" fill="#ff7d93"/>
      <path d="M17 6.5q2-2.5 4-.5" fill="none" stroke="#e7b980" stroke-width="1" stroke-linecap="round"/>
      <g transform="translate(31 5) rotate(15)"><circle r="2.6" fill="var(--db-DL,#8ea6ef)"/><circle r="1" fill="#fff8d0"/></g>
    </g></svg>`;
  function spot(){   // where the dog sits, relative to the bar: on top of the head, following its movement
    const a=av.getBoundingClientRect(),b=bar.getBoundingClientRect(),k=a.width/120;
    let hx=0,hy=0;const h=document.getElementById('avHead');const m=h&&/translate\(([-\d.]+)[ ,]+([-\d.]+)\)/.exec(h.getAttribute('transform')||'');if(m){hx=+m[1];hy=+m[2]}
    return {x:a.left-b.left+(60+hx)*k-W/2,y:a.top-b.top+(22+hy)*k-H*.86};
  }
  function place(){if(!dog)return;const p=spot();dog.style.left=p.x+'px';dog.style.top=p.y+'px';raf=requestAnimationFrame(place)}
  function hopOn(){
    if(dog&&!leaving)return;if(dog){dog.remove();dog=null}
    leaving=false;dog=document.createElement('div');dog.className='puppy';dog.innerHTML=SVG;dog.title='Dahlia\'s puppy';bar.appendChild(dog);
    cancelAnimationFrame(raf);place();
    if(reduce||!dog.animate)return;
    dog.firstElementChild.animate([   // hop in from the right with a bounce and a little squash on landing
      {transform:'translate(120px,60px) rotate(18deg) scale(.7)',opacity:0},
      {transform:'translate(70px,-34px) rotate(-8deg) scale(.95)',opacity:1,offset:.45},
      {transform:'translate(0,-6px) rotate(-4deg) scale(1)',offset:.8},
      {transform:'translate(0,2px) scale(1.12,.86)',offset:.9},
      {transform:'translate(0,0) scale(1)'}],{duration:950,easing:'cubic-bezier(.3,.6,.4,1)'});
  }
  function hopOff(){
    if(!dog||leaving)return;leaving=true;const d=dog;
    const done=()=>{if(dog===d){cancelAnimationFrame(raf);d.remove();dog=null;leaving=false}};
    if(reduce||!d.animate)return done();
    d.firstElementChild.animate([{transform:'translate(0,0)'},{transform:'translate(0,3px) scale(1.1,.88)',offset:.15},
      {transform:'translate(-60px,-36px) rotate(-14deg)',offset:.55},{transform:'translate(-120px,70px) rotate(-24deg) scale(.7)',opacity:0}],{duration:800,easing:'ease-in',fill:'forwards'}).onfinish=done;
  }
  window.syncPuppy=()=>{try{(typeof SEL_DB!=='undefined'&&SEL_DB.includes('DL'))?hopOn():hopOff()}catch(e){}};
  // a pat on the head: clicking the dog makes it jump for joy
  bar.addEventListener('click',e=>{const p=e.target.closest&&e.target.closest('.puppy');if(!p||reduce||!p.animate)return;e.stopPropagation();
    p.firstElementChild.animate([{transform:'translateY(0)'},{transform:'translateY(-14px) rotate(-6deg)',offset:.4},{transform:'translateY(0) scale(1.08,.9)',offset:.8},{transform:'translateY(0)'}],{duration:520,easing:'ease-out'});});
})();
