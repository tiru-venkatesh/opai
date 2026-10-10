/* OPAI ux: dark/light toggle + section animations. Plain JS, no dependencies.
   Put <script src="opai-ux.js"></script> in <head> (theme applies before first paint, so no flash). */
(function(){
  var KEY='opai_theme',root=document.documentElement,mq=matchMedia('(prefers-color-scheme:dark)');
  function saved(){try{return localStorage.getItem(KEY)}catch(e){return null}}
  function current(){var s=saved();return s==='dark'||s==='light'?s:(mq.matches?'dark':'light')}
  function apply(t){root.setAttribute('data-theme',t);root.classList.toggle('dark',t==='dark');
    var m=document.querySelector('meta[name=theme-color]');if(m)m.setAttribute('content',t==='dark'?'#0f1211':'#F6F4EE')}
  apply(current());
  mq.addEventListener&&mq.addEventListener('change',function(){if(!saved())apply(current())});
  addEventListener('storage',function(e){if(e.key===KEY)apply(current())});
  window.OPAI_THEME={get:current,set:function(t){try{localStorage.setItem(KEY,t)}catch(e){}apply(t);sync()},toggle:function(){
    root.classList.add('opai-swap');clearTimeout(window.__oSw);window.__oSw=setTimeout(function(){root.classList.remove('opai-swap')},500);
    this.set(current()==='dark'?'light':'dark')}};

  var SUN='<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
      MOON='<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function sync(){[].forEach.call(document.querySelectorAll('.opai-theme'),function(b){var d=current()==='dark';b.setAttribute('aria-pressed',d);b.title=d?'Switch to light mode':'Switch to dark mode';b.setAttribute('aria-label',b.title)})}
  function mount(){
    if(document.querySelector('.opai-theme'))return;
    var b=document.createElement('button');b.type='button';b.className='opai-theme';b.innerHTML=SUN+MOON;
    b.onclick=function(){OPAI_THEME.toggle()};
    var right=document.querySelector('.opai-right');
    if(right)right.insertBefore(b,right.firstChild);
    else{b.classList.add('float');document.body.appendChild(b)}
    sync();
  }
  /* shell builds its header on DOMContentLoaded; mount after it (and once more if the header shows up late) */
  function boot(){
    setTimeout(function(){mount()},60);
    var tries=0,iv=setInterval(function(){var f=document.querySelector('.opai-theme.float'),r=document.querySelector('.opai-right');
      if(f&&r){f.remove();mount()}if(++tries>20||(r&&document.querySelector('.opai-right .opai-theme')))clearInterval(iv)},150);
    motion();
  }

  /* ---------- motion ---------- */
  var RM=matchMedia('(prefers-reduced-motion:reduce)').matches;
  var CARD='article,.hk,.card,.panel,.cc,.addbox,.course,.task,.kpi,.stat,.proj,.opp,.sec,.sechd,.blk,.tp,details.ph,.msg,.repo,.col>*,.today-card,.hero-card,section>h2,main section,main>div>div,.wrap>section,.wrap>.grid>*';
  function motion(){
    if(RM||!('IntersectionObserver' in window))return;
    root.classList.add('o-js');
    var bar=document.createElement('div');bar.id='o-prog';document.body.appendChild(bar);
    var tick=0;addEventListener('scroll',function(){if(tick)return;tick=requestAnimationFrame(function(){tick=0;var h=root.scrollHeight-innerHeight;bar.style.transform='scaleX('+(h>0?Math.min(1,scrollY/h):0)+')'})},{passive:true});
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('o-in');io.unobserve(e.target)}})},{threshold:.08,rootMargin:'0px 0px -4% 0px'});
    var seen=new WeakSet();
    function skip(n){return n.closest('.opai-hd,.opai-dock,.opai-timer,#opai-guide,dialog,.modal,#karna-pop,[id^=karna]')||n.classList.contains('o-rv')}
    function scan(rootEl,late){
      var list=[].slice.call(rootEl.querySelectorAll(CARD)).filter(function(n){return !seen.has(n)&&!skip(n)&&n.offsetHeight<=innerHeight*1.1});/* page-sized wrappers are skipped so the cards inside them animate instead */
      /* only top-most matches: don't animate a card and the card inside it */
      list=list.filter(function(n){var p=n.parentElement;while(p&&p!==rootEl){if(list.indexOf(p)>-1)return false;p=p.parentElement}return true});
      var i=0,vh=innerHeight;
      list.forEach(function(n){seen.add(n);
        if(late){n.style.setProperty('--o-d',Math.min(i++,8)*45+'ms');n.classList.add('o-new');setTimeout(function(){n.classList.remove('o-new')},900);return}
        var r=n.getBoundingClientRect();n.style.setProperty('--o-d',(r.top<vh?Math.min(i++,8)*60:0)+'ms');n.classList.add('o-rv');io.observe(n)});
    }
    scan(document.body,false);
    /* content rendered by JS after fetch/tab switch: stagger it in; a tab switch gets the swap fade on its container */
    var q=0,pending=[];
    new MutationObserver(function(ms){
      ms.forEach(function(m){[].forEach.call(m.addedNodes,function(n){if(n.nodeType===1&&!skip(n)&&n.id!=='o-prog'&&!n.classList.contains('opai-theme'))pending.push(n)})});
      if(q)return;q=requestAnimationFrame(function(){q=0;var batch=pending;pending=[];
        batch.forEach(function(n){if(!n.isConnected)return;if(n.matches&&n.matches(CARD)&&!seen.has(n)){seen.add(n);n.classList.add('o-new');setTimeout(function(){n.classList.remove('o-new')},900)}scan(n,true)})})
    }).observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
