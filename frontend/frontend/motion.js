/* OPAI motion v2 — cursor spotlight, ripple, route sweep. No dependencies. */
(()=>{
if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
const bar=document.createElement('div');bar.id='fx-route';document.body.append(bar);
const sweep=()=>{bar.classList.remove('go');void bar.offsetWidth;bar.classList.add('go')};
/* spotlight follows the cursor on any card */
addEventListener('pointermove',e=>{
  const p=e.target.closest&&e.target.closest('.panel');if(!p)return;
  const r=p.getBoundingClientRect();
  p.style.setProperty('--mx',(e.clientX-r.left)+'px');p.style.setProperty('--my',(e.clientY-r.top)+'px');
},{passive:true});
/* ripple from the click point; sweep bar on tab change */
addEventListener('click',e=>{
  const b=e.target.closest&&e.target.closest('.btn,.send');
  if(b){const r=b.getBoundingClientRect(),s=Math.max(r.width,r.height)*2;
    const d=document.createElement('span');d.className='fx-rip';
    d.style.cssText=`width:${s}px;height:${s}px;left:${e.clientX-r.left-s/2}px;top:${e.clientY-r.top-s/2}px`;
    b.append(d);setTimeout(()=>d.remove(),650)}
  if(e.target.closest&&e.target.closest('.nav button'))sweep();
});
})();