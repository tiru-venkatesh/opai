/* OPAI shell: one header, floating dock and focus timer on every app page. Exposes window.OPAI_FOCUS. */
(function(){
  if(window.OPAI_SHELL)return;window.OPAI_SHELL=1;
  var path=(location.pathname.split('/').pop()||'today.html').replace(/\/$/,'')||'today.html';
  if(path==='super-chat'||path==='')path='super-chat.html';
  var NAV=[['Today','today.html'],['KARNA','super-chat.html'],['Plan','plan.html'],['Applications','applications.html'],['Projects','projects.html'],['Academics','academics.html'],['Overview','app.html'],['Console','agent-console.html']];
  var isChat=/super-chat/.test(path);
  var API=(localStorage.getItem('opa_api_base')||(/^(localhost|127\.0\.0\.1)$/.test(location.hostname)?'http://localhost:8000':'https://opa-52ug.onrender.com')).replace(/\/+$/,'');
  var uid=localStorage.getItem('opa_guest_uid'),mail=localStorage.getItem('opai_sc_email');
  function h(s){var d=document.createElement('div');d.innerHTML=s.trim();return d.firstChild}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  var LOGO='<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><rect x="3" y="4" width="10" height="22" rx="5" transform="rotate(-12 8 15)" fill="#E8705A"/><rect x="17" y="4" width="10" height="22" rx="5" fill="#17504A"/></svg>';
  function header(){
    var old=document.querySelector('body > header, body > .app > header, header');
    var hd=h('<header class="opai-hd" role="banner"><div class="in"><a class="opai-logo" href="today.html" aria-label="OPAI home">'+LOGO+'<span><b>OPAI</b><small>v8</small></span></a>'+
      '<nav class="opai-pills" aria-label="Pages">'+NAV.map(function(n){return '<a href="'+n[1]+'"'+(n[1]===path?' aria-current="page"':'')+'>'+n[0]+'</a>'}).join('')+'</nav>'+
      '<div class="opai-right"><button class="opai-k" type="button" id="opai-k" aria-label="Search sections">⌕ Ctrl K</button><span class="opai-st" id="opai-st"><i></i><span>KARNA · checking</span></span>'+
      '<a class="opai-user" href="login.html" title="Account"><span class="av" id="opai-av">·</span><span><b id="opai-un">Guest</b><small id="opai-us">OPAI</small></span></a></div></div></header>');
    if(isChat)return null;
    var pos=old?getComputedStyle(old).position:'';
    if(old&&(pos==='fixed'||pos==='sticky'||old.parentNode===document.body))old.replaceWith(hd);else document.body.insertBefore(hd,document.body.firstChild);
    document.body.classList.add('opai-has-shell');if(pos!=='fixed')document.body.classList.add('opai-pad');return hd;
  }
  function icons(){var s='fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';return {
    today:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    chat:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.3A8 8 0 1 1 21 12z"/></svg>',
    plan:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
    guide:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/></svg>',
    term:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/></svg>',
    dl:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg>'}}
  var deferred=null;addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferred=e});
  function dock(){
    if(isChat)return;var I=icons();
    var d=h('<div class="opai-dock" role="toolbar" aria-label="Quick actions"><a href="today.html" title="Today" '+(path==='today.html'?'aria-current="page"':'')+'>'+I.today+'</a><a href="super-chat.html" title="Ask KARNA">'+I.chat+'</a><a href="plan.html" title="Plan" '+(path==='plan.html'?'aria-current="page"':'')+'>'+I.plan+'</a><button type="button" id="dk-guide" title="Guide: which section does what">'+I.guide+'</button><a href="agent-console.html" title="Agent console" '+(path==='agent-console.html'?'aria-current="page"':'')+'>'+I.term+'</a><button type="button" id="dk-install" title="Install OPAI as an app">'+I.dl+'</button></div>');
    document.body.appendChild(d);
    document.getElementById('dk-guide').onclick=function(){window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
    document.getElementById('dk-install').onclick=function(){if(deferred){deferred.prompt();deferred=null}else alert('To install: browser menu → "Add to Home Screen" (or "Install app").')};
  }
  /* focus timer, persisted so it survives page changes */
  var KEY='opai_focus',tm,tick;
  function load(){try{return JSON.parse(localStorage.getItem(KEY)||'null')}catch(e){return null}}
  function save(f){try{f?localStorage.setItem(KEY,JSON.stringify(f)):localStorage.removeItem(KEY)}catch(e){}}
  function left(f){return f.paused?f.left:Math.max(0,Math.round((f.end-Date.now())/1000))}
  function paint(){
    var f=load();if(!tm)return;if(!f){tm.className='opai-timer';clearInterval(tick);tick=null;return}
    var s=left(f);tm.className='opai-timer on'+(f.paused?' paused':'');
    tm.querySelector('b').textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');
    tm.querySelector('span').textContent=s===0?f.title+' · done':f.title;
    tm.querySelector('[data-t=pause]').textContent=f.paused?'▶':'❚❚';
    if(!tick)tick=setInterval(paint,1000);
  }
  function timer(){
    tm=h('<div class="opai-timer" role="timer" aria-live="off"><i></i><b>00:00</b><span></span><button type="button" data-t="pause" aria-label="Pause or resume">❚❚</button><button type="button" data-t="stop" aria-label="Stop timer">✕</button></div>');
    document.body.appendChild(tm);
    tm.onclick=function(e){var b=e.target.closest('button');if(!b)return;var f=load();if(!f)return;
      if(b.dataset.t==='stop')save(null);else if(f.paused){f.paused=false;f.end=Date.now()+f.left*1000;save(f)}else{f.left=left(f);f.paused=true;save(f)}paint()};
    addEventListener('storage',paint);paint();
  }
  window.OPAI_FOCUS={start:function(title,min){save({title:title,end:Date.now()+min*60000,paused:false,left:min*60,total:min*60});paint()},stop:function(){save(null);paint()},current:load};
  /* profile + health */
  function who(){
    var st=document.getElementById('opai-st'),av=document.getElementById('opai-av'),un=document.getElementById('opai-un'),us=document.getElementById('opai-us');if(!st)return;
    fetch(API+'/v1/health').then(function(r){if(!r.ok)throw 0;st.className='opai-st';st.querySelector('span').textContent='KARNA · Ready · Guarded'}).catch(function(){st.className='opai-st off';st.querySelector('span').textContent='Backend waking up'});
    if(!uid)return;fetch(API+'/v1/profile?user_id='+encodeURIComponent(uid)).then(function(r){return r.ok?r.json():null}).then(function(p){if(!p)return;
      var n=p.name&&!/^guest/i.test(p.name)?p.name:(mail?mail.split('@')[0]:'Guest');un.textContent=n;av.textContent=(n[0]||'G').toUpperCase();us.textContent=[p.branch,p.degree].filter(Boolean).join(' · ')||'Personal workspace'}).catch(function(){});
  }
  function boot(){var hd=header();dock();timer();if(hd){who();document.getElementById('opai-k').onclick=function(){window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
      addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();window.OPAI_GUIDE&&OPAI_GUIDE.open('')}})}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
