/* ---------- Shared state: change events (3.13.0, REQ-61 stage 5) ----------
   Views subscribe to a topic instead of calling each other's render functions (or wrapping them), so a new view is
   wired in one place – next to its own code – and the load order of the scripts no longer matters for updates.

   Topic         emitted by                                   when
   documents     documents.js  loadDocs()                     DOCS / PROJECTS (re)loaded
   databases     databases.js  saveDbSel()                    database selection SEL_DB changed
   clusters      cluster-core.js cvChanged()                  cluster selection CV.sels changed
   cluster-page  cluster-page.js renderClusterPage()          the B page was drawn (citations, map window follow)
   gate          documents.js  setDbUnlocked()                password gate locked or unlocked

   Shared data stays in the existing globals (core.js, databases.js, documents.js, cluster-core.js):
   DOCS, PROJECTS (documents), DATABASES, DB_ALL, SEL_DB, PUBLIC_DBS, DB_UNLOCKED (databases and gate),
   CV (cluster selection and colour mode), CG (B page: selected cluster/project, colour mode).
   Subscribers run in ascending `order` (equal order: subscription order); one failing view never stops the others. */
const Store={
  _subs:{},
  on(topic,fn,order=50){
    const list=this._subs[topic]||(this._subs[topic]=[]);
    list.push({fn,order,i:list.length});list.sort((a,b)=>a.order-b.order||a.i-b.i);
    return fn;
  },
  emit(topic,detail){
    for(const s of [...(this._subs[topic]||[])]){try{s.fn(detail)}catch(e){console.error(`[${topic}]`,e)}}
  },
  topics(){return Object.fromEntries(Object.entries(this._subs).map(([k,v])=>[k,v.length]))}
};
