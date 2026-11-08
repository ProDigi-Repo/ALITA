/* REQ-102: the document types as sea creatures – on the maps (2D SVG, layer and 3D canvas), in legends and lists.
   paper = octopus · project = whale · note = herring · law = shark · standard = shell · guideline = dolphin · FAQ = pufferfish.
   Each creature is drawn in a 24 × 24 box: a filled body, light details (eyes, ribs) and an outline in the panel colour,
   so it stays readable on dark and light backgrounds and in the colour of its type or database. */
const SEA={
  research_paper:{name:'octopus',body:'M12 2.5C7.6 2.5 5 5.8 5 9.6c0 2.3 1 4 2.4 5.1L4.5 19.6c-.4.7.4 1.4 1 .9l3.3-3.1-.6 4.4c-.1.8 1 1 1.2.2l1.4-4.4.9 4.6c.2.8 1.4.8 1.5 0l.9-4.6 1.4 4.4c.3.8 1.4.6 1.2-.2l-.6-4.4 3.3 3.1c.6.5 1.4-.2 1-.9l-2.9-4.9c1.4-1.1 2.4-2.8 2.4-5.1C19 5.8 16.4 2.5 12 2.5Z',
    dots:[[9.6,9.4,1.25],[14.4,9.4,1.25]]},
  research_project:{name:'whale',body:'M1.6 8.6c1.6.3 2.8 1.3 3.4 2.6C6.6 8.8 9.6 7.2 13.4 7.2c5 0 8.6 3.1 8.6 6.8 0 3-2.7 5.1-7.1 5.1H10.2c-3.1 0-5.2-1.6-5.8-3.7-.8 1.1-2 1.9-3.1 2 1-1.3 1.5-2.7 1.5-4.2 0-1.6-.5-3.1-1.2-4.6Z',
    lines:'M10 16.2c3 1.2 7.6 1.3 11-.4M12.6 4.6c0-1 .5-1.9 1.3-2.4M14.4 4.4c.3-.8 1-1.4 1.8-1.6', dots:[[17.8,12.6,1.1]]},
  research_notes:{name:'herring',body:'M1.4 12C5 8.4 11.6 7.8 17.1 10.5L22.6 7.3v9.4L17.1 13.5C11.6 16.2 5 15.6 1.4 12Z',
    lines:'M3.5 12.1C8 10.9 12.6 10.8 16.7 11.6M6.8 9.8c.9 1.4.9 3 0 4.4', dots:[[4.6,11.3,1]]},
  legal_project:{name:'shark',body:'M1.4 13.4C4 11.7 7.5 10.9 10.5 10.8L13.4 5.5c.3-.5 1-.4 1 .2l.3 5.3c2.4.4 4.6 1.2 6.2 2.2l1.8-2.6c.3-.4.9-.2.8.3l-.6 3.4.9 3.1c.1.5-.5.8-.8.4l-1.9-2.4c-3.5 1.6-8.3 2.1-12.5 1.3l-1.6 2.2c-.3.4-.9.2-.9-.3l.3-2.7C4 16.4 2.3 15.2 1.4 13.4Z',
    lines:'M3.3 14.6c1 .3 2.2.3 3.3 0M8.2 12.6v2.2M9.5 12.4v2.4M10.8 12.3v2.4', dots:[[5.1,12.7,1]]},
  standard:{name:'shell',body:'M12 20.4 3.9 13.1C2.9 7.9 6.9 3.4 12 3.4s9.1 4.5 8.1 9.7L12 20.4ZM9.4 20.2h5.2l-1 1.9h-3.2Z',
    lines:'M12 4.4v15M8.4 5.2l2.6 13.6M15.6 5.2 13 18.8M5.5 8.4l5.4 10.4M18.5 8.4l-5.4 10.4', dots:[]},
  legal_guideline:{name:'dolphin',body:'M1.6 16.8c2.4-.6 4.3-1.8 5.9-3.5 2.2-2.4 4.8-3.9 8.1-4.1l1.7-2.9c.3-.5 1-.3 1 .2l-.1 3c1.7.7 2.9 1.9 3.5 3.3l1.7.5c.4.2.4.8 0 .9l-1.9.6c-.9 2.3-3.5 3.8-6.8 3.8-1.6 0-3-.3-4.2-.9l-2.6 2.4c-.4.4-1.1 0-.9-.6l.7-3c-2 .1-4-.4-6.1-1.7Z',
    lines:'M12.7 16.4c2.2.4 4.6.1 6.3-.9', dots:[[18.6,12.4,1]]},
  guidance:{name:'pufferfish',body:'M3.2 12a7.6 7.6 0 1 0 15.2 0 7.6 7.6 0 1 0-15.2 0ZM18.2 12l4.3-3.4v6.8Z',
    spikes:'M10.8 1.6v2.6M10.8 19.8v2.6M3.3 4.5l1.9 1.8M16.4 17.7l1.9 1.8M3.3 19.5l1.9-1.8M16.4 6.3l1.9-1.8M.8 12h2.6M6.4 2.6l.8 2.4M14.4 19l.8 2.4M6.4 21.4l.8-2.4M14.4 5l.8-2.4',
    lines:'M6.6 14.6c.9.8 2 1 3 .6', dots:[[7.9,10.2,1.3]]},
};
const SEA_NAME_DE={octopus:'Krake',whale:'Wal',herring:'Hering',shark:'Hai',shell:'Muschel',dolphin:'Delfin',pufferfish:'Kugelfisch'};
function seaOf(t){return SEA[t]||SEA.research_notes}

