/* Notion-style chrome: emoji nav icons, sticky breadcrumb bar, big page icon above the title. Pure decoration; no data or behaviour changes. */
(function(){
  if(window.__ntDone)return;window.__ntDone=1;
  var EM={'today.html':'☀️','super-chat.html':'💬','plan.html':'📅','opportunities.html':'💼','projects.html?view=hackathons':'⚡','projects.html?view=programs':'🎓','projects.html?view=projects':'📁','resume-lab.html':'📄','academics.html':'📚','review.html':'📊','feedback.html':'📝','landing.html':'🏠','#logout':'↩️','profile.html':'👤','internship.html':'💼','briefs.html':'🗒️','coding.html':'💻','dsa.html':'🧮','app.html':'☀️'};
  var GR={'Work':'Workspace','More':'More'};
  function run(){
    var sb=document.getElementById('opai-sb');if(!sb||sb.__nt)return;sb.__nt=1;
    var cur=EM[location.pathname.split('/').pop()]||'📄',title=document.title.replace(/\s*[·|—-]\s*OPAI.*$/,'')||'OPAI';
    [].forEach.call(sb.querySelectorAll('nav a'),function(a){
      var k=a.getAttribute('href'),e=EM[k]||'📄';var s=document.createElement('span');s.className='nt-em';s.textContent=e;a.insertBefore(s,a.firstChild);
      if(a.getAttribute('aria-current')==='page'){cur=e;title=(a.getAttribute('title')||title)}});
    [].forEach.call(sb.querySelectorAll('.sb-gh'),function(g){if(GR[g.textContent])g.textContent=GR[g.textContent]});
    var first=sb.querySelector('nav');if(first&&!sb.querySelector('.sb-gh.nt-fav')){var f=document.createElement('div');f.className='sb-gh nt-fav';f.textContent='Favorites';first.parentNode.insertBefore(f,first)}
    /* Notion-style toggle sections, remembered */
    var store={};try{store=JSON.parse(localStorage.getItem('opai_nt_fold')||'{}')}catch(e){}
    [].forEach.call(sb.querySelectorAll('.sb-gh'),function(g){
      var nv=g.nextElementSibling;if(!nv||nv.tagName!=='NAV')return;g.setAttribute('role','button');g.tabIndex=0;g.classList.add('nt-fold');
      function set(c){g.classList.toggle('closed',c);nv.style.display=c?'none':'';store[g.textContent]=c;try{localStorage.setItem('opai_nt_fold',JSON.stringify(store))}catch(e){}}
      if(store[g.textContent]&&!nv.querySelector('[aria-current=page]'))set(true);
      g.onclick=function(){set(!g.classList.contains('closed'))};g.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();g.click()}}});
    var uh=sb.querySelector('a.opai-user[aria-current=page]');if(uh){cur='👤';title='Profile'}
    var sr=sb.querySelector('.sb-search .l');if(sr)sr.textContent='Search';
    if(document.body.classList.contains('opai-chat')){return}
    /* sticky breadcrumb bar */
    var main=document.querySelector('main')||document.querySelector('.wrap')||document.querySelector('#projwrap');
    var top=document.createElement('div');top.className='nt-top';
    top.innerHTML='<div class="crumb"><span>'+cur+'</span>'+title.replace(/</g,'&lt;')+'</div><div class="sp"></div>';
    var th=document.querySelector('.opai-theme');if(th){th.classList.remove('float');top.appendChild(th)}
    var h1t=(main||document).querySelector('h1');if(h1t&&h1t.textContent.trim().length<40){top.querySelector('.crumb').lastChild.textContent=h1t.textContent.trim()}
    document.body.insertBefore(top,sb.nextSibling);
    if(main&&main.parentNode===document.body)document.body.insertBefore(top,main);
    /* big page icon above the first title */
    var h1=(main||document).querySelector('h1');
    if(main&&!document.querySelector('.nt-cover')){var COV=['linear-gradient(120deg,#E7F3F8,#E8DEEE)','linear-gradient(120deg,#FBF3DB,#FADEC9)','linear-gradient(120deg,#DDEDEA,#D3E5EF)','linear-gradient(120deg,#F5E0E9,#FAEBDD)','linear-gradient(120deg,#EEE0DA,#FBF3DB)'];
      var hsh=0;for(var q=0;q<location.pathname.length;q++)hsh+=location.pathname.charCodeAt(q);
      var cv=document.createElement('div');cv.className='nt-cover';cv.style.background=COV[hsh%COV.length];cv.setAttribute('aria-hidden','true');main.parentNode.insertBefore(cv,main)}
    if(h1&&!document.querySelector('.nt-icon')){var ic=document.createElement('span');ic.className='nt-icon';ic.setAttribute('aria-hidden','true');ic.textContent=cur;h1.parentNode.insertBefore(ic,h1)}
  }
  if(document.readyState!=='loading')setTimeout(run,0);else document.addEventListener('DOMContentLoaded',function(){setTimeout(run,0)});
  var n=0,t=setInterval(function(){run();if(++n>20||(document.getElementById('opai-sb')||{}).__nt)clearInterval(t)},150);
  /* Hackathons table header (re-applied after each render) */
  function heads(){[].forEach.call(document.querySelectorAll('.hlist'),function(l){var f=l.firstElementChild;if(f&&f.classList.contains('hl-head'))return;if(!l.querySelector('.hk'))return;var d=document.createElement('div');d.className='hl-head';d.innerHTML='<span>Date</span><span>Name</span><span>Tags</span><span></span>';l.insertBefore(d,l.firstChild)})}
  var hk=document.getElementById('hack');if(hk){heads();new MutationObserver(heads).observe(hk,{childList:true,subtree:true})}
})();
/* Today: Notion database view switcher (Table | Gallery). Layout only; render and click logic stay in today.html. */
(function(){
  function go(){
    var list=document.getElementById('list');
    if(!list||!document.getElementById('sprint')||document.querySelector('.td-bar'))return;
    var K='opai_nt_today_view',v='table';try{v=localStorage.getItem(K)||'table'}catch(e){}
    var bar=document.createElement('div');bar.className='td-bar';
    bar.innerHTML='<div class="hseg td-views" role="group" aria-label="View"><button type="button" data-v="table">▤ Table</button><button type="button" data-v="gallery">▦ Gallery</button></div><div class="td-head"><span>Aa&nbsp; Task</span><span>Due · Category</span></div>';
    list.parentNode.insertBefore(bar,list);
    function set(x){
      list.classList.toggle('nt-gallery',x==='gallery');bar.classList.toggle('gal',x==='gallery');
      [].forEach.call(bar.querySelectorAll('button'),function(b){b.setAttribute('aria-pressed',String(b.dataset.v===x))});
      try{localStorage.setItem(K,x)}catch(e){}}
    bar.querySelector('.td-views').onclick=function(e){var b=e.target.closest('button');if(b)set(b.dataset.v)};
    set(v);
  }
  if(document.readyState!=='loading')go();else document.addEventListener('DOMContentLoaded',go);
})();

