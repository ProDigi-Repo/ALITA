/* ---------- Cluster space 3D · time axis (REQ-32) ----------
   Depth = decimal year: item.tm is the exact document date (item.t stays the document type).
   S3.zs = depth units per year, S3.z0 = decimal year at depth 0. The narrower the chosen time range, the finer the
   scale – years → months (weeks / days on request), each unit S3_YEAR (22) deep. Loaded before space3d.js. */
const S3_UNITS={year:1,month:12,week:52.1775,day:365.25};
const S3_MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const S3_DSRC={doc_properties:'file properties',file_mtime:'file date – uncertain (last saved/copied)',filename_year:'year from the file name',
  text:'from the text',curated:'curated',project_date:'project date (set on upload)'};

/* "YYYY-MM-DD…" → decimal year (2021-07-02 → 2021.5); null if there is no full date */
function s3T(s){const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(s||'');if(!m)return null;
  const y=+m[1],a=Date.UTC(y,0,1);return y+(Date.UTC(y,+m[2]-1,+m[3])-a)/(Date.UTC(y+1,0,1)-a)}
/* decimal year → depth on the current scale */
function s3Z(t){return (t-S3.z0)*S3.zs}
/* Auto scale: years for 6 or more years, months for a narrower range */
function s3AutoUnit(){const D=S3.D;return ((S3.until??D.ymax)-(S3.from??D.ymin)+1)>=6?'year':'month'}
/* set S3.unit / S3.zs / S3.z0 from the range or the "Scale" choice; returns true when the unit changed */
function s3Scale(){
  const D=S3.D,auto=!S3.unitSel||S3.unitSel==='auto',u=auto?s3AutoUnit():S3.unitSel,changed=u!==S3.unit;
  S3.unit=u;S3.zs=S3_YEAR*S3_UNITS[u];S3.z0=u==='year'?D.ymin:(S3.from??D.ymin);S3.dirty=true;
  const o=$('#s3UnitOut');if(o)o.textContent=auto?`→ ${u}s`:'';
  return changed;
}
/* planes along the time axis: every year (year scale) or every month / week / day inside the chosen range */
function s3Ticks(from,until){
  const D=S3.D,u=S3.unit,out=[];
  if(u==='year'){for(let y=D.ymin;y<=D.ymax;y++)out.push({t:y,y,label:String(y),major:true});return out}
  const DAY=864e5,end=Date.UTC(until+1,0,1),iso=(y,m,d)=>`${y}-${String(m+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
  let d=new Date(Date.UTC(from,0,1));
  if(u==='week'){const wd=(d.getUTCDay()+6)%7;if(wd)d=new Date(d.getTime()+(7-wd)*DAY)}   // weeks start on Monday
  for(let k=0;d.getTime()<end&&k<3000;k++){
    const y=d.getUTCFullYear(),m=d.getUTCMonth(),dd=d.getUTCDate(),major=m===0&&dd<=(u==='week'?7:1);
    const label=u==='month'?(m===0?`${S3_MON[m]} ${y}`:S3_MON[m])
      :u==='week'?`${dd}. ${S3_MON[m]}${major?' '+y:''}`
      :(dd===1?`${dd}. ${S3_MON[m]}${m===0?' '+y:''}`:String(dd));
    out.push({t:s3T(iso(y,m,dd)),y,label,major});
    d=u==='month'?new Date(Date.UTC(y,m+1,1)):new Date(d.getTime()+(u==='week'?7:1)*DAY);
  }
  return out;
}
/* tooltip pieces: when, and where the date comes from */
function s3When(h){return h.proj?(h.y0===h.y1?h.y0:h.y0+'–'+h.y1):h.approx?`${h.y0} (year only)`:`📅 ${h.d.split('-').reverse().join('.')}`}
function s3DateSource(h){return !h.proj&&h.ds?`<br><small>date: ${esc(S3_DSRC[h.ds]||h.ds)}</small>`:''}