/* SVG: the creature centred on (x, y), `size` = width of its box in px */
function seaGlyphSVG(t,x,y,size,fill,outline='var(--panel)',detail='rgba(255,255,255,.92)'){
  const s=seaOf(t),k=size/24,sw=(1.1/k).toFixed(2);
  return `<g transform="translate(${(x-size/2).toFixed(1)} ${(y-size/2).toFixed(1)}) scale(${k.toFixed(3)})">`
    +(s.spikes?`<path d="${s.spikes}" stroke="${fill}" stroke-width="1.6" stroke-linecap="round" fill="none"/>`:'')
    +`<path d="${s.body}" fill="${fill}" stroke="${outline}" stroke-width="${sw}" stroke-linejoin="round"/>`
    +(size>=12&&s.lines?`<path d="${s.lines}" stroke="${detail}" stroke-width="1.1" stroke-linecap="round" fill="none" opacity=".75"/>`:'')
    +(size>=9?(s.dots||[]).map(([cx,cy,r])=>`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${detail}"/>`).join(''):'')+'</g>';
}
/* a small inline icon (legends, lists, chips) in the colour of the type */
function seaIcon(t,size=16,fill='currentColor'){
  const s=seaOf(t);
  return `<svg class="sea-ic" width="${size}" height="${size}" viewBox="0 0 24 24" role="img" aria-label="${s.name}">${seaGlyphSVG(t,12,12,24,fill,'none','var(--panel,#fff)')}</svg>`;
}
/* canvas: the same creature centred on (x, y) with box width `size` */
const SEA_PATHS={};
function seaPaths(t){
  if(SEA_PATHS[t])return SEA_PATHS[t];
  const s=seaOf(t),P=d=>(typeof Path2D==='function'&&d?new Path2D(d):null);
  return SEA_PATHS[t]={body:P(s.body),lines:P(s.lines),spikes:P(s.spikes),dots:s.dots||[]};
}
function seaGlyphCanvas(g,t,x,y,size,fill,outline='rgba(255,255,255,.9)',detail='rgba(255,255,255,.92)'){
  const p=seaPaths(t);if(!p.body)return false;
  const k=size/24;g.save();g.translate(x-size/2,y-size/2);g.scale(k,k);
  if(p.spikes){g.strokeStyle=fill;g.lineWidth=1.6;g.lineCap='round';g.stroke(p.spikes)}
  g.fillStyle=fill;g.fill(p.body);
  if(outline&&size>=8){g.strokeStyle=outline;g.lineWidth=1.1/k;g.lineJoin='round';g.stroke(p.body)}
  if(size>=12&&p.lines){g.globalAlpha*=.75;g.strokeStyle=detail;g.lineWidth=1.1;g.lineCap='round';g.stroke(p.lines);g.globalAlpha/=.75}
  if(size>=9){g.fillStyle=detail;p.dots.forEach(([cx,cy,r])=>{g.beginPath();g.arc(cx,cy,r,0,Math.PI*2);g.fill()})}
  g.restore();return true;
}
const SEA_LABEL={research_paper:'Paper',research_notes:'Note',research_project:'Project',legal_project:'Law',legal_guideline:'Guideline',standard:'Standard',guidance:'FAQ'};
const SEA_VAR={research_paper:'--t-paper',research_notes:'--t-notes',research_project:'--t-project',legal_project:'--t-legal',legal_guideline:'--t-guideline',standard:'--t-standard',guidance:'--t-guidance'};
/* legend entries: creature + type name (+ the creature's name as tooltip) */
function seaLegend(types){
  return [...new Set(types)].map(t=>`<span class="sea-leg" title="${SEA_LABEL[t]||t} = ${seaOf(t).name}">${seaIcon(t,18,`var(${SEA_VAR[t]||'--muted'})`)}${SEA_LABEL[t]||t}</span>`).join('');
}
