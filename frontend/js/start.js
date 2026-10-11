/* ---------- Start ---------- */
(async()=>{
  let start='graph';   // B Interaction Interface is always the start page (a #hash in the URL still wins)
  const h=location.hash.slice(1);if(h==='release-notes')start='release';else if(['chat','docs','graph','release','compliance','tech'].includes(h))start=h;
  showPage(start);
  if(await detectBackend()===false)return;
  await loadSysDefaults();
  await loadDocs();
  if(!LIVE&&DOCS.length){
    const a={...demoAnswer('Which methods does the project use?',ragFilters()),applied_filters:ragFilters()};
    const im=analyzeQuery('Which methods does the project use?',ragFilters());
    userMsg($('#ragChat'),'Which methods does the project use?',['version:latest'],im,spSnapshot('rag'));botMsg($('#ragChat'),a);
    if(!HIST.rag.length){recordTurn('rag',{role:'user',text:'Which methods does the project use?',filters:['version:latest'],meta:im,sp:spSnapshot('rag')});recordTurn('rag',{role:'bot',a})}
  }
  if(!LIVE)askGraphIntro();
})();
function askGraphIntro(){const a={...(()=>{const g=DOCS.length?demoGraphAnswer('Which methods were used to study trust?'):GRAPH_ANSWER;const {docs,allSources,graphContext,...k}=g;return k})(),model:'no language model (demo)'};const im=analyzeQuery('Which methods were used to study trust?',null);userMsg($('#graphChat'),'Which methods were used to study trust?',[],im,spSnapshot('graph'));botMsg($('#graphChat'),a);
  if(!HIST.graph.length){recordTurn('graph',{role:'user',text:'Which methods were used to study trust?',meta:im,sp:spSnapshot('graph')});recordTurn('graph',{role:'bot',a})}}
