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
  var MQ='(max-width:900px)';
  var CSS='\
:root{--opai-sw:248px}\
html.opai-min{--opai-sw:76px}\
body.opai-side{padding-left:var(--opai-sw);transition:padding-left .22s cubic-bezier(.16,1,.3,1)}\
.opai-sb{position:fixed;top:0;left:0;bottom:0;width:var(--opai-sw);z-index:55;display:flex;flex-direction:column;gap:4px;padding:14px 12px calc(12px + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,#14172e 0%,#0d0f21 100%);color:#e9ebff;border-right:1px solid rgba(255,255,255,.06);overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;font:14px/20px "Plus Jakarta Sans","Geist",system-ui,-apple-system,"Segoe UI",sans-serif;scrollbar-width:none;transition:width .22s cubic-bezier(.16,1,.3,1)}\
.opai-sb::-webkit-scrollbar{display:none}\
.opai-sb .sb-top{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:2px 2px 14px}\
.opai-sb .sb-brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:inherit;min-width:0}\
.opai-sb .sb-brand img{width:34px;height:34px;border-radius:11px;object-fit:cover;display:block;flex:none;box-shadow:0 0 0 1px rgba(255,255,255,.12)}\
.opai-sb .sb-brand b{display:block;font:800 17px/1 inherit;letter-spacing:-.02em;color:#fff}\
.opai-sb .sb-brand small{display:block;font:500 11px/1.2 "JetBrains Mono",ui-monospace,monospace;color:#8b90b8;margin-top:3px}\
.opai-sb .sb-col{flex:none;width:32px;height:32px;display:grid;place-items:center;border-radius:10px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#c9ccee;cursor:pointer;padding:0;transition:background-color .15s,transform .22s}\
.opai-sb .sb-col:hover{background:rgba(255,255,255,.12);color:#fff}\
html.opai-min .opai-sb .sb-col svg{transform:rotate(180deg)}\
.opai-sb .sb-search{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;margin:0 0 10px;padding:9px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.06);color:#a3a8cf;font:500 13px/18px inherit;cursor:pointer;text-align:left}\
.opai-sb .sb-search:hover{background:rgba(255,255,255,.11);color:#fff}\
.opai-sb .sb-search kbd{font:500 10.5px/14px "JetBrains Mono",ui-monospace,monospace;padding:1px 6px;border-radius:6px;border:1px solid rgba(255,255,255,.14);background:transparent;color:#a3a8cf}\
.opai-sb .sb-search .sb-s{display:flex;align-items:center;gap:9px}\
.opai-sb .sb-gh{margin:14px 12px 4px;font:700 10px/14px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:#6f759e;white-space:nowrap}\
.opai-sb nav{display:flex;flex-direction:column;gap:3px}\
.opai-sb nav a{position:relative;display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:12px;color:#b5b9dd;text-decoration:none;font-weight:600;white-space:nowrap;transition:background-color .15s,color .15s,transform .15s}\
.opai-sb nav a svg{flex:none}\
.opai-sb nav a:hover{background:rgba(255,255,255,.08);color:#fff;transform:translateX(2px)}\
.opai-sb nav a[aria-current=page]{background:#c6f135;color:#10122a;font-weight:700;box-shadow:0 8px 22px -10px rgba(198,241,53,.65)}\
.opai-sb nav a[aria-current=page]:hover{transform:none}\
.opai-sb a:focus-visible,.opai-sb button:focus-visible{outline:2px solid #c6f135;outline-offset:2px}\
.opai-sb .sb-foot{margin-top:auto;display:flex;flex-direction:column;gap:8px;padding-top:14px}\
.opai-sb .sb-tools{display:flex;gap:6px}\
.opai-sb .sb-tools button{flex:1;display:flex;align-items:center;justify-content:center;gap:6px;padding:8px;border-radius:11px;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#c3c7ea;font:600 12px/16px inherit;cursor:pointer;white-space:nowrap}\
.opai-sb .sb-tools .ic{display:none;font-weight:800}\
html.opai-min .opai-sb .sb-tools .ic{display:inline}\
.opai-sb .sb-tools button:hover{background:rgba(255,255,255,.12);color:#fff}\
.opai-sb .opai-st{display:flex;align-items:center;gap:7px;padding:6px 11px;border-radius:999px;background:rgba(198,241,53,.14);color:#c6f135;font:600 10.5px/16px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;white-space:nowrap;align-self:flex-start}\
.opai-sb .opai-st i{width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}\
.opai-sb .opai-st.off{background:rgba(255,120,120,.15);color:#ff8f8f}\
.opai-sb .opai-user{display:flex;align-items:center;gap:10px;padding:7px 10px 7px 7px;border-radius:14px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.06);text-decoration:none;color:inherit;min-width:0}\
.opai-sb .opai-user:hover{background:rgba(255,255,255,.12)}\
.opai-sb .opai-user[aria-current=page]{border-color:#c6f135}\
.opai-sb .opai-user .av{flex:none;width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#6d63ff,#f43f8e);color:#fff;display:grid;place-items:center;font:700 13px inherit}\
.opai-sb .opai-user .ut{min-width:0}\
.opai-sb .opai-user b{display:block;font:700 12.5px/16px inherit;color:#fff;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\
.opai-sb .opai-user small{display:block;font:500 11px/14px "JetBrains Mono",ui-monospace,monospace;color:#8b90b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}\
html.opai-min .opai-sb .l,html.opai-min .opai-sb .sb-gh,html.opai-min .opai-sb .sb-search kbd,html.opai-min .opai-sb .opai-st span,html.opai-min .opai-sb .sb-tools button .l{display:none}\
html.opai-min .opai-sb .sb-top{flex-direction:column;gap:10px;padding-bottom:10px}\
html.opai-min .opai-sb .sb-search,html.opai-min .opai-sb nav a,html.opai-min .opai-sb .opai-user{justify-content:center;padding-left:0;padding-right:0}\
html.opai-min .opai-sb .opai-user{border-color:transparent;background:none}\
html.opai-min .opai-sb nav{margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.07)}\
html.opai-min .opai-sb .sb-tools{flex-direction:column}\
html.opai-min .opai-sb .opai-st{padding:6px;align-self:center}\
.opai-scrim{position:fixed;inset:0;z-index:54;background:rgba(8,9,24,.55);backdrop-filter:blur(2px);opacity:0;pointer-events:none;transition:opacity .2s}\
.opai-menu{display:none;align-items:center;justify-content:center;width:40px;height:40px;border-radius:12px;border:0;background:#14172e;color:#fff;cursor:pointer;flex:none;padding:0}\
.opai-mbar{display:none}\
body.opai-side .opai-timer{left:calc(var(--opai-sw) + 14px)}\
body.opai-side .dock{left:var(--opai-sw)}\
body.opai-side .tabs-wrap{top:0}\
body.opai-side #ktools .back{display:none}\
body.opai-side:not(:has(#ktools)){padding-bottom:0}\
@media '+MQ+'{\
 html.opai-min{--opai-sw:248px}\
 body.opai-side{padding-left:0}\
 body.opai-side:not(.opai-chat){padding-top:var(--opai-mb)}\
 .opai-sb{width:min(290px,86vw);transform:translateX(-102%);transition:transform .24s cubic-bezier(.16,1,.3,1)}\
 body.opai-nav-open .opai-sb{transform:none;box-shadow:0 0 50px rgba(0,0,0,.45)}\
 body.opai-nav-open .opai-scrim{opacity:1;pointer-events:auto}\
 .opai-sb .sb-col{display:none}\
 html.opai-min .opai-sb .sb-tools .ic{display:none}\
 html.opai-min .opai-sb .l,html.opai-min .opai-sb .sb-gh{display:revert}\
 html.opai-min .opai-sb .sb-search kbd{display:none}\
 .opai-menu{display:inline-flex}\
 .opai-mbar{position:fixed;top:0;left:0;right:0;height:var(--opai-mb);z-index:50;display:flex;align-items:center;gap:10px;padding:0 12px;padding-top:env(safe-area-inset-top,0px);background:rgba(245,246,251,.92);backdrop-filter:blur(10px);border-bottom:1px solid #e3e5f1;font:700 15px/20px "Plus Jakarta Sans",system-ui,sans-serif;color:#12142b}\
 html[data-theme=dark] .opai-mbar{background:rgba(11,13,26,.92);border-bottom-color:#262a45;color:#eceeff}\
 html[data-theme=dark] .opai-menu{background:#262a45}\
 body.opai-chat .opai-mbar{display:none}\
 body.opai-side .opai-timer{left:12px}\
 body.opai-side .dock{left:0}\
 body.opai-side .tabs-wrap{top:var(--opai-mb)}\
}\
@media(prefers-reduced-motion:reduce){.opai-sb,.opai-scrim,body.opai-side{transition:none}}';
  var MB_VAR=':root{--opai-mb:52px}';
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
    chev:'<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg>',
    search:'<svg width="16" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'}}
  function isCur(href){
    var u=href.split('?'),file=u[0],view=(u[1]||'').replace(/^view=/,'');
    if(file!==path)return false;
    if(file==='projects.html'){var cv=new URLSearchParams(location.search).get('view')||'projects';return cv===view}
    return true;
  }
  function curTitle(){var t='OPAI';NAV.forEach(function(g){g.items.forEach(function(n){if(isCur(n[1]))t=n[0]})});if(path==='profile.html')t='Profile';return t}
  function header(){
    if(!document.getElementById('opai-sb-css')){var st=document.createElement('style');st.id='opai-sb-css';st.textContent=MB_VAR+CSS;document.head.appendChild(st)}
    if(!document.getElementById('opai-redesign')){var lk=document.createElement('link');lk.id='opai-redesign';lk.rel='stylesheet';lk.href='opai-redesign.css?v=1';document.head.appendChild(lk);
      var fl=document.createElement('link');fl.rel='stylesheet';fl.href='https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400..800&display=swap';document.head.appendChild(fl)}
    try{if(localStorage.getItem('opai_sb_min')==='1')document.documentElement.classList.add('opai-min')}catch(e){}
    /* the old per-page top nav (a body-level <header>, never the chat tool row) is removed */
    var old=document.querySelector('body > header:not(#ktools), body > .app > header');
    if(old&&old.parentNode)old.parentNode.removeChild(old);
    var I=sbIcons();
    var nav=NAV.map(function(g){return (g.g?'<div class="sb-gh">'+g.g+'</div>':'')+'<nav aria-label="'+(g.g||'Main')+'">'+g.items.map(function(n){return '<a href="'+n[1]+'" title="'+n[0]+'"'+(isCur(n[1])?' aria-current="page"':'')+'>'+I[n[2]]+'<span class="l">'+n[0]+'</span></a>'}).join('')+'</nav>'}).join('');
    var sb=h('<aside class="opai-sb" id="opai-sb" aria-label="Main navigation"><div class="sb-top"><a class="sb-brand" href="today.html" aria-label="OPAI home" title="OPAI">'+LOGO+'<span class="l"><b>OPAI</b><small>v8</small></span></a>'+
      '<button class="sb-col" type="button" id="opai-collapse" aria-label="Collapse sidebar" aria-expanded="true" title="Collapse / expand (Ctrl B)">'+I.chev+'</button></div>'+
      '<button class="sb-search" type="button" id="opai-k" aria-label="Search sections" title="Search (Ctrl K)"><span class="sb-s">'+I.search+'<span class="l">Search</span></span><kbd>Ctrl K</kbd></button>'+nav+
      '<div class="sb-foot"><span class="opai-st" id="opai-st"><i></i><span>Connecting…</span></span>'+
      '<div class="sb-tools"><button type="button" id="hd-guide" title="Guide: which section does what"><span class="ic">?</span><span class="l">Guide</span></button><button type="button" id="hd-install" title="Install OPAI as an app"><span class="ic">↓</span><span class="l">Install</span></button></div>'+
      '<a class="opai-user" href="profile.html" title="Profile" aria-label="Open your profile"'+(path==='profile.html'?' aria-current="page"':'')+'><span class="av" id="opai-av">·</span><span class="ut l"><b id="opai-un">Account</b><small id="opai-us">OPAI</small></span></a></div></aside>');
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
    var cb=sb.querySelector('#opai-collapse');
    function setMin(m){document.documentElement.classList.toggle('opai-min',m);cb.setAttribute('aria-expanded',m?'false':'true');cb.setAttribute('aria-label',m?'Expand sidebar':'Collapse sidebar');try{localStorage.setItem('opai_sb_min',m?'1':'0')}catch(e){}}
    setMin(document.documentElement.classList.contains('opai-min'));
    cb.onclick=function(){setMin(!document.documentElement.classList.contains('opai-min'))};
    addEventListener('keydown',function(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='b'&&!/^(INPUT|TEXTAREA|SELECT)$/.test((e.target||{}).tagName||'')){e.preventDefault();cb.click()}});
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
