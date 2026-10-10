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
  window.OPAI_THEME={get:current,set:function(t){try{localStorage.setItem(KEY,t)}catch(e){}apply(t);sync()},toggle:function(ev){
    var next=current()==='dark'?'light':'dark',self=this,RMq=matchMedia('(prefers-reduced-motion:reduce)').matches;
    if(!RMq&&document.startViewTransition&&ev&&ev.clientX!=null){
      var x=ev.clientX,y=ev.clientY,r=Math.hypot(Math.max(x,innerWidth-x),Math.max(y,innerHeight-y));
      root.classList.add('opai-vt');
      var vt=document.startViewTransition(function(){self.set(next)});
      vt.ready.then(function(){root.animate({clipPath:['circle(0px at '+x+'px '+y+'px)','circle('+r+'px at '+x+'px '+y+'px)']},{duration:650,easing:'cubic-bezier(.22,.61,.36,1)',pseudoElement:'::view-transition-new(root)'})}).catch(function(){});
      vt.finished.finally(function(){root.classList.remove('opai-vt')});return}
    root.classList.add('opai-swap');clearTimeout(window.__oSw);window.__oSw=setTimeout(function(){root.classList.remove('opai-swap')},500);
    this.set(next)}};

  var SUN='<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
      MOON='<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  function sync(){[].forEach.call(document.querySelectorAll('.opai-theme'),function(b){var d=current()==='dark';b.setAttribute('aria-pressed',d);b.title=d?'Switch to light mode':'Switch to dark mode';b.setAttribute('aria-label',b.title)})}
  function mount(){
    if(document.querySelector('.opai-theme'))return;
    var b=document.createElement('button');b.type='button';b.className='opai-theme';b.innerHTML=SUN+MOON;
    b.onclick=function(e){OPAI_THEME.toggle(e)};
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
    motion();extras();
  }


  /* ---------- motion v2 ---------- */
  function extras(){
    if(RM)return;
    var $=function(s,r){return [].slice.call((r||document).querySelectorAll(s))};
    /* ambient glow */
    var amb=document.createElement('div');amb.id='o-amb';amb.innerHTML='<i></i><i></i><i></i>';document.body.appendChild(amb);
    /* header: shrink on scroll */
    var hd=document.querySelector('.opai-hd');
    addEventListener('scroll',function(){var h=document.querySelector('.opai-hd');h&&h.classList.toggle('o-sc',scrollY>24)},{passive:true});
    /* sliding hover pill in the nav */
    function pills(){var nav=document.querySelector('.opai-pills');if(!nav||nav.querySelector('.o-ind'))return;
      var ind=document.createElement('span');ind.className='o-ind';nav.insertBefore(ind,nav.firstChild);
      function to(a){var r=a.getBoundingClientRect(),n=nav.getBoundingClientRect();ind.style.width=r.width+'px';ind.style.transform='translateX('+(r.left-n.left+nav.scrollLeft)+'px)';ind.style.opacity='1'}
      $('a',nav).forEach(function(a){a.addEventListener('pointerenter',function(){to(a)})});
      nav.addEventListener('pointerleave',function(){ind.style.opacity='0'})}
    /* cursor spotlight, dock magnify, ripple (one delegated listener each) */
    var SPOT='.card,.panel,.cc,.course,article,.hk,.addbox,.today-card,.proj,.opp';
    addEventListener('pointermove',function(e){
      var t=e.target&&e.target.closest?e.target.closest(SPOT):null;
      if(t){var r=t.getBoundingClientRect();t.style.setProperty('--mx',(e.clientX-r.left)+'px');t.style.setProperty('--my',(e.clientY-r.top)+'px');t.classList.add('o-spot')}
      var dk=e.target&&e.target.closest?e.target.closest('.opai-dock'):null;
      if(dk){$('a,button',dk).forEach(function(b){var r=b.getBoundingClientRect(),d=Math.abs(e.clientX-(r.left+r.width/2)),s=1+Math.max(0,1-d/90)*.35;b.style.transform='translateY('+(-(s-1)*20)+'px) scale('+s.toFixed(3)+')'})}
    },{passive:true});
    addEventListener('pointerout',function(e){var dk=e.target&&e.target.closest?e.target.closest('.opai-dock'):null;if(dk&&!dk.contains(e.relatedTarget))$('a,button',dk).forEach(function(b){b.style.transform=''})});
    addEventListener('pointerdown',function(e){
      var b=e.target&&e.target.closest?e.target.closest('button,.btn,.b,.big,.chip,a.b'):null;if(!b||b.disabled||b.closest('.opai-dock'))return;
      if(getComputedStyle(b).position==='static')b.classList.add('o-rip-host');else if(!/(absolute|fixed|relative|sticky)/.test(getComputedStyle(b).position))return;
      var r=b.getBoundingClientRect(),s=Math.max(r.width,r.height)*2.2,d=document.createElement('span');d.className='o-rip';
      d.style.cssText='width:'+s+'px;height:'+s+'px;left:'+(e.clientX-r.left-s/2)+'px;top:'+(e.clientY-r.top-s/2)+'px';
      if(getComputedStyle(b).overflow==='visible')b.style.overflow='hidden';
      b.appendChild(d);setTimeout(function(){d.remove()},650)},{passive:true});
    /* heading words rise in (plain-text headings only) */
    function words(h){if(h.dataset.ow||h.children.length||!h.textContent.trim()||h.textContent.length>90)return;h.dataset.ow=1;
      var t=h.textContent.trim();h.setAttribute('aria-label',t);var i=0;h.textContent='';
      t.split(/\s+/).forEach(function(w,k){var o=document.createElement('span');o.className='o-w';o.setAttribute('aria-hidden','true');var s=document.createElement('span');s.textContent=w;s.style.setProperty('--w',k);o.appendChild(s);h.appendChild(o);if(k<t.split(/\s+/).length-1)h.appendChild(document.createTextNode(' '))})}
    /* count-up for big numbers */
    function count(n){if(n.dataset.oc)return;var m=n.textContent.trim().match(/^(\D{0,2})(\d{1,5}(?:\.\d+)?)(\s?(?:%|min|m|h|d|days?))?$/);if(!m)return;
      var fs=parseFloat(getComputedStyle(n).fontSize);if(fs<20)return;n.dataset.oc=1;var end=parseFloat(m[2]),dec=m[2].indexOf('.')>-1?1:0,t0=performance.now();
      (function f(now){var k=Math.min(1,(now-t0)/1000);n.textContent=m[1]+(end*(1-Math.pow(1-k,3))).toFixed(dec)+(m[3]||'');if(k<1)requestAnimationFrame(f)})(t0)}
    function sweep(rootEl){
      $('h1,h2',rootEl).forEach(function(h){if(!h.closest('.opai-hd,#opai-guide,dialog,.modal'))words(h)});
      $('b,strong,span,div,p,h3,h4',rootEl).forEach(function(n){if(n.children.length===0&&n.textContent.length<9&&/^\D{0,2}\d/.test(n.textContent.trim())&&!n.closest('.opai-hd,.opai-timer,input'))count(n)});
      $('p,span,div,small',rootEl).forEach(function(n){if(!n.children.length&&/^Loading/i.test(n.textContent.trim())&&n.textContent.length<40)n.classList.add('o-shim')});
    }
    pills();setTimeout(pills,300);setTimeout(pills,1200);
    setTimeout(function(){sweep(document.body)},120);
    var q2=0,pend=[];
    new MutationObserver(function(ms){ms.forEach(function(m){[].forEach.call(m.addedNodes,function(n){if(n.nodeType===1&&n.id!=='o-amb'&&!n.classList.contains('o-ind'))pend.push(n)})});
      if(q2)return;q2=setTimeout(function(){q2=0;var b=pend;pend=[];b.forEach(function(n){if(n.isConnected){sweep(n);pills()}})},90)}).observe(document.body,{childList:true,subtree:true});
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
