/* OPAI shell: left sidebar (replaces the old top nav + bottom dock) and focus timer on every app page. Exposes window.OPAI_FOCUS. */
(function(){
  if(window.OPAI_SHELL)return;window.OPAI_SHELL=1;
  var EMBED=window.top!==window.self||/[?&]embed=1/.test(location.search);
  if(EMBED){window.OPAI_KARNA_POPUP=1;var st=document.createElement('style');st.textContent='body>header,header.opai-hd,.opai-dock,.opai-sb,.opai-mbar,.opai-scrim{display:none!important}body{padding-top:0!important;padding-left:0!important}';document.head.appendChild(st);return}
  var path=(location.pathname.split('/').pop()||'today.html').replace(/\/$/,'')||'today.html';
  if(path==='super-chat'||path==='')path='super-chat.html';
  var NAV=[
    {g:'',items:[['Today','today.html','today'],['KARNA','super-chat.html','chat'],['Plan','plan.html','plan']]},
    {g:'Work',items:[['Internship','opportunities.html','intern'],['Hackathons','projects.html?view=hackathons','hack'],['Programs','projects.html?view=programs','prog'],['Projects','projects.html?view=projects','proj'],['Resume','resume-lab.html','resume'],['Academics','academics.html','acad']]},
    {g:'More',items:[['Review','review.html','review'],['Feedback','feedback.html','fb']]}
  ];
  var isChat=/super-chat/.test(path);
  var API=(localStorage.getItem('opa_api_base')||(/^(localhost|127\.0\.0\.1)$/.test(location.hostname)?'http://localhost:8000':'https://opa-52ug.onrender.com')).replace(/\/+$/,'');
  var uid=null,mail=((localStorage.getItem('opai_sc_email')||'').trim().toLowerCase())||null;
  function h(s){var d=document.createElement('div');d.innerHTML=s.trim();return d.firstChild}
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  var LOGO='<img class="opai-mark" src="assets/opai-logo-96.png" width="30" height="30" alt="" decoding="async">';

  /* ---------- sidebar ---------- */
  var SW=236,MQ='(max-width:900px)';
  var CSS='\
:root{--opai-sw:'+SW+'px;--opai-mb:52px}\
body.opai-side{padding-left:var(--opai-sw)}\
.opai-sb{position:fixed;top:0;left:0;bottom:0;width:var(--opai-sw);z-index:55;display:flex;flex-direction:column;gap:4px;padding:16px 12px calc(12px + env(safe-area-inset-bottom,0px));background:var(--card,#FBFAF6);color:var(--ink,#16181A);border-right:1px solid var(--hair,#E3DFD3);overflow-y:auto;overscroll-behavior:contain;font:14px/20px var(--sans,"Geist",system-ui,-apple-system,"Segoe UI",sans-serif);scrollbar-width:thin}\
html[data-theme=dark] .opai-sb{background:#161212;border-right-color:#2c2526;color:#ECE7E6}\
.opai-sb .sb-brand{display:flex;align-items:center;gap:10px;padding:4px 8px 12px;text-decoration:none;color:inherit}\
.opai-sb .sb-brand img{width:30px;height:30px;border-radius:8px;object-fit:cover;display:block}\
.opai-sb .sb-brand b{display:block;font:700 17px/1 var(--sans,system-ui);letter-spacing:-.02em}\
.opai-sb .sb-brand small{display:block;font:11px/1.2 var(--mono,ui-monospace,monospace);color:var(--ink-3,#7A7F80);margin-top:3px}\
.opai-sb .sb-search{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;margin:0 0 10px;padding:8px 12px;border-radius:10px;border:1px solid var(--hair,#E3DFD3);background:var(--well,#EDE9DF);color:var(--ink-3,#7A7F80);font:13px/18px var(--sans,system-ui);cursor:pointer;text-align:left}\
html[data-theme=dark] .opai-sb .sb-search{background:#211b1c;border-color:#2c2526;color:#a89f9f}\
.opai-sb .sb-search:hover{color:var(--ink,#16181A)}\
.opai-sb .sb-search kbd{font:11px/14px var(--mono,ui-monospace,monospace);padding:1px 6px;border-radius:6px;border:1px solid var(--hair,#E3DFD3);background:rgba(255,255,255,.5);color:inherit}\
.opai-sb .sb-gh{margin:12px 10px 4px;font:600 10.5px/14px var(--mono,ui-monospace,monospace);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3,#7A7F80)}\
.opai-sb nav{display:flex;flex-direction:column;gap:2px}\
.opai-sb nav a{display:flex;align-items:center;gap:11px;padding:8px 10px;border-radius:10px;color:var(--ink-2,#4A4F52);text-decoration:none;font-weight:500;transition:background-color .15s,color .15s}\
.opai-sb nav a svg{flex:none;opacity:.85}\
.opai-sb nav a:hover{background:var(--well,#EDE9DF);color:var(--ink,#16181A)}\
html[data-theme=dark] .opai-sb nav a{color:#bdb4b4}html[data-theme=dark] .opai-sb nav a:hover{background:#241d1e;color:#fff}\
.opai-sb nav a[aria-current=page]{background:var(--teal-soft,#E1EEEA);color:var(--teal,#17504A);font-weight:600}\
html[data-theme=dark] .opai-sb nav a[aria-current=page]{background:#E4EBE9;color:#120F0F}\
.opai-sb nav a:focus-visible,.opai-sb button:focus-visible,.opai-sb .opai-user:focus-visible{outline:2px solid var(--teal,#17504A);outline-offset:1px}\
.opai-sb .sb-foot{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding-top:12px}\
.opai-sb .sb-tools{display:flex;gap:6px}\
.opai-sb .sb-tools button{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:7px 8px;border-radius:10px;border:1px solid var(--hair,#E3DFD3);background:transparent;color:var(--ink-2,#4A4F52);font:12px/16px var(--sans,system-ui);cursor:pointer}\
.opai-sb .sb-tools button:hover{background:var(--well,#EDE9DF);color:var(--ink,#16181A)}\
html[data-theme=dark] .opai-sb .sb-tools button{border-color:#2c2526;color:#bdb4b4}\
.opai-sb .opai-st{display:flex;align-items:center;gap:7px;padding:6px 10px;border-radius:999px;background:var(--teal-soft,#E1EEEA);color:var(--teal,#17504A);font:11px/16px var(--mono,ui-monospace,monospace);letter-spacing:.04em;text-transform:uppercase;white-space:nowrap;align-self:flex-start}\
.opai-sb .opai-st i{width:7px;height:7px;border-radius:50%;background:currentColor}\
.opai-sb .opai-st.off{background:var(--coral-soft,#FCE4DC);color:var(--coral-ink,#C2452F)}\
.opai-sb .opai-user{display:flex;align-items:center;gap:10px;padding:6px 10px 6px 6px;border-radius:12px;border:1px solid var(--hair,#E3DFD3);background:var(--card-2,#F2EFE7);text-decoration:none;color:inherit;min-width:0}\
html[data-theme=dark] .opai-sb .opai-user{background:#1d1718;border-color:#2c2526}\
.opai-sb .opai-user[aria-current=page]{border-color:var(--teal,#17504A)}\
.opai-sb .opai-user .av{flex:none;width:32px;height:32px;border-radius:50%;background:var(--teal,#17504A);color:#fff;display:grid;place-items:center;font:600 13px var(--sans,system-ui)}\
.opai-sb .opai-user>span:last-child{min-width:0}\
.opai-sb .opai-user b{display:block;font:600 12.5px/16px var(--sans,system-ui);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\
.opai-sb .opai-user small{display:block;font:11px/14px var(--mono,ui-monospace,monospace);color:var(--ink-3,#7A7F80);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\
.opai-scrim{position:fixed;inset:0;z-index:54;background:rgba(22,24,26,.4);opacity:0;pointer-events:none;transition:opacity .2s}\
.opai-menu{display:none;align-items:center;justify-content:center;width:40px;height:40px;border-radius:10px;border:1px solid var(--hair,#E3DFD3);background:var(--card,#FBFAF6);color:var(--ink,#16181A);cursor:pointer;flex:none;padding:0}\
html[data-theme=dark] .opai-menu{background:#1d1718;border-color:#2c2526;color:#ECE7E6}\
.opai-mbar{display:none}\
body.opai-side .opai-timer{left:calc(var(--opai-sw) + 14px)}\
body.opai-side .dock{left:var(--opai-sw)}\
body.opai-side .tabs-wrap{top:0}\
body.opai-side #ktools .back{display:none}\
body.opai-side:not(:has(#ktools)){padding-bottom:0}\
@media '+MQ+'{\
 body.opai-side{padding-left:0}\
 body.opai-side:not(.opai-chat){padding-top:var(--opai-mb)}\
 .opai-sb{transform:translateX(-102%);transition:transform .22s cubic-bezier(.16,1,.3,1);box-shadow:none;width:min(280px,86vw)}\
 body.opai-nav-open .opai-sb{transform:none;box-shadow:0 0 40px rgba(0,0,0,.25)}\
 body.opai-nav-open .opai-scrim{opacity:1;pointer-events:auto}\
 .opai-menu{display:inline-flex}\
 .opai-mbar{position:fixed;top:0;left:0;right:0;height:var(--opai-mb);z-index:50;display:flex;align-items:center;gap:10px;padding:0 12px;padding-top:env(safe-area-inset-top,0px);background:var(--paper,#F6F4EE);border-bottom:1px solid var(--hair,#E3DFD3);font:600 15px/20px var(--sans,system-ui);color:var(--ink,#16181A)}\
 html[data-theme=dark] .opai-mbar{background:#120F0F;border-bottom-color:#2c2526;color:#ECE7E6}\
 body.opai-chat .opai-mbar{display:none}\
 body.opai-side .opai-timer{left:12px}\
 body.opai-side .dock{left:0}\
 body.opai-side .tabs-wrap{top:var(--opai-mb)}\
}\
@media(prefers-reduced-motion:reduce){.opai-sb,.opai-scrim{transition:none}}';
  function sbIcons(){var s='width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';return {
    today:'<svg '+s+'><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    chat:'<svg '+s+'><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.3A8 8 0 1 1 21 12z"/></svg>',
    plan:'<svg '+s+'><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
    intern:'<svg '+s+'><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/></svg>',
    hack:'<svg '+s+'><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>',
    prog:'<svg '+s+'><path d="M3 9l9-5 9 5-9 5z"/><path d="M7 11.5V16c0 1.2 2.2 2.5 5 2.5s5-1.3 5-2.5v-4.5"/></svg>',
    proj:'<svg '+s+'><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    resume:'<svg '+s+'><path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/></svg>',
    acad:'<svg '+s+'><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M9 7h6"/></svg>',
    review:'<svg '+s+'><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    fb:'<svg '+s+'><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    menu:'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
    search:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'}}
  function isCur(href){
    var u=href.split('?'),file=u[0],view=(u[1]||'').replace(/^view=/,'');
    if(file!==path)return false;
    if(file==='projects.html'){var cv=new URLSearchParams(location.search).get('view')||'projects';return cv===view}
    return true;
  }
  function curTitle(){var t='OPAI';NAV.forEach(function(g){g.items.forEach(function(n){if(isCur(n[1]))t=n[0]})});if(path==='profile.html')t='Profile';return t}
  function header(){
    if(!document.getElementById('opai-sb-css')){var st=document.createElement('style');st.id='opai-sb-css';st.textContent=CSS;document.head.appendChild(st)}
    /* the old per-page top nav (a body-level <header>, never the chat tool row) is removed */
    var old=document.querySelector('body > header:not(#ktools), body > .app > header');
    if(old&&old.parentNode)old.parentNode.removeChild(old);
    var I=sbIcons();
    var nav=NAV.map(function(g){return (g.g?'<div class="sb-gh">'+g.g+'</div>':'')+'<nav aria-label="'+(g.g||'Main')+'">'+g.items.map(function(n){return '<a href="'+n[1]+'"'+(isCur(n[1])?' aria-current="page"':'')+'>'+I[n[2]]+'<span>'+n[0]+'</span></a>'}).join('')+'</nav>'}).join('');
    var sb=h('<aside class="opai-sb" id="opai-sb" aria-label="Main navigation"><a class="sb-brand" href="today.html" aria-label="OPAI home">'+LOGO+'<span><b>OPAI</b><small>v8</small></span></a>'+
      '<button class="sb-search" type="button" id="opai-k" aria-label="Search sections"><span style="display:flex;align-items:center;gap:8px">'+I.search+'Search</span><kbd>Ctrl K</kbd></button>'+nav+
      '<div class="sb-foot"><span class="opai-st" id="opai-st"><i></i><span>Connecting…</span></span>'+
      '<div class="sb-tools"><button type="button" id="hd-guide" title="Guide: which section does what">Guide</button><button type="button" id="hd-install" title="Install OPAI as an app">Install</button></div>'+
      '<a class="opai-user" href="profile.html" title="Profile" aria-label="Open your profile"'+(path==='profile.html'?' aria-current="page"':'')+'><span class="av" id="opai-av">·</span><span><b id="opai-un">Account</b><small id="opai-us">OPAI</small></span></a></div></aside>');
    var scrim=h('<div class="opai-scrim" id="opai-scrim"></div>');
    document.body.insertBefore(scrim,document.body.firstChild);
    document.body.insertBefore(sb,document.body.firstChild);
    document.body.classList.add('opai-side','opai-has-shell');
    if(isChat)document.body.classList.add('opai-chat');
    /* phone: a slim bar holds only the menu button + page name; on the chat page the button joins the chat tool row instead */
    var mb=h('<button class="opai-menu" type="button" id="opai-menu" aria-label="Open menu" aria-controls="opai-sb" aria-expanded="false">'+I.menu+'</button>');
    var tools=isChat&&document.querySelector('#ktools .lead');
    if(tools)tools.insertBefore(mb,tools.firstChild);
    else{var bar=h('<div class="opai-mbar"></div>');bar.appendChild(mb);var tt=document.createElement('span');tt.textContent=curTitle();bar.appendChild(tt);document.body.insertBefore(bar,sb)}
    function setOpen(o){document.body.classList.toggle('opai-nav-open',o);mb.setAttribute('aria-expanded',o?'true':'false')}
    mb.onclick=function(){setOpen(!document.body.classList.contains('opai-nav-open'))};
    scrim.onclick=function(){setOpen(false)};
    addEventListener('keydown',function(e){if(e.key==='Escape')setOpen(false)});
    sb.addEventListener('click',function(e){if(e.target.closest('a'))setOpen(false)});
    var gb=sb.querySelector('#hd-guide'),ib=sb.querySelector('#hd-install');
    gb.onclick=function(){setOpen(false);window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
    var standalone=(window.matchMedia&&matchMedia('(display-mode: standalone)').matches)||navigator.standalone;
    if(standalone)ib.style.display='none';   /* already installed */
    ib.onclick=function(){if(deferred){deferred.prompt();deferred=null}else alert('To install: browser menu → "Add to Home Screen" (or "Install app").')};
    requestAnimationFrame(function(){try{var ac=sb.querySelector('[aria-current=page]');ac&&ac.scrollIntoView&&ac.scrollIntoView({block:'nearest'})}catch(e){}});
    return sb;
  }
  function icons(){var s='fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';return {
    today:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    chat:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.3A8 8 0 1 1 21 12z"/></svg>',
    work:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/></svg>',
    plan:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/></svg>',
    guide:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01"/></svg>',
    term:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/></svg>',
    dl:'<svg width="20" height="20" viewBox="0 0 24 24" '+s+'><path d="M12 4v11M7 11l5 5 5-5M5 20h14"/></svg>'}}
  var deferred=null;addEventListener('beforeinstallprompt',function(e){e.preventDefault();deferred=e});
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
  function boot(){keepAlive();var hd=header();if(!isChat)timer();karna();if(hd){who();document.getElementById('opai-k').onclick=function(){window.OPAI_GUIDE&&OPAI_GUIDE.open('')};
      addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();window.OPAI_GUIDE&&OPAI_GUIDE.open('')}})}}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