/* AURORA 2026: floating dock + top chip replace the sidebar and breadcrumb bar. Reads links from the existing sidebar, so NAV stays defined in opai-shell.js. */
(function(){
  if(window.__auDone)return;window.__auDone=1;
  document.documentElement.setAttribute('data-pg',(location.pathname.split('/').pop()||'').replace('.html',''));
  var EM={'today.html':'☀️','super-chat.html':'💬','plan.html':'📅','opportunities.html':'💼','projects.html?view=hackathons':'⚡','projects.html?view=programs':'🎓','projects.html?view=projects':'📁','resume-lab.html':'📄','academics.html':'📚','review.html':'📊','feedback.html':'📝','landing.html':'🏠','profile.html':'👤','more':'▦','search':'🔍','#logout':'🚪'};
  var MAIN=['today.html','super-chat.html','plan.html','opportunities.html','projects.html?view=projects'];
  var LBL={'projects.html?view=projects':'Projects'};
  (function(){if(document.getElementById('au-fonts'))return;var l=document.createElement('link');l.id='au-fonts';l.rel='stylesheet';l.href='https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&family=Space+Grotesk:wght@500;600;700&family=Material+Symbols+Outlined:wght@400&display=swap';document.head.appendChild(l)})();
  var MS={'today.html':'wb_sunny','super-chat.html':'auto_awesome','plan.html':'calendar_month','opportunities.html':'work','projects.html?view=projects':'folder','projects.html?view=hackathons':'bolt','projects.html?view=programs':'school','resume-lab.html':'description','academics.html':'menu_book','review.html':'monitoring','feedback.html':'rate_review','landing.html':'home','#logout':'logout','more':'apps','search':'search'};
  function ic(k){return "<span class='ic' data-e='"+(EM[k]||'•')+"'><i class='ms'>"+(MS[k]||'circle')+"</i></span>"}
  function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function run(){
    var sb=document.getElementById('opai-sb');if(!sb||document.querySelector('.au-dock'))return;
    var links={},groups=[],g=null;function G(t){return g||(g={t:t,a:[]},groups.push(g),g)}
    [].forEach.call(sb.querySelectorAll('.sb-gh,nav a'),function(n){
      if(n.classList.contains('sb-gh')){if(!n.classList.contains('nt-fav'))g={t:n.textContent,a:[]},groups.push(g);return}
      var k=n.getAttribute('href');if(!k||k==='#logout'){if(k==='#logout'){G('More').a.push({k:k,n:n})}return}
      var name=(n.getAttribute('title')||(n.querySelector('.l')||n).textContent||'').trim();
      var it={k:k,name:name,cur:n.getAttribute('aria-current')==='page',n:n};links[k]=it;G('Menu').a.push(it)});
    var dock=el('nav','au-dock');dock.setAttribute('aria-label','Main navigation');
    MAIN.forEach(function(k){var it=links[k];if(!it)return;
      var a=el('a','',ic(k)+"<span class='t'>"+esc(LBL[k]||it.name)+'</span>');a.href=k;a.title=it.name;if(it.cur)a.setAttribute('aria-current','page');dock.appendChild(a)});
    dock.appendChild(el('span','sep'));
    var more=el('button','au-more',ic('more'));more.type='button';more.title='All sections';more.setAttribute('aria-label','All sections');dock.appendChild(more);
    var srch=el('button','',ic('search'));srch.type='button';srch.title='Search (Ctrl K)';srch.setAttribute('aria-label','Search');srch.onclick=function(){var k=document.getElementById('opai-k');if(k)k.click()};dock.appendChild(srch);
    var sheet=el('div','au-sheet'),inn=el('div','in');
    groups.forEach(function(gr){if(!gr.a.length)return;inn.appendChild(el('h4','',esc(gr.t==='Workspace'?'Work':gr.t)));var grid=el('div','g');
      gr.a.forEach(function(it){var a;if(it.k==='#logout'){a=el('a','',ic('#logout')+'Log out');a.href='#';a.onclick=function(e){e.preventDefault();it.n.click()}}
        else{a=el('a','',ic(it.k)+esc(it.name));a.href=it.k;if(it.cur)a.setAttribute('aria-current','page')}grid.appendChild(a)});inn.appendChild(grid)});
    sheet.appendChild(inn);
    function open(v){sheet.classList.toggle('open',v)}
    more.onclick=function(){open(!sheet.classList.contains('open'))};sheet.onclick=function(e){if(e.target===sheet)open(false)};
    addEventListener('keydown',function(e){if(e.key==='Escape')open(false)});
    document.body.appendChild(sheet);document.body.appendChild(dock);
    try{document.fonts.load('22px "Material Symbols Outlined"').then(function(f){if(f&&f.length)return;fb()},fb)}catch(e){fb()}
    function fb(){[].forEach.call(document.querySelectorAll('.au-dock .ic,.au-sheet .ic'),function(x){x.textContent=x.dataset.e})}
    if(document.body.classList.contains('opai-chat'))return;
    var cur=Object.keys(links).filter(function(k){return links[k].cur})[0],title=(cur&&links[cur].name)||document.title.replace(/\s*[·|—-]\s*OPAI.*$/,'')||'OPAI';
    var top=el('div','au-top'),chip=el('a','au-chip','<img src="assets/opai-logo-96.png?v=3d" alt=""><span>OPAI<em>'+esc(title)+'</em></span>');chip.href='today.html';
    var tools=el('div','au-tools'),th=document.querySelector('.opai-theme');if(th){th.classList.remove('float');tools.appendChild(th)}
    var av=sb.querySelector('a.opai-user');if(av){var pa=el('a','av',(document.getElementById('opai-av')||{}).textContent||'·');pa.href='profile.html';pa.title='Profile';tools.appendChild(pa)}
    top.appendChild(chip);top.appendChild(tools);document.body.appendChild(top);
  }
  if(document.readyState!=='loading')setTimeout(run,60);else document.addEventListener('DOMContentLoaded',function(){setTimeout(run,60)});
  var n=0,t=setInterval(function(){run();if(++n>25||document.querySelector('.au-dock'))clearInterval(t)},160);
})();
