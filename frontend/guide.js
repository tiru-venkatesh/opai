/* OPAI Guide: section map + keyword navigation (English / Hinglish / Tenglish). Exposes window.OPAI_GUIDE. */
(function(){
  var S=[
   {id:'overview',t:'Overview',h:'app.html',d:'Whole-workspace summary: counts, deadlines, status of everything.',k:'overview home dashboard summary status mukhya home dikhao'},
   {id:'today',t:'Today',h:'today.html',d:'What to do today: tasks, classes, deadlines due now.',k:'today aaj ivala eroju tasks todo kaam pani deadline schedule'},
   {id:'plan',t:'Plan',h:'plan.html',d:'Weekly plan and study blocks. Build or change your schedule here.',k:'plan planner schedule timetable study blocks week yojana'},
   {id:'applications',t:'Opportunities',h:'opportunities.html',d:'Find, evaluate and track internships and research roles; professor outreach; approved emails and follow-ups.',k:'applications application apply internship job intern status kahan ekkada undi'},
   {id:'projects',t:'Projects',h:'projects.html',d:'Your projects, stack and progress.',k:'projects project app build stack prayog'},
   {id:'dsa',t:'DSA Roadmap',h:'dsa.html',d:'Phase-based DSA plan for placements: one small block in Today, links to external practice sites, progress tracking. Not a coding-practice platform.',k:'dsa roadmap data structures algorithms placement leetcode arrays hashing dp graphs learning plan interview prep'},
   {id:'academics',t:'Academics',h:'academics.html',d:'Coming soon: exams, subjects and study planning.',k:'academics exam exams subject timetable grades marks semester padhai chaduvu add cheyali kaise'},
   {id:'karna',t:'KARNA (chat)',h:'super-chat.html',d:'Chat agent. Add things by typing, ask about your data and documents.',k:'karna chat agent super assistant ask puchho adugu'},
   {id:'console',t:'Agent Console',h:'agent-console.html',d:'See what the agent did, approvals and logs.',k:'agent console approvals logs outbox audit history'}
  ];
  var RE=/guide|help|kahan|kaha|kidhar|ekkada|ekada|where|which section|em chestundi|kya karta|ela |kaise|kaisa|ekkadundi|undi\b|how (do|to)|navigate|section/i;
  function norm(s){return String(s||'').toLowerCase().replace(/[^a-z0-9\u0900-\u097f\u0c00-\u0c7f ]+/g,' ')}
  function find(q){
    var w=norm(q).split(/\s+/).filter(function(x){return x.length>2}), best=[],i,j,sc;
    for(i=0;i<S.length;i++){sc=0;var hay=' '+norm(S[i].k+' '+S[i].t)+' ';
      for(j=0;j<w.length;j++){if(hay.indexOf(' '+w[j]+' ')>-1)sc+=3;else if(hay.indexOf(w[j])>-1)sc+=1}
      if(sc)best.push([sc,S[i]])}
    best.sort(function(a,b){return b[0]-a[0]});return best.slice(0,3).map(function(x){return x[1]});
  }
  function isGuideQuery(q){q=String(q||'').trim();if(/^\/guide\b/i.test(q))return true;return RE.test(q)&&q.length<90&&find(q).length>0}
  function mapMd(list){return (list||S).map(function(s){return '- **'+s.t+'** — '+s.d+' ['+'open'+']('+s.h+')'}).join('\n')}
  /* answer text uses plain markdown; relative links are rendered by the host page */
  function answer(q,lang){
    var body=String(q||'').replace(/^\/guide\b/i,'').trim(), hits=body?find(body):[];
    if(hits.length)var I={en:['Here is what you asked about:','Type `/guide` for the full map.'],hi:['Ye raha jo aapne pucha:','Poora map dekhne ke liye `/guide` likho.'],te:['Idhigo, nuvvu adigindi ikkada undi:','Mottam map kosam `/guide` ani type chey.']}[lang||'en'];return I[0]+'\n\n'+mapMd(hits)+'\n\n'+I[1];
    return ({en:'OPAI sections:',hi:'OPAI ke sections:',te:'OPAI sections:'}[lang||'en'])+'\n\n'+mapMd();
  }
  var panel;
  function open(q){
    if(!panel){panel=document.createElement('div');panel.id='opai-guide';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Guide');
      panel.innerHTML='<div class="gp"><button class="gx" aria-label="Close">×</button><h2>Guide</h2><p class="gs">Which section does what. Type "applications kahan hai?" or "exam ela add cheyali?"</p><input type="search" placeholder="Search a section…" aria-label="Search sections"><div id="opai-gl"></div></div>';
      document.body.appendChild(panel);
      panel.addEventListener('click',function(e){if(e.target===panel||e.target.className==='gx')panel.classList.remove('open')});
      panel.querySelector('input').addEventListener('input',function(e){render(e.target.value)});
      document.addEventListener('keydown',function(e){if(e.key==='Escape')panel.classList.remove('open')});}
    var inp=panel.querySelector('input');inp.value=q||'';render(q||'');panel.classList.add('open');}
  function render(q){var l=q&&q.trim()?find(q):S;if(!l.length)l=S;
    panel.querySelector('#opai-gl').innerHTML=l.map(function(s){return '<a class="gi" href="'+s.h+'"><b>'+s.t+'</b><span>'+s.d+'</span></a>'}).join('')}
  function fab_unused(){if(document.getElementById('opai-guide-fab')||document.getElementById('b-guide')||/login|landing/.test(location.pathname))return;
    var b=document.createElement('button');b.id='opai-guide-fab';b.type='button';b.title='Guide: which section does what';b.setAttribute('aria-label','Guide');b.textContent='?';
    b.onclick=function(){open('')};document.body.appendChild(b)}
  
  /* tooltips on every nav link, on all pages */
  function tips(){var m={};S.forEach(function(x){m[x.h]=x.d});
    [].forEach.call(document.querySelectorAll('nav a[href], header a[href$=".html"]'),function(a){var h=(a.getAttribute('href')||'').split('#')[0];if(m[h]&&!a.title)a.title=m[h]})}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',tips);else tips();
  window.OPAI_GUIDE={sections:S,find:find,isGuideQuery:isGuideQuery,answer:answer,open:open};
})();
