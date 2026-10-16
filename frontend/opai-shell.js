/* OPAI shell: one header, floating dock and focus timer on every app page. Exposes window.OPAI_FOCUS. */
(function(){
  if(window.OPAI_SHELL)return;window.OPAI_SHELL=1;
  var EMBED=window.top!==window.self||/[?&]embed=1/.test(location.search);
  if(EMBED){window.OPAI_KARNA_POPUP=1;var st=document.createElement('style');st.textContent='body>header,header.opai-hd,.opai-dock{display:none!important}body{padding-top:0!important}';document.head.appendChild(st);return}
  var path=(location.pathname.split('/').pop()||'today.html').replace(/\/$/,'')||'today.html';
  if(path==='super-chat'||path==='')path='super-chat.html';
  var NAV=[['Today','today.html'],['KARNA','super-chat.html'],['Plan','plan.html'],['Work','work.html'],['Overview','app.html'],['Review','review.html']];
  var isChat=/super-chat/.test(path);
  var API=(localStorage.getItem('opa_api_base')||(/^(localhost|127\.0\.0\.1)$/.test(location.hostname)?'http://localhost:8000':'https://opa-52ug.onrender.com')).replace(/\/+$/,'');
  var uid=null,mail=((localStorage.getItem('opai_sc_email')||'').trim().toLowerCase())||null;
  function h(s){var d=document.createElement('div');d.innerHTML=s.trim();return d.firstChild}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  var LOGO='<img class="opai-mark" src="assets/opai-logo-96.png" width="30" height="30" alt="" decoding="async">';

  if(isChat&&!document.getElementById('opai-karna-css')){var st=document.createElement('style');st.id='opai-karna-css';st.textContent=
   '.opai-karna{display:inline-flex;align-items:center;gap:8px;margin-left:2px;padding:6px 14px 6px 12px;border-radius:999px;text-decoration:none;flex:none;position:relative;'+
   'background:linear-gradient(135deg,rgba(15,82,87,.10),rgba(36,94,99,.04));border:1px solid rgba(15,82,87,.22);box-shadow:0 1px 0 rgba(255,255,255,.6) inset,0 6px 18px -8px rgba(15,82,87,.45);transition:transform .2s,box-shadow .2s}'+
   '.opai-karna:before{content:"";position:absolute;left:-12px;top:50%;width:1px;height:22px;transform:translateY(-50%);background:linear-gradient(transparent,rgba(15,82,87,.35),transparent)}'+
   '.opai-karna b{font:700 13px/1 "Space Grotesk",Inter,system-ui,sans-serif;letter-spacing:.24em;text-indent:.24em;margin-right:-.24em;background:linear-gradient(90deg,#0f5257,#2f8a90 60%,#4aa6ab);-webkit-background-clip:text;background-clip:text;color:transparent}'+
   '.opai-karna .dot{width:7px;height:7px;border-radius:50%;background:#2f8a90;box-shadow:0 0 0 0 rgba(47,138,144,.55);animation:opaiKp 2.4s ease-out infinite}'+
   '@keyframes opaiKp{0%{box-shadow:0 0 0 0 rgba(47,138,144,.55)}70%,100%{box-shadow:0 0 0 8px rgba(47,138,144,0)}}'+
   '.opai-karna:hover{transform:translateY(-1px);box-shadow:0 1px 0 rgba(255,255,255,.6) inset,0 10px 22px -8px rgba(15,82,87,.55)}'+
   'html[data-theme=dark] .opai-karna{background:linear-gradient(135deg,rgba(74,166,171,.18),rgba(74,166,171,.06));border-color:rgba(126,224,230,.28);box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 8px 20px -10px rgba(0,0,0,.8)}'+
   'html[data-theme=dark] .opai-karna b{background:linear-gradient(90deg,#9be7ec,#5fc0c6 60%,#3aa0a6);-webkit-background-clip:text;background-clip:text}'+
   'html[data-theme=dark] .opai-karna:before{background:linear-gradient(transparent,rgba(126,224,230,.4),transparent)}'+
   '@media(max-width:1000px){.opai-karna{display:none}}@media(prefers-reduced-motion:reduce){.opai-karna .dot{animation:none}}';
   document.head.appendChild(st)}
  function header(){
    var old=document.querySelector('body > header, body > .app > header, header');
    var hd=h('<header class="opai-hd" role="banner"><div class="in"><a class="opai-logo" href="today.html" aria-label="OPAI home">'+LOGO+'<span><b>OPAI</b><small>v8</small></span></a>'+(isChat?'<a class="opai-karna" href="super-chat.html" aria-label="KARNA"><i class="dot"></i><b>KARNA</b></a>':'')+
      '<nav class="opai-pills" aria-label="Pages">'+NAV.map(function(n){return '<a href="'+n[1]+'"'+((n[1]===path||(n[1]==='work.html'&&/^(opportunities|dsa|projects|academics|applications)\.html$/.test(path)))?' aria-current="page"':'')+'>'+n[0]+'</a>'}).join('')+'</nav>'+
      '<div class="opai-right"><button class="opai-k" type="button" id="opai-k" aria-label="Search sections">Search <kbd>Ctrl K</kbd></button><span class="opai-st" id="opai-st"><i></i><span>Connecting…</span></span>'+
      (isChat?'':'<button class="opai-ib" type="button" id="hd-guide" title="Guide: which section does what" aria-label="Open the guide">'+icons().guide+'</button><button class="opai-ib" type="button" id="hd-install" title="Install OPAI as an app" aria-label="Install OPAI as an app">'+icons().dl+'</button>')+'<a class="opai-user" href="profile.html" title="Profile" aria-label="Open your profile"'+(path==='profile.html'?' aria-current="page"':'')+'><span class="av" id="opai-av">·</span><span><b id="opai-un">Account</b><small id="opai-us">OPAI</small></span></a></div></div></header>');
    var pos=old?getComputedStyle(old).position:'';
    if(old&&(pos==='fixed'||pos==='sticky'||old.parentNode===document.body))old.replaceWith(hd);else document.body.insertBefore(hd,document.body.firstChild);
    var gb=hd.querySelector('#hd-guide'),ib=hd.querySelector('#hd-install');
    if(gb)gb.onclick=function(){window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
    if(ib){var standalone=(window.matchMedia&&matchMedia('(display-mode: standalone)').matches)||navigator.standalone;
      if(standalone)ib.style.display='none';   /* already installed */
      ib.onclick=function(){if(deferred){deferred.prompt();deferred=null}else alert('To install: browser menu → "Add to Home Screen" (or "Install app").')}}
    document.body.classList.add('opai-has-shell');if(pos!=='fixed')document.body.classList.add('opai-pad');
    requestAnimationFrame(function(){try{var nv=hd.querySelector('.opai-pills'),ac=nv&&nv.querySelector('[aria-current=page]');if(ac&&nv.scrollWidth>nv.clientWidth)nv.scrollLeft=Math.max(0,ac.offsetLeft-6)}catch(e){}});return hd;
  }
  function icons(){var s='fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';return {
    today:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    chat:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.3A8 8 0 1 1 21 12z"/></svg>',
    work:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/></svg>',
    plan:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
    guide:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/></svg>',
    term:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/></svg>',
    dl:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg>'}}
  var deferred=null;addEventListener('beforeinstallprompt',function(e){if(isChat)return;e.preventDefault();deferred=e});
  function dock(){
    if(isChat)return;var I=icons();
    var d=h('<div class="opai-dock" role="toolbar" aria-label="Quick actions"><a href="today.html" title="Today" '+(path==='today.html'?'aria-current="page"':'')+'>'+I.today+'<small>Today</small></a><a href="super-chat.html" title="Ask KARNA">'+I.chat+'<small>KARNA</small></a><a href="work.html" title="Work" '+(/^(work|opportunities|dsa|projects|academics)\.html$/.test(path)?'aria-current="page"':'')+'>'+I.work+'<small>Work</small></a></div>');
    document.body.appendChild(d);
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
  function photoUrl(){try{var u=localStorage.getItem('opai_sc_photo')||'';return /^https:\/\//.test(u)?u:''}catch(e){return ''}}
  function paintAv(el,name){var ph=photoUrl(),ini=((name||mail||'A')[0]||'A').toUpperCase();el.textContent=ini;
    if(ph){var im=new Image();im.alt='';im.referrerPolicy='no-referrer';im.style.cssText='width:100%;height:100%;border-radius:50%;object-fit:cover;display:block';
      im.onload=function(){el.textContent='';el.style.padding='0';el.style.overflow='hidden';el.appendChild(im)};im.src=ph}}
  /* Render free tier sleeps: the first calls fail with a network error or 502/503/504. Retry with backoff so the avatar, name and onboarding check still work after the wake-up. */
  function devLogin(n){return fetch(API+'/v1/auth/dev-login?email='+encodeURIComponent(mail),{method:'POST'}).then(function(r){if(r.status>=502&&r.status<=504&&n<5)throw 0;return r},function(){throw 0}).catch(function(){if(n>=5)return null;return new Promise(function(ok){setTimeout(ok,2000*(n+1))}).then(function(){return devLogin(n+1)})})}
  function who(){
    var st=document.getElementById('opai-st'),av=document.getElementById('opai-av'),un=document.getElementById('opai-un'),us=document.getElementById('opai-us');if(!st)return;
    fetch(API+'/v1/health').then(function(r){if(!r.ok)throw 0;st.className='opai-st';st.querySelector('span').textContent='Online'}).catch(function(){st.className='opai-st off';st.querySelector('span').textContent='Waking up…'});
    setTimeout(function(){var sp=st.querySelector('span');if(sp&&sp.textContent==='Connecting…'){st.className='opai-st off';sp.textContent='Waking up…'}},6000);
    if(!mail)return;devLogin(0).then(function(r){return r&&r.ok?r.json():null}).then(function(d){if(!d)return null;uid=d.user_id;if(d.onboarding_required&&!/onboarding\.html/.test(location.pathname)){location.replace('onboarding.html');return null}return fetch(API+'/v1/profile?user_id='+encodeURIComponent(uid))}).then(function(r){return r&&r.ok?r.json():null}).then(function(p){if(!p)return;
      var n=p.name?p.name:(mail?mail.split('@')[0]:'Account');un.textContent=n;paintAv(av,n);us.textContent=[p.branch,p.degree].filter(Boolean).join(' · ')||'Personal workspace'}).catch(function(){});
  }
  function karna(){if(isChat||window.OPAI_KARNA_POPUP||document.querySelector('script[src*="karna-popup.js"]'))return;var k=document.createElement('script');k.src='karna-popup.js';k.defer=true;document.body.appendChild(k)}
  /* keep the free-tier backend awake while a tab is open (Render sleeps after ~15 min idle); wake it early when the tab returns */
  function keepAlive(){var ping=function(){try{fetch(API+'/v1/health',{cache:'no-store'}).catch(function(){})}catch(e){}};
    setInterval(function(){if(!document.hidden)ping()},9*60*1000);
    document.addEventListener('visibilitychange',function(){if(!document.hidden)ping()})}
  function boot(){keepAlive();var hd=header();dock();timer();karna();if(hd){who();document.getElementById('opai-k').onclick=function(){window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
      addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();window.OPAI_GUIDE&&OPAI_GUIDE.open('')}})}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();

/* mobile: scroll the top nav so the current page's tab is visible */
(function(){var n=0,t=setInterval(function(){var p=document.querySelector('.opai-pills'),c=p&&p.querySelector('[aria-current]');if(c){p.scrollLeft=Math.max(0,c.offsetLeft-(p.clientWidth-c.offsetWidth)/2);clearInterval(t)}else if(++n>20)clearInterval(t)},100)})();
