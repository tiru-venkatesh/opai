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
