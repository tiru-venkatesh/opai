/* KARNA popup: floating chat on any page that includes this script. Same backend + identity as super-chat.html. */
(function(){
  if(window.OPAI_KARNA_POPUP)return;window.OPAI_KARNA_POPUP=1;
  var page=(location.pathname.split('/').pop()||'').replace(/\.html$/,'');
  if(/^super-chat/.test(page)){window.OPAI_KARNA_POPUP=0;return}
  var CTX={
    projects:{label:'Projects',chips:['Which project is in progress?','Add project: Portfolio v2, stack React','What should I work on next?']},
    academics:{label:'Academics',chips:['What exams are coming up?','Add exam: OS on 20 Nov','Which subject needs the most revision?']}
  }[page]||{label:'OPAI',chips:['What is due today?','What did I apply to this week?']};

  var API=(localStorage.getItem('opa_api_base')||(/^(localhost|127\.0\.0\.1)$/.test(location.hostname)?'http://localhost:8000':'https://opa-52ug.onrender.com')).replace(/\/+$/,'');
  var KEY='opai_popup_chat',OPEN='opai_popup_open';
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function loadMsgs(){try{var m=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(m)?m.slice(-40):[]}catch(e){return[]}}
  function saveMsgs(){try{localStorage.setItem(KEY,JSON.stringify(msgs.slice(-40)))}catch(e){}}
  var msgs=loadMsgs(),busy=false,ctrl=null,uid=null,changed=false;

  async function api(path,opts){
    opts=opts||{};
    var res=await fetch(API+path,Object.assign({headers:opts.body?{'Content-Type':'application/json'}:{}},opts));
    if(!res.ok){var d='';try{d=(await res.json()).detail||''}catch(e){}if(Array.isArray(d))d=d.map(function(x){return x.msg}).join('; ');var er=new Error(d||(res.status+' '+res.statusText));er.status=res.status;throw er}
    var t=await res.text();return t?JSON.parse(t):null;
  }
  async function ensureUser(){
    if(uid)return uid;
    var email=localStorage.getItem('opai_sc_email');
    if(email){uid=(await api('/v1/auth/dev-login?email='+encodeURIComponent(email),{method:'POST'})).user_id;return uid}
    throw new Error('Not signed in');
  }
  function explain(e){
    if(e.name==='AbortError')return null;
    if((e.status===503||e.status===502)&&/GROQ|not configured|AI is not/i.test(e.message))return 'The AI key is not set on the backend yet. Add GROQ_API_KEY and retry.';
    if(e.status===429)return 'Too many requests. Wait a minute and retry.';
    if(e.name==='TypeError')return 'Could not reach the backend. If it is on a free host it may be waking up; retry in a minute.';
    return e.message||'Something went wrong.';
  }

  /* tiny safe markdown: bold, code, relative/https links, bullets */
  function md(t){
    var s=esc(t);
    s=s.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
    s=s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g,function(m,a,u){u=u.replace(/&amp;/g,'&');return /^(https:\/\/|[\w.\/#?=&-]+$)/.test(u)?'<a href="'+esc(u)+'">'+a+'</a>':a});
    var out=[],inList=false;
    s.split('\n').forEach(function(l){
      var b=/^\s*[-*]\s+(.*)/.exec(l);
      if(b){if(!inList){out.push('<ul>');inList=true}out.push('<li>'+b[1]+'</li>')}
      else{if(inList){out.push('</ul>');inList=false}out.push(l.trim()?'<p>'+l+'</p>':'')}
    });
    if(inList)out.push('</ul>');return out.join('');
  }

  var css='#kp-fab{position:fixed;right:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));z-index:65;display:flex;align-items:center;gap:8px;height:48px;padding:0 18px 0 14px;border:0;border-radius:999px;background:var(--teal,#17504A);color:#fff;font:600 14px var(--sans,system-ui);cursor:pointer;box-shadow:0 12px 30px -10px rgba(23,80,74,.6)}'+
  '#kp-fab:hover{background:var(--teal-2,#1F6A62)}#kp-fab i{width:9px;height:9px;border-radius:50%;background:var(--coral,#E8705A);flex:none}'+
  '#kp{position:fixed;right:14px;bottom:calc(74px + env(safe-area-inset-bottom,0px));z-index:80;width:min(390px,calc(100vw - 24px));height:min(580px,calc(100vh - 150px));display:none;flex-direction:column;background:var(--card,#FBFAF6);color:var(--ink,#16181A);border:1px solid var(--hair,#E3DFD3);border-radius:18px;box-shadow:0 24px 60px -20px rgba(22,24,26,.45);overflow:hidden;font:14px/21px var(--sans,system-ui)}'+
  '#kp.open{display:flex}#kp *{box-sizing:border-box}'+
  '#kp .hd{display:flex;align-items:center;gap:10px;padding:12px 14px;border-bottom:1px solid var(--hair,#E3DFD3);background:var(--paper,#F6F4EE)}'+
  '#kp .av{width:30px;height:30px;border-radius:50%;background:var(--teal,#17504A);color:#fff;display:grid;place-items:center;font:700 13px var(--sans,system-ui);flex:none}'+
  '#kp .hd b{display:block;font-size:14px;line-height:16px}#kp .hd small{display:block;font:11px/14px var(--mono,monospace);color:var(--ink-3,#7A7F80)}#kp .hd .sp{flex:1;min-width:0}'+
  '#kp .hd a,#kp .hd button{border:0;background:none;color:var(--ink-2,#4A4F52);cursor:pointer;font:12px var(--mono,monospace);text-decoration:none;padding:6px 8px;border-radius:8px}'+
  '#kp .hd a:hover,#kp .hd button:hover{background:var(--well,#EDE9DF)}#kp .hd .x{font-size:20px;line-height:1;padding:2px 8px}'+
  '#kp .th{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;overscroll-behavior:contain}'+
  '#kp .m{max-width:88%;padding:9px 12px;border-radius:14px;word-wrap:break-word}#kp .m p{margin:0 0 6px}#kp .m p:last-child{margin:0}#kp .m ul{margin:4px 0 6px;padding-left:18px;list-style:disc}#kp .m li{display:list-item;margin:2px 0}'+
  '#kp .m code{font:12px var(--mono,monospace);background:var(--well,#EDE9DF);padding:1px 5px;border-radius:5px}#kp .m a{color:var(--teal,#17504A);text-decoration:underline}'+
  '#kp .u{align-self:flex-end;background:var(--teal,#17504A);color:#fff;border-bottom-right-radius:4px}#kp .u a{color:#fff}'+
  '#kp .a{align-self:flex-start;background:var(--card-2,#F2EFE7);border:1px solid var(--hair,#E3DFD3);border-bottom-left-radius:4px}'+
  '#kp .e{align-self:flex-start;background:var(--coral-soft,#FCE4DC);color:var(--coral-ink,#C2452F);border-radius:12px}'+
  '#kp .s{align-self:center;font:11px var(--mono,monospace);color:var(--ink-3,#7A7F80)}'+
  '#kp .ty em{font:12px var(--mono,monospace);color:var(--ink-3,#7A7F80);font-style:normal}'+
  '#kp .ch{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 10px}#kp .ch button,#kp .rf{border:1px solid var(--hair,#E3DFD3);background:var(--well,#EDE9DF);color:var(--ink-2,#4A4F52);border-radius:999px;padding:5px 11px;font:12px var(--sans,system-ui);cursor:pointer}'+
  '#kp .ch button:hover,#kp .rf:hover{color:var(--ink,#16181A);border-color:var(--line-2,#D2CCBC)}#kp .rf{align-self:flex-start;background:var(--teal-soft,#E1EEEA);color:var(--teal,#17504A)}'+
  '#kp .bp{margin-top:8px;padding:8px 10px;border-radius:10px;background:var(--well,#EDE9DF);font-size:13px}#kp .ac{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}#kp .ac button{border:1px solid var(--hair,#E3DFD3);background:var(--teal-soft,#E1EEEA);color:var(--teal,#17504A);border-radius:999px;padding:6px 11px;font:600 12px var(--sans,system-ui);cursor:pointer}#kp .ac button:disabled{opacity:.6;cursor:default}'+
  '#kp .ft{display:flex;gap:8px;align-items:flex-end;padding:10px 12px calc(10px + env(safe-area-inset-bottom,0px));border-top:1px solid var(--hair,#E3DFD3);background:var(--paper,#F6F4EE)}'+
  '#kp textarea{flex:1;resize:none;max-height:110px;min-height:40px;border:1px solid var(--hair,#E3DFD3);border-radius:12px;padding:9px 12px;background:#fff;color:inherit;font:14px/20px var(--sans,system-ui)}'+
  '#kp .go{width:40px;height:40px;border:0;border-radius:50%;background:var(--coral,#E8705A);color:#fff;font-size:17px;cursor:pointer;flex:none}#kp .go:disabled{opacity:.5;cursor:default}'+
  '@media(max-width:760px){#kp-fab{bottom:calc(76px + env(safe-area-inset-bottom,0px));right:12px}#kp{right:0;left:0;bottom:0;width:100%;height:78vh;border-radius:18px 18px 0 0}}'+
  '@media(prefers-reduced-motion:no-preference){#kp.open{animation:kpIn .18s ease-out}@keyframes kpIn{from{opacity:0;transform:translateY(10px)}}}';

  var fab,box,th,ta,go;
  function build(){
    var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);
    fab=document.createElement('button');fab.id='kp-fab';fab.type='button';fab.setAttribute('aria-label','Open KARNA chat');fab.innerHTML='<i></i>Ask KARNA';
    box=document.createElement('div');box.id='kp';box.setAttribute('role','dialog');box.setAttribute('aria-label','KARNA chat');
    box.innerHTML='<div class="hd"><div class="av">K</div><div class="sp"><b>KARNA</b><small>'+esc(CTX.label)+' · workspace</small></div><button type="button" class="nw" title="Start a new chat">new</button><a href="super-chat.html" title="Open full KARNA">full ↗</a><button type="button" class="x" aria-label="Close">×</button></div><div class="th" aria-live="polite"></div><div class="ch"></div><div class="ft"><textarea rows="1" placeholder="Ask or add something…" aria-label="Message KARNA"></textarea><button type="button" class="go" aria-label="Send">➤</button></div>';
    document.body.appendChild(fab);document.body.appendChild(box);
    th=box.querySelector('.th');ta=box.querySelector('textarea');go=box.querySelector('.go');
    fab.onclick=function(){toggle()};
    box.querySelector('.x').onclick=function(){toggle(false)};
    box.querySelector('.nw').onclick=function(){if(busy)return;msgs=[];changed=false;saveMsgs();draw()};
    go.onclick=function(){send()};
    ta.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send()}});
    ta.addEventListener('input',function(){ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight,110)+'px'});
    box.querySelector('.ch').addEventListener('click',function(e){var b=e.target.closest('button');if(b){ta.value=b.textContent;ta.focus()}});
    th.addEventListener('click',function(e){if(e.target.closest('.rf'))location.reload()});
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&box.classList.contains('open'))toggle(false);
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='j'){e.preventDefault();toggle()}});
    draw();
    if(sessionStorage.getItem(OPEN)==='1')toggle(true);
  }
  function toggle(on){
    var o=on==null?!box.classList.contains('open'):on;
    box.classList.toggle('open',o);fab.style.display=o&&innerWidth<=760?'none':'';
    try{sessionStorage.setItem(OPEN,o?'1':'0')}catch(e){}
    if(o){scrollEnd();setTimeout(function(){ta.focus()},50)}
  }
  function scrollEnd(){th.scrollTop=th.scrollHeight}
  function bubble(m){
    var d=document.createElement('div');
    if(m.role==='user'){d.className='m u';d.textContent=m.text}
    else if(m.role==='err'){d.className='m e';d.textContent=m.text}
    else{d.className='m a';d.innerHTML=md(m.text||'(no reply)');
      if(m.brief&&m.brief.priorities&&m.brief.priorities.length){var bp=document.createElement('div');bp.className='bp';
        m.brief.priorities.forEach(function(p){var l=document.createElement('div');l.textContent=p.rank+'. '+p.title+(p.duration_min?' · '+p.duration_min+' min':'');bp.appendChild(l)});d.appendChild(bp)}
      if(m.actions&&m.actions.length){var cs=document.createElement('div');cs.className='ac';
        m.actions.forEach(function(a){var b=document.createElement('button');b.type='button';b.textContent=a.label;
          if(a.status==='executed'){b.disabled=true;b.textContent='✓ '+a.label}
          b.onclick=function(){runAction(a,b)};cs.appendChild(b)});d.appendChild(cs)}}
    return d;
  }
  function draw(){
    th.innerHTML='';
    if(!msgs.length){var w=document.createElement('div');w.className='m a';w.innerHTML='<p>Hi, I am KARNA. Ask about your '+esc(CTX.label.toLowerCase())+' or add things by typing.</p>';th.appendChild(w)}
    msgs.forEach(function(m){th.appendChild(bubble(m))});
    if(changed){var r=document.createElement('button');r.type='button';r.className='rf';r.textContent='↻ Refresh page to see changes';th.appendChild(r)}
    box.querySelector('.ch').style.display=msgs.length?'none':'flex';
    box.querySelector('.ch').innerHTML=CTX.chips.map(function(c){return '<button type="button">'+esc(c)+'</button>'}).join('');
    scrollEnd();
  }
  function safeUrl(u){try{var x=new URL(u,location.href);if(x.protocol==='https:'||x.protocol==='http:')return x.href}catch(e){}return null}
  async function runAction(a,btn){
    if(a.type==='open_brief'||a.kind==='navigate'&&a.client_only){var u=safeUrl(a.link);if(u)location.href=u;return}
    if(a.kind==='prompt'){ta.value=a.prompt||'';ta.focus();return}
    btn.disabled=true;
    try{var uid=await ensureUser();
      var r=await api('/v1/actions/'+a.id+'/execute',{method:'POST',body:JSON.stringify({user_id:uid})});
      if(r.status==='needs_confirmation'){if(!confirm(a.label+'?\n\nRisk: '+a.risk+'. Nothing has changed yet.')){btn.disabled=false;return}
        r=await api('/v1/actions/'+a.id+'/confirm',{method:'POST',body:JSON.stringify({user_id:uid})})}
      if(r.status==='pending_approval'){btn.textContent='Waiting for approval';return}
      if(r.navigate&&a.kind==='navigate'){var nu=safeUrl(r.navigate);if(nu)location.href=nu;return}
      a.status='executed';btn.textContent='✓ '+a.label;changed=true;saveMsgs();
    }catch(e){btn.disabled=false;btn.textContent=a.label+' (retry)'}
  }
  function history(){
    var li=msgs.map(function(m){return m.role}).lastIndexOf('user');
    return msgs.slice(0,li<0?0:li).filter(function(m){return m.role==='user'||m.role==='agent'}).slice(-8)
      .map(function(m){return{role:m.role==='user'?'user':'assistant',content:String(m.text||'').slice(0,1500)}});
  }
  function setBusy(b){busy=b;go.disabled=b;ta.disabled=b}
  async function send(){
    if(busy)return;var text=ta.value.trim();if(!text)return;
    ta.value='';ta.style.height='auto';
    var um={role:'user',text:text};msgs.push(um);box.querySelector('.ch').style.display='none';
    th.appendChild(bubble(um));scrollEnd();saveMsgs();
    var lang='en';try{lang=localStorage.getItem('opai_reply_lang')||'en'}catch(e){}
    if(window.OPAI_GUIDE&&OPAI_GUIDE.isGuideQuery(text)){
      var gm={role:'agent',text:OPAI_GUIDE.answer(text,lang)};msgs.push(gm);th.appendChild(bubble(gm));scrollEnd();saveMsgs();return;
    }
    setBusy(true);
    var t=document.createElement('div');t.className='m a ty';t.innerHTML='<em>thinking 0.0s</em>';th.appendChild(t);scrollEnd();
    var t0=performance.now(),iv=setInterval(function(){t.firstChild.textContent='thinking '+((performance.now()-t0)/1000).toFixed(1)+'s'},100);
    ctrl=new AbortController();
    try{
      var tz=null;try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone}catch(e){}
      var conv=null;try{conv=sessionStorage.getItem('kp_conv')}catch(e){}
      var r=await api('/v1/chat',{method:'POST',signal:ctrl.signal,body:JSON.stringify({user_id:await ensureUser(),text:text,channel:'popup',timezone:tz,conversation_id:conv,history:history()})});
      try{if(r.conversation_id)sessionStorage.setItem('kp_conv',r.conversation_id)}catch(e){}
      var am={role:'agent',text:r.reply||'',brief:r.brief||null,actions:r.actions||[],status:r.status};msgs.push(am);
      if(r.action==='task'||(r.tool_calls&&r.tool_calls.length))changed=true;
      clearInterval(iv);saveMsgs();draw();
    }catch(e){
      clearInterval(iv);t.remove();var why=explain(e);
      if(why!==null){var em={role:'err',text:why};msgs.push(em);saveMsgs();th.appendChild(bubble(em));scrollEnd()}
    }finally{ctrl=null;setBusy(false);ta.focus()}
  }
  window.OPAI_KARNA_POPUP={open:function(){toggle(true)},close:function(){toggle(false)}};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',build);else build();
})();
