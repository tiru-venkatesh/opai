/* OPAI motion — vanilla, no dependencies */
(()=>{
const RM=matchMedia('(prefers-reduced-motion:reduce)').matches,$=(s,r=document)=>[...r.querySelectorAll(s)];
if(RM)return;
const root=document.documentElement;

/* scroll progress + header hairline */
const bar=document.createElement('div');bar.id='fx-progress';document.body.append(bar);
const hdr=document.querySelector('header');
const onScroll=()=>{const h=root.scrollHeight-innerHeight;bar.style.transform=`scaleX(${h>0?scrollY/h:0})`;hdr&&hdr.classList.toggle('fx-scrolled',scrollY>8)};
addEventListener('scroll',onScroll,{passive:true});onScroll();

/* landing */
const hero=document.querySelector('.hero');
if(hero){
 root.classList.add('fx-on');
 // hero: ordered fade-up
 [...hero.querySelectorAll('.eyebrow,h1,.lead,.hero-actions,.hero-fine,.device')].forEach((n,i)=>{n.style.setProperty('--i',i);n.classList.add('fx-up')});
 // section reveal, light stagger among siblings
 const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}}),{threshold:.12,rootMargin:'0px 0px -5% 0px'});
 $('.section-head,.inside-cell,.persona,.step,.stat,.faq-item,.sw-workflow-header,.foot-row').forEach(n=>{
  if(n.closest('.hero'))return;n.style.setProperty('--d',Math.min([...n.parentElement.children].indexOf(n),5)*70+'ms');n.classList.add('fx-r');io.observe(n)});
 // stats count-up
 $('.stat .val,.stat .n').forEach(n=>{const m=n.textContent.match(/^(\D*)(\d+(?:\.\d+)?)(.*)$/);if(!m)return;
  new IntersectionObserver(([e],o)=>{if(!e.isIntersecting)return;o.disconnect();const t=+m[2],d=m[2].includes('.')?1:0,t0=performance.now();
   (function f(now){const k=Math.min(1,(now-t0)/1100);n.textContent=m[1]+(t*(1-Math.pow(1-k,3))).toFixed(d)+m[3];k<1&&requestAnimationFrame(f)})(t0)}).observe(n)});
}

/* app: animate only when the user switches tab, not on data refresh */
const view=document.getElementById('view');
if(view){
 let last='',q;
 const enter=()=>{const key=(document.querySelector('.nav button.on')||{}).textContent||'';if(key===last)return;last=key;
  $('.panel,.task,.card,.kpi,.stat',view).slice(0,10).forEach((n,i)=>{n.style.setProperty('--i',i);n.classList.remove('fx-s');void n.offsetWidth;n.classList.add('fx-s')})};
 new MutationObserver(()=>{cancelAnimationFrame(q);q=requestAnimationFrame(enter)}).observe(view,{childList:true});enter();
}
})();
