<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OPA — your operating agent</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400..700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
/* =====================================================================
   OPA DESIGN SYSTEM  ·  "Personal AI" light skin
   Palette   cream #F6F4EE · deep green #134E48 · coral #EE7B5D
   Type      Newsreader (display) · Inter (body) · IBM Plex Mono (labels/data)
   The base rules below are the original system; the block at the very end
   of this <style> re-skins them to the light look.
   ===================================================================== */
:root{
  --bg:#14161B;
  --surface:#1B1E27;
  --surface-2:#242833;
 
  --ink:#D8D1BC;
  --ink-2:#8F8A76;
  --ink-3:#5F5A4A;
  --line:#262A35;
  --line-2:#38404F;
 
  --accent:#E2A73E;
  --accent-d:#F5C065;
  --accent-soft:#2E2410;
 
  --good:#5FA085;  --good-soft:#13291F;
  --warn:#D89A5C;  --warn-soft:#2E2410;
  --bad:#C96A52;   --bad-soft:#301810;
 
  --c-app:#6F93C4;
  --c-out:#D89A5C;
  --c-proj:#5FA085;
  --c-acad:#A480C4;
  --c-req:#E2A73E;
  --c-opp:#A39C86;
 
  --r-lg:10px; --r-md:8px; --r-sm:6px;
  --shadow-1:0 0 0 1px var(--line), 0 10px 30px -18px rgba(226,167,62,.18);
  --shadow-2:0 0 0 1px var(--line-2), 0 24px 60px -20px rgba(226,167,62,.28);
  --glow:0 0 14px rgba(226,167,62,.45);
  --display:'Bricolage Grotesque',system-ui,-apple-system,'Segoe UI',sans-serif;
  --body:'Figtree',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono',ui-monospace,'SF Mono',Menlo,monospace;
  color-scheme:dark;
}
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#EFE7D2; --surface:#FBF7EC; --surface-2:#E2D8BB;
    --ink:#2A2A22; --ink-2:#5A5A48; --ink-3:#A39C86;
    --line:#D5C9A6; --line-2:#C7B98E;
    --accent:#8A5F18; --accent-d:#6B4712; --accent-soft:#F7ECD5;
    --good:#3D6553; --good-soft:#DFEAE4;
    --warn:#8A5A28; --warn-soft:#F3E6D0;
    --bad:#8A3D2B;  --bad-soft:#F5E1DB;
    --c-app:#3E5C87; --c-out:#8A5A28; --c-proj:#3D6553; --c-acad:#614876; --c-req:#8A5F18; --c-opp:#6B6552;
    --shadow-1:0 1px 0 rgba(20,22,27,.06);
    --shadow-2:0 14px 34px -18px rgba(20,22,27,.28);
    --glow:none;
    color-scheme:light;
  }
}
:root[data-theme="light"]{
  --bg:#EFE7D2; --surface:#FBF7EC; --surface-2:#E2D8BB;
  --ink:#2A2A22; --ink-2:#5A5A48; --ink-3:#A39C86;
  --line:#D5C9A6; --line-2:#C7B98E;
  --accent:#8A5F18; --accent-d:#6B4712; --accent-soft:#F7ECD5;
  --good:#3D6553; --good-soft:#DFEAE4;
  --warn:#8A5A28; --warn-soft:#F3E6D0;
  --bad:#8A3D2B;  --bad-soft:#F5E1DB;
  --c-app:#3E5C87; --c-out:#8A5A28; --c-proj:#3D6553; --c-acad:#614876; --c-req:#8A5F18; --c-opp:#6B6552;
  --shadow-1:0 1px 0 rgba(20,22,27,.06);
  --shadow-2:0 14px 34px -18px rgba(20,22,27,.28);
  --glow:none;
  color-scheme:light;
}
 
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased;background:var(--bg);
  background-image:
    linear-gradient(rgba(226,167,62,.05) 1px,transparent 1px),
    linear-gradient(90deg,rgba(226,167,62,.05) 1px,transparent 1px),
    radial-gradient(ellipse 900px 460px at 50% -8%,rgba(226,167,62,.10),transparent 70%);
  background-size:34px 34px,34px 34px,100% 100%;
  background-attachment:fixed;
}
h1,h2,h3,h4,p{margin:0}
button,input,select,textarea{font:inherit;color:inherit}
button{cursor:pointer}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
::selection{background:var(--accent-soft);color:var(--accent-d)}
.ic{flex-shrink:0}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
 
/* ---------- Shell ---------- */
.app{display:grid;grid-template-columns:258px minmax(0,1fr);min-height:100vh}
.side{position:sticky;top:0;height:100vh;background:var(--surface);border-right:1px solid var(--line);
  display:flex;flex-direction:column;padding:20px 14px 16px;overflow-y:auto;z-index:40}
.brand{display:flex;align-items:center;gap:11px;padding:4px 8px 18px}
.brand-mark{width:36px;height:36px;border-radius:6px;background:radial-gradient(circle at 34% 28%,#FFF6E0 0%,var(--accent) 55%,#3A2A10 100%);
  display:grid;place-items:center;flex-shrink:0;box-shadow:0 0 14px rgba(226,167,62,.5)}
.brand-mark svg{display:block}
.brand b{font-family:var(--display);font-size:21px;font-weight:700;letter-spacing:-.02em;display:block;line-height:1.05}
.brand span{font-size:12px;color:var(--ink-3)}
 
.search-btn{display:flex;align-items:center;gap:9px;width:100%;margin:0 0 14px;padding:9px 11px;
  border:1px solid var(--line);border-radius:var(--r-sm);background:var(--bg);color:var(--ink-3);
  font-size:13.5px;text-align:left;transition:border-color .15s,color .15s}
.search-btn:hover{border-color:var(--line-2);color:var(--ink-2)}
.search-btn .kbd{margin-left:auto}
 
.nav{display:flex;flex-direction:column;gap:1px}
.nav-group{font-size:10.5px;font-family:var(--mono);letter-spacing:.14em;text-transform:uppercase;font-weight:600;color:var(--ink-3);padding:14px 10px 5px}
.nav-group:first-child{padding-top:0}
.nav button{display:flex;align-items:center;gap:10px;width:100%;padding:8px 10px;border:0;background:none;
  border-radius:var(--r-sm);color:var(--ink-2);font-weight:500;text-align:left;transition:background .12s,color .12s}
.nav button:hover{background:var(--bg);color:var(--ink)}
.nav button.on{background:var(--accent-soft);color:var(--accent-d);font-weight:650;box-shadow:inset 2px 0 0 var(--accent),0 0 12px -6px rgba(226,167,62,.7)}
.nav button .dot{width:7px;height:7px;border-radius:50%;background:var(--c);flex-shrink:0}
.nav .count{margin-left:auto;font-size:11.5px;font-weight:650;min-width:20px;text-align:center;
  padding:1px 6px;border-radius:999px;background:var(--surface-2);color:var(--ink-2)}
.nav button.on .count{background:#fff;color:var(--accent-d)}
:root[data-theme="dark"] .nav button.on .count{background:var(--surface)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .nav button.on .count{background:var(--surface)}}
.nav .count.alert{background:var(--warn-soft);color:var(--warn)}
 
.side-foot{margin-top:auto;padding-top:14px}
.conn{display:flex;gap:9px;align-items:flex-start;padding:11px;border:1px solid var(--line);
  border-radius:var(--r-sm);background:var(--bg);font-size:12px;color:var(--ink-2);line-height:1.45}
.conn i{width:7px;height:7px;border-radius:50%;background:var(--warn);margin-top:5px;flex-shrink:0;
  box-shadow:0 0 8px -1px var(--warn);animation:blip 1.8s ease-in-out infinite}
@keyframes blip{0%,100%{opacity:1}50%{opacity:.35}}
.conn b{display:block;color:var(--ink);font-weight:650;font-size:12.5px;font-family:var(--mono);letter-spacing:.04em;text-transform:uppercase;font-size:11px}
.kbd{display:inline-block;border:1px solid var(--line-2);border-bottom-width:2px;border-radius:5px;
  padding:0 5px;font-size:10.5px;font-family:var(--mono);background:var(--surface);color:var(--ink-2);line-height:1.6}
 
.topbar{display:none}
.scrim{display:none}
main{padding:38px 48px 110px;min-width:0;max-width:1220px;width:100%}
#view{animation:viewin .28s cubic-bezier(.2,.8,.2,1)}
@keyframes viewin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.scanline{position:fixed;left:0;right:0;height:120px;pointer-events:none;z-index:5;
  background:linear-gradient(rgba(226,167,62,0),rgba(226,167,62,.05),rgba(226,167,62,0));
  animation:sweep 9s linear infinite}
@keyframes sweep{0%{top:-120px}100%{top:100vh}}
@media (max-width:920px){.scanline{display:none}}
 
@media (max-width:920px){
  .app{grid-template-columns:1fr}
  .side{position:fixed;left:0;top:0;bottom:0;width:280px;transform:translateX(-104%);
    transition:transform .25s cubic-bezier(.2,.8,.2,1);box-shadow:var(--shadow-2)}
  body.nav-open .side{transform:none}
  body.nav-open .scrim{display:block;position:fixed;inset:0;background:rgba(15,17,24,.4);z-index:35}
  .topbar{display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:30;padding:12px 16px;
    background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
  .topbar b{font-family:var(--display);font-size:18px;letter-spacing:-.02em}
  main{padding:22px 16px 100px}
}
 
/* ---------- Headings ---------- */
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;flex-wrap:wrap;margin-bottom:26px}
.head h1{font-family:var(--display);font-size:32px;font-weight:700;letter-spacing:-.03em;line-height:1.08}
.head p{color:var(--ink-2);margin-top:7px;max-width:56ch;font-size:14.5px}
@media (max-width:600px){.head h1{font-size:26px}}
 
/* ---------- Buttons ---------- */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:10px 16px;border-radius:6px;
  border:1px solid var(--accent);background:var(--accent);color:#4A3410;font-weight:700;font-size:13.5px;
  box-shadow:0 0 16px -4px rgba(226,167,62,.7);
  transition:background .15s,transform .08s,box-shadow .15s;white-space:nowrap}
.btn:hover{background:var(--accent-d);border-color:var(--accent-d);box-shadow:0 0 22px -3px rgba(226,167,62,.9)}
.btn:active{transform:translateY(1px)}
.btn.soft{background:var(--accent-soft);color:var(--accent-d);border-color:transparent}
.btn.soft:hover{filter:brightness(.96)}
.btn.ghost{background:var(--surface);color:var(--ink);border-color:var(--line-2)}
.btn.ghost:hover{background:var(--bg)}
.btn.danger{background:var(--bad);border-color:var(--bad)}
.btn.danger:hover{filter:brightness(.92)}
.btn.sm{padding:6px 12px;font-size:12.5px;border-radius:6px}
.btn:disabled{opacity:.5;cursor:not-allowed}
.icon-btn{width:32px;height:32px;display:grid;place-items:center;border-radius:6px;border:0;
  background:transparent;color:var(--ink-3);transition:background .12s,color .12s;flex-shrink:0}
.icon-btn:hover{background:var(--bg);color:var(--ink)}
.icon-btn.del:hover{background:var(--bad-soft);color:var(--bad)}
 
/* ---------- Surfaces ---------- */
.panel{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow-1)}
.panel:before,.panel:after{content:"";position:absolute;width:10px;height:10px;border:1.5px solid var(--accent);opacity:.55;pointer-events:none}
.panel:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.panel:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.panel-h{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:16px 20px;border-bottom:1px solid var(--line)}
.panel-h h3{font-family:var(--mono);font-size:12.5px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-2)}
.panel-h span{font-size:12.5px;color:var(--ink-3)}
 
.rows>.row{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:center;padding:15px 20px;border-bottom:1px solid var(--line)}
.rows>.row:last-child{border-bottom:0}
.rows>.row.noicon{grid-template-columns:1fr auto}
.row-t{font-weight:650;font-size:14.5px}
.row-s{font-size:13.5px;color:var(--ink-2);margin-top:2px}
.row-m{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:8px}
.row-a{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
@media (max-width:680px){.rows>.row,.rows>.row.noicon{grid-template-columns:1fr}.row-a{justify-content:flex-start;margin-top:4px}}
 
.swatch{width:34px;height:34px;border-radius:6px;display:grid;place-items:center;flex-shrink:0;
  background:color-mix(in srgb,var(--c) 14%,var(--surface));color:var(--c)}
 
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;padding:2px 9px;border-radius:999px;
  background:var(--bg);color:var(--ink-2);font-weight:500;border:1px solid transparent}
.chip.warn{background:var(--warn-soft);color:var(--warn);font-weight:650}
.chip.bad{background:var(--bad-soft);color:var(--bad);font-weight:650}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 10px;border-radius:999px;
  font-weight:650;background:var(--bg);color:var(--ink-2)}
.pill:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.brand{background:var(--accent-soft);color:var(--accent-d)}
.pill.good{background:var(--good-soft);color:var(--good)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.pill.bad{background:var(--bad-soft);color:var(--bad)}
 
.meter{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2)}
.meter div{width:76px;height:6px;border-radius:99px;background:var(--line);overflow:hidden}
.meter i{display:block;height:100%;border-radius:99px;background:var(--accent)}
.meter.hi i{background:var(--good)}
 
.empty{padding:56px 24px;text-align:center;color:var(--ink-2)}
.empty h3{font-family:var(--display);font-size:19px;color:var(--ink);margin-bottom:6px;font-weight:650}
.empty p{max-width:42ch;margin:0 auto 18px}
.empty.plain{border:1.5px dashed var(--line-2);border-radius:var(--r-lg);background:transparent}
 
input[type=checkbox].ck{appearance:none;-webkit-appearance:none;width:21px;height:21px;border-radius:50%;
  border:2px solid var(--line-2);background:var(--surface);display:grid;place-items:center;cursor:pointer;
  transition:border-color .15s,background .15s;margin:0;flex-shrink:0}
input[type=checkbox].ck:hover{border-color:var(--accent)}
input[type=checkbox].ck:checked{background:var(--accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m5 12 4.5 4.5L19 7'/%3E%3C/svg%3E") center/12px no-repeat;border-color:var(--accent)}
input[type=checkbox].ck:checked:not(:disabled){animation:tick .26s cubic-bezier(.2,.8,.2,1)}
@keyframes tick{0%{transform:scale(.78)}55%{transform:scale(1.16)}100%{transform:scale(1)}}
 
/* ---------- Today / flight strip ---------- */
.hero{position:relative;padding:28px 30px 24px;margin-bottom:22px;background:var(--surface);border:1px solid var(--line);
  border-radius:6px;box-shadow:var(--shadow-1)}
.hero:before,.hero:after{content:"";position:absolute;width:14px;height:14px;border:1.5px solid var(--accent);opacity:.6;pointer-events:none}
.hero:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.hero:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.hero-top{display:flex;justify-content:space-between;align-items:flex-start;gap:20px}
.hero h1{font-family:var(--display);font-size:clamp(28px,4vw,44px);font-weight:700;letter-spacing:-.035em;line-height:1.03;
  text-shadow:0 0 24px rgba(226,167,62,.25)}
.hero .lead{margin-top:9px;color:var(--ink-2);font-size:15px;max-width:58ch}
 
.ring{position:relative;width:76px;height:76px;flex-shrink:0}
.ring span{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11.5px;font-family:var(--mono);color:var(--ink-3)}
.ring b{font-family:var(--mono);font-size:19px;font-weight:600;color:var(--ink);margin-right:1px}
.ring circle:last-child{transition:stroke-dasharray .6s cubic-bezier(.2,.8,.2,1);filter:drop-shadow(0 0 5px rgba(226,167,62,.65))}
@media (max-width:600px){.ring{width:58px;height:58px}.ring svg{width:58px;height:58px}.ring b{font-size:16px}}
 
.strip{margin-top:24px}
.strip-top{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:9px}
.strip-top b{font-family:var(--display);font-size:19px;color:var(--ink);font-weight:650;letter-spacing:-.01em}
.strip-top span{font-size:13px;color:var(--ink-2)}
.strip-bar{position:relative;display:flex;gap:3px;height:34px;padding-top:9px}
.strip-bar:before{content:"";position:absolute;top:0;left:0;right:0;height:1px;
  background-image:linear-gradient(to right,var(--line-2) 1px,transparent 1px);
  background-size:calc(100%/6) 100%}
.seg{position:relative;border-radius:6px;background:var(--c);min-width:6px;transform-origin:left;align-self:stretch;box-shadow:0 0 10px -1px var(--c)}
.seg.free{background:repeating-linear-gradient(135deg,var(--line) 0 6px,transparent 6px 12px);border:1px dashed var(--line-2)}
.strip-bar.anim .seg{animation:grow .7s cubic-bezier(.2,.8,.2,1) both;animation-delay:calc(var(--i)*65ms)}
@keyframes grow{from{transform:scaleX(0);opacity:0}to{transform:scaleX(1);opacity:1}}
.strip-ticks{display:flex;justify-content:space-between;font-size:10.5px;font-family:var(--mono);color:var(--ink-3);margin-top:4px}
.legend{display:flex;gap:15px;flex-wrap:wrap;margin-top:13px;font-size:12px;color:var(--ink-2)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:8px;height:8px;border-radius:2.5px;background:var(--c)}
 
.quick{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:24px;background:var(--line);
  border:1px solid var(--line);border-radius:8px;overflow:hidden}
.quick button{background:var(--surface);border:0;padding:14px 16px;text-align:left;transition:background .12s}
.quick button:hover{background:var(--accent-soft)}
.quick b{display:block;font-family:var(--mono);font-size:22px;font-weight:600;letter-spacing:-.01em;line-height:1.1}
.quick span{font-size:12.5px;color:var(--ink-2)}
@media (max-width:680px){.quick{grid-template-columns:1fr 1fr}.hero{padding:20px 18px}}
 
.two{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(0,1fr);gap:18px;align-items:start}
@media (max-width:1000px){.two{grid-template-columns:1fr}}
 
.plan-row{display:grid;grid-template-columns:auto auto 1fr auto auto;gap:13px;align-items:center;padding:13px 20px;border-bottom:1px solid var(--line)}
.plan-row:last-child{border-bottom:0}
.plan-ic{width:32px;height:32px;border-radius:6px;display:grid;place-items:center;
  background:color-mix(in srgb,var(--c) 14%,var(--surface));color:var(--c);flex-shrink:0}
.plan-name{font-weight:650;font-size:14px}
.plan-sub{font-size:12.5px;color:var(--ink-2)}
.plan-dur{font-size:12px;font-family:var(--mono);color:var(--ink-3);white-space:nowrap}
.plan-row.done .plan-name{text-decoration:line-through;color:var(--ink-3)}
.plan-row.done .plan-ic{background:var(--bg);color:var(--ink-3)}
 
.week-row{display:flex;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line);align-items:center}
.week-row:last-child{border-bottom:0}
.week-d{width:42px;text-align:center;flex-shrink:0;line-height:1.1}
.week-d b{display:block;font-family:var(--mono);font-size:19px;font-weight:600}
.week-d span{font-size:11px;color:var(--ink-3)}
.week-t{font-size:13.5px}
 
/* ---------- Board (Applications) ---------- */
.board{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(254px,1fr);gap:12px;overflow-x:auto;
  padding:2px 2px 10px;scroll-snap-type:x proximity}
.col{background:var(--surface-2);border-radius:8px;padding:9px;scroll-snap-align:start;min-height:200px;
  transition:outline-color .15s,background .15s}
.col.over{outline:2px dashed var(--accent);outline-offset:-4px}
.col-h{display:flex;align-items:center;justify-content:space-between;padding:5px 7px 11px;font-weight:650;font-size:13.5px}
.col-h span{font-weight:650;font-size:11.5px;color:var(--ink-2);background:var(--surface);border-radius:99px;padding:1px 8px}
.kcard{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:13px;margin-bottom:8px;box-shadow:var(--shadow-1);
  border-left:3px solid var(--c);cursor:grab}
.kcard.dragging{opacity:.4}
.kcard:after{content:"";position:absolute;top:-1px;right:-1px;width:8px;height:8px;border:1.5px solid var(--accent);opacity:.5;border-left:0;border-bottom:0;pointer-events:none}
.kcard-top{display:flex;justify-content:space-between;align-items:flex-start;gap:6px}
.k-title{font-weight:650;font-size:14px}
.k-sub{font-size:12.5px;color:var(--ink-2);margin-top:1px}
.k-note{font-size:12px;color:var(--ink-3);margin-top:8px;line-height:1.4}
.kcard .row-m{margin-bottom:0}
.kcard .btn{margin-top:11px;width:100%}
.col-empty{font-size:12.5px;color:var(--ink-3);text-align:center;padding:20px 8px}
 
/* ---------- Projects ---------- */
.grid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.proj{padding:19px}
.proj-h{display:flex;justify-content:space-between;gap:10px}
.proj h3{font-family:var(--display);font-size:18px;font-weight:650;letter-spacing:-.02em}
.proj .desc{font-size:13.5px;color:var(--ink-2);margin-top:3px}
.prog{height:6px;border-radius:99px;background:var(--line);margin:15px 0 4px;overflow:hidden}
.prog i{display:block;height:100%;background:var(--c-proj);border-radius:99px;transition:width .4s}
.prog-l{font-size:12px;color:var(--ink-3);margin-bottom:8px}
.task{display:flex;align-items:center;gap:10px;padding:7px 0}
.task label{flex:1;font-size:14px}
.task.done label{text-decoration:line-through;color:var(--ink-3)}
.task .icon-btn{width:26px;height:26px}
.addtask{display:flex;gap:8px;margin-top:9px}
.addtask input{flex:1}
 
/* ---------- Forms ---------- */
.fields{display:grid;grid-template-columns:1fr 1fr;gap:15px}
.field{grid-column:1/-1}
.field.half{grid-column:auto}
@media (max-width:540px){.field.half{grid-column:1/-1}}
.field label{display:block;font-size:13px;font-weight:650;margin-bottom:6px}
.field .hint{font-size:12px;color:var(--ink-3);margin-top:5px}
input[type=text],input[type=email],input[type=date],select,textarea,.addtask input{
  width:100%;padding:10px 12px;border:1px solid var(--line-2);border-radius:6px;background:var(--surface);
  transition:border-color .15s,box-shadow .15s}
textarea{resize:vertical;min-height:80px;line-height:1.5}
input:hover,select:hover,textarea:hover{border-color:var(--ink-3)}
input:focus,select:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-soft);outline:none}
.field.bad input,.field.bad textarea{border-color:var(--bad);box-shadow:0 0 0 4px var(--bad-soft)}
.form-panel{padding:22px;max-width:620px}
.data-actions{display:flex;gap:10px;flex-wrap:wrap}
 
/* ---------- Modal ---------- */
.overlay{position:fixed;inset:0;background:rgba(15,17,24,.45);backdrop-filter:blur(3px);display:none;
  align-items:flex-start;justify-content:center;padding:6vh 16px;overflow-y:auto;z-index:100}
.overlay.on{display:flex}
.dialog{position:relative;background:var(--surface);border:1px solid var(--line-2);border-radius:6px;width:100%;max-width:540px;padding:24px;
  box-shadow:var(--shadow-2);animation:pop .2s cubic-bezier(.2,.8,.2,1)}
@keyframes pop{from{transform:translateY(8px) scale(.98);opacity:0}to{transform:none;opacity:1}}
.dialog:before,.dialog:after{content:"";position:absolute;width:12px;height:12px;border:1.5px solid var(--accent);opacity:.55;pointer-events:none}
.dialog:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.dialog:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.dialog h3{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:-.02em;margin-bottom:16px}
.dialog .foot{display:flex;justify-content:flex-end;gap:10px;margin-top:20px;flex-wrap:wrap}
.mail{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:15px;font-size:13.5px;
  white-space:pre-wrap;max-height:290px;overflow-y:auto;margin:6px 0;line-height:1.55}
.mail-meta{font-size:13px;color:var(--ink-2);margin-bottom:4px}
.note{font-size:12.5px;color:var(--ink-2);background:var(--warn-soft);border-radius:8px;padding:10px 14px;margin-top:12px}
 
/* ---------- Command palette ---------- */
#palette{padding-top:11vh}
.pal{background:var(--surface);border-radius:6px;width:100%;max-width:600px;box-shadow:var(--shadow-2);
  overflow:hidden;animation:pop .16s cubic-bezier(.2,.8,.2,1)}
.pal-in{display:flex;align-items:center;gap:11px;padding:15px 18px;border-bottom:1px solid var(--line);color:var(--ink-3)}
.pal-in input{flex:1;border:0;outline:0;box-shadow:none;padding:2px 0;font-size:15.5px;color:var(--ink);background:transparent}
.pal-in input:focus{box-shadow:none}
.pal-list{max-height:min(50vh,410px);overflow-y:auto;padding:7px}
.pal-it{display:flex;align-items:center;gap:11px;width:100%;padding:9px 11px;border:0;border-radius:6px;
  background:none;text-align:left;color:var(--ink-2)}
.pal-it.sel{background:var(--accent-soft);color:var(--accent-d)}
.pal-t{flex:1;min-width:0;font-weight:600;color:var(--ink);font-size:14px}
.pal-it.sel .pal-t{color:var(--accent-d)}
.pal-t small{display:block;font-weight:400;font-size:12px;color:var(--ink-3)}
.pal-g{font-size:12px;color:var(--ink-3)}
.pal-empty{padding:32px 18px;text-align:center;color:var(--ink-2);font-size:14px}
.pal-foot{display:flex;gap:16px;padding:9px 18px;border-top:1px solid var(--line);font-size:12px;color:var(--ink-3);background:var(--bg)}
 
/* ---------- Focus timer ---------- */
.focus{position:fixed;right:22px;bottom:22px;width:290px;background:var(--surface);border:1px solid var(--line);
  border-radius:6px;box-shadow:var(--shadow-2);padding:16px 18px;z-index:90;display:none}
.focus.on{display:block;animation:pop .2s cubic-bezier(.2,.8,.2,1)}
.focus:before,.focus:after{content:"";position:absolute;width:11px;height:11px;border:1.5px solid var(--accent);opacity:.55;pointer-events:none}
.focus:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.focus:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.f-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.f-name{font-weight:650;font-size:13.5px;line-height:1.35}
.f-label{font-size:12px;color:var(--ink-3);margin-bottom:2px}
.f-time{font-family:var(--mono);font-size:38px;font-weight:600;letter-spacing:-.01em;line-height:1.1;
  margin:5px 0 8px;font-variant-numeric:tabular-nums}
.f-bar{height:6px;border-radius:99px;background:var(--line);overflow:hidden}
.f-bar i{display:block;height:100%;background:var(--accent);border-radius:99px;transition:width 1s linear}
.f-act{display:flex;gap:8px;margin-top:13px}
.f-act .btn{flex:1}
@media (max-width:600px){.focus{left:12px;right:12px;bottom:12px;width:auto}}
 
/* ---------- Toast ---------- */
.toast{position:fixed;bottom:22px;left:50%;transform:translate(-50%,14px);background:var(--ink);color:var(--bg);
  padding:11px 18px;border-radius:8px;font-size:13.5px;font-weight:500;opacity:0;pointer-events:none;
  transition:.2s;z-index:200;max-width:88vw;box-shadow:var(--shadow-2)}
.toast.on{opacity:1;transform:translate(-50%,0);pointer-events:auto}
.toast.err{background:var(--bad);color:#fff}
.toast-act{margin-left:15px;background:none;border:0;color:var(--accent-soft);font-weight:700;padding:0}
.toast-act:hover{text-decoration:underline}
 
/* ---------- Resume check ---------- */
.resume-box{min-height:210px}
.skill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;
  border:1px solid var(--line-2);background:var(--surface);font-size:13px;margin:0 6px 8px 0;transition:.12s}
button.skill:hover{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-d)}
.skill.added{background:var(--good-soft);border-color:transparent;color:var(--good);font-weight:600}
.notes{margin:8px 0 0;padding-left:19px;color:var(--ink-2)}
.notes li{margin-bottom:6px;font-size:13.5px}
 
/* ---------- History ---------- */
.tl{position:relative;padding-left:24px;max-width:700px}
.tl:before{content:"";position:absolute;left:4px;top:8px;bottom:8px;width:2px;background:var(--line)}
.tl-day{position:relative;margin-bottom:24px}
.tl-day:before{content:"";position:absolute;left:-24px;top:6px;width:11px;height:11px;border-radius:50%;
  background:var(--accent);border:3px solid var(--bg)}
.tl-day h3{font-family:var(--display);font-size:18px;font-weight:650;margin-bottom:7px}
.tl-e{display:flex;gap:13px;padding:5px 0;color:var(--ink-2);font-size:13.5px}
.tl-e time{width:58px;flex-shrink:0;color:var(--ink-3);font-size:12px;padding-top:1px}
 
/* ---------- JARVIS ---------- */
.jv{display:grid;grid-template-columns:minmax(0,1fr) 278px;gap:18px;align-items:start}
@media (max-width:1040px){.jv{grid-template-columns:1fr}.jv-ctx{display:none}}
.jv-main{display:flex;flex-direction:column;height:calc(100vh - 160px);min-height:540px;overflow:hidden}
.jv-top{display:flex;align-items:center;gap:11px;padding:14px 18px;border-bottom:1px solid var(--line)}
.orb{width:34px;height:34px;border-radius:50%;flex-shrink:0;
  background:radial-gradient(circle at 32% 28%,#fff 0 6%,#FFE9B8 22%,var(--accent) 60%,#3A2A10 100%);
  box-shadow:0 0 16px rgba(226,167,62,.55),0 0 3px rgba(255,255,255,.4);
  animation:orbpulse 2.6s ease-in-out infinite}
@keyframes orbpulse{0%,100%{box-shadow:0 0 12px rgba(226,167,62,.4),0 0 3px rgba(255,255,255,.35)}50%{box-shadow:0 0 22px rgba(226,167,62,.75),0 0 5px rgba(255,255,255,.55)}}
.jv-top b{font-family:var(--display);font-size:16px;display:block;line-height:1.1}
.jv-top span{font-size:12px;color:var(--ink-3)}
.jv-top .btn{margin-left:auto}
.msgs{flex:1;overflow-y:auto;padding:22px 20px;display:flex;flex-direction:column;gap:13px}
.welcome{margin:auto;text-align:center;max-width:520px}
.welcome h2{font-family:var(--display);font-size:32px;font-weight:700;letter-spacing:-.03em;line-height:1.08}
.welcome p{color:var(--ink-2);margin:9px 0 22px;font-size:14.5px}
.prompts{display:grid;grid-template-columns:1fr 1fr;gap:9px}
@media (max-width:560px){.prompts{grid-template-columns:1fr}}
.prompts button{padding:12px 14px;text-align:left;background:var(--surface);border:1px solid var(--line-2);
  border-radius:8px;font-weight:550;font-size:13.5px;transition:.12s}
.prompts button:hover{border-color:var(--accent);background:var(--accent-soft);color:var(--accent-d)}
.m{display:flex;max-width:100%}
.m.you{justify-content:flex-end}
.bubble{max-width:min(82%,620px);padding:10px 14px;border-radius:10px;font-size:14px;line-height:1.55;
  background:var(--bg);border-bottom-left-radius:5px}
.m.you .bubble{background:var(--accent);color:#4A3410;border-bottom-left-radius:17px;border-bottom-right-radius:5px}
.bubble strong{font-weight:700}
.typing{display:inline-flex;gap:4px;padding:4px 0}
.typing i{width:6px;height:6px;border-radius:50%;background:var(--ink-3);animation:blink 1s infinite}
.typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
@keyframes blink{0%,60%,100%{opacity:.25}30%{opacity:1}}
.composer{padding:13px 15px;border-top:1px solid var(--line)}
.cbox{display:flex;align-items:flex-end;gap:8px;padding:7px 7px 7px 13px;border:1px solid var(--line-2);
  border-radius:8px;background:var(--surface)}
.cbox:focus-within{border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-soft)}
.cbox textarea{flex:1;border:0;outline:0;resize:none;min-height:22px;max-height:126px;padding:5px 0;
  box-shadow:none;background:transparent}
.cbox textarea:focus{box-shadow:none}
.send{width:36px;height:36px;border-radius:6px;border:0;background:var(--accent);color:#4A3410;display:grid;place-items:center;flex-shrink:0;box-shadow:0 0 14px -3px rgba(226,167,62,.75)}
.send:hover{background:var(--accent-d)}
.jv-ctx{padding:17px}
.jv-ctx h3{font-family:var(--display);font-size:15px;font-weight:650;margin-bottom:9px}
.ctx-row{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--line);font-size:13.5px;color:var(--ink-2)}
.ctx-row:last-of-type{border-bottom:0}
.ctx-row b{color:var(--ink);font-family:var(--mono);font-weight:600}
.ctx-note{font-size:12px;color:var(--ink-3);margin-top:11px;line-height:1.5}
 
@media (prefers-reduced-motion:reduce){
  *,*:before,*:after{animation-duration:.01ms!important;animation-delay:0ms!important;
    transition-duration:.01ms!important;scroll-behavior:auto!important}
}
 
/* ---------- Floating calendar ---------- */
main{padding-top:78px}
.cal-fab{position:fixed;top:16px;right:22px;z-index:60;display:flex;align-items:center;gap:10px;padding:7px 16px 7px 7px;
  border-radius:999px;border:1px solid var(--line-2);background:color-mix(in srgb,var(--surface) 82%,transparent);
  backdrop-filter:blur(12px);box-shadow:var(--shadow-2),var(--glow);color:var(--ink);transition:transform .15s,box-shadow .15s}
.cal-fab:hover{transform:translateY(-2px)}
.cal-badge{width:38px;height:38px;border-radius:50%;background:var(--accent);color:#4A3410;display:grid;place-items:center;
  font-family:var(--mono);font-weight:700;font-size:16px;box-shadow:var(--glow)}
.cal-txt{text-align:left;line-height:1.15}
.cal-txt b{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase}
.cal-txt span{font-size:12px;color:var(--ink-2)}
.cal-pop{position:fixed;top:74px;right:22px;width:420px;max-height:calc(100vh - 96px);overflow-y:auto;z-index:60;
  background:color-mix(in srgb,var(--surface) 94%,transparent);backdrop-filter:blur(14px);border:1px solid var(--line-2);border-radius:12px;
  box-shadow:var(--shadow-2),var(--glow);padding:18px;display:none}
.cal-pop.on{display:block;animation:pop .2s cubic-bezier(.2,.8,.2,1)}
.cal-pop:before,.cal-pop:after{content:"";position:absolute;width:14px;height:14px;border:1.5px solid var(--accent);opacity:.7;pointer-events:none}
.cal-pop:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.cal-pop:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.cal-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:14px}
.cal-mo{font-family:var(--display);font-size:26px;font-weight:700;letter-spacing:-.035em;line-height:1}
.cal-yr{font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--ink-3);margin-top:5px}
.cal-ctl{display:flex;gap:4px;align-items:center}
.cal-ctl .icon-btn{font-size:18px;font-weight:700;border:1px solid var(--line)}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
.cal-wd{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--ink-3);text-align:center;padding:2px 0 5px;text-transform:uppercase}
.cal-wd.we{color:var(--c-acad)}
.cal-d{position:relative;aspect-ratio:1/1.02;border:1px solid var(--line);border-radius:8px;
  background:color-mix(in srgb,var(--accent) calc(var(--h,0)*9%),var(--surface-2));color:var(--ink-2);
  font-family:var(--mono);font-size:13px;font-weight:600;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;
  transition:transform .12s,border-color .12s,background .12s}
.cal-d:hover{transform:translateY(-1px);border-color:var(--accent);color:var(--ink)}
.cal-d.we{color:var(--c-acad)}
.cal-d.past{opacity:.72}
.cal-d.today{border-color:var(--accent);color:var(--ink);box-shadow:0 0 0 1px var(--accent),0 0 14px -2px var(--accent)}
.cal-d.sel{background:var(--accent);border-color:var(--accent);color:#4A3410;opacity:1}
.cal-d em{display:flex;gap:2px;height:5px;font-style:normal}
.cal-d em i{width:5px;height:5px;border-radius:50%}
.cal-d.sel em i{box-shadow:0 0 0 1px #4A3410}
.cal-d s{position:absolute;top:3px;right:4px;width:5px;height:5px;border-radius:50%;background:var(--good);text-decoration:none;box-shadow:0 0 6px var(--good)}
.cal-lg{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:12px;font-size:11.5px;color:var(--ink-2)}
.cal-lg span{display:inline-flex;align-items:center;gap:6px}
.cal-lg i{width:8px;height:8px;border-radius:2.5px;background:var(--c)}
.cal-day{margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}
.cal-dh{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.cal-dh b{font-family:var(--display);font-size:18px;font-weight:650;letter-spacing:-.02em}
.cal-rel{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;padding:3px 9px;border-radius:999px;background:var(--accent-soft);color:var(--accent-d);border:1px solid var(--line-2)}
.cal-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:12px 0 4px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.cal-stats div{background:var(--surface);padding:9px 12px}
.cal-stats b{display:block;font-family:var(--mono);font-size:18px;font-weight:600;line-height:1.1}
.cal-stats span{font-size:11.5px;color:var(--ink-2)}
.cal-sec{margin-top:14px}
.cal-sec h5{display:flex;justify-content:space-between;font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;margin:0 0 6px}
.cal-it{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;padding:8px 10px;margin-bottom:5px;border-radius:8px;
  background:var(--bg);border:1px solid var(--line);border-left:3px solid var(--c)}
.cal-it i{width:8px;height:8px;border-radius:50%;background:var(--c);box-shadow:0 0 8px -1px var(--c)}
.cal-it b{display:block;font-size:13px;font-weight:650;line-height:1.3}
.cal-it small{display:block;font-size:11.5px;color:var(--ink-3)}
.cal-r{font-family:var(--mono);font-size:11px;color:var(--ink-2);white-space:nowrap}
.cal-it.done b{text-decoration:line-through;color:var(--ink-3)}
.cal-it.done .cal-r{color:var(--good)}
.cal-log{display:flex;gap:10px;padding:4px 2px;font-size:12.5px;color:var(--ink-2)}
.cal-log time{font-family:var(--mono);font-size:11px;color:var(--ink-3);width:54px;flex-shrink:0;padding-top:1px}
.cal-none{font-size:12.5px;color:var(--ink-3);padding:6px 2px}
.cal-ai{margin-top:16px;padding:13px 15px;border-radius:10px;background:var(--accent-soft);border:1px solid var(--line-2);font-size:12.5px;color:var(--ink-2);line-height:1.55}
.cal-ai b{display:flex;align-items:center;gap:7px;color:var(--accent-d);font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px}
.cal-ai p{margin:0}
.ai-note{display:inline-flex;align-items:center;gap:8px;margin-top:14px;padding:7px 12px;border-radius:999px;font-size:12.5px;
  background:var(--accent-soft);color:var(--accent-d);border:1px solid var(--line-2)}
@media (max-width:920px){
  main{padding-top:22px}
  .cal-fab{top:8px;right:56px;padding:4px}
  .cal-txt{display:none}
  .cal-badge{width:34px;height:34px}
  .cal-pop{top:58px;right:10px;left:10px;width:auto;padding:14px}
}
 
/* ---- Login gate + account ---- */
.gate{position:fixed;inset:0;z-index:1000;background:var(--bg);display:none;align-items:center;justify-content:center;padding:20px}
.gate.on{display:flex}
.gate-card{position:relative;width:100%;max-width:400px;background:var(--surface);border:1px solid var(--line-2);border-radius:6px;padding:32px 28px;text-align:center}
.gate-card:before,.gate-card:after{content:"";position:absolute;width:12px;height:12px;border:1.5px solid var(--accent);opacity:.55}
.gate-card:before{top:-1px;left:-1px;border-right:0;border-bottom:0}
.gate-card:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.gate-card .brand-mark{margin:0 auto 16px}
.gate-card h1{font-family:var(--display);font-size:26px;font-weight:700;letter-spacing:-.02em;margin-bottom:6px}
.gate-card p{color:var(--ink-2);font-size:13.5px;margin-bottom:22px}
.gate-card .btn{width:100%;margin-bottom:10px;padding:12px 16px}
.gate-err{color:var(--bad);font-size:12.5px;min-height:18px;margin-top:4px}
.gate-fine{color:var(--ink-3);font-size:11.5px;margin-top:14px}
.userchip{display:flex;gap:10px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:var(--r-sm);margin-bottom:10px}
.userchip .av{width:30px;height:30px;border-radius:50%;background:var(--accent-soft);color:var(--accent-d);display:grid;place-items:center;font-weight:700;font-size:13px;flex-shrink:0;overflow:hidden}
.userchip .av img{width:100%;height:100%;object-fit:cover}
.userchip b{display:block;font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px}
.userchip span{display:block;font-size:11.5px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px}
.userchip .icon-btn{margin-left:auto}
 
/* =====================================================================
   "PERSONAL AI" LIGHT SKIN — overrides everything above
   ===================================================================== */
html:root:root, html:root:root[data-theme]{
  --bg:#F6F4EE; --surface:#FDFCF9; --surface-2:#EFEDE3;
  --ink:#1E2A28; --ink-2:#5E6A66; --ink-3:#8F9894;
  --line:#E7E4D9; --line-2:#D8D4C6;
  --accent:#EE7B5D; --accent-d:#D9613F; --accent-soft:#FCE4DB;
  --good:#1B5A50; --good-soft:#E0EBE5;
  --warn:#E0873A; --warn-soft:#FBEBD9;
  --bad:#D9613F; --bad-soft:#FCE4DB;
  --c-app:#1B5A50; --c-out:#EE7B5D; --c-proj:#2F7A6B; --c-acad:#8A7BB0; --c-req:#E0873A; --c-opp:#8F9894;
  --side:#134E48;
  --shadow-1:none; --shadow-2:0 12px 32px -16px rgba(19,78,72,.25); --glow:none;
  --display:'Newsreader',Georgia,serif;
  --body:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,'SF Mono',Menlo,monospace;
  color-scheme:light;
}
body{background:var(--bg);background-image:none;font-size:14px}
.scanline{display:none}
.panel:before,.panel:after,.hero:before,.hero:after,.dialog:before,.dialog:after,
.cal-pop:before,.cal-pop:after,.focus:before,.focus:after,.gate-card:before,.gate-card:after,.kcard:after{display:none}
 
/* type */
.head h1,.hero h1,.welcome h2{font-weight:500;letter-spacing:-.02em;text-shadow:none}
.panel-h{border-bottom:0;padding:18px 20px 8px}
.panel-h h3{font-family:var(--display);font-size:18px;font-weight:600;letter-spacing:0;text-transform:none;color:var(--ink)}
.panel{border-radius:12px;box-shadow:none}
 
/* buttons */
.btn{color:#fff;border-radius:8px;box-shadow:none}
.btn:hover{box-shadow:none}
.btn.soft{color:var(--accent-d)}
.btn.ghost{color:var(--ink)}
.m.you .bubble,.send,.cal-badge,.cal-d.sel{color:#fff;box-shadow:none}
 
/* sidebar */
.side{background:var(--side);border-right:0;color:#CFE0DB}
.brand-mark{background:var(--accent);border-radius:6px;box-shadow:none}
.brand b{color:#fff;font-size:18px;font-weight:600}
.brand span{font-family:var(--mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:#7FA79E}
.search-btn{display:none}
.nav-group{color:#6E9A91}
.nav button{color:#BFD4CE;border-radius:6px;font-size:13px}
.nav button:hover{background:rgba(255,255,255,.07);color:#fff}
.nav button.on{background:var(--accent);color:#fff;box-shadow:none;font-weight:600}
.nav .count{background:rgba(255,255,255,.12);color:#DCEBE7}
html:root .nav button.on .count{background:rgba(255,255,255,.25);color:#fff}
.nav .count.alert{background:var(--accent);color:#fff}
.conn{background:rgba(255,255,255,.06);border-color:rgba(255,255,255,.1);color:#9FBFB7}
.conn b{color:#6FD1A6}
.conn i{background:#4FD08F;box-shadow:none;animation:none}
.side .kbd{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.18);color:#BFD4CE}
.userchip{border-color:rgba(255,255,255,.12)}
.userchip b{color:#fff}
.userchip span{color:#8FB3AA}
.userchip .icon-btn{color:#BFD4CE}
.userchip .icon-btn:hover{background:rgba(255,255,255,.1);color:#fff}
 
/* header bar */
.hdr{display:none}
@media (min-width:921px){
  .hdr{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:14px;height:64px;padding:0 28px 0 0;
    background:var(--surface);border-bottom:1px solid var(--line)}
  .hdr-search{display:flex;align-items:center;gap:10px;flex:1;max-width:520px;height:100%;padding:0 22px;border:0;
    background:var(--good-soft);color:var(--ink-3);font-size:13px;text-align:left}
  .hdr-search .kbd{margin-left:auto}
  .hdr-sp{flex:1}
  .hdr-user{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:500}
  .hdr-av{width:32px;height:32px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-weight:600;font-size:13px}
  main{padding:32px 36px 90px;max-width:1280px}
  .cal-fab{top:15px;right:250px;padding:4px;background:var(--surface);backdrop-filter:none;box-shadow:none}
  .cal-txt{display:none}
  .cal-badge{width:32px;height:32px;font-size:14px}
  .cal-pop{top:72px}
}
 
/* Home */
.hm-top{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap;margin-bottom:22px}
.hm-eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:12px}
.hm-top h1{font-family:var(--display);font-weight:500;font-size:clamp(34px,4.2vw,50px);letter-spacing:-.02em;line-height:1.08}
.hm-top p{color:var(--ink-2);font-size:14px;max-width:44ch;margin-top:10px}
.hm-btns{display:flex;gap:10px}
.hm-btns .btn.ghost{background:var(--good-soft);border-color:transparent}
.hm-plan{padding:0 20px 20px;margin-bottom:18px}
.hm-plan .panel-h{padding:18px 0 14px}
.hm-link{border:0;background:none;color:var(--accent-d);font-size:12.5px;font-weight:500;padding:0}
.hm-link:hover{text-decoration:underline}
.hm-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.hm-card{text-align:left;border:0;border-radius:8px;padding:14px 16px 16px;background:var(--good-soft);transition:transform .12s;color:var(--ink)}
.hm-card:first-child{background:var(--accent-soft)}
.hm-card:hover{transform:translateY(-1px)}
.hm-card-t{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;font-family:var(--mono);font-size:11px;color:var(--ink-3)}
.hm-card:first-child .n{color:var(--accent-d)}
.hm-tag{font-family:var(--mono);font-size:10px;padding:2px 9px;border-radius:999px;background:rgba(255,255,255,.7);color:var(--ink-2)}
.hm-card:first-child .hm-tag{background:var(--warn);color:#fff}
.hm-card b{display:block;font-size:14px;font-weight:600;margin-bottom:6px}
.hm-card small{font-family:var(--mono);font-size:10.5px;color:var(--ink-2)}
.hm-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;align-items:start}
.hm-col{display:flex;flex-direction:column;gap:18px;min-width:0}
.hm-list{padding:2px 20px 18px}
.hm-li{display:flex;gap:12px;align-items:flex-start;padding:8px 0}
.hm-li i{width:6px;height:6px;border-radius:50%;background:var(--good);margin-top:7px;flex-shrink:0}
.hm-li i.hot{background:var(--accent)}
.hm-li b{display:block;font-size:13px;font-weight:600}
.hm-li small{display:block;font-size:11.5px;color:var(--ink-3);margin-top:1px}
.hm-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:4px 20px 20px}
.hm-stat{background:#E7EAE2;border-radius:8px;padding:10px 12px}
.hm-stat b{display:block;font-family:var(--display);font-size:26px;font-weight:500;line-height:1.1}
.hm-stat span{font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;color:var(--ink-3)}
.hm-stat.hot{background:var(--accent-soft)}
.hm-stat.hot b{color:var(--accent-d)}
.hm-stat.dark{background:var(--good)}
.hm-stat.dark b,.hm-stat.dark span{color:#fff}
.hm-wk{display:flex;justify-content:space-between;align-items:center;padding:7px 0;font-size:12px;color:var(--ink-2)}
.hm-bar{display:block;height:3px;border-radius:3px;background:var(--good)}
.hm-bar.hot{background:var(--accent)}
.hm-ins{background:var(--accent-soft);border:1px solid #F3CFC2;border-left:3px solid var(--accent);border-radius:12px;padding:16px 18px}
.hm-ins h3{display:flex;justify-content:space-between;align-items:center;font-family:var(--display);font-size:17px;font-weight:600;margin-bottom:8px}
.hm-ins h3 i{width:7px;height:7px;border-radius:50%;background:var(--accent)}
.hm-ins p{font-size:12.5px;color:var(--ink-2);line-height:1.55}
@media (max-width:1100px){.hm-grid{grid-template-columns:1fr 1fr}}
@media (max-width:700px){.hm-grid,.hm-cards{grid-template-columns:1fr}}
</style>
</head>
<body>
 
<div class="gate" id="gate" role="dialog" aria-modal="true" aria-label="Sign in">
  <div class="gate-card">
    <div class="brand-mark"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 1.9"/></svg></div>
    <h1>Welcome to OPA</h1>
    <p>Sign in to keep your own workspace and send approved emails from your Gmail.</p>
    <button class="btn" id="gate-google" onclick="gateGoogle()"><svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.3l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.4-4.8 7.1l7.6 5.9c4.4-4.1 7-10.1 7-17.5z"/><path fill="#FBBC05" d="M10.5 28.6c-.5-1.5-.8-3-.8-4.6s.3-3.1.8-4.6l-7.9-6.1C.9 16.6 0 20.2 0 24s.9 7.4 2.6 10.7l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.6-5.9c-2.1 1.4-4.9 2.3-8.3 2.3-6.3 0-11.6-4.1-13.5-9.9l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg>Continue with Google</button>
    <button class="btn ghost" onclick="gateGuest()">Continue as guest</button>
    <div class="gate-err" id="gate-err" role="alert"></div>
    <div class="gate-fine" id="gate-fine"></div>
  </div>
</div>
<div class="app">
  <aside class="side" id="side" aria-label="Main navigation">
    <div class="brand">
      <div class="brand-mark"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 1.9"/></svg></div>
      <div><b>OPA</b><span>Operating agent</span></div>
    </div>
    <button class="search-btn" onclick="openPalette()" aria-label="Search or jump to">
      <svg class="ic" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      Search or jump to <span class="kbd">Ctrl K</span>
    </button>
    <nav class="nav" id="nav"></nav>
    <div class="side-foot">
      <div class="userchip" id="userchip" style="display:none"></div>
      <div class="conn"><i></i><div><b>Demo data on this device</b>The backend is switched off for now. <span class="kbd">Ctrl K</span> searches, <span class="kbd">Ctrl J</span> opens JARVIS.</div></div>
    </div>
  </aside>
  <div class="scrim" id="scrim"></div>
 
  <div>
    <div class="topbar">
      <button class="icon-btn" id="menu-btn" aria-label="Open menu"></button>
      <b>OPA</b>
      <button class="icon-btn" style="margin-left:auto" onclick="openPalette()" aria-label="Search">
        <svg class="ic" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      </button>
    </div>
    <div class="hdr">
      <button class="hdr-search" onclick="openPalette()" aria-label="Search">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <span>Search tasks, companies, jobs, notes…</span><span class="kbd">Ctrl K</span>
      </button>
      <span class="hdr-sp"></span>
      <button class="icon-btn" onclick="switchTab('outbox')" aria-label="Notifications" title="Outbox">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>
      </button>
      <div class="hdr-user"><span class="hdr-av" id="hdr-av">A</span><b id="hdr-name">You</b></div>
    </div>
    <main id="view" tabindex="-1"></main>
  </div>
</div>
 
<button class="cal-fab" id="cal-fab" onclick="calToggle()" aria-label="Open calendar" aria-expanded="false"></button>
<div class="cal-pop" id="cal-pop" role="dialog" aria-label="Calendar"></div>
<div class="scanline"></div>
<div class="overlay" id="overlay"><div class="dialog" id="dialog" role="dialog" aria-modal="true"></div></div>
<div class="overlay" id="palette"><div class="pal" role="dialog" aria-modal="true" aria-label="Search and commands">
  <div class="pal-in">
    <svg class="ic" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="pal-q" type="text" placeholder="Search records, jump to a tab, or create something" autocomplete="off" aria-label="Search">
  </div>
  <div class="pal-list" id="pal-list" role="listbox"></div>
  <div class="pal-foot"><span><span class="kbd">↑</span> <span class="kbd">↓</span> move</span><span><span class="kbd">Enter</span> open</span><span><span class="kbd">Esc</span> close</span></div>
</div></div>
<div class="focus" id="focus" role="region" aria-label="Focus timer"></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
 
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>
<script>
/* =====================================================================
   BACKEND — DISABLED FOR NOW
   ---------------------------------------------------------------------
   The whole app currently runs on local demo data through the `S` state
   object and the plain helper functions below (save/upsert/remove).
   When the real backend is ready, uncomment this client and swap the
   local read/writes for the matching calls. Nothing here runs today.
 
   const LS_BASE = 'opa_api_base';
   const getBase = () => localStorage.getItem(LS_BASE) || 'http://localhost:8000';
 
   async function api(path, opts = {}) {
     const res = await fetch(getBase() + path, {
       credentials: 'include',
       headers: opts.body ? { 'Content-Type': 'application/json' } : {},
       ...opts,
     });
     if (res.status === 401) throw new Error('unauthenticated');
     if (!res.ok) {
       let detail = '';
       try { detail = (await res.json()).detail || ''; } catch (e) {}
       throw new Error(res.status + ' ' + res.statusText + (detail ? ' - ' + detail : ''));
     }
     if (res.status === 204) return null;
     const text = await res.text();
     return text ? JSON.parse(text) : null;
   }
   const GET   = (p)    => api(p);
   const POST  = (p, b) => api(p, { method: 'POST',  body: b !== undefined ? JSON.stringify(b) : undefined });
   const PATCH = (p, b) => api(p, { method: 'PATCH', body: JSON.stringify(b) });
   const DEL   = (p)    => api(p, { method: 'DELETE' });
 
   Endpoints the UI is built to call once the backend exists:
     POST /v1/auth/dev-login?email=...      POST /v1/auth/logout
     GET|PATCH /v1/profile                  GET /v1/plan/today
     GET|POST /v1/applications              PATCH|DELETE /v1/applications/:id
     GET|POST /v1/opportunities             POST /v1/opportunities/:id/convert | /dismiss
     GET|POST /v1/contacts                  POST /v1/drafts/outreach {contact_id}
     GET|POST /v1/projects                  POST /v1/projects/:id/tasks   PATCH|DELETE /v1/tasks/:id
     GET|POST /v1/academics                 GET|POST /v1/requests   POST /v1/drafts/proposal {request_id}
     GET /v1/outbox                         POST /v1/outbox/:id/approve | /reject
     POST /v1/resume/analyze {text}         GET /v1/history
     POST /v1/jarvis/chat {messages} -> {reply}
   ===================================================================== */
 
/* ================= 1. UTILITIES ================= */
const $ = (id) => document.getElementById(id);
const esc = (s) => (s == null ? '' : String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const escA = (s) => esc(s).replace(/"/g,'&quot;');
const uid = () => 'x' + Math.random().toString(36).slice(2, 9);
const pad = (n) => String(n).padStart(2, '0');
const iso = (off = 0) => { const d = new Date(); d.setDate(d.getDate() + off); return d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()); };
const fmtDate = (d) => d ? new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';
const daysUntil = (d) => { if (!d) return 999; const t = new Date(d + 'T00:00:00'); const n = new Date(); n.setHours(0,0,0,0); return Math.round((t - n) / 86400000); };
const fmtMins = (m) => { m = Math.round(m || 0); if (m < 60) return m + 'm'; const h = Math.floor(m/60), r = m % 60; return r ? h + 'h ' + r + 'm' : h + 'h'; };
const fmtDue = (d) => { const n = daysUntil(d); if (n < 0) return 'Overdue by ' + (-n) + 'd'; if (n === 0) return 'Due today'; if (n === 1) return 'Due tomorrow'; if (n <= 6) return 'Due in ' + n + ' days'; return 'Due ' + fmtDate(d); };
const dueTone = (d, status) => { if (!d || ['Offer','Rejected','Applied'].includes(status)) return ''; const n = daysUntil(d); return n < 0 ? 'bad' : n <= 2 ? 'warn' : ''; };
const splitList = (s) => (s || '').split(',').map(x => x.trim()).filter(Boolean);
 
const IC = {
  spark:'<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/><path d="M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7L19 16z"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  brief:'<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5.5A1.5 1.5 0 0 1 9.5 4h5A1.5 1.5 0 0 1 16 5.5V7"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  mail:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/>',
  book:'<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H14v15H5.5A1.5 1.5 0 0 1 4 17.5v-12z"/><path d="M14 4h4.5A1.5 1.5 0 0 1 20 5.5v12a1.5 1.5 0 0 1-1.5 1.5H14"/>',
  chat:'<path d="M4 5h16v11H9l-5 4V5z"/>',
  send:'<path d="M3 11 21 3l-8 18-2.5-7.5L3 11z"/>',
  file:'<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M9 12h6M9 16h6M9 8h3"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  user:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1.3-3.6 4-5 7-5s5.7 1.4 7 5"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  check:'<path d="m5 12 4.5 4.5L19 7"/>',
  edit:'<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>',
  trash:'<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
  up:'<path d="M12 19V5M5 12l7-7 7 7"/>',
  x:'<path d="M6 6l12 12M18 6 6 18"/>',
  play:'<path d="M8 5v14l11-7z"/>',
  grad:'<path d="M2 9.5 12 5l10 4.5-10 4.5-10-4.5z"/><path d="M6 12v4.5c0 1.2 2.7 2.5 6 2.5s6-1.3 6-2.5V12"/>'
};
const icon = (n, s = 18) => '<svg class="ic" viewBox="0 0 24 24" width="' + s + '" height="' + s + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + IC[n] + '</svg>';
 
let toastTimer;
function toast(msg, isErr, act) {
  const el = $('toast');
  el.innerHTML = esc(msg) + (act ? '<button class="toast-act" id="toast-act">' + esc(act.label) + '</button>' : '');
  el.classList.toggle('err', !!isErr); el.classList.add('on');
  if (act) $('toast-act').onclick = () => { act.fn(); el.classList.remove('on'); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('on'), act ? 5500 : isErr ? 3400 : 2200);
}
 
/* ================= 2. LOCAL DATA (stands in for the backend) ================= */
let LS_KEY = 'opa_demo_v3';
const MASTER_SKILLS = ['React','Node.js','Next.js','Vue','Angular','Python','JavaScript','TypeScript','Java','C++','RAG','LLM agents','Gemini','Google ADK','LangChain','Prompt engineering','Machine learning','Deep learning','TensorFlow','PyTorch','Computer vision','NLP','SQL','MongoDB','PostgreSQL','Firebase','AWS','Docker','Kubernetes','Git','GitHub Actions','REST APIs','GraphQL','Access control','RBAC','Security','Full-stack web','Mobile development','Flutter','React Native','UI/UX design','Data structures','Algorithms','System design','WhatsApp API','Odoo'];
 
/* Small, verified starter set of IIT faculty — pulled by hand from public
   department pages (not a live scrape; see the note in the Outreach tab).
   Each entry links back to its source so you can double-check before
   emailing. Treat this as a seed, not a full directory. */
const IIT_SEED_FACULTY = [
  { name:'Parag Singla', institute:'IIT Delhi \u00b7 CSE', area:'Machine learning, neuro-symbolic reasoning', tags:'Machine learning, Deep learning, NLP', email:'parags@cse.iitd.ac.in', source:'https://www.cse.iitd.ac.in/~parags/' },
  { name:'Naveen Garg', institute:'IIT Delhi \u00b7 CSE', area:'Algorithms, approximation algorithms, optimization', tags:'Algorithms, System design', email:'naveen@cse.iitd.ac.in', source:'https://en.wikipedia.org/wiki/Naveen_Garg' }
];
 
function seed() {
  return {
    profile: {
      name: 'Tiru', track: 'B.Tech Computer Science', github: '', email: '',
      skills: 'React, Python, LLM agents, RAG, Node.js, Full-stack web, Prompt engineering',
      highlight: 'I build AI-powered products end to end, from LLM agents to full-stack dashboards.'
    },
    applications: [
      { id: uid(), company: 'Northwind Labs', role: 'ML Engineer Intern', type: 'Internship', deadline: iso(2), status: 'Not started', effort_min: 90, notes: 'Tailor the resume toward LLM work' },
      { id: uid(), company: 'BuildFest 2026', role: 'Team entry', type: 'Hackathon', deadline: iso(4), status: 'Not started', effort_min: 45, notes: '' },
      { id: uid(), company: 'Halden Research Group', role: 'Research assistant', type: 'Research', deadline: iso(6), status: 'Applied', effort_min: 60, notes: '' },
      { id: uid(), company: 'Lumen AI', role: 'Full-stack intern', type: 'Internship', deadline: iso(9), status: 'Interview', effort_min: 60, notes: 'Prepare a system design walkthrough' }
    ],
    opportunities: [
      { id: uid(), title: 'Applied ML Fellowship', org: 'Kestrel Institute', type: 'Fellowship', tags: 'Machine learning, Python, PyTorch', deadline: iso(5), status: 'New' },
      { id: uid(), title: 'Frontend Engineer Intern', org: 'Orbit Studio', type: 'Internship', tags: 'React, TypeScript, UI/UX design', deadline: iso(12), status: 'New' }
    ],
    contacts: [
      { id: uid(), name: 'Dr. Meera Rao', institute: 'Riverside Institute of Technology', area: 'Retrieval-augmented generation', tags: 'RAG, NLP, LLM agents', email: 'meera.rao@example.edu', status: 'Not started', sent_on: null },
      { id: uid(), name: 'Prof. Daniel Osei', institute: 'Coastal University', area: 'Computer vision', tags: 'Computer vision, Deep learning', email: 'd.osei@example.edu', status: 'Sent', sent_on: iso(-8) }
    ],
    projects: [
      { id: uid(), name: 'Operating Agent MVP', description: 'Connect the dashboard to a real backend.', tasks: [
        { id: uid(), name: 'Design the API contract', done: true },
        { id: uid(), name: 'Wire Gmail sending', done: false },
        { id: uid(), name: 'Connect JARVIS to a model', done: false }
      ] },
      { id: uid(), name: 'Portfolio refresh', description: 'Add two recent case studies.', tasks: [
        { id: uid(), name: 'Write the first case study', done: false },
        { id: uid(), name: 'Record a short demo video', done: false }
      ] }
    ],
    academics: [
      { id: uid(), subject: 'Operating Systems', task: 'Revise scheduling and memory management', exam_date: iso(3), effort_min: 90, done: false },
      { id: uid(), subject: 'Database Systems', task: 'Practice normalization problems', exam_date: iso(10), effort_min: 60, done: false }
    ],
    requests: [
      { id: uid(), client: 'Sunrise Bakery', ask: 'A website with online ordering', scope: '', timeline: '3 weeks', price: '', email: 'hello@sunrisebakery.example', status: 'New' },
      { id: uid(), client: 'FitHub Gym', ask: 'Member dashboard with class booking', scope: 'Login, class calendar, booking flow, admin view', timeline: '5 weeks', price: '', email: 'owner@fithub.example', status: 'Scoped' }
    ],
    outbox: [],
    history: [{ id: uid(), at: new Date().toISOString(), text: 'Workspace created with sample data' }],
    doneToday: { date: iso(0), items: [] },
    daily: {}
  };
}
function load() {
  try { const r = localStorage.getItem(LS_KEY); if (r) return JSON.parse(r); } catch (e) {}
  return seed();
}
let S = load();
function save() { try { localStorage.setItem(LS_KEY, JSON.stringify(S)); } catch (e) { toast('Could not save — your browser storage may be full', true); } }
function log(text) { S.history.unshift({ id: uid(), at: new Date().toISOString(), text }); }
const byId = (coll, id) => S[coll].find(x => x.id === id);
function upsert(coll, obj) {
  if (obj.id) { const i = S[coll].findIndex(x => x.id === obj.id); if (i > -1) S[coll][i] = { ...S[coll][i], ...obj }; }
  else S[coll].unshift({ ...obj, id: uid() });
  save();
}
function remove(coll, id) { S[coll] = S[coll].filter(x => x.id !== id); save(); }
function doneList() { if (!S.doneToday || S.doneToday.date !== iso(0)) S.doneToday = { date: iso(0), items: [] }; return S.doneToday.items; }
 
function matchScore(tags, skills) {
  const t = splitList(tags).map(x => x.toLowerCase());
  const s = splitList(skills).map(x => x.toLowerCase());
  if (!t.length || !s.length) return 0;
  const hits = t.filter(x => s.some(y => y.includes(x) || x.includes(y))).length;
  return Math.round(hits / t.length * 100);
}
 
/* ================= 3. TODAY'S PLAN (computed locally) ================= */
const KIND = {
  app:  { label: 'Applications',  color: 'var(--c-app)',  icon: 'brief' },
  out:  { label: 'Outreach',      color: 'var(--c-out)',  icon: 'mail' },
  proj: { label: 'Projects',      color: 'var(--c-proj)', icon: 'layers' },
  acad: { label: 'Academics',     color: 'var(--c-acad)', icon: 'book' },
  req:  { label: 'Requests',      color: 'var(--c-req)',  icon: 'chat' },
  opp:  { label: 'Opportunities', color: 'var(--c-opp)',  icon: 'target' }
};
function buildPlan() {
  const items = [];
  S.applications.forEach(a => {
    if (a.status === 'Not started') items.push({ kind:'app', id:a.id, name:'Apply to ' + a.company, sub:a.role + (a.deadline ? ' · ' + fmtDue(a.deadline) : ''), effort:a.effort_min || 60, pri:a.deadline ? daysUntil(a.deadline) : 30 });
    else if (a.status === 'Interview') items.push({ kind:'app', id:a.id, name:'Prepare for ' + a.company, sub:a.role + ' interview', effort:a.effort_min || 60, pri:Math.min(8, a.deadline ? Math.max(daysUntil(a.deadline), 1) : 8) });
  });
  S.contacts.forEach(c => {
    if (c.status === 'Not started') items.push({ kind:'out', id:c.id, name:'Email ' + c.name, sub:c.institute + (c.area ? ' · ' + c.area : ''), effort:20, pri:10 });
    else if (c.status === 'Drafted') items.push({ kind:'out', id:c.id, name:'Approve the draft to ' + c.name, sub:'Waiting in your Outbox', effort:5, pri:5 });
  });
  S.projects.forEach(p => {
    const t = p.tasks.find(x => !x.done);
    if (t) items.push({ kind:'proj', id:p.id, taskId:t.id, name:t.name, sub:p.name, effort:45, pri:12 });
  });
  S.academics.forEach(a => {
    if (!a.done) { const d = a.exam_date ? daysUntil(a.exam_date) : 25; if (d <= 21) items.push({ kind:'acad', id:a.id, name:a.subject + ': ' + a.task, sub:a.exam_date ? 'Exam ' + fmtDate(a.exam_date) : 'No exam date', effort:a.effort_min || 60, pri:d }); }
  });
  S.requests.forEach(r => {
    if (r.status === 'New') items.push({ kind:'req', id:r.id, name:'Scope the request from ' + r.client, sub:r.ask, effort:30, pri:6 });
    else if (r.status === 'Scoped') items.push({ kind:'req', id:r.id, name:'Send a proposal to ' + r.client, sub:r.ask, effort:20, pri:4 });
  });
  S.opportunities.forEach(o => {
    if (o.status === 'New' && o.deadline && daysUntil(o.deadline) <= 5) items.push({ kind:'opp', id:o.id, name:'Decide on ' + o.title, sub:o.org + ' · ' + fmtDue(o.deadline).replace('Due', 'closes'), effort:15, pri:daysUntil(o.deadline) + 1 });
  });
  items.forEach(i => { i.key = i.kind + ':' + i.id + ':' + (i.taskId || ''); });
  items.sort((a, b) => a.pri - b.pri);
  return items.slice(0, 8);
}
function weekAhead() {
  const rows = [];
  S.applications.forEach(a => { if (a.deadline && !['Offer','Rejected','Applied'].includes(a.status)) rows.push({ date:a.deadline, text:a.company + ' application closes' }); });
  S.opportunities.forEach(o => { if (o.deadline && o.status === 'New') rows.push({ date:o.deadline, text:o.title + ' closes' }); });
  S.academics.forEach(a => { if (a.exam_date && !a.done) rows.push({ date:a.exam_date, text:a.subject + ' exam' }); });
  return rows.filter(r => { const d = daysUntil(r.date); return d >= 0 && d <= 7; }).sort((a, b) => a.date.localeCompare(b.date));
}
 
/* ================= 4. FORMS, MODALS, CONFIRM ================= */
function openModal(html) { $('dialog').innerHTML = html; $('overlay').classList.add('on'); const f = $('dialog').querySelector('input,textarea,select'); if (f) setTimeout(() => f.focus(), 30); }
function closeModal() { $('overlay').classList.remove('on'); }
$('overlay').addEventListener('mousedown', (e) => { if (e.target.id === 'overlay') closeModal(); });
 
function fieldHTML(f, v) {
  const val = v[f.k] == null ? '' : v[f.k];
  let inp;
  if (f.t === 'textarea') inp = '<textarea id="f-' + f.k + '" rows="' + (f.rows || 3) + '" placeholder="' + escA(f.ph || '') + '">' + esc(val) + '</textarea>';
  else if (f.t === 'select') inp = '<select id="f-' + f.k + '">' + f.opts.map(o => { const ov = typeof o === 'object' ? o.v : o, ol = typeof o === 'object' ? o.l : o; return '<option value="' + escA(ov) + '"' + (String(val) === String(ov) ? ' selected' : '') + '>' + esc(ol) + '</option>'; }).join('') + '</select>';
  else inp = '<input id="f-' + f.k + '" type="' + (f.t || 'text') + '" value="' + escA(val) + '" placeholder="' + escA(f.ph || '') + '">';
  return '<div class="field' + (f.half ? ' half' : '') + '" id="w-' + f.k + '"><label for="f-' + f.k + '">' + f.l + '</label>' + inp + (f.hint ? '<div class="hint">' + f.hint + '</div>' : '') + '</div>';
}
function openForm(o) {
  const v = o.values || {};
  openModal('<h3>' + esc(o.title) + '</h3><div class="fields">' + o.fields.map(f => fieldHTML(f, v)).join('') + '</div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="form-save">' + esc(o.saveLabel || 'Save') + '</button></div>');
  $('form-save').onclick = () => {
    const out = {}; let bad = null;
    o.fields.forEach(f => {
      const el = $('f-' + f.k); let x = el.value.trim();
      $('w-' + f.k).classList.remove('bad');
      if (f.req && !x) { $('w-' + f.k).classList.add('bad'); bad = bad || f; }
      if (f.num) x = parseInt(x, 10) || 0;
      out[f.k] = x;
    });
    if (bad) { toast('Add ' + bad.l.toLowerCase() + ' to continue', true); return; }
    o.onSave(out);
  };
}
function confirmBox(msg, yesLabel, onYes) {
  openModal('<h3>' + esc(msg) + '</h3><div class="foot"><button class="btn ghost" onclick="closeModal()">Keep it</button><button class="btn danger" id="yes-btn">' + esc(yesLabel) + '</button></div>');
  $('yes-btn').onclick = () => { closeModal(); onYes(); };
}
function confirmDelete(coll, id, label) {
  confirmBox('Delete ' + label + '?', 'Delete', () => {
    const idx = S[coll].findIndex(x => x.id === id); const snap = S[coll][idx];
    remove(coll, id); log('Deleted ' + label); save(); render();
    toast('Deleted ' + label, false, { label: 'Undo', fn: () => { S[coll].splice(Math.min(idx, S[coll].length), 0, snap); S.history.shift(); save(); render(); } });
  });
}
 
/* ================= 5. STATUS PILLS ================= */
const TONE = { 'Not started':'', Applied:'brand', Interview:'warn', Offer:'good', Rejected:'bad', New:'brand', Converted:'good', Dismissed:'', Drafted:'warn', Sent:'good', Replied:'good', Scoped:'warn', Quoted:'brand', Won:'good', Declined:'bad', pending:'warn', approved:'good', rejected:'bad' };
const LABEL = { pending:'Needs approval', approved:'Approved', rejected:'Rejected' };
const pill = (s) => '<span class="pill ' + (TONE[s] || '') + '">' + esc(LABEL[s] || s) + '</span>';
const meter = (score) => '<div class="meter' + (score >= 60 ? ' hi' : '') + '" title="' + score + '% skill match"><div><i style="width:' + score + '%"></i></div>' + score + '% match</div>';
const head = (title, sub, action) => '<div class="head"><div><h1>' + title + '</h1>' + (sub ? '<p>' + sub + '</p>' : '') + '</div>' + (action || '') + '</div>';
const addBtn = (label, fn) => '<button class="btn" onclick="' + fn + '">' + icon('plus', 16) + label + '</button>';
const rowBtns = (edit, del) => '<button class="icon-btn" onclick="' + edit + '" aria-label="Edit" title="Edit">' + icon('edit', 16) + '</button><button class="icon-btn del" onclick="' + del + '" aria-label="Delete" title="Delete">' + icon('trash', 16) + '</button>';
const emptyPanel = (title, text, btn) => '<div class="empty plain"><h3>' + title + '</h3><p>' + text + '</p>' + (btn || '') + '</div>';
 
/* ================= 6. VIEWS ================= */
let animateNext = true;
 
/* ---- Home (Today) ---- */
function viewToday() {
  const plan = buildPlan();
  const top = plan.slice(0, 3);
  const now = new Date();
  const hr = now.getHours();
  const greet = hr < 12 ? 'Good morning' : hr < 17 ? 'Good afternoon' : 'Good evening';
  const first = S.profile.name ? esc(S.profile.name.split(' ')[0]) : '';
  const wk = (() => { const d = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())); const n = d.getUTCDay() || 7; d.setUTCDate(d.getUTCDate() + 4 - n); const y0 = new Date(Date.UTC(d.getUTCFullYear(), 0, 1)); return Math.ceil(((d - y0) / 86400000 + 1) / 7); })();
  const eyebrow = now.toLocaleDateString('en-US', { weekday: 'long' }) + ' · ' + now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' · Week ' + wk;
  const words = ['No', 'One', 'Two', 'Three'];
  const lead = top.length
    ? words[top.length] + ' high-impact ' + (top.length === 1 ? 'move' : 'moves') + ' will keep your applications, research and projects on track.'
    : 'Nothing queued yet. Add an application, contact or project to build today\u2019s plan.';
 
  const tag = (i) => i.pri <= 0 ? 'Due today' : i.pri === 1 ? 'Due tomorrow' : i.pri <= 3 ? 'In ' + i.pri + ' days' : KIND[i.kind].label;
  const cards = top.map((i, n) => `<button class="hm-card" onclick="startFocus('${i.key}')" title="Start a focus timer"><div class="hm-card-t"><span class="n">${pad(n + 1)}</span><span class="hm-tag">${esc(tag(i))}</span></div><b>${esc(i.name)}</b><small>${esc(i.sub)} · ${fmtMins(i.effort)}</small></button>`).join('');
 
  const li = (hot, t, s) => `<div class="hm-li"><i class="${hot ? 'hot' : ''}"></i><div><b>${esc(t)}</b><small>${esc(s)}</small></div></div>`;
  const none = (t) => `<div class="row-s" style="padding:4px 0">${t}</div>`;
  const card = (title, link, fn, body) => `<section class="panel"><div class="panel-h"><h3>${title}</h3>${link ? `<button class="hm-link" onclick="${fn}">${link}</button>` : ''}</div><div class="hm-list">${body}</div></section>`;
 
  // deadlines
  const dl = [];
  S.applications.forEach(a => { if (a.deadline && !['Applied', 'Offer', 'Rejected'].includes(a.status)) dl.push({ d: a.deadline, t: a.company + ' ' + a.role, s: 'Application · ' + fmtDue(a.deadline) }); });
  S.academics.forEach(a => { if (a.exam_date && !a.done) dl.push({ d: a.exam_date, t: a.subject + ': ' + a.task, s: 'Academic · Exam ' + fmtDate(a.exam_date) }); });
  S.opportunities.forEach(o => { if (o.deadline && o.status === 'New') dl.push({ d: o.deadline, t: o.title, s: 'Opportunity · ' + fmtDue(o.deadline).replace('Due', 'closes') }); });
  dl.sort((a, b) => a.d.localeCompare(b.d));
  const dlHTML = dl.slice(0, 3).map(x => li(daysUntil(x.d) <= 2, x.t, x.s)).join('') || none('Nothing dated coming up.');
 
  // matched opportunities
  const opps = S.opportunities.filter(o => o.status === 'New').map(o => ({ o, sc: matchScore(o.tags, S.profile.skills) })).sort((a, b) => b.sc - a.sc).slice(0, 3);
  const oppHTML = opps.map((x, n) => li(n === 0, x.o.title + (x.o.org ? ' · ' + x.o.org : ''), x.sc + '% match' + (x.o.tags ? ' · ' + x.o.tags : ''))).join('') || none('No new opportunities.');
 
  // pipeline
  const cnt = (s) => S.applications.filter(a => a.status === s).length;
  const stats = [['Saved', cnt('Not started'), ''], ['Applied', cnt('Applied'), ''], ['Interview', cnt('Interview'), ' hot'], ['Offer', cnt('Offer'), ' dark']]
    .map(x => `<div class="hm-stat${x[2]}"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('');
 
  // follow-ups
  const fu = S.contacts.filter(c => c.status === 'Sent' || c.status === 'Drafted').slice(0, 3);
  const fuHTML = fu.map(c => li(c.status === 'Sent' && c.sent_on && daysUntil(c.sent_on) <= -7, c.name + (c.institute ? ' · ' + c.institute : ''), c.status === 'Sent' ? 'Sent ' + fmtDate(c.sent_on) + ' · no reply yet' : 'Draft waiting in Outbox')).join('') || none('No follow-ups pending.');
 
  // projects
  const prHTML = S.projects.slice(0, 3).map((p, n) => {
    const done = p.tasks.filter(t => t.done).length, total = p.tasks.length, nx = p.tasks.find(t => !t.done);
    return li(n === 0, p.name + (p.description ? ' · ' + p.description : ''), (total ? Math.round(done / total * 100) : 0) + '% · next: ' + (nx ? nx.name : 'all done'));
  }).join('') || none('No active projects.');
 
  // weekly outlook (Mon–Fri)
  const ev = calEvents();
  const mon = new Date(); mon.setHours(0, 0, 0, 0); mon.setDate(mon.getDate() - ((mon.getDay() + 6) % 7));
  const wkHTML = [0, 1, 2, 3, 4].map(k => {
    const d = new Date(mon); d.setDate(mon.getDate() + k);
    const e = ev[localKey(d)] || [];
    return `<div class="hm-wk"><span>${d.toLocaleDateString('en-US', { weekday: 'short' })} · ${e.length ? esc(KIND[e[0].k].label.toLowerCase()) : 'open'}</span><i class="hm-bar${e.length >= 2 ? ' hot' : ''}" style="width:${14 + Math.min(e.length, 3) * 22}px"></i></div>`;
  }).join('');
 
  const sent = S.contacts.filter(c => c.status === 'Sent').length;
  const insight = sent
    ? sent + ' outreach email' + (sent > 1 ? 's are' : ' is') + ' waiting on a reply. A short follow-up that cites one concrete paper or project tends to get answered.'
    : 'No outreach is waiting on a reply. Drafting two or three emails this week keeps your research pipeline moving.';
 
  animateNext = false;
  return `
  <div class="hm-top">
    <div><div class="hm-eyebrow">${esc(eyebrow)}</div><h1>${greet}${first ? ', ' + first : ''}.</h1><p>${lead}</p></div>
    <div class="hm-btns">
      <button class="btn" onclick="switchTab('jarvis');setTimeout(function(){jarvisSend('Help me plan the next 3 hours.')},80)">Plan my day</button>
      <button class="btn ghost" onclick="switchTab('opportunities')">Review matches</button>
    </div>
  </div>
  <section class="panel hm-plan">
    <div class="panel-h"><h3>AI priority plan</h3><button class="hm-link" onclick="animateNext=true;render();toast('Plan refreshed')">Regenerate</button></div>
    ${cards ? `<div class="hm-cards">${cards}</div>` : none('Add work in any tab and the top three priorities appear here.')}
  </section>
  <div class="hm-grid">
    <div class="hm-col">
      ${card('Upcoming deadlines', 'View all', "switchTab('applications')", dlHTML)}
      ${card('Matched opportunities', 'Review matches', "switchTab('opportunities')", oppHTML)}
    </div>
    <div class="hm-col">
      <section class="panel"><div class="panel-h"><h3>Application pipeline</h3><button class="hm-link" onclick="switchTab('applications')">Open tracker</button></div><div class="hm-stats">${stats}</div></section>
      ${card('Research follow-ups', 'Draft follow-up', "switchTab('outreach')", fuHTML)}
      ${card('Active projects', '', '', prHTML)}
    </div>
    <div class="hm-col">
      ${card('Weekly outlook', '', '', wkHTML)}
      <section class="hm-ins"><h3>AI insight<i></i></h3><p>${esc(insight)}</p></section>
    </div>
  </div>`;
}
function completeItem(key, cb) {
  const it = buildPlan().find(i => i.key === key);
  if (!it) { render(); return; }
  if (it.kind === 'app') {
    const a = byId('applications', it.id);
    if (a && a.status === 'Not started') { a.status = 'Applied'; log('Applied to ' + a.company); }
    else log('Finished preparing for ' + (a ? a.company : 'an interview'));
  } else if (it.kind === 'out') {
    const c = byId('contacts', it.id);
    if (c && c.status === 'Not started') { cb.checked = false; draftOutreach(it.id); return; }
    if (c && c.status === 'Drafted') { cb.checked = false; toast('Approve the pending draft in your Outbox'); switchTab('outbox'); return; }
  } else if (it.kind === 'proj') {
    const p = byId('projects', it.id); const t = p && p.tasks.find(x => x.id === it.taskId);
    if (t) { t.done = true; log('Finished task: ' + t.name); }
  } else if (it.kind === 'acad') {
    const a = byId('academics', it.id); if (a) { a.done = true; log('Finished studying: ' + a.subject); }
  } else if (it.kind === 'req') {
    const r = byId('requests', it.id);
    if (r && r.status === 'Scoped') { cb.checked = false; draftProposal(it.id); return; }
    if (r) { r.status = 'Scoped'; log('Scoped the request from ' + r.client); }
  } else if (it.kind === 'opp') { log('Reviewed ' + it.name.replace('Decide on ', '')); }
  doneList().push({ key: it.key, kind: it.kind, name: it.name, sub: it.sub, effort: it.effort }); save(); render(); toast('Done: ' + it.name);
}
 
/* ---- Applications (pipeline board) ---- */
const APP_COLS = ['Not started', 'Applied', 'Interview', 'Offer', 'Rejected'];
const APP_NEXT = { 'Not started': 'Applied', Applied: 'Interview', Interview: 'Offer' };
function viewApps() {
  if (!S.applications.length) return head('Applications', 'Internships, research labs, and hackathons in one pipeline.', addBtn('Add application', 'editApp()')) + emptyPanel('No applications yet', 'Add the first one and track it from draft to offer.', '<button class="btn" onclick="editApp()">Add application</button>');
  const cols = APP_COLS.map(st => {
    const list = S.applications.filter(a => a.status === st);
    const cards = list.map(a => {
      const tone = dueTone(a.deadline, a.status);
      return '<article class="kcard" style="--c:var(--c-app)" draggable="true" ondragstart="dragApp(event,\'' + a.id + '\')" ondragend="this.classList.remove(\'dragging\')"><div class="kcard-top"><div><div class="k-title">' + esc(a.company) + '</div><div class="k-sub">' + esc(a.role) + '</div></div><div style="display:flex"><button class="icon-btn" onclick="editApp(\'' + a.id + '\')" aria-label="Edit ' + escA(a.company) + '" title="Edit">' + icon('edit', 15) + '</button><button class="icon-btn del" onclick="confirmDelete(\'applications\',\'' + a.id + '\',\'' + escA(a.company) + '\')" aria-label="Delete ' + escA(a.company) + '" title="Delete">' + icon('trash', 15) + '</button></div></div>' +
        '<div class="row-m"><span class="chip">' + esc(a.type) + '</span>' + (a.deadline ? '<span class="chip ' + tone + '">' + (['Applied','Interview','Offer','Rejected'].includes(a.status) ? 'Deadline ' + fmtDate(a.deadline) : fmtDue(a.deadline)) + '</span>' : '') + '</div>' +
        (a.notes ? '<div class="k-note">' + esc(a.notes) + '</div>' : '') +
        (APP_NEXT[a.status] ? '<button class="btn soft sm" onclick="advanceApp(\'' + a.id + '\')">Mark as ' + APP_NEXT[a.status].toLowerCase() + '</button>' : '') + '</article>';
    }).join('');
    return '<section class="col" aria-label="' + st + '" ondragover="event.preventDefault();this.classList.add(\'over\')" ondragleave="this.classList.remove(\'over\')" ondrop="dropApp(event,\'' + st + '\')"><div class="col-h">' + st + '<span>' + list.length + '</span></div>' + (cards || '<div class="col-empty">Nothing here</div>') + '</section>';
  }).join('');
  return head('Applications', 'Internships, research labs, and hackathons in one pipeline. Drag a card between stages, or use the quick-advance button.', addBtn('Add application', 'editApp()')) + '<div class="board">' + cols + '</div>';
}
function editApp(id) {
  const a = id ? byId('applications', id) : { type: 'Internship', status: 'Not started', effort_min: 60 };
  openForm({ title: id ? 'Edit application' : 'Add application', values: a, saveLabel: id ? 'Save changes' : 'Add application',
    fields: [
      { k:'company', l:'Company or lab', req:true, ph:'e.g. Northwind Labs' },
      { k:'role', l:'Role', ph:'e.g. ML Engineer Intern' },
      { k:'type', l:'Type', t:'select', half:true, opts:['Internship','Research','Hackathon'] },
      { k:'status', l:'Status', t:'select', half:true, opts:APP_COLS },
      { k:'deadline', l:'Deadline', t:'date', half:true },
      { k:'effort_min', l:'Time needed', t:'select', half:true, num:true, opts:[15,30,45,60,90,120,180].map(m => ({ v:m, l:fmtMins(m) })) },
      { k:'notes', l:'Notes', t:'textarea' }
    ],
    onSave: (v) => { v.deadline = v.deadline || null; if (id) v.id = id; upsert('applications', v); log((id ? 'Updated ' : 'Added application: ') + v.company); closeModal(); render(); toast('Saved'); } });
}
function dragApp(e, id) { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move'; e.currentTarget.classList.add('dragging'); }
function dropApp(e, st) {
  e.preventDefault();
  const a = byId('applications', e.dataTransfer.getData('text/plain'));
  if (!a || a.status === st) { render(); return; }
  a.status = st; log(a.company + ' moved to ' + st); save(); render(); toast(a.company + ': ' + st);
}
function advanceApp(id) { const a = byId('applications', id); if (!a || !APP_NEXT[a.status]) return; a.status = APP_NEXT[a.status]; log(a.company + ' moved to ' + a.status); save(); render(); toast(a.company + ': ' + a.status); }
 
/* ---- Opportunities ---- */
function viewOpps() {
  const h = head('Opportunities', 'Roles and labs you are weighing, scored against your profile skills. Track the good ones as applications.', addBtn('Add opportunity', 'editOpp()'));
  if (!S.opportunities.length) return h + emptyPanel('Nothing on the radar', 'Save roles you are considering and see how well your skills match.', '<button class="btn" onclick="editOpp()">Add opportunity</button>');
  const rows = S.opportunities.map(o => {
    const sc = matchScore(o.tags, S.profile.skills);
    const tone = o.status === 'New' && o.deadline && daysUntil(o.deadline) <= 3 ? 'warn' : '';
    return '<div class="row" style="grid-template-columns:auto 1fr auto"><div class="swatch" style="--c:var(--c-opp)">' + icon('target', 16) + '</div><div><div class="row-t">' + esc(o.title) + '</div><div class="row-s">' + esc(o.org) + ' · ' + esc(o.type) + '</div><div class="row-m">' + pill(o.status) + (o.deadline ? '<span class="chip ' + tone + '">' + fmtDue(o.deadline).replace('Due', 'Closes') + '</span>' : '') + meter(sc) + (o.tags ? '<span class="chip">' + esc(o.tags) + '</span>' : '') + '</div></div><div class="row-a">' +
      (o.status === 'New' ? '<button class="btn sm" onclick="convertOpp(\'' + o.id + '\')">Track as application</button><button class="btn ghost sm" onclick="dismissOpp(\'' + o.id + '\')">Dismiss</button>' : '') +
      rowBtns('editOpp(\'' + o.id + '\')', 'confirmDelete(\'opportunities\',\'' + o.id + '\',\'' + escA(o.title) + '\')') + '</div></div>';
  }).join('');
  return h + '<div class="panel rows">' + rows + '</div>';
}
function editOpp(id) {
  const o = id ? byId('opportunities', id) : { type: 'Internship', status: 'New' };
  openForm({ title: id ? 'Edit opportunity' : 'Add opportunity', values: o, saveLabel: id ? 'Save changes' : 'Add opportunity',
    fields: [
      { k:'title', l:'Title', req:true, ph:'e.g. Applied ML Fellowship' },
      { k:'org', l:'Organization or lab' },
      { k:'type', l:'Type', t:'select', half:true, opts:['Internship','Research','Fellowship','Hackathon','Freelance'] },
      { k:'status', l:'Status', t:'select', half:true, opts:['New','Converted','Dismissed'] },
      { k:'tags', l:'Tags', ph:'React, Python, RAG', hint:'Comma-separated. Matched against the skills in your profile.' },
      { k:'deadline', l:'Closes', t:'date' }
    ],
    onSave: (v) => { v.deadline = v.deadline || null; if (id) v.id = id; upsert('opportunities', v); closeModal(); render(); toast('Saved'); } });
}
function convertOpp(id) {
  const o = byId('opportunities', id); if (!o) return;
  const type = ['Internship','Research','Hackathon'].includes(o.type) ? o.type : 'Internship';
  upsert('applications', { company: o.org || o.title, role: o.title, type, deadline: o.deadline || null, status: 'Not started', effort_min: 60, notes: '' });
  o.status = 'Converted'; log('Tracking ' + o.title + ' as an application'); save(); render(); toast('Added to Applications');
}
function dismissOpp(id) { const o = byId('opportunities', id); if (!o) return; o.status = 'Dismissed'; log('Dismissed ' + o.title); save(); render(); toast('Dismissed'); }
 
/* ---- Outreach ---- */
/* ---- Find IIT faculty (a verified starter set + paste-and-parse importer for Outreach) ---- */
const IIT_LINKS = [
  { l: 'IIT Delhi \u00b7 CSE', u: 'https://www.cse.iitd.ac.in/people/faculty.shtml' },
  { l: 'IIT Kanpur \u00b7 CSE', u: 'https://iitk.ac.in/july14cse/faculty' },
  { l: 'IIT Madras \u00b7 CSE', u: 'https://www.cse.iitm.ac.in/listpeople.php?arg=MSQw' },
  { l: 'IIT BHU \u00b7 CSE', u: 'https://iitbhu.ac.in/dept/cse/faculty' },
  { l: 'IIT Palakkad \u00b7 CSE', u: 'https://cse.iitpkd.ac.in/faculty' },
  { l: 'IIT Kharagpur \u00b7 CSE', u: 'https://cse.iitkgp.ac.in/people/faculty' },
  { l: 'Find another IIT dept', u: 'https://www.google.com/search?q=IIT+CSE+department+faculty+list' }
];
let facultyOpen = false, facultyRows = [];
function toggleFacultyFinder() { facultyOpen = !facultyOpen; render(); }
function seedAdded(email) { return S.contacts.some(c => c.email && c.email.toLowerCase() === email.toLowerCase()); }
function addSeedFaculty(i) {
  const f = IIT_SEED_FACULTY[i]; if (!f) return;
  if (seedAdded(f.email)) { toast(f.name + ' is already in Outreach'); return; }
  upsert('contacts', { name: f.name, institute: f.institute, area: f.area, tags: f.tags, email: f.email, status: 'Not started', sent_on: null });
  log('Added ' + f.name + ' (' + f.institute + ') to Outreach'); save(); render();
  toast('Added ' + f.name + ' \u2014 verify the email before sending');
}
function parseFacultyPaste() {
  const text = $('faculty-paste').value;
  const inst = $('faculty-inst').value.trim();
  const emailRe = /[a-zA-Z0-9._%+-]+\s*(?:@|\bAT\b|\[at\])\s*[a-zA-Z0-9.-]+\s*(?:\.|\[dot\])\s*[a-zA-Z]{2,}(?:\s*(?:\.|\[dot\])\s*[a-zA-Z]{2,})*/g;
  const blocks = text.split(/\n\s*\n+/).map(b => b.trim()).filter(Boolean);
  const rows = [];
  const scan = (block) => {
    const m = block.match(emailRe); if (!m) return;
    const email = m[0].replace(/\s*\[at\]\s*|\s*\bAT\b\s*/gi, '@').replace(/\s*\[dot\]\s*|\s+\.\s+/gi, '.').replace(/\s+/g, '');
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
    let name = lines.find(l => !l.includes('@') && !/^(email|e-mail|tel|phone|office|room|ph\.?d|research|area|interest)/i.test(l) && l.length < 60) || '';
    name = name.replace(/^(Dr\.?|Prof\.?|Professor|Mr\.?|Ms\.?|Mrs\.?)\s+/i, '').trim();
    const area = lines.filter(l => /research|interest|area/i.test(l)).map(l => l.replace(/research interests?\s*:?\s*/i, '').replace(/area\s*:?\s*/i, '')).join('; ') ||
      lines.filter(l => l !== name && !l.includes('@') && !/^(tel|phone|office|room)/i.test(l)).join(' ').slice(0, 140);
    if (name && email) rows.push({ name, email, area: area.slice(0, 160), sel: true });
  };
  blocks.forEach(scan);
  if (!rows.length) { const m2 = text.match(emailRe); if (m2) m2.forEach(e => scan(e)); }
  facultyRows = rows;
  if (!rows.length) toast('Couldn\u2019t find name+email pairs in that paste \u2014 try pasting a bigger chunk including the research interests line', true);
  else toast('Found ' + rows.length + ' possible contact' + (rows.length > 1 ? 's' : '') + ' \u2014 review below');
  S._facultyInst = inst; render();
}
function toggleFacultyRow(i) { facultyRows[i].sel = !facultyRows[i].sel; render(); }
function addSelectedFaculty() {
  const inst = ($('faculty-inst') ? $('faculty-inst').value.trim() : S._facultyInst) || 'IIT';
  const picked = facultyRows.filter(r => r.sel);
  if (!picked.length) { toast('Select at least one row first', true); return; }
  picked.forEach(r => {
    const tags = MASTER_SKILLS.filter(s => r.area.toLowerCase().includes(s.toLowerCase())).join(', ');
    upsert('contacts', { name: r.name, institute: inst, area: r.area, tags, email: r.email, status: 'Not started', sent_on: null });
  });
  log('Imported ' + picked.length + ' faculty contact' + (picked.length > 1 ? 's' : '') + ' from ' + inst);
  facultyRows = []; facultyOpen = false; save(); render();
  toast('Added ' + picked.length + ' contact' + (picked.length > 1 ? 's' : '') + ' to Outreach');
}
function facultyFinderHTML() {
  const linkRow = IIT_LINKS.map(x => '<a class="btn ghost sm" href="' + x.u + '" target="_blank" rel="noopener">' + esc(x.l) + '</a>').join('');
  const seedRows = IIT_SEED_FACULTY.map((f, i) => {
    const added = seedAdded(f.email);
    return '<div class="row" style="grid-template-columns:auto 1fr auto"><div class="swatch" style="--c:var(--c-out)">' + icon('grad', 16) + '</div><div><div class="row-t">' + esc(f.name) + '</div><div class="row-s">' + esc(f.institute) + ' \u00b7 ' + esc(f.area) + '</div><div class="row-m"><span class="chip">' + esc(f.email) + '</span><a class="chip" href="' + escA(f.source) + '" target="_blank" rel="noopener">Source</a></div></div><div class="row-a">' +
      (added ? '<span class="pill good">' + icon('check', 13) + ' Added</span>' : '<button class="btn sm" onclick="addSeedFaculty(' + i + ')">Add to Outreach</button>') + '</div></div>';
  }).join('');
  const rowsHTML = facultyRows.length ? '<div class="panel rows" style="margin-top:14px">' + facultyRows.map((r, i) =>
    '<div class="row noicon"><div style="display:flex;gap:12px;align-items:flex-start"><input type="checkbox" class="ck" ' + (r.sel ? 'checked' : '') + ' onchange="toggleFacultyRow(' + i + ')" style="margin-top:2px"><div><div class="row-t">' + esc(r.name) + '</div><div class="row-s">' + esc(r.email) + (r.area ? ' \u00b7 ' + esc(r.area) : '') + '</div></div></div></div>').join('') + '</div>' +
    '<button class="btn" style="margin-top:12px" onclick="addSelectedFaculty()">Add ' + facultyRows.filter(r => r.sel).length + ' selected to Outreach</button>' : '';
  return '<section class="panel" style="margin-bottom:18px">' +
    '<div class="panel-h"><h3>IIT faculty database</h3><button class="icon-btn" onclick="toggleFacultyFinder()" aria-label="' + (facultyOpen ? 'Collapse' : 'Expand') + '" title="' + (facultyOpen ? 'Collapse' : 'Expand') + '">' + icon(facultyOpen ? 'x' : 'plus', 16) + '</button></div>' +
    (facultyOpen ? '<div style="padding:18px 20px">' +
      '<div class="note" style="margin:0 0 16px">Being straight about how this works: a page running in your browser cannot reach iitd.ac.in, iitk.ac.in, etc. directly \u2014 those sites block cross-origin requests from other sites, which is a browser security rule, not something OPA can bypass. So "full data" here means two things: a small hand-verified starter list below, sourced from public department pages, and a scanner that turns a pasted faculty page into structured contacts in one go. Always double-check an email before sending \u2014 department pages change.</div>' +
      '<h4 style="font-family:var(--display);font-weight:650;font-size:14px;margin-bottom:8px">Verified starter contacts</h4>' +
      '<div class="panel rows" style="margin-bottom:18px">' + seedRows + '</div>' +
      '<h4 style="font-family:var(--display);font-weight:650;font-size:14px;margin-bottom:8px">Scan a full department page</h4>' +
      '<p class="row-s" style="margin-bottom:14px">Open a department\u2019s page below, select-all + copy the faculty section, and paste it here. OPA pulls out every name, email, and research area it can find in one pass, matches each against your skills, and you pick which ones become outreach contacts.</p>' +
      '<div class="row-m" style="margin-bottom:16px">' + linkRow + '</div>' +
      '<div class="field"><label for="faculty-inst">Institute (used for every row you add)</label><input id="faculty-inst" type="text" placeholder="e.g. IIT Delhi, CSE" value="' + escA(S._facultyInst || '') + '"></div>' +
      '<div class="field"><label for="faculty-paste">Pasted faculty listing</label><textarea id="faculty-paste" rows="6" placeholder="Paste the copied faculty section here \u2014 works best with one professor\u2019s name, research interests, and email per block"></textarea></div>' +
      '<button class="btn soft" onclick="parseFacultyPaste()">Scan for contacts</button>' +
      rowsHTML +
      '</div>' : '') + '</section>';
}
function viewOutreach() {
  const h = head('Outreach', 'Contacts matched to your skills. Drafting creates an Outbox item, and nothing goes out until you approve it.', addBtn('Add contact', 'editContact()'));
  const finder = facultyFinderHTML();
  if (!S.contacts.length) return h + finder + emptyPanel('No contacts yet', 'Add a professor, founder, or recruiter to start drafting, or use the IIT faculty database above.', '<button class="btn" onclick="editContact()">Add contact</button>');
  const rows = S.contacts.map(c => {
    const sc = matchScore(c.tags, S.profile.skills);
    let act = '';
    if (c.status === 'Not started') act = '<button class="btn sm" onclick="draftOutreach(\'' + c.id + '\')">Draft email</button>';
    else if (c.status === 'Drafted') act = '<button class="btn soft sm" onclick="switchTab(\'outbox\')">Open in Outbox</button>';
    else if (c.status === 'Sent') act = '<button class="btn soft sm" onclick="draftOutreach(\'' + c.id + '\')">Draft follow-up</button>';
    return '<div class="row" style="grid-template-columns:auto 1fr auto"><div class="swatch" style="--c:var(--c-out)">' + icon('mail', 16) + '</div><div><div class="row-t">' + esc(c.name) + '</div><div class="row-s">' + esc(c.institute) + (c.area ? ' · ' + esc(c.area) : '') + '</div><div class="row-m">' + pill(c.status) + meter(sc) + (c.sent_on ? '<span class="chip">Sent ' + fmtDate(c.sent_on) + '</span>' : '') + '</div></div><div class="row-a">' + act + rowBtns('editContact(\'' + c.id + '\')', 'confirmDelete(\'contacts\',\'' + c.id + '\',\'' + escA(c.name) + '\')') + '</div></div>';
  }).join('');
  return h + finder + '<div class="panel rows">' + rows + '</div>';
}
function editContact(id) {
  const c = id ? byId('contacts', id) : {};
  openForm({ title: id ? 'Edit contact' : 'Add contact', values: c, saveLabel: id ? 'Save changes' : 'Add contact',
    fields: [
      { k:'name', l:'Name', req:true },
      { k:'institute', l:'Institute or company' },
      { k:'area', l:'Research area or focus' },
      { k:'tags', l:'Tags', ph:'RAG, NLP', hint:'Comma-separated. Matched against your profile skills.' },
      { k:'email', l:'Email', t:'email' }
    ],
    onSave: (v) => { if (id) { v.id = id; } else { v.status = 'Not started'; v.sent_on = null; } upsert('contacts', v); closeModal(); render(); toast('Saved'); } });
}
function makeOutbox(payload, ref) {
  const item = { id: uid(), channel: 'email', status: 'pending', created: new Date().toISOString(), payload, ref, note: '' };
  S.outbox.unshift(item); return item;
}
function draftOutreach(id) {
  const c = byId('contacts', id); if (!c) return;
  const p = S.profile; const follow = c.status === 'Sent';
  const subject = follow ? 'Following up on my note about ' + (c.area || 'your work') : 'Interested in your work on ' + (c.area || 'your research');
  const body = 'Dear ' + c.name + ',\n\n' +
    (follow ? 'I wanted to follow up on my earlier email about ' + (c.area || 'your work') + '. I know inboxes fill up quickly, so a short reply either way would help me a lot.\n\n'
            : 'I\u2019m ' + p.name + (p.track ? ', a ' + p.track + ' student' : '') + ', and I\u2019ve been following your work' + (c.area ? ' on ' + c.area : '') + (c.institute ? ' at ' + c.institute : '') + '.\n\n') +
    (p.highlight ? p.highlight + '\n\n' : '') +
    (splitList(p.skills).length ? 'My main skills: ' + splitList(p.skills).slice(0, 5).join(', ') + '.\n\n' : '') +
    'Would you be open to a short conversation about opportunities to contribute?\n\nBest regards,\n' + p.name + (p.github ? '\n' + p.github : '');
  const item = makeOutbox({ to: c.email, subject, body }, { kind: 'contact', id: c.id });
  if (c.status === 'Not started') c.status = 'Drafted';
  log('Drafted an email to ' + c.name); save(); render();
  showDraft('Draft created', item);
}
function showDraft(title, item) {
  openModal('<h3>' + esc(title) + '</h3><div class="mail-meta"><b>To:</b> ' + esc(item.payload.to || 'No email address yet') + '</div><div class="mail-meta"><b>Subject:</b> ' + esc(item.payload.subject) + '</div><div class="mail">' + esc(item.payload.body) + '</div><div class="note">Saved to your Outbox as \u201cNeeds approval.\u201d Nothing is sent from demo mode.</div><div class="foot"><button class="btn ghost" onclick="closeModal();switchTab(\'outbox\')">Review in Outbox</button><button class="btn" onclick="approveOutbox(\'' + item.id + '\');closeModal()">Approve draft</button></div>');
}
 
/* ---- Projects ---- */
function viewProjects() {
  const h = head('Projects', 'Break technical work into tasks the planner can schedule.', addBtn('Add project', 'editProject()'));
  if (!S.projects.length) return h + emptyPanel('No projects yet', 'Create a project, add tasks, and the next open task shows up on Today.', '<button class="btn" onclick="editProject()">Add project</button>');
  return h + '<div class="grid2">' + S.projects.map(p => {
    const done = p.tasks.filter(t => t.done).length, total = p.tasks.length;
    return '<section class="panel proj"><div class="proj-h"><div><h3>' + esc(p.name) + '</h3>' + (p.description ? '<div class="desc">' + esc(p.description) + '</div>' : '') + '</div><div style="display:flex">' + rowBtns('editProject(\'' + p.id + '\')', 'confirmDelete(\'projects\',\'' + p.id + '\',\'' + escA(p.name) + '\')') + '</div></div>' +
      '<div class="prog"><i style="width:' + (total ? Math.round(done / total * 100) : 0) + '%"></i></div><div class="prog-l">' + done + ' of ' + total + ' tasks done</div>' +
      (p.tasks.map(t => '<div class="task' + (t.done ? ' done' : '') + '"><input type="checkbox" class="ck" id="t-' + t.id + '" ' + (t.done ? 'checked' : '') + ' onchange="toggleTask(\'' + p.id + '\',\'' + t.id + '\')"><label for="t-' + t.id + '">' + esc(t.name) + '</label><button class="icon-btn del" onclick="deleteTask(\'' + p.id + '\',\'' + t.id + '\')" aria-label="Delete task" title="Delete task">' + icon('x', 14) + '</button></div>').join('') || '<div class="row-s" style="padding:6px 0">No tasks yet.</div>') +
      '<div class="addtask"><input type="text" id="nt-' + p.id + '" placeholder="Add a task" aria-label="New task name" onkeydown="if(event.key===\'Enter\')addTask(\'' + p.id + '\')"><button class="btn ghost sm" onclick="addTask(\'' + p.id + '\')">Add</button></div></section>';
  }).join('') + '</div>';
}
function editProject(id) {
  const p = id ? byId('projects', id) : {};
  openForm({ title: id ? 'Edit project' : 'Add project', values: p, saveLabel: id ? 'Save changes' : 'Add project',
    fields: [{ k:'name', l:'Project name', req:true }, { k:'description', l:'Description', t:'textarea', rows:2 }],
    onSave: (v) => { if (id) v.id = id; else v.tasks = []; upsert('projects', v); closeModal(); render(); toast('Saved'); } });
}
function toggleTask(pid, tid) { const t = byId('projects', pid).tasks.find(x => x.id === tid); t.done = !t.done; if (t.done) log('Finished task: ' + t.name); save(); render(); }
function deleteTask(pid, tid) { const p = byId('projects', pid); p.tasks = p.tasks.filter(x => x.id !== tid); save(); render(); }
function addTask(pid) { const el = $('nt-' + pid); const name = el.value.trim(); if (!name) return; byId('projects', pid).tasks.push({ id: uid(), name, done: false }); save(); render(); const n = $('nt-' + pid); if (n) n.focus(); }
 
/* ---- Academics ---- */
function viewAcads() {
  const h = head('Academics', 'Exam prep and coursework, sized so the planner can fit it around everything else.', addBtn('Add study task', 'editAcad()'));
  if (!S.academics.length) return h + emptyPanel('No study tasks yet', 'Add what you need to revise and when the exam is.', '<button class="btn" onclick="editAcad()">Add study task</button>');
  const list = S.academics.slice().sort((a, b) => (a.done - b.done) || ((a.exam_date ? daysUntil(a.exam_date) : 999) - (b.exam_date ? daysUntil(b.exam_date) : 999)));
  return h + '<div class="panel rows">' + list.map(t => {
    const d = t.exam_date ? daysUntil(t.exam_date) : null;
    return '<div class="row"><input type="checkbox" class="ck" ' + (t.done ? 'checked' : '') + ' aria-label="Mark ' + escA(t.subject) + ' done" onchange="toggleAcad(\'' + t.id + '\')"><div><div class="row-t" style="' + (t.done ? 'text-decoration:line-through;color:var(--ink-3)' : '') + '">' + esc(t.subject) + '</div><div class="row-s">' + esc(t.task) + '</div><div class="row-m">' + (t.done ? '<span class="pill good">Done</span>' : (d != null ? '<span class="chip ' + (d <= 3 ? 'warn' : '') + '">' + (d < 0 ? 'Exam passed' : d === 0 ? 'Exam today' : 'Exam in ' + d + (d === 1 ? ' day' : ' days')) + '</span>' : '<span class="chip">No exam date</span>')) + '<span class="chip">' + fmtMins(t.effort_min) + '</span></div></div><div class="row-a">' + rowBtns('editAcad(\'' + t.id + '\')', 'confirmDelete(\'academics\',\'' + t.id + '\',\'' + escA(t.subject) + '\')') + '</div></div>';
  }).join('') + '</div>';
}
function editAcad(id) {
  const t = id ? byId('academics', id) : { effort_min: 60 };
  openForm({ title: id ? 'Edit study task' : 'Add study task', values: t, saveLabel: id ? 'Save changes' : 'Add study task',
    fields: [
      { k:'subject', l:'Subject', req:true }, { k:'task', l:'What to study' },
      { k:'exam_date', l:'Exam date', t:'date', half:true },
      { k:'effort_min', l:'Time needed', t:'select', half:true, num:true, opts:[30,45,60,90,120,180].map(m => ({ v:m, l:fmtMins(m) })) }
    ],
    onSave: (v) => { v.exam_date = v.exam_date || null; if (id) v.id = id; else v.done = false; upsert('academics', v); closeModal(); render(); toast('Saved'); } });
}
function toggleAcad(id) { const t = byId('academics', id); t.done = !t.done; if (t.done) log('Finished studying: ' + t.subject); save(); render(); }
 
/* ---- Requests ---- */
function viewReqs() {
  const h = head('Client requests', 'Turn \u201ccan you build me a website?\u201d into a scoped proposal you can send.', addBtn('Add request', 'editReq()'));
  if (!S.requests.length) return h + emptyPanel('No requests yet', 'When someone asks for work, log it here and scope it.', '<button class="btn" onclick="editReq()">Add request</button>');
  return h + '<div class="panel rows">' + S.requests.map(r =>
    '<div class="row" style="grid-template-columns:auto 1fr auto"><div class="swatch" style="--c:var(--c-req)">' + icon('chat', 16) + '</div><div><div class="row-t">' + esc(r.client) + '</div><div class="row-s">' + esc(r.ask) + '</div><div class="row-m">' + pill(r.status) + (r.timeline ? '<span class="chip">' + esc(r.timeline) + '</span>' : '') + (r.price ? '<span class="chip">Quote: ' + esc(r.price) + '</span>' : '') + '</div>' + (r.scope ? '<div class="k-note">Scope: ' + esc(r.scope) + '</div>' : '') + '</div><div class="row-a">' +
    ((r.status === 'New' || r.status === 'Scoped') ? '<button class="btn sm" onclick="draftProposal(\'' + r.id + '\')">Draft proposal</button>' : '') + rowBtns('editReq(\'' + r.id + '\')', 'confirmDelete(\'requests\',\'' + r.id + '\',\'' + escA(r.client) + '\')') + '</div></div>').join('') + '</div>';
}
function editReq(id) {
  const r = id ? byId('requests', id) : { status: 'New' };
  openForm({ title: id ? 'Edit request' : 'Add request', values: r, saveLabel: id ? 'Save changes' : 'Add request',
    fields: [
      { k:'client', l:'Client', req:true },
      { k:'ask', l:'What they asked for', t:'textarea', rows:2 },
      { k:'scope', l:'Scoped deliverables', t:'textarea', rows:2, hint:'Used in the proposal draft.' },
      { k:'timeline', l:'Timeline', half:true, ph:'e.g. 3 weeks' },
      { k:'price', l:'Quote', half:true, ph:'e.g. ₹60,000' },
      { k:'email', l:'Email', t:'email', half:true },
      { k:'status', l:'Status', t:'select', half:true, opts:['New','Scoped','Quoted','Won','Declined'] }
    ],
    onSave: (v) => { if (id) v.id = id; upsert('requests', v); closeModal(); render(); toast('Saved'); } });
}
function draftProposal(id) {
  const r = byId('requests', id); if (!r) return;
  const p = S.profile;
  const body = 'Hi ' + r.client + ',\n\nThanks for reaching out about: ' + (r.ask || 'your project') + '.\n\nProposed scope:\n' + (r.scope || 'To be confirmed after a short call.') + '\n\nTimeline: ' + (r.timeline || 'To be confirmed') + '\nEstimate: ' + (r.price || 'To be confirmed') + '\n\nIf this looks right, reply and I will send a short agreement and a start date.\n\nBest,\n' + p.name;
  const item = makeOutbox({ to: r.email, subject: 'Proposal for ' + r.client, body }, { kind: 'request', id: r.id });
  if (r.status === 'New') r.status = 'Scoped';
  log('Drafted a proposal for ' + r.client); save(); render();
  showDraft('Proposal drafted', item);
}
 
/* ---- Outbox ---- */
function viewOutbox() {
  const h = head('Outbox', 'Every message passes through here. Nothing is delivered without your approval.', '');
  const info = '<div class="note" style="margin:0 0 18px;max-width:720px">' + (AUTH.user ? 'Approving sends the email from your Gmail (' + esc(AUTH.user.email) + ').' : 'Demo mode: approving only marks a message as approved. Sign in with Google to send real email.') + '</div>';
  if (!S.outbox.length) return h + info + emptyPanel('Your outbox is empty', 'Draft an outreach email or a client proposal and it will wait here for your approval.', '<button class="btn" onclick="switchTab(\'outreach\')">Go to Outreach</button>');
  const order = { pending: 0, approved: 1, rejected: 2 };
  const items = S.outbox.slice().sort((a, b) => order[a.status] - order[b.status]);
  return h + info + '<div class="panel rows">' + items.map(o =>
    '<div class="row noicon"><div><div class="row-t">' + esc(o.payload.subject || '(no subject)') + '</div><div class="row-s">To ' + esc(o.payload.to || 'no address yet') + '</div><div class="row-m">' + pill(o.status) + '<span class="chip">' + esc(o.channel) + '</span>' + (o.note ? '<span class="chip">' + esc(o.note) + '</span>' : '') + '</div></div><div class="row-a">' +
    (o.status === 'pending' ? '<button class="btn sm" onclick="approveOutbox(\'' + o.id + '\')">Approve</button><button class="btn ghost sm" onclick="rejectOutbox(\'' + o.id + '\')">Reject</button>' : '') +
    '<button class="btn ghost sm" onclick="viewOutboxItem(\'' + o.id + '\')">View</button></div></div>').join('') + '</div>';
}
function approveOutbox(id) {
  const o = byId('outbox', id); if (!o || o.status !== 'pending') return;
  if (!AUTH.user) { finishApprove(o, 'Not delivered in demo mode'); toast('Approved. Sign in with Google to send real email.'); return; }
  if (SENDING.has(id)) return;
  if (!gmailToken()) { askGmail(id); return; }
  sendViaGmail(id);
}
function finishApprove(o, note) {
  o.status = 'approved'; o.note = note;
  if (o.ref && o.ref.kind === 'contact') { const c = byId('contacts', o.ref.id); if (c) { c.status = 'Sent'; c.sent_on = iso(0); } }
  if (o.ref && o.ref.kind === 'request') { const r = byId('requests', o.ref.id); if (r) r.status = 'Quoted'; }
  log('Approved: ' + o.payload.subject); save(); render();
}
const SENDING = new Set();
async function sendViaGmail(id) {
  const o = byId('outbox', id); if (!o || o.status !== 'pending' || SENDING.has(id)) return;
  const to = String(o.payload.to || '').replace(/[\r\n]+/g, ' ').trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) { toast('This draft has no valid email address. Add one and try again.', true); return; }
  SENDING.add(id); toast('Sending\u2026');
  try {
    const res = await fetch('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + gmailToken(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw: buildRaw(to, o.payload.subject || '', o.payload.body || '') })
    });
    if (res.status === 401) { GMAIL.token = null; askGmail(id, 'Your Gmail session expired. Connect again to send.'); return; }
    if (!res.ok) {
      let d = ''; try { d = (await res.json()).error?.message || ''; } catch (e) {}
      if (res.status === 403 && /has not been used|is disabled|accessNotConfigured/i.test(d)) throw new Error('Gmail API is not enabled in your Google Cloud project. Enable it in APIs & Services, wait a minute, then approve again.');
      if (res.status === 403) throw new Error('Gmail permission is missing. Connect Gmail again and allow sending. ' + d);
      throw new Error('Gmail error ' + res.status + (d ? ': ' + d : ''));
    }
    finishApprove(o, 'Sent via Gmail'); toast('Sent from your Gmail');
  } catch (e) {
    toast(e && e.message ? e.message : 'Could not send. The draft is still pending.', true);
  } finally { SENDING.delete(id); }
}
function rejectOutbox(id) {
  const o = byId('outbox', id); if (!o) return;
  o.status = 'rejected'; log('Rejected: ' + o.payload.subject); save(); render(); toast('Rejected');
}
function viewOutboxItem(id) {
  const o = byId('outbox', id); if (!o) return;
  openModal('<h3>' + esc(o.payload.subject || 'Outbox item') + '</h3><div class="mail-meta"><b>To:</b> ' + esc(o.payload.to || 'No email address yet') + '</div><div class="mail">' + esc(o.payload.body || '') + '</div><div class="foot"><button class="btn ghost" onclick="closeModal()">Close</button></div>');
}
 
/* ---- Resume check ---- */
let resumeText = '';
function viewResume() {
  return head('Resume check', 'Paste a resume or project summary. OPA finds the skills it recognizes so you can add them to your matching profile.', '') +
    '<div style="max-width:720px"><div class="field"><label for="resume-text">Resume or project text</label><textarea class="resume-box" id="resume-text" placeholder="Paste resume text, a GitHub README, or a project summary" oninput="resumeText=this.value">' + esc(resumeText) + '</textarea></div><div style="display:flex;gap:10px;margin-top:14px"><button class="btn" onclick="analyzeResume()">Analyze</button><button class="btn ghost" onclick="teachResume()">Add to JARVIS memory</button><button class="btn ghost" onclick="clearResume()">Clear</button></div><div id="resume-results" style="margin-top:22px"></div></div>';
}
function analyzeResume() {
  const text = $('resume-text').value; resumeText = text;
  const el = $('resume-results');
  if (!text.trim()) { el.innerHTML = '<div class="empty plain" style="padding:30px"><p style="margin:0">Paste some text first.</p></div>'; return; }
  const lower = text.toLowerCase();
  const found = MASTER_SKILLS.filter(s => { const k = s.toLowerCase(); const i = lower.indexOf(k); if (i < 0) return false; if (k.length <= 3) { const re = new RegExp('(^|[^a-z0-9+#])' + k.replace(/[.+*?^${}()|[\]\\]/g, '\\$&') + '($|[^a-z0-9+#])', 'i'); return re.test(text); } return true; });
  const words = (text.match(/\S+/g) || []).length;
  const bullets = text.split('\n').filter(l => /^\s*[-•*–]\s+/.test(l)).length;
  const numbers = (text.match(/\d+%?/g) || []).length;
  const links = /(https?:\/\/|github\.com|linkedin\.com)/i.test(text);
  const notes = [];
  if (words < 120) notes.push('This is short (' + words + ' words). A full resume usually runs 250 words or more.');
  if (bullets < 3) notes.push('Use bullet points for accomplishments so they are easy to scan.');
  if (numbers < 3) notes.push('Add measurable results, such as users, percentages, or time saved.');
  if (!links) notes.push('Add a GitHub or portfolio link so reviewers can see your work.');
  const have = splitList(S.profile.skills).map(x => x.toLowerCase());
  el.innerHTML = '<section class="panel" style="padding:20px;margin-bottom:14px"><h3 style="font-family:var(--display);font-size:17px;margin-bottom:12px">Skills recognized (' + found.length + ')</h3>' +
    (found.length ? found.map(s => have.includes(s.toLowerCase()) ? '<span class="skill added">' + icon('check', 13) + esc(s) + '</span>' : '<button class="skill" onclick="addSkill(\'' + escA(s) + '\')">' + icon('plus', 13) + esc(s) + '</button>').join('') + '<div class="row-s" style="margin-top:6px">Select a skill to add it to your profile.</div>' : '<div class="row-s">Nothing matched the known skill list.</div>') + '</section>' +
    '<section class="panel" style="padding:20px"><h3 style="font-family:var(--display);font-size:17px;margin-bottom:4px">How the draft reads</h3><div class="row-s">' + words + ' words, ' + bullets + ' bullet lines, ' + numbers + ' numbers</div><ul class="notes">' + (notes.length ? notes : ['The structure looks solid: length, bullets, numbers, and links are all present.']).map(n => '<li>' + esc(n) + '</li>').join('') + '</ul></section>';
}
function addSkill(s) { const list = splitList(S.profile.skills); if (!list.some(x => x.toLowerCase() === s.toLowerCase())) list.push(s); S.profile.skills = list.join(', '); log('Added skill: ' + s); save(); analyzeResume(); renderNav(); toast(s + ' added to your profile'); }
function clearResume() { resumeText = ''; $('resume-text').value = ''; $('resume-results').innerHTML = ''; }
 
/* ---- History ---- */
function viewHistory() {
  const h = head('History', 'A log of everything you complete, draft, and approve.', '');
  if (!S.history.length) return h + emptyPanel('Nothing logged yet', 'Complete an item on Today or draft a message to start your history.', '');
  const days = {};
  S.history.forEach(e => { const d = e.at.slice(0, 10); (days[d] = days[d] || []).push(e); });
  return h + '<div class="tl">' + Object.keys(days).sort().reverse().map(d => {
    const label = d === iso(0) ? 'Today' : d === iso(-1) ? 'Yesterday' : new Date(d + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
    return '<div class="tl-day"><h3>' + label + '</h3>' + days[d].map(e => '<div class="tl-e"><time>' + new Date(e.at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) + '</time><span>' + esc(e.text) + '</span></div>').join('') + '</div>';
  }).join('') + '</div>';
}
 
/* ---- Profile ---- */
function viewProfile() {
  const p = S.profile;
  const f = (k, l, ph, t) => '<div class="field"><label for="p-' + k + '">' + l + '</label>' + (t === 'ta' ? '<textarea id="p-' + k + '" rows="2">' + esc(p[k]) + '</textarea>' : '<input id="p-' + k + '" type="text" value="' + escA(p[k]) + '" placeholder="' + escA(ph || '') + '">') + '</div>';
  return head('Profile', 'Used to personalize skill matching and outreach drafts.', '') +
    '<section class="panel form-panel">' + f('name', 'Name') + f('track', 'Track or year', 'e.g. B.Tech Computer Science, 3rd year') + f('github', 'GitHub', 'github.com/username') + f('email', 'Email') +
    '<div class="field"><label for="p-skills">Skills</label><input id="p-skills" type="text" value="' + escA(p.skills) + '"><div class="hint">Comma-separated. Used to score opportunities and contacts.</div></div>' +
    '<div class="field"><label for="p-highlight">Resume highlight</label><textarea id="p-highlight" rows="2">' + esc(p.highlight) + '</textarea><div class="hint">One line, used in outreach drafts.</div></div>' +
    '<button class="btn" onclick="saveProfile()">Save profile</button></section>' +
    '<section class="panel form-panel" style="margin-top:20px"><h3 style="font-family:var(--display);font-size:18px;font-weight:650;margin-bottom:8px">Data on this device</h3><p class="row-s" style="margin-bottom:16px">Everything here is stored in this browser as demo data. The backend is switched off, so nothing is sent anywhere except JARVIS calls once connected from the JARVIS tab. When the full MVP is ready, this app will read and write real records instead.</p><div class="data-actions"><button class="btn ghost" onclick="exportData()">Download backup</button><button class="btn ghost" onclick="$(\'imp\').click()">Restore from backup</button><button class="btn ghost" onclick="resetData()">Reset to sample data</button></div><input type="file" id="imp" accept="application/json,.json" hidden onchange="importData(this)"></section>' + accountPanel();
}
function saveProfile() {
  ['name','track','github','email','skills','highlight'].forEach(k => { S.profile[k] = $('p-' + k).value.trim(); });
  save(); render(); toast('Profile saved');
}
function saveGroqKey() {
  const k = $('jv-groqKey').value.trim(); const m = $('jv-groqModel').value;
  S.profile.groqKey = k; S.profile.groqModel = m; save(); render();
  toast(k ? 'Connected \u2014 JARVIS will use the live model' : 'Saved');
}
function clearGroqKey() { S.profile.groqKey = ''; save(); render(); toast('Disconnected. JARVIS is back on local replies'); }
async function testGroq() {
  toast('Testing connection\u2026');
  try {
    const r = await groqChat([{ role: 'user', content: 'Reply with just: connected' }]);
    toast(r ? 'Groq responded: ' + r.slice(0, 60) : 'No response from Groq', !r);
  } catch (e) { toast('Groq test failed: ' + e.message, true); }
}
function resetData() { confirmBox('Reset all data to the sample workspace?', 'Reset data', () => { S = seed(); save(); render(); toast('Sample data restored'); }); }
 
/* ---- Groq (optional live JARVIS) ---- */
const GROQ_MODELS = [
  { v: 'openai/gpt-oss-120b', l: 'GPT-OSS 120B (best quality)' },
  { v: 'openai/gpt-oss-20b', l: 'GPT-OSS 20B (fastest)' },
  { v: 'qwen/qwen3.6-27b', l: 'Qwen3.6 27B' }
];
async function groqChat(messages) {
  const key = S.profile.groqKey; if (!key) return null;
  const model = S.profile.groqModel || GROQ_MODELS[0].v;
  const res = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key },
    body: JSON.stringify({ model, messages, temperature: 0.6, max_tokens: 1000 })
  });
  if (!res.ok) { let d = ''; try { d = (await res.json()).error?.message || ''; } catch (e) {} throw new Error(res.status + (d ? ' \u2014 ' + d : '')); }
  const data = await res.json();
  return data.choices?.[0]?.message?.content || '';
}
function workspaceSnapshot() {
  const plan = buildPlan();
  const lines = [];
  lines.push('Today\u2019s queued plan (' + plan.length + ' items, ' + fmtMins(plan.reduce((s, i) => s + i.effort, 0)) + '): ' + (plan.map(i => i.name).join('; ') || 'nothing queued'));
  lines.push('Open applications: ' + S.applications.filter(a => ['Not started', 'Applied', 'Interview'].includes(a.status)).map(a => a.company + ' (' + a.status + (a.deadline ? ', ' + fmtDue(a.deadline) : '') + ')').join('; ') || 'none');
  lines.push('Contacts awaiting a first email: ' + S.contacts.filter(c => c.status === 'Not started').map(c => c.name).join(', ') || 'none');
  lines.push('Open projects: ' + S.projects.map(p => p.name + ' (' + p.tasks.filter(t => !t.done).length + ' open tasks)').join('; ') || 'none');
  lines.push('Open client requests: ' + S.requests.filter(r => ['New', 'Scoped'].includes(r.status)).map(r => r.client + ': ' + r.ask).join('; ') || 'none');
  lines.push('Upcoming exams: ' + S.academics.filter(a => !a.done).map(a => a.subject + (a.exam_date ? ' (' + fmtDate(a.exam_date) + ')' : '')).join('; ') || 'none');
  return lines.join('\n');
}
 
/* ---- JARVIS ---- */
let CHAT = [];
const PROMPTS = ['What should I focus on today?', 'Summarize my applications and deadlines.', 'Which projects need attention?', 'Help me plan the next 3 hours.'];
function viewJarvis() {
  const live = !!S.profile.groqKey;
  const gm = S.profile.groqModel || GROQ_MODELS[0].v;
  const connectBanner = live ? '' :
    '<div style="padding:14px 18px;border-bottom:1px solid var(--line);background:var(--surface-2)">' +
    '<div class="row-s" style="margin-bottom:10px">Connect a Groq API key to swap these canned replies for a real model. Saved only in this browser \u2014 sent straight to Groq, never through any server of ours.</div>' +
    '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end">' +
    '<div style="flex:1;min-width:180px"><input id="jv-groqKey" type="password" placeholder="gsk_..." autocomplete="off"></div>' +
    '<select id="jv-groqModel" style="width:auto">' + GROQ_MODELS.map(m => '<option value="' + m.v + '">' + m.l + '</option>').join('') + '</select>' +
    '<button class="btn sm" onclick="saveGroqKey()">Connect</button></div></div>';
  return head('JARVIS', 'Your operating copilot. Ask about today\u2019s work, applications, projects, outreach, or what to do next.', '') +
    '<div class="jv"><section class="panel jv-main"><div class="jv-top"><div class="orb"></div><div><b>JARVIS</b><span>' + (live ? 'Live on Groq \u00b7 ' + escA(gm) : 'Answering from your workspace data') + '</span></div>' +
    (live ? '<span class="pill good" style="margin-left:auto;margin-right:10px">Live</span><button class="btn ghost sm" onclick="clearGroqKey()" title="Disconnect Groq">Disconnect</button>' : '<span class="pill" style="margin-left:auto;margin-right:10px">Local</span>') +
    '<button class="btn ghost sm" onclick="jarvisNew()">New chat</button></div>' +
    connectBanner +
    '<div class="msgs" id="msgs">' + (CHAT.length ? CHAT.map(bubbleHTML).join('') : welcomeHTML()) + '</div>' +
    '<div class="composer"><div class="cbox"><textarea id="jv-input" rows="1" placeholder="Ask JARVIS about your workspace" aria-label="Message JARVIS"></textarea><button class="send" onclick="jarvisSend()" aria-label="Send message">' + icon('up', 17) + '</button></div></div></section>' +
    '<aside class="panel jv-ctx"><h3>Workspace right now</h3><div id="ctx"></div><div class="ctx-note">' + (live ? 'Connected to Groq (' + escA(gm) + '). Use Test or Disconnect from the chat header.' : 'Local mode: answers come from searching your workspace. Connect a Groq key for full written answers.') + '</div></aside></div>';
}
function welcomeHTML() { return '<div class="welcome" id="welcome"><h2>What should we work on?</h2><p>Pick a starting point or type your own question below.</p><div class="prompts">' + PROMPTS.map(p => '<button onclick="jarvisSend(this.textContent)">' + esc(p) + '</button>').join('') + '</div></div>'; }
function fmtMsg(t) { return esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>'); }
function bubbleHTML(m) {
  const src = m.sources && m.sources.length ? '<div class="srcs">' + m.sources.map(x => '<button class="chip src" onclick="switchTab(\'' + x.tab + '\')" title="Open ' + escA(x.tab) + '">' + (x.n ? x.n + ' \u00b7 ' : '') + esc(x.label) + '</button>').join('') + '</div>' : '';
  return '<div class="m ' + (m.role === 'user' ? 'you' : '') + '"><div class="bubble">' + fmtMsg(m.text) + src + '</div></div>';
}
function ctxHTML() {
  const plan = buildPlan(); const mins = plan.reduce((s, i) => s + i.effort, 0);
  const rows = [['Queued today', fmtMins(mins)], ['Open applications', S.applications.filter(a => ['Not started','Applied','Interview'].includes(a.status)).length], ['Emails to write', S.contacts.filter(c => c.status === 'Not started').length], ['Open requests', S.requests.filter(r => r.status === 'New' || r.status === 'Scoped').length], ['Awaiting approval', S.outbox.filter(o => o.status === 'pending').length]];
  let ix = { N: 0 }; try { ix = ragIndex(); } catch (e) {}
  return rows.map(r => '<div class="ctx-row"><span>' + r[0] + '</span><b>' + r[1] + '</b></div>').join('') +
    '<h3 style="margin-top:16px">JARVIS memory</h3><div class="ctx-row"><span>Indexed records</span><b>' + ix.N + '</b></div><div class="ctx-row"><span>Notes you taught</span><b>' + kb().length + '</b></div>' +
    '<button class="btn ghost sm" style="margin-top:10px;width:100%" onclick="teachOpen()">Teach JARVIS</button>';
}
function refreshCtx() { const el = $('ctx'); if (el) el.innerHTML = ctxHTML(); }
function jarvisNew() { CHAT = []; $('msgs').innerHTML = welcomeHTML(); }
/* ---- JARVIS quick-create: chat -> real records ---- */
function extractDate(s) {
  const MON = 'jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec';
  const DOWS = { sun:0, mon:1, tue:2, tues:2, wed:3, thu:4, thur:4, thurs:4, fri:5, sat:6 };
  const lead = '(?:\\b(?:by|due|on|before|deadline)\\s+)?';
  const mi = (n) => ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(String(n).slice(0, 3).toLowerCase());
  const fromMD = (mon, day) => {
    const now = new Date(); let d = new Date(now.getFullYear(), mi(mon), +day);
    if (d < new Date(now.getFullYear(), now.getMonth(), now.getDate())) d = new Date(now.getFullYear() + 1, mi(mon), +day);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  };
  const rules = [
    [/(\d{4}-\d{2}-\d{2})/, (m) => m[1]],
    [/day after tomorrow/i, () => iso(2)],
    [/tomorrow/i, () => iso(1)],
    [/today/i, () => iso(0)],
    [/in (\d+) days?/i, (m) => iso(+m[1])],
    [/next week/i, () => iso(7)],
    [/(?:next\s+|this\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday|sun|mon|tues|tue|wed|thurs|thur|thu|fri|sat)/i, (m) => {
      const want = DOWS[m[1].slice(0, m[1].length > 3 && !/^(tues|thur|thurs)$/i.test(m[1]) ? 3 : m[1].length).toLowerCase()];
      let add = (want - new Date().getDay() + 7) % 7; if (add === 0) add = 7; return iso(add);
    }],
    [new RegExp('(\\d{1,2})(?:st|nd|rd|th)?\\s+(' + MON + ')[a-z]*', 'i'), (m) => fromMD(m[2], m[1])],
    [new RegExp('(' + MON + ')[a-z]*\\s+(\\d{1,2})(?:st|nd|rd|th)?', 'i'), (m) => fromMD(m[1], m[2])]
  ];
  for (const [re, fn] of rules) {
    const m = s.match(new RegExp(lead + '\\b' + re.source + '\\b', 'i'));
    if (m) {
      const parts = m.slice(0);
      const date = fn(re.exec(m[0].replace(/^(?:by|due|on|before|deadline)\s+/i, '')) || parts.slice(0));
      return { date, rest: s.replace(m[0], ' ').replace(/\s{2,}/g, ' ').replace(/[\s,;:-]+$/, '').trim() };
    }
  }
  return { date: null, rest: s.trim() };
}
const QC_TYPES = ['application', 'task', 'project', 'study', 'request', 'contact', 'mail'];
function parseQuick(text) {
  const t = text.trim().replace(/[.!]+$/, ''); let m;
  const V = '(?:please\\s+)?(?:add|create|make|track|log|new)\\s+';
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?(?:(internship|research|hackathon)\\s+)?application\\s+(?:to|for|at|with)\\s+(.+)$', 'i')))) {
    const d = extractDate(m[2]);
    const sp = d.rest.split(/\s+(?:for|as)\s+(?:an?\s+|the\s+)?/i);
    const company = sp[0].trim(), role = sp.slice(1).join(' for ').trim();
    const blob = (m[1] || '') + ' ' + d.rest;
    const type = /hackathon/i.test(blob) ? 'Hackathon' : /research|lab\b|\bra\b/i.test(blob) ? 'Research' : 'Internship';
    return { type: 'application', data: { company, role, type: type, deadline: d.date } };
  }
  if ((m = t.match(new RegExp('^' + V + '(?:another\\s+|an?\\s+)?(?:new\\s+)?(?:block|card|entry|row|item)?\\s*(?:in|to|into)\\s+(?:the\\s+)?applications?\\s+(.+)$', 'i')))) {
    const d = extractDate(m[1].replace(/^["'\u201c\u201d]+|["'\u201c\u201d]+$/g, ''));
    const type = /hackathon/i.test(d.rest) ? 'Hackathon' : /research|lab\b/i.test(d.rest) ? 'Research' : 'Internship';
    return { type: 'application', data: { company: d.rest.replace(/^["'\u201c\u201d]+|["'\u201c\u201d]+$/g, ''), role: '', type, deadline: d.date } };
  }
  if ((m = t.match(/^\s*(?:please\s+)?(?:write|draft|compose|send)\s+(?:an?\s+)?(?:e-?mail|mail)\s+(?:to|for)\s+(.+)$/i)))
    return { type: 'mail', data: { to: m[1].trim() } };
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?task\\s+(.+?)\\s+(?:to|in|into|for|under)\\s+(?:the\\s+)?(.+?)(?:\\s+project)?$', 'i'))))
    return { type: 'task', data: { name: m[1].replace(/^["'\u201c]|["'\u201d]$/g, '').trim(), project: m[2].trim() } };
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?project\\s+(?:called\\s+|named\\s+)?(.+)$', 'i'))))
    return { type: 'project', data: { name: m[1].trim() } };
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?(?:study|exam|academic)(?:\\s+(?:task|item|reminder))?\\s*(?:for|on|:)?\\s*(.+)$', 'i')))) {
    const d = extractDate(m[1]); const sp = d.rest.split(/\s*[:\u2014]\s*|\s+-\s+/);
    const subject = sp[0].trim(); const task = sp.slice(1).join(': ').trim() || ('Revise ' + subject);
    return { type: 'study', data: { subject, task, exam_date: d.date } };
  }
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?(?:client\\s+)?(?:request|lead)\\s+(?:from|for)\\s+(.+?)(?:\\s*:\\s*|\\s+(?:to|needs?|wants?|for)\\s+)(.+)$', 'i'))))
    return { type: 'request', data: { client: m[1].trim(), ask: m[2].replace(/^(?:needs?|wants?)\s+/i, '').trim() } };
  if ((m = t.match(new RegExp('^' + V + '(?:an?\\s+)?(?:new\\s+)?(?:contact|professor|prof)\\s+(.+)$', 'i')))) {
    let rest = m[1]; const em = rest.match(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/); if (em) rest = rest.replace(em[0], ' ').replace(/\s{2,}/g, ' ').trim();
    const sp = rest.split(/\s+(?:at|from|@)\s+/i);
    return { type: 'contact', data: { name: sp[0].replace(/[,\s]+$/, '').trim(), institute: (sp[1] || '').trim(), email: em ? em[0] : '' } };
  }
  return null;
}
/* Pull "ACTION: {...}" out of a model reply. Brace-balanced and string-aware, so nested data:{...} objects survive. */
function extractAction(reply) {
  const i = reply.search(/ACTION\s*:/i); if (i < 0) return { text: reply, action: null };
  const start = reply.indexOf('{', i); if (start < 0) return { text: reply.slice(0, i).trim(), action: null };
  let depth = 0, inStr = false, esc = false, end = -1;
  for (let k = start; k < reply.length; k++) {
    const c = reply[k];
    if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === '"') inStr = false; continue; }
    if (c === '"') inStr = true; else if (c === '{') depth++; else if (c === '}') { depth--; if (depth === 0) { end = k; break; } }
  }
  const text = (reply.slice(0, i) + (end > -1 ? reply.slice(end + 1) : '')).replace(/```(?:json)?\s*```/g, '').replace(/\s+$/, '').trim();
  if (end < 0) return { text, action: null };
  try { const a = JSON.parse(reply.slice(start, end + 1)); return { text, action: a.data ? a : (a.type ? { type: a.type, data: a } : null) }; } catch (e) { return { text, action: null }; }
}
function execAction(a) {
  if (!a || !QC_TYPES.includes(a.type) || !a.data) return null;
  const s = (v) => (v == null ? '' : String(v).trim()); const d = a.data; const dt = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(s(v)) ? s(v) : null);
  const due = (v) => (v ? ' (' + fmtDue(v).toLowerCase() + ')' : '');
  if (a.type === 'application') {
    if (!s(d.company)) return 'I need a company name to add an application.';
    const type = ['Internship', 'Research', 'Hackathon'].includes(d.type) ? d.type : 'Internship';
    upsert('applications', { company: s(d.company), role: s(d.role), type, deadline: dt(d.deadline), status: 'Not started', effort_min: 60, notes: s(d.notes) });
    log('Added application: ' + s(d.company)); renderNav();
    return 'Added **' + s(d.company) + '**' + (s(d.role) ? ' \u2014 ' + s(d.role) : '') + ' to Applications' + due(dt(d.deadline)) + '.';
  }
  if (a.type === 'task') {
    const q = s(d.project).toLowerCase(); if (!s(d.name)) return 'What should the task say?';
    const p = S.projects.find(x => x.name.toLowerCase() === q) || S.projects.find(x => x.name.toLowerCase().includes(q) || (q && q.includes(x.name.toLowerCase())));
    if (!p) return 'I could not find a project matching "' + s(d.project) + '". Your projects: ' + (S.projects.map(x => x.name).join(', ') || 'none yet') + '. Say "create project ' + s(d.project) + '" first.';
    p.tasks.push({ id: uid(), name: s(d.name), done: false }); log('Added task: ' + s(d.name)); save(); renderNav();
    return 'Added task **' + s(d.name) + '** to **' + p.name + '**.';
  }
  if (a.type === 'project') {
    if (!s(d.name)) return 'What should the project be called?';
    upsert('projects', { name: s(d.name), description: s(d.description), tasks: [] }); log('Added project: ' + s(d.name)); renderNav();
    return 'Created project **' + s(d.name) + '**. Say "add task X to ' + s(d.name) + '" to fill it.';
  }
  if (a.type === 'study') {
    if (!s(d.subject)) return 'Which subject is this for?';
    upsert('academics', { subject: s(d.subject), task: s(d.task) || 'Revise ' + s(d.subject), exam_date: dt(d.exam_date), effort_min: 60, done: false }); log('Added study task: ' + s(d.subject)); renderNav();
    return 'Added a study task for **' + s(d.subject) + '** in Academics' + due(dt(d.exam_date)) + '.';
  }
  if (a.type === 'request') {
    if (!s(d.client)) return 'Which client is this from?';
    upsert('requests', { client: s(d.client), ask: s(d.ask), scope: '', timeline: s(d.timeline), price: '', email: s(d.email), status: 'New' }); log('Added client request: ' + s(d.client)); renderNav();
    return 'Logged a client request from **' + s(d.client) + '**.';
  }
  if (a.type === 'mail') {
    const to = s(d.to); const em = (to.match(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/) || [])[0] || '';
    let c = em ? S.contacts.find(x => (x.email || '').toLowerCase() === em.toLowerCase()) : S.contacts.find(x => x.name.toLowerCase().includes(to.toLowerCase()));
    if (!c) {
      if (!em) return 'I could not find a contact called "' + to + '". Give me an email address, or add the contact first.';
      const nm = em.split('@')[0].replace(/[._\d]+/g, ' ').trim().replace(/\b\w/g, ch => ch.toUpperCase()) || em;
      upsert('contacts', { name: nm, institute: '', area: '', tags: '', email: em, status: 'Not started', sent_on: null });
      c = S.contacts[0]; log('Added contact: ' + nm);
    }
    draftOutreach(c.id);
    return 'Drafted an email to **' + c.name + '** (' + (c.email || 'no email') + '). It is in your Outbox awaiting approval.';
  }
  if (a.type === 'contact') {
    if (!s(d.name)) return 'What is the contact\u2019s name?';
    upsert('contacts', { name: s(d.name), institute: s(d.institute), area: s(d.area), tags: s(d.tags), email: s(d.email), status: 'Not started', sent_on: null }); log('Added contact: ' + s(d.name)); renderNav();
    return 'Added **' + s(d.name) + '** to Outreach' + (s(d.email) ? '' : ' (no email yet)') + '.';
  }
  return null;
}
function quickCreate(text) { const a = parseQuick(text); return a ? execAction(a) : null; }
 
async function jarvisSend(text) {
  const input = $('jv-input');
  const t = (text || (input ? input.value : '')).trim(); if (!t) return;
  if (input) { input.value = ''; input.style.height = 'auto'; }
  const box = $('msgs'); const w = $('welcome'); if (w) w.remove();
  CHAT.push({ role: 'user', text: t }); box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'user', text: t }));
  box.insertAdjacentHTML('beforeend', '<div class="m" id="typing"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>');
  box.scrollTop = box.scrollHeight;
  const finish = (reply, sources) => {
    const ty = $('typing'); if (ty) ty.remove();
    const m = { role: 'assistant', text: reply, sources: sources || [] };
    CHAT.push(m); box.insertAdjacentHTML('beforeend', bubbleHTML(m));
    box.scrollTop = box.scrollHeight; refreshCtx();
  };
  const rem = t.match(/^\s*(?:remember(?:\s+that)?|note(?:\s+that|:)|save\s+(?:this|that)\s*:?)\s*[:,\-]?\s*([\s\S]{4,})$/i);
  if (rem) { teachAdd('', rem[1]); setTimeout(() => finish('Saved to my memory: \u201c' + rem[1].trim().slice(0, 120) + '\u201d. Ask me about it any time.'), 250); return; }
  const qc = quickCreate(t);
  if (qc) { setTimeout(() => finish(qc), 250); return; }
  if (S.profile.groqKey) {
    let reply, sources = [];
    try {
      const ctx = ragContext(t);
      const sys = 'You are JARVIS, the AI copilot inside OPA, ' + (S.profile.name || 'the user') + '\u2019s personal operating agent. ' +
        'Answer ONLY from the WORKSPACE SUMMARY and RETRIEVED RECORDS below. Cite the records you use as [n]. If the answer is not in them, say you do not have that in the workspace and suggest the user tell you with "remember that ...". Never invent names, dates, numbers, or statuses. Be direct and brief \u2014 a few sentences or a short list, not an essay. ' +
        'You cannot send emails or apply anywhere. You CAN create records. When the user asks you to add/create something, confirm in one short sentence and end your reply with one line: ACTION: {"type":"<application|task|project|study|request|contact|mail>","data":{...}}. ' +
        'Data fields: application {company, role, type: Internship|Research|Hackathon, deadline: YYYY-MM-DD or null}; task {name, project}; mail {to: email or contact name}; project {name}; study {subject, task, exam_date: YYYY-MM-DD or null}; request {client, ask}; contact {name, institute, email}. Only emit ACTION when the user clearly asked to create something.\n\n' + ctx.text;
      const msgs = [{ role: 'system', content: sys }, ...CHAT.slice(-10).map(m => ({ role: m.role, content: m.text }))];
      reply = await groqChat(msgs);
      if (!reply) reply = jarvisReply(t) || JV_GENERIC;
      else {
        const ex = extractAction(reply);
        if (ex.action) { const done = execAction(ex.action); reply = (ex.text ? ex.text + '\n\n' : '') + (done || 'I could not create that record.'); } else reply = ex.text;
        const cited = [...new Set((reply.match(/\[(\d+)\]/g) || []).map(x => +x.slice(1, -1)))];
        sources = cited.map(n => ctx.hits[n - 1] && { n, label: ctx.hits[n - 1].doc.title, tab: R_TYPE_TAB[ctx.hits[n - 1].doc.type] || 'today' }).filter(Boolean);
      }
    } catch (e) { const r = ragLocalAnswer(t); reply = 'Groq call failed (' + e.message + '). From your workspace instead:\n\n' + r.text; sources = r.sources; }
    finish(reply, sources);
    return;
  }
  setTimeout(() => {
    const q = ragQuery(t);
    const strongNote = ragSearch(q, 3).find(h => h.doc.type === 'note' && h.raw > 0 && h.score >= 0.5);
    if (ragEntities(q).length || strongNote || ragSpecific(q)) { const r = ragLocalAnswer(t); finish(r.text, r.sources); return; }
    const canned = jarvisReply(t);
    if (canned) { finish(canned, []); return; }
    const r = ragLocalAnswer(t); finish(r.hitsNone ? JV_GENERIC : r.text, r.sources);
  }, 450);
}
function clockStrOf(d) { return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); }
const JV_GENERIC = 'I can help with your plan, applications, projects, outreach, client requests, and study tasks. Try "What should I focus on today?" or "Help me plan the next 3 hours."';
function jarvisReply(text) {
  const t = text.toLowerCase(); const plan = buildPlan();
  if (/(3 hours|three hours|next 3|schedule)/.test(t)) {
    if (!plan.length) return 'Your queue is empty, so the next three hours are open. Add an application, contact, or project task and I will build a schedule around it.';
    let cur = new Date(); cur.setMinutes(Math.ceil(cur.getMinutes() / 15) * 15, 0, 0); let left = 180; const lines = [];
    for (const i of plan) { const m = Math.min(i.effort, left); if (m < 10) break; lines.push('**' + clockStrOf(cur) + '** ' + i.name + ' (' + fmtMins(m) + ')'); cur = new Date(cur.getTime() + m * 60000); left -= m; if (left <= 0) break; }
    return 'Here is a plan for the next three hours, most urgent first:\n\n' + lines.join('\n') + (left > 0 ? '\n\nThat leaves about ' + fmtMins(left) + ' of buffer.' : '');
  }
  if (/(focus|today|first|what should|next)/.test(t)) {
    if (!plan.length) return 'Nothing is queued today. A good use of a free day: draft an outreach email or add tasks to a project.';
    const top = plan.slice(0, 3).map((i, n) => (n + 1) + '. **' + i.name + '**, ' + i.sub + ' (' + fmtMins(i.effort) + ')').join('\n');
    return 'Start with the most urgent items:\n\n' + top + '\n\nThe full plan is about ' + fmtMins(plan.reduce((s, i) => s + i.effort, 0)) + ' of work.';
  }
  if (/(application|deadline|apply)/.test(t)) {
    const open = S.applications.filter(a => ['Not started','Applied','Interview'].includes(a.status));
    if (!open.length) return 'You have no open applications. Add one from the Applications tab.';
    const soon = open.filter(a => a.deadline).sort((a, b) => a.deadline.localeCompare(b.deadline)).slice(0, 3).map(a => '• **' + a.company + '** (' + a.status.toLowerCase() + '): ' + fmtDue(a.deadline).toLowerCase()).join('\n');
    const c = (s) => S.applications.filter(a => a.status === s).length;
    return 'You have ' + open.length + ' open applications: ' + c('Not started') + ' not started, ' + c('Applied') + ' applied, ' + c('Interview') + ' in interview stage.\n\nNearest deadlines:\n' + soon;
  }
  if (/project|task/.test(t)) {
    const ps = S.projects.map(p => ({ p, left: p.tasks.filter(x => !x.done).length })).filter(x => x.left).sort((a, b) => b.left - a.left);
    if (!ps.length) return 'Every project is caught up. Add new tasks to keep the planner fed.';
    return 'Projects with the most open work:\n\n' + ps.slice(0, 3).map(x => '• **' + x.p.name + '**: ' + x.left + ' open, next up "' + x.p.tasks.find(k => !k.done).name + '"').join('\n');
  }
  if (/(outreach|email|contact|professor)/.test(t)) {
    const n = S.contacts.filter(c => c.status === 'Not started'); const d = S.contacts.filter(c => c.status === 'Drafted').length;
    return n.length ? 'You have ' + n.length + ' contact' + (n.length > 1 ? 's' : '') + ' waiting for a first email, starting with **' + n[0].name + '**.' + (d ? ' ' + d + ' draft' + (d > 1 ? 's are' : ' is') + ' also waiting for approval.' : '') : 'No first emails are pending.' + (d ? ' ' + d + ' draft(s) need approval in the Outbox.' : '');
  }
  if (/(request|client|proposal)/.test(t)) {
    const r = S.requests.filter(x => x.status === 'New' || x.status === 'Scoped');
    return r.length ? 'Open client requests:\n\n' + r.map(x => '• **' + x.client + '** (' + x.status.toLowerCase() + '): ' + x.ask).join('\n') : 'No open client requests right now.';
  }
  if (/(exam|study|academic)/.test(t)) {
    const a = S.academics.filter(x => !x.done).sort((p, q) => (p.exam_date ? daysUntil(p.exam_date) : 999) - (q.exam_date ? daysUntil(q.exam_date) : 999));
    return a.length ? 'Study priorities:\n\n' + a.slice(0, 3).map(x => '• **' + x.subject + '**: ' + x.task + (x.exam_date ? ' (exam ' + fmtDate(x.exam_date) + ')' : '')).join('\n') : 'No pending study tasks.';
  }
  return null;
}
 
/* ================= JARVIS RAG (runs in the browser) ================= */
const R_STOP = new Set('a an the and or of to in on for with at by from is are was were be been it this that these those as i my me we our you your they their he she his her its into over under about can could should would will do does did have has had not no yes so if then than also just more most some any all what which who whom how when where why tell show give list please jarvis work working want need get make know find like use going'.split(' '));
const R_GENERIC = new Set(['dr', 'prof', 'lab', 'labs', 'group', 'institute', 'university', 'research', 'team', 'entry', 'technology', 'the', 'and', 'college', 'school', 'of', 'ai']);
const R_SYN = {
  email: ['mail', 'outreach', 'draft', 'outbox'], mail: ['email', 'outbox', 'draft'], job: ['internship', 'role', 'application', 'opportunity'],
  intern: ['internship'], apply: ['application', 'deadline'], deadline: ['due', 'closes'], due: ['deadline'], exam: ['academic', 'study', 'subject'],
  study: ['academic', 'subject', 'exam'], client: ['request', 'proposal'], freelance: ['request', 'client'], professor: ['contact', 'outreach', 'faculty'],
  prof: ['contact'], faculty: ['contact', 'professor'], skill: ['profile', 'skills'], resume: ['resume', 'profile', 'highlight'], task: ['project'],
  todo: ['task', 'project'], approve: ['outbox', 'pending'], sent: ['outbox'], remind: ['deadline'], fellowship: ['opportunity'], hackathon: ['application']
};
const R_TYPES = {
  application: /applic|apply|applied|intern|deadline|interview|hackathon/i, opportunity: /opportun|fellowship|\brole|\bjob/i,
  contact: /professor|\bprof\b|contact|outreach|faculty|reach out/i, project: /project|\btask|todo|milestone/i,
  academic: /\bexam|study|academ|subject|revis/i, request: /client|request|proposal|freelanc/i,
  outbox: /outbox|draft|approv|\bsent\b|e?mail/i, profile: /\bskill|profile|resume|about me|who am i|my name|github/i,
  note: /\bnote|remember|told you|i said|my \w*(cgpa|gpa|goal|plan)/i, history: /history|yesterday|last week|did i|what happened|activity|\blog\b/i
};
const R_TYPE_LABEL = { profile: 'Profile', application: 'Application', opportunity: 'Opportunity', contact: 'Contact', project: 'Project', academic: 'Academics', request: 'Client request', outbox: 'Outbox', history: 'History', note: 'Note', plan: 'Today' };
const R_TYPE_TAB = { profile: 'profile', application: 'applications', opportunity: 'opportunities', contact: 'outreach', project: 'projects', academic: 'academics', request: 'requests', outbox: 'outbox', history: 'history', note: 'jarvis', plan: 'today' };

function rStem(w) {
  if (w.length > 4 && w.endsWith('ies')) w = w.slice(0, -3) + 'y';
  else if (w.length > 4 && w.endsWith('ied')) w = w.slice(0, -3) + 'y';
  else if (w.length > 3 && w.endsWith('s') && !w.endsWith('ss')) w = w.slice(0, -1);
  if (w.length > 5 && w.endsWith('ing')) w = w.slice(0, -3);
  else if (w.length > 4 && w.endsWith('ed')) w = w.slice(0, -2);
  if (w.length > 6 && w.endsWith('ion')) w = w.slice(0, -3);
  if (w.length > 4 && w.endsWith('e')) w = w.slice(0, -1);
  return w;
}
(function () { const o = {}; Object.keys(R_SYN).forEach(k => { o[rStem(k)] = R_SYN[k].map(rStem); }); Object.keys(R_SYN).forEach(k => delete R_SYN[k]); Object.assign(R_SYN, o); })();
function rTok(t) { return (String(t || '').toLowerCase().match(/[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]/g) || []).filter(w => !R_STOP.has(w)).map(rStem); }
function rTri(w) { const s = '  ' + w + ' ', o = new Set(); for (let i = 0; i < s.length - 2; i++) o.add(s.slice(i, i + 3)); return o; }
function rSim(a, b) { const A = rTri(a), B = rTri(b); let n = 0; A.forEach(x => { if (B.has(x)) n++; }); return n / (A.size + B.size - n || 1); }
function rChunk(text, max) {
  text = String(text || '').trim(); max = max || 500; if (!text) return [];
  const parts = text.split(/\n\s*\n|\n(?=[-\u2022*]\s)/).map(x => x.trim()).filter(Boolean), out = []; let cur = '';
  const push = (u) => { if (cur && cur.length + u.length + 1 > max) { out.push(cur); cur = u; } else cur = (cur ? cur + '\n' : '') + u; };
  for (const p of parts) {
    if (p.length <= max) { push(p); continue; }
    for (const s of p.split(/(?<=[.!?])\s+/)) { if (s.length > max) { for (let i = 0; i < s.length; i += max) push(s.slice(i, i + max)); } else push(s); }
  }
  if (cur) out.push(cur); return out;
}
const dueWords = (d) => { if (!d) return ''; const n = daysUntil(d); return n < 0 ? 'overdue by ' + (-n) + ' days' : n === 0 ? 'due today' : n === 1 ? 'due tomorrow' : 'due in ' + n + ' days (' + fmtDate(d) + ')'; };
function kb() { if (!Array.isArray(S.knowledge)) S.knowledge = []; return S.knowledge; }

/* Build every document from the workspace. `text` is indexed; `line` is what the user reads. */
function ragDocs() {
  const docs = [];
  const add = (type, title, text, line, o) => docs.push(Object.assign({ id: type + ':' + docs.length, type, title, text, line: line || text, names: [], due: null, boost: 1 }, o || {}));
  const p = S.profile || {};
  add('profile', 'Your profile', ['Name: ' + p.name, p.track && 'Track: ' + p.track, p.github && 'GitHub: ' + p.github, p.email && 'Email: ' + p.email, 'Skills: ' + p.skills, p.highlight && 'Highlight: ' + p.highlight].filter(Boolean).join('. '),
    '**' + (p.name || 'You') + '**' + (p.track ? ', ' + p.track : '') + '. Skills: ' + (p.skills || 'none listed') + '.' + (p.highlight ? ' ' + p.highlight : ''), { names: [p.name] });
  const plan = buildPlan();
  add('plan', 'Today\u2019s plan', 'Today plan focus queue: ' + (plan.map(i => i.name + ' (' + i.sub + ')').join('; ') || 'nothing queued'), plan.length ? 'Today\u2019s queue: ' + plan.slice(0, 5).map(i => '**' + i.name + '**').join(', ') + '.' : 'Nothing is queued today.');
  (S.applications || []).forEach(a => add('application', a.company + ' \u2014 ' + a.role,
    ['Application', a.company, a.role, a.type, 'status ' + a.status, dueWords(a.deadline), a.effort_min && 'effort ' + fmtMins(a.effort_min), a.notes && 'notes: ' + a.notes].filter(Boolean).join('. '),
    '**' + a.company + '**, ' + a.role + ' (' + a.type + '). Status: ' + String(a.status).toLowerCase() + '.' + (a.deadline ? ' ' + dueWords(a.deadline).replace(/^./, c => c.toUpperCase()) + '.' : '') + (a.notes ? ' Note: ' + a.notes : ''), { names: [a.company], due: a.deadline && !['Rejected', 'Offer', 'Withdrawn'].includes(a.status) ? daysUntil(a.deadline) : null }));
  (S.opportunities || []).forEach(o => add('opportunity', o.title + ' \u2014 ' + o.org,
    ['Opportunity', o.title, o.org, o.type, 'tags ' + o.tags, 'status ' + o.status, dueWords(o.deadline), 'skill match ' + matchScore(o.tags, p.skills) + '%'].filter(Boolean).join('. '),
    '**' + o.title + '** at ' + o.org + ' (' + o.type + '). ' + matchScore(o.tags, p.skills) + '% skill match.' + (o.deadline ? ' ' + dueWords(o.deadline).replace(/^./, c => c.toUpperCase()) + '.' : ''), { names: [o.org, o.title], due: o.deadline ? daysUntil(o.deadline) : null }));
  (S.contacts || []).forEach(c => add('contact', c.name + ' \u2014 ' + c.institute,
    ['Contact professor faculty', c.name, c.institute, c.area && 'research area ' + c.area, c.tags && 'tags ' + c.tags, 'outreach status ' + c.status, c.sent_on && 'emailed on ' + c.sent_on, c.email, 'skill match ' + matchScore(c.tags, p.skills) + '%'].filter(Boolean).join('. '),
    '**' + c.name + '**, ' + c.institute + (c.area ? ' (' + c.area + ')' : '') + '. Outreach: ' + String(c.status).toLowerCase() + (c.sent_on ? ' on ' + fmtDate(c.sent_on) : '') + '. ' + matchScore(c.tags, p.skills) + '% skill match.', { names: [c.name, c.institute] }));
  (S.projects || []).forEach(pr => {
    const open = (pr.tasks || []).filter(t => !t.done), done = (pr.tasks || []).filter(t => t.done);
    add('project', pr.name, ['Project', pr.name, pr.description, open.length && 'open tasks: ' + open.map(t => t.name).join('; '), done.length && 'done tasks: ' + done.map(t => t.name).join('; ')].filter(Boolean).join('. '),
      '**' + pr.name + '**: ' + done.length + ' of ' + (pr.tasks || []).length + ' tasks done.' + (open.length ? ' Open: ' + open.map(t => t.name).join('; ') + '.' : ' All caught up.'), { names: [pr.name] });
  });
  (S.academics || []).forEach(a => add('academic', a.subject,
    ['Academics study exam', a.subject, a.task, a.exam_date && 'exam ' + dueWords(a.exam_date), a.done ? 'done' : 'pending'].filter(Boolean).join('. '),
    '**' + a.subject + '**: ' + a.task + (a.exam_date ? '. Exam ' + dueWords(a.exam_date) : '') + (a.done ? ' (done)' : ''), { names: [a.subject], due: !a.done && a.exam_date ? daysUntil(a.exam_date) : null }));
  (S.requests || []).forEach(r => add('request', r.client + ' \u2014 ' + r.ask,
    ['Client request proposal', r.client, r.ask, r.scope && 'scope ' + r.scope, r.timeline && 'timeline ' + r.timeline, r.price && 'price ' + r.price, 'status ' + r.status, r.email].filter(Boolean).join('. '),
    '**' + r.client + '**: ' + r.ask + '. Status: ' + String(r.status).toLowerCase() + (r.timeline ? ', timeline ' + r.timeline : '') + '.', { names: [r.client] }));
  (S.outbox || []).forEach(o => {
    const head = 'Outbox email ' + o.status + '. To ' + (o.payload.to || 'no address') + '. Subject: ' + (o.payload.subject || '(none)');
    rChunk(o.payload.body || '', 450).forEach((ch, i, arr) => add('outbox', (o.payload.subject || 'Email') + (arr.length > 1 ? ' (part ' + (i + 1) + ')' : ''), head + '. ' + ch,
      '**' + (o.payload.subject || '(no subject)') + '** to ' + (o.payload.to || 'no address') + ', ' + o.status + (o.note ? ' (' + o.note + ')' : '') + '.'));
    if (!(o.payload.body || '').trim()) add('outbox', o.payload.subject || 'Email', head, '**' + (o.payload.subject || '(no subject)') + '** to ' + (o.payload.to || 'no address') + ', ' + o.status + '.');
  });
  (S.history || []).slice(0, 40).forEach(h => add('history', 'Activity ' + new Date(h.at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), 'Activity log ' + h.text + ' on ' + new Date(h.at).toDateString(), h.text + ' (' + new Date(h.at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ')', { boost: 0.8 }));
  kb().forEach(n => rChunk(n.text, 500).forEach((ch, i, arr) => add('note', n.title || 'Note', (n.title ? n.title + '. ' : '') + ch, ch, { boost: 1.2, names: n.title ? [n.title] : [] })));
  return docs;
}

let _ragCache = null;
function ragIndex() {
  const docs = ragDocs(), sig = JSON.stringify(docs.map(d => d.text + d.title)), N = docs.length;
  if (_ragCache && _ragCache.sig === sig) return _ragCache;
  const df = {}; let total = 0;
  docs.forEach(d => { d.toks = rTok(d.title).concat(rTok(d.title), rTok(d.text)); d.tf = {}; d.toks.forEach(t => d.tf[t] = (d.tf[t] || 0) + 1); total += d.toks.length; Object.keys(d.tf).forEach(t => df[t] = (df[t] || 0) + 1); });
  return (_ragCache = { sig, docs, df, N, avg: total / (N || 1) || 1 });
}
function ragTypes(q) { return Object.keys(R_TYPES).filter(k => R_TYPES[k].test(q)); }

function ragSearch(query, k) {
  k = k || 6; const ix = ragIndex(), qt = rTok(query); if (!qt.length) return [];
  const w = new Map();
  qt.forEach(t => {
    if (ix.df[t]) w.set(t, Math.max(w.get(t) || 0, 1));
    else if (t.length >= 4) { let best = null, bs = 0; for (const v in ix.df) { const s = rSim(t, v); if (s > bs) { bs = s; best = v; } } if (best && bs >= 0.5) w.set(best, Math.max(w.get(best) || 0, 0.8)); }
  });
  qt.forEach(t => (R_SYN[t] || []).forEach(s => { if (ix.df[s] && !w.has(s)) w.set(s, 0.4); }));
  const types = ragTypes(query), K1 = 1.4, B = 0.75, urgent = /due|deadline|urgent|soon|week|today|tomorrow|next|closing|overdue/i.test(query);
  const ent = ragEntities(query).map(d => d.id);
  let scored = ix.docs.map(d => {
    let s = 0; w.forEach((wt, t) => { const f = d.tf[t]; if (!f) return; const idf = Math.log(1 + (ix.N - ix.df[t] + 0.5) / (ix.df[t] + 0.5)); s += wt * idf * f * (K1 + 1) / (f + K1 * (1 - B + B * d.toks.length / ix.avg)); });
    return { doc: d, raw: s };
  });
  const max = Math.max.apply(null, scored.map(x => x.raw).concat([0.0001]));
  scored.forEach(x => {
    let s = x.raw / max;
    if (x.raw > 0 || types.includes(x.doc.type)) { if (types.includes(x.doc.type)) s += 0.3; }
    if (urgent && x.doc.due != null && x.doc.due >= -1 && x.doc.due <= 7) s += 0.2 * (1 - Math.max(0, x.doc.due) / 8);
    if (ent.includes(x.doc.id)) s += 1;
    if (x.doc.type === 'profile' && !types.includes('profile')) s *= 0.85;
    x.score = s * x.doc.boost;
  });
  scored = scored.filter(x => (x.raw > 0 && x.score >= 0.15) || (types.length && types.includes(x.doc.type)) || ent.includes(x.doc.id));
  if (!types.length) scored = scored.filter(x => x.raw > 0 || ent.includes(x.doc.id));
  scored.sort((a, b) => b.score - a.score);
  const per = {}, out = [];
  for (const x of scored) { per[x.doc.type] = (per[x.doc.type] || 0) + 1; if (per[x.doc.type] <= 4) out.push(x); if (out.length >= k) break; }
  return out;
}
/* Records the question names directly ("Northwind", "Dr. Rao", "Operating Agent MVP"). */
function ragEntities(query) {
  const ql = String(query || '').toLowerCase(), words = new Set(ql.match(/[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]/g) || []), hits = [];
  ragIndexDocsRaw().forEach(d => {
    const ok = d.names.some(n => {
      n = String(n || '').toLowerCase().trim(); if (n.length < 3) return false;
      if (ql.includes(n)) return true;
      const parts = (n.match(/[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]/g) || []).filter(x => x.length >= 4 && !R_GENERIC.has(x) && !R_STOP.has(x));
      return parts.some(x => words.has(x));
    });
    if (ok && d.type !== 'profile') hits.push(d);
  });
  return hits;
}
function ragIndexDocsRaw() { return ragIndex().docs; }

function ragQuery(t) {
  const users = CHAT.filter(m => m.role === 'user');
  const prev = users.length > 1 ? users[users.length - 2].text : '';
  if (!prev) return t;
  if (/\b(it|that|this|them|those|these|he|she|there|its|their)\b/i.test(t)) return prev + ' ' + t;
  if (/^\s*(and|also|what about|how about|why|so|then)\b/i.test(t) && rTok(t).length <= 4) return prev + ' ' + t;
  return t;
}
/* true when the question has a content word that exists in the workspace (beyond generic type words) */
const R_GENERIC_Q = new Set('application apply contact email mail project task exam study request client outreach professor deadline due today next first focus plan open pending status summarize summary help hour outbox draft sent'.split(' ').map(rStem));
function ragSpecific(q) {
  const ix = ragIndex();
  return rTok(q).some(t => !R_GENERIC_Q.has(t) && !/^\d+$/.test(t) && t.length > 2 && (ix.df[t] || (t.length >= 5 && Object.keys(ix.df).some(v => rSim(t, v) >= 0.6))));
}
function ragSources(hits) { const seen = new Set(); return hits.map((h, i) => ({ n: i + 1, label: h.doc.title, tab: R_TYPE_TAB[h.doc.type] || 'today' })).filter(s => !seen.has(s.label) && seen.add(s.label)); }
function ragContext(query) {
  const ix = ragIndex(), hits = ragSearch(ragQuery(query), 7);
  const open = (S.applications || []).filter(a => ['Not started', 'Applied', 'Interview'].includes(a.status)).length;
  const summary = ['Today is ' + iso(0) + '.', 'Open applications: ' + open + '. Contacts awaiting first email: ' + (S.contacts || []).filter(c => c.status === 'Not started').length + '. Drafts awaiting approval: ' + (S.outbox || []).filter(o => o.status === 'pending').length + '. Projects: ' + (S.projects || []).length + '. Open client requests: ' + (S.requests || []).filter(r => ['New', 'Scoped'].includes(r.status)).length + '.',
    'Today\u2019s queue: ' + (buildPlan().slice(0, 6).map(i => i.name).join('; ') || 'empty') + '.'].join('\n');
  const body = hits.length ? hits.map((h, i) => '[' + (i + 1) + '] (' + R_TYPE_LABEL[h.doc.type] + ') ' + h.doc.text).join('\n') : '(no matching records found)';
  return { text: 'WORKSPACE SUMMARY (always accurate):\n' + summary + '\n\nRETRIEVED RECORDS (cite as [n]):\n' + body, hits, indexed: ix.N };
}
function ragLocalAnswer(t) {
  const hits = ragSearch(ragQuery(t), 5);
  if (!hits.length) return { text: 'I could not find anything about that in your workspace. You can teach me: say **remember that ...** or press Teach JARVIS on the right, and I will use it from then on.', sources: [] };
  const ents = ragEntities(ragQuery(t)).filter(d => hits.some(h => h.doc.id === d.id));
  const use = ents.length ? hits.filter(h => ents.some(e => e.id === h.doc.id)).slice(0, 3) : hits.filter(h => h.score >= hits[0].score * 0.45).slice(0, 4);
  return { text: (ents.length ? '' : 'Here is what I found in your workspace:\n\n') + use.map(h => '\u2022 ' + h.doc.line).join('\n'), sources: ragSources(use) };
}

/* ---- Teach JARVIS (notes become retrievable knowledge) ---- */
function teachOpen() {
  const notes = kb();
  openModal('<h3>Teach JARVIS</h3><p class="row-s" style="margin-bottom:12px">Anything you add here is indexed and used to answer your questions: resume text, goals, facts about you, course details.</p>' +
    '<div class="field"><label for="kn-title">Title</label><input id="kn-title" type="text" placeholder="e.g. Resume, Goals, CGPA"></div>' +
    '<div class="field"><label for="kn-text">What should JARVIS remember?</label><textarea id="kn-text" rows="5" placeholder="Paste or type it here"></textarea></div>' +
    (notes.length ? '<div class="row-s" style="margin-top:14px;margin-bottom:6px">Taught so far</div>' + notes.map(n => '<div class="ctx-row"><span>' + esc(n.title || 'Note') + ' \u00b7 ' + esc(String(n.text).slice(0, 40)) + (n.text.length > 40 ? '\u2026' : '') + '</span><button class="btn ghost sm" onclick="teachDel(\'' + n.id + '\')">Remove</button></div>').join('') : '') +
    '<div class="foot"><button class="btn ghost" onclick="closeModal()">Close</button><button class="btn" onclick="teachSave()">Save to memory</button></div>');
}
function teachAdd(title, text) {
  text = String(text || '').trim(); if (!text) return false;
  const n = kb(); const i = title ? n.findIndex(x => (x.title || '').toLowerCase() === title.toLowerCase()) : -1;
  if (i > -1) n[i] = Object.assign(n[i], { text, at: new Date().toISOString() }); else n.unshift({ id: uid(), title: title || '', text, at: new Date().toISOString() });
  log('Taught JARVIS: ' + (title || text.slice(0, 40))); save(); refreshCtx(); return true;
}
function teachSave() { const ok = teachAdd($('kn-title').value.trim(), $('kn-text').value); if (!ok) { toast('Write something for JARVIS to remember', true); return; } closeModal(); toast('JARVIS will use this from now on'); }
function teachDel(id) { S.knowledge = kb().filter(n => n.id !== id); save(); refreshCtx(); teachOpen(); }
function teachResume() { const t = ($('resume-text') || {}).value || ''; if (!t.trim()) { toast('Paste resume text first', true); return; } teachAdd('Resume', t); toast('Resume added to JARVIS memory'); }

/* ---- Overview (everything, one page) ---- */
function ovHead(title, count, tab) {
  return '<div class="panel-h"><h3>' + title + '</h3><span style="display:flex;align-items:center;gap:10px">' + (count != null ? count : '') + '<button class="btn ghost sm" onclick="switchTab(\'' + tab + '\')">See all</button></span></div>';
}
function viewOverview() {
  const apps = S.applications.slice(0, 4);
  const opps = S.opportunities.filter(o => o.status === 'New').slice(0, 3);
  const contacts = S.contacts.slice(0, 4);
  const projs = S.projects.slice(0, 3);
  const acads = S.academics.filter(a => !a.done).slice(0, 4);
  const reqs = S.requests.filter(r => r.status === 'New' || r.status === 'Scoped').slice(0, 3);
  const outboxPending = S.outbox.filter(o => o.status === 'pending').slice(0, 3);
  const hist = S.history.slice(0, 5);
 
  const appsRows = apps.length ? apps.map(a => '<div class="row noicon"><div><div class="row-t">' + esc(a.company) + '</div><div class="row-s">' + esc(a.role) + '</div></div><div class="row-a">' + pill(a.status) + (a.deadline ? '<span class="chip ' + dueTone(a.deadline, a.status) + '">' + fmtDue(a.deadline) + '</span>' : '') + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">No applications yet.</p></div>';
 
  const oppsRows = opps.length ? opps.map(o => '<div class="row noicon"><div><div class="row-t">' + esc(o.title) + '</div><div class="row-s">' + esc(o.org) + '</div></div><div class="row-a">' + (o.deadline ? '<span class="chip">' + fmtDue(o.deadline).replace('Due', 'Closes') + '</span>' : '') + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">Nothing new on the radar.</p></div>';
 
  const contactRows = contacts.length ? contacts.map(c => '<div class="row noicon"><div><div class="row-t">' + esc(c.name) + '</div><div class="row-s">' + esc(c.institute) + '</div></div><div class="row-a">' + pill(c.status) + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">No contacts yet.</p></div>';
 
  const projRows = projs.length ? projs.map(p => { const done = p.tasks.filter(t => t.done).length, total = p.tasks.length; return '<div class="row noicon"><div style="width:100%"><div class="row-t">' + esc(p.name) + '</div><div class="prog" style="margin:8px 0 4px"><i style="width:' + (total ? Math.round(done/total*100) : 0) + '%"></i></div><div class="prog-l" style="margin:0">' + done + ' of ' + total + ' tasks done</div></div></div>'; }).join('') : '<div class="empty" style="padding:22px"><p style="margin:0">No projects yet.</p></div>';
 
  const acadRows = acads.length ? acads.map(a => '<div class="row noicon"><div><div class="row-t">' + esc(a.subject) + '</div><div class="row-s">' + esc(a.task) + '</div></div><div class="row-a">' + (a.exam_date ? '<span class="chip">' + fmtDate(a.exam_date) + '</span>' : '') + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">Nothing to study.</p></div>';
 
  const reqRows = reqs.length ? reqs.map(r => '<div class="row noicon"><div><div class="row-t">' + esc(r.client) + '</div><div class="row-s">' + esc(r.ask) + '</div></div><div class="row-a">' + pill(r.status) + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">No open requests.</p></div>';
 
  const outboxRows = outboxPending.length ? outboxPending.map(o => '<div class="row noicon"><div><div class="row-t">' + esc(o.payload.subject || '(no subject)') + '</div><div class="row-s">To ' + esc(o.payload.to || 'no address') + '</div></div><div class="row-a">' + pill(o.status) + '</div></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">Outbox is clear.</p></div>';
 
  const histRows = hist.length ? hist.map(e => '<div class="tl-e" style="padding:9px 20px"><time>' + new Date(e.at).toLocaleTimeString('en-US', { hour:'numeric', minute:'2-digit' }) + '</time><span>' + esc(e.text) + '</span></div>').join('') : '<div class="empty" style="padding:22px"><p style="margin:0">Nothing logged yet.</p></div>';
 
  const skillChips = splitList(S.profile.skills).slice(0, 8).map(s => '<span class="chip">' + esc(s) + '</span>').join('');
 
  return head('Overview', 'Everything across OPA, on one page. Tap "See all" to open a section in full.', '') +
    '<div class="grid2">' +
      '<section class="panel">' + ovHead('Applications', S.applications.length, 'applications') + '<div class="rows">' + appsRows + '</div></section>' +
      '<section class="panel">' + ovHead('Opportunities', S.opportunities.length, 'opportunities') + '<div class="rows">' + oppsRows + '</div></section>' +
      '<section class="panel">' + ovHead('Outreach', S.contacts.length, 'outreach') + '<div class="rows">' + contactRows + '</div></section>' +
      '<section class="panel">' + ovHead('Projects', S.projects.length, 'projects') + '<div class="rows">' + projRows + '</div></section>' +
      '<section class="panel">' + ovHead('Academics', S.academics.length, 'academics') + '<div class="rows">' + acadRows + '</div></section>' +
      '<section class="panel">' + ovHead('Client requests', S.requests.length, 'requests') + '<div class="rows">' + reqRows + '</div></section>' +
      '<section class="panel">' + ovHead('Outbox', S.outbox.filter(o=>o.status==='pending').length, 'outbox') + '<div class="rows">' + outboxRows + '</div></section>' +
      '<section class="panel">' + ovHead('History', null, 'history') + '<div>' + histRows + '</div></section>' +
    '</div>' +
    '<section class="panel form-panel" style="margin-top:16px;max-width:none">' +
      '<div class="panel-h" style="padding:0 0 14px;border:0"><h3>Profile</h3><button class="btn ghost sm" onclick="switchTab(\'profile\')">Edit</button></div>' +
      '<div class="row-t" style="margin-bottom:4px">' + esc(S.profile.name || 'Unnamed') + '</div>' +
      '<div class="row-s" style="margin-bottom:10px">' + esc(S.profile.track || '') + '</div>' +
      '<div class="row-m">' + (skillChips || '<span class="row-s">No skills added yet.</span>') + '</div>' +
    '</section>';
}
 
/* ================= 7. NAVIGATION & RENDER ================= */
const NAV = [
  { id:'jarvis', l:'JARVIS', i:'spark', g:'Assistant' },
  { id:'overview', l:'Overview', i:'layers' },
  { id:'today', l:'Today', i:'sun', g:'Plan' },
  { id:'applications', l:'Applications', i:'brief' },
  { id:'opportunities', l:'Opportunities', i:'target' },
  { id:'outreach', l:'Outreach', i:'mail' },
  { id:'projects', l:'Projects', i:'layers', g:'Work' },
  { id:'academics', l:'Academics', i:'book' },
  { id:'requests', l:'Requests', i:'chat' },
  { id:'outbox', l:'Outbox', i:'send', g:'Tools' },
  { id:'resume', l:'Resume check', i:'file' },
  { id:'history', l:'History', i:'clock' },
  { id:'profile', l:'Profile', i:'user' }
];
const VIEWS = { jarvis: viewJarvis, overview: viewOverview, today: viewToday, applications: viewApps, opportunities: viewOpps, outreach: viewOutreach, projects: viewProjects, academics: viewAcads, requests: viewReqs, outbox: viewOutbox, resume: viewResume, history: viewHistory, profile: viewProfile };
let cur = 'today';
 
function badge(id) {
  if (id === 'applications') return S.applications.filter(a => ['Not started','Applied','Interview'].includes(a.status)).length;
  if (id === 'opportunities') return S.opportunities.filter(o => o.status === 'New').length;
  if (id === 'requests') return S.requests.filter(r => r.status === 'New' || r.status === 'Scoped').length;
  if (id === 'outbox') return S.outbox.filter(o => o.status === 'pending').length;
  return 0;
}
function renderNav() {
  $('nav').innerHTML = NAV.map(n => {
    const c = badge(n.id);
    return (n.g ? '<div class="nav-group">' + n.g + '</div>' : '') + '<button class="' + (n.id === cur ? 'on' : '') + '" onclick="switchTab(\'' + n.id + '\')"' + (n.id === cur ? ' aria-current="page"' : '') + '>' + icon(n.i, 17) + n.l + (c ? '<span class="count' + (n.id === 'outbox' ? ' alert' : '') + '">' + c + '</span>' : '') + '</button>';
  }).join('');
}
function render(fromNav) {
  renderNav();
  if (cur === 'jarvis' && !fromNav) { refreshCtx(); return; }
  const y = window.scrollY;
  const v = $('view');
  v.style.animation = 'none'; v.offsetHeight; v.style.animation = '';
  v.innerHTML = VIEWS[cur]();
  if (cur === 'jarvis') { refreshCtx(); wireJarvis(); }
  if (!fromNav) window.scrollTo(0, y);
}
function wireJarvis() {
  const input = $('jv-input'); if (!input) return;
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); jarvisSend(); } });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 126) + 'px'; });
  const m = $('msgs'); if (m) m.scrollTop = m.scrollHeight;
}
function switchTab(name) {
  if (!VIEWS[name]) name = 'today';
  cur = name; animateNext = true;
  document.body.classList.remove('nav-open');
  if (location.hash !== '#/' + name) history.replaceState(null, '', '#/' + name);
  render(true); window.scrollTo(0, 0);
}
$('menu-btn').innerHTML = icon('menu', 21);
$('menu-btn').addEventListener('click', () => document.body.classList.toggle('nav-open'));
$('scrim').addEventListener('click', () => document.body.classList.remove('nav-open'));
window.addEventListener('hashchange', () => { const n = location.hash.replace('#/', ''); if (VIEWS[n] && n !== cur) switchTab(n); });
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeModal(); closePalette(); document.body.classList.remove('nav-open'); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if ($('palette').classList.contains('on')) closePalette(); else openPalette(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); closePalette(); switchTab('jarvis'); setTimeout(() => { const i = $('jv-input'); if (i) i.focus(); }, 40); }
});
 
/* ================= 8. COMMAND PALETTE ================= */
let palSel = 0, palItems = [];
function palData() {
  const out = [];
  NAV.forEach(n => out.push({ g: 'Go to', t: n.l, i: n.i, run: () => switchTab(n.id) }));
  [['Add application', 'applications', 'editApp()'], ['Add opportunity', 'opportunities', 'editOpp()'], ['Add contact', 'outreach', 'editContact()'], ['Add project', 'projects', 'editProject()'], ['Add study task', 'academics', 'editAcad()'], ['Add client request', 'requests', 'editReq()']]
    .forEach(c => out.push({ g: 'Create', t: c[0], i: 'plus', run: () => { switchTab(c[1]); (new Function(c[2]))(); } }));
  S.applications.forEach(a => out.push({ g: 'Application', t: a.company, s: a.role + ' · ' + a.status, i: 'brief', run: () => { switchTab('applications'); editApp(a.id); } }));
  S.opportunities.forEach(o => out.push({ g: 'Opportunity', t: o.title, s: o.org, i: 'target', run: () => { switchTab('opportunities'); editOpp(o.id); } }));
  S.contacts.forEach(c => out.push({ g: 'Contact', t: c.name, s: c.institute, i: 'mail', run: () => { switchTab('outreach'); editContact(c.id); } }));
  S.projects.forEach(p => out.push({ g: 'Project', t: p.name, s: p.tasks.filter(t => !t.done).length + ' open tasks', i: 'layers', run: () => { switchTab('projects'); } }));
  S.academics.forEach(a => out.push({ g: 'Study', t: a.subject, s: a.task, i: 'book', run: () => { switchTab('academics'); editAcad(a.id); } }));
  S.requests.forEach(r => out.push({ g: 'Request', t: r.client, s: r.ask, i: 'chat', run: () => { switchTab('requests'); editReq(r.id); } }));
  return out;
}
function openPalette() { closeModal(); $('palette').classList.add('on'); const q = $('pal-q'); q.value = ''; palRender(); setTimeout(() => q.focus(), 20); }
function closePalette() { $('palette').classList.remove('on'); }
function palRender() {
  const words = $('pal-q').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  palItems = palData().filter(it => { const hay = (it.t + ' ' + (it.s || '') + ' ' + it.g).toLowerCase(); return words.every(w => hay.includes(w)); }).slice(0, 40);
  palSel = 0; palDraw();
}
function palDraw() {
  $('pal-list').innerHTML = palItems.length
    ? palItems.map((it, n) => '<button class="pal-it' + (n === palSel ? ' sel' : '') + '" role="option" onmousemove="palHover(' + n + ')" onclick="palRun(' + n + ')">' + icon(it.i, 16) + '<span class="pal-t">' + esc(it.t) + (it.s ? '<small>' + esc(it.s) + '</small>' : '') + '</span><span class="pal-g">' + esc(it.g) + '</span></button>').join('')
    : '<div class="pal-empty">Nothing matches. Try a company, a contact, or a tab name.</div>';
  const sel = $('pal-list').querySelector('.sel'); if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest' });
}
function palHover(n) { if (n === palSel) return; palSel = n; document.querySelectorAll('.pal-it').forEach((el, i) => el.classList.toggle('sel', i === n)); }
function palRun(n) { const it = palItems[n]; if (!it) return; closePalette(); it.run(); }
$('pal-q').addEventListener('input', palRender);
$('pal-q').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); palSel = Math.min(palSel + 1, palItems.length - 1); palDraw(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); palSel = Math.max(palSel - 1, 0); palDraw(); }
  else if (e.key === 'Enter') { e.preventDefault(); palRun(palSel); }
});
$('palette').addEventListener('mousedown', (e) => { if (e.target.id === 'palette') closePalette(); });
 
/* ================= 9. FOCUS TIMER ================= */
let FOCUS = null, focusTick = null;
const BASE_TITLE = document.title;
const clockStr = (sec) => pad(Math.floor(sec / 60)) + ':' + pad(sec % 60);
function startFocus(key) {
  const it = buildPlan().find(i => i.key === key); if (!it) return;
  FOCUS = { key, name: it.name, total: it.effort * 60, left: it.effort * 60, paused: false, over: false };
  clearInterval(focusTick); focusTick = setInterval(tickFocus, 1000); renderFocus();
}
function tickFocus() {
  if (!FOCUS || FOCUS.paused) return;
  FOCUS.left--;
  if (FOCUS.left <= 0) { FOCUS.left = 0; FOCUS.paused = true; FOCUS.over = true; toast('Focus block finished: ' + FOCUS.name); renderFocus(); return; }
  const t = $('f-time'), b = $('f-bar'); if (t) t.textContent = clockStr(FOCUS.left); if (b) b.style.width = Math.round((1 - FOCUS.left / FOCUS.total) * 100) + '%';
  document.title = clockStr(FOCUS.left) + ' · ' + FOCUS.name;
}
function renderFocus() {
  const el = $('focus');
  if (!FOCUS) { el.classList.remove('on'); el.innerHTML = ''; document.title = BASE_TITLE; return; }
  el.classList.add('on');
  el.innerHTML = '<div class="f-top"><div><div class="f-label">' + (FOCUS.over ? 'Time is up' : FOCUS.paused ? 'Paused' : 'Focusing on') + '</div><div class="f-name">' + esc(FOCUS.name) + '</div></div><button class="icon-btn" onclick="stopFocus()" aria-label="Cancel focus timer" title="Cancel">' + icon('x', 16) + '</button></div>' +
    '<div class="f-time" id="f-time">' + clockStr(FOCUS.left) + '</div><div class="f-bar"><i id="f-bar" style="width:' + Math.round((1 - FOCUS.left / FOCUS.total) * 100) + '%"></i></div>' +
    '<div class="f-act">' + (FOCUS.over ? '' : '<button class="btn ghost sm" onclick="toggleFocus()">' + (FOCUS.paused ? 'Resume' : 'Pause') + '</button>') + '<button class="btn sm" onclick="finishFocus()">Mark done</button></div>';
  document.title = clockStr(FOCUS.left) + ' · ' + FOCUS.name;
}
function toggleFocus() { if (!FOCUS) return; FOCUS.paused = !FOCUS.paused; renderFocus(); }
function stopFocus() { clearInterval(focusTick); FOCUS = null; renderFocus(); }
function finishFocus() { if (!FOCUS) return; const k = FOCUS.key; stopFocus(); completeItem(k, { checked: false }); }
 
/* ================= 10. BACKUP ================= */
function exportData() {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(S, null, 2)], { type: 'application/json' }));
  a.download = 'opa-backup-' + iso(0) + '.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1500); toast('Backup downloaded');
}
function importData(inp) {
  const f = inp.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = () => {
    try {
      const d = JSON.parse(r.result);
      if (!d.profile || !Array.isArray(d.applications) || !Array.isArray(d.projects)) throw new Error('bad file');
      S = { ...seed(), ...d }; save(); render(); toast('Backup restored');
    } catch (e) { toast('That file is not an OPA backup', true); }
    inp.value = '';
  };
  r.readAsText(f);
}
 
/* ================= FLOATING CALENDAR ================= */
let calOpen = false, calY = new Date().getFullYear(), calM = new Date().getMonth(), calSel = iso(0);
function localKey(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function calRel(key) { const n = daysUntil(key); return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : n === -1 ? 'Yesterday' : n > 0 ? 'In ' + n + ' days' : (-n) + ' days ago'; }
function calActivity(key) { return S.history.filter(e => localKey(new Date(e.at)) === key); }
function dailySnapshot() {
  S.daily = S.daily || {};
  const k = iso(0);
  const items = buildPlan().map(i => ({ name: i.name, sub: i.sub, kind: i.kind, effort: i.effort, done: false }))
    .concat(doneList().map(i => ({ name: i.name, sub: i.sub, kind: i.kind, effort: i.effort, done: true })));
  const prev = S.daily[k];
  if (!prev || JSON.stringify(prev.items) !== JSON.stringify(items)) { S.daily[k] = { at: new Date().toISOString(), items }; save(); }
}
function calEvents() {
  const m = {};
  const add = (d, t, k, sub) => { if (!d) return; (m[d] = m[d] || []).push({ t, k, sub }); };
  S.applications.forEach(a => { if (!['Offer', 'Rejected'].includes(a.status)) add(a.deadline, a.company, 'app', a.role + ' \u00b7 ' + a.status); });
  S.opportunities.forEach(o => { if (o.status === 'New') add(o.deadline, o.title + ' closes', 'opp', o.org); });
  S.academics.forEach(a => { if (!a.done) add(a.exam_date, a.subject + ' exam', 'acad', a.task); });
  S.contacts.forEach(c => { if (c.sent_on) add(c.sent_on, 'Emailed ' + c.name, 'out', c.institute); });
  return m;
}
function calFab() {
  const d = new Date();
  $('cal-fab').innerHTML = '<span class="cal-badge">' + d.getDate() + '</span><span class="cal-txt"><b>Calendar</b><span>' +
    d.toLocaleDateString('en-US', { weekday: 'long', month: 'short' }) + '</span></span>';
}
function calItem(color, title, sub, right, done) {
  return '<div class="cal-it' + (done ? ' done' : '') + '" style="--c:' + color + '"><i></i><div><b>' + esc(title) + '</b>' + (sub ? '<small>' + esc(sub) + '</small>' : '') + '</div>' + (right ? '<span class="cal-r">' + esc(right) + '</span>' : '<span></span>') + '</div>';
}
function calSec(title, count, body) { return '<div class="cal-sec"><h5><span>' + title + '</span>' + (count != null ? '<span>' + count + '</span>' : '') + '</h5>' + body + '</div>'; }
function calDayHTML(key, ev) {
  const events = ev[key] || [];
  const acts = calActivity(key);
  const n = daysUntil(key);
  const label = new Date(key + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
  const snap = (S.daily || {})[key];
  let plannedRows = [], doneCount = 0, mins = 0, planTitle = 'AI daily tasks', empty = '';
  if (n === 0) {
    const plan = buildPlan(), done = doneList();
    let tm = new Date(); tm.setSeconds(0, 0);
    if (tm.getHours() < 9 || tm.getHours() >= 20) tm.setHours(9, 0, 0, 0); else tm.setMinutes(Math.ceil(tm.getMinutes() / 15) * 15, 0, 0);
    plan.forEach(i => { const t = clockStrOf(tm); tm = new Date(tm.getTime() + i.effort * 60000); plannedRows.push(calItem(KIND[i.kind].color, i.name, i.sub, t + ' \u00b7 ' + fmtMins(i.effort), false)); mins += i.effort; });
    done.forEach(i => { plannedRows.push(calItem(KIND[i.kind].color, i.name, i.sub, 'Done', true)); doneCount++; });
    empty = 'Nothing queued for today. Add work in any tab and it shows here.';
  } else if (n < 0) {
    planTitle = 'What was planned';
    if (snap) snap.items.forEach(i => { plannedRows.push(calItem(KIND[i.kind].color, i.name, i.sub, i.done ? 'Done' : fmtMins(i.effort), i.done)); if (i.done) doneCount++; mins += i.effort; });
    empty = 'No daily snapshot was saved for this day.';
  } else {
    empty = 'AI will write this day\u2019s tasks on the morning of ' + fmtDate(key) + '. Deadlines below are already locked in.';
  }
  const stats = '<div class="cal-stats"><div><b>' + events.length + '</b><span>Due &amp; events</span></div><div><b>' + doneCount + '</b><span>Done</span></div><div><b>' + fmtMins(mins) + '</b><span>Planned</span></div></div>';
  let html = '<div class="cal-day"><div class="cal-dh"><b>' + label + '</b><span class="cal-rel">' + calRel(key) + '</span></div>' + stats;
  html += calSec(planTitle, plannedRows.length || null, plannedRows.length ? plannedRows.join('') : '<div class="cal-none">' + empty + '</div>');
  html += calSec('Deadlines &amp; events', events.length || null, events.length ? events.map(e => calItem(KIND[e.k].color, e.t, e.sub, '', false)).join('') : '<div class="cal-none">Nothing due.</div>');
  if (n <= 0) html += calSec('Activity log', acts.length || null, acts.length ? acts.map(e => '<div class="cal-log"><time>' + new Date(e.at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) + '</time><span>' + esc(e.text) + '</span></div>').join('') : '<div class="cal-none">No activity logged.</div>');
  return html + '</div>';
}
function calDraw() {
  dailySnapshot();
  const ev = calEvents();
  const start = new Date(calY, calM, 1).getDay(), days = new Date(calY, calM + 1, 0).getDate();
  let cells = ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((w, i) => '<div class="cal-wd' + (i === 0 || i === 6 ? ' we' : '') + '">' + w + '</div>').join('');
  for (let i = 0; i < start; i++) cells += '<span></span>';
  for (let d = 1; d <= days; d++) {
    const key = calY + '-' + pad(calM + 1) + '-' + pad(d);
    const dow = new Date(calY, calM, d).getDay();
    const evs = ev[key] || [];
    const kinds = [...new Set(evs.map(x => x.k))].slice(0, 3);
    const heat = Math.min(4, evs.length + (calActivity(key).length ? 1 : 0));
    const snap = (S.daily || {})[key];
    cells += '<button class="cal-d' + (dow === 0 || dow === 6 ? ' we' : '') + (daysUntil(key) < 0 ? ' past' : '') + (key === iso(0) ? ' today' : '') + (key === calSel ? ' sel' : '') + '" style="--h:' + heat + '" onclick="calPick(\'' + key + '\')" aria-label="' + key + '">' +
      (snap && snap.items.length ? '<s title="AI daily data saved"></s>' : '') + d + '<em>' + kinds.map(k => '<i style="background:' + KIND[k].color + '"></i>').join('') + '</em></button>';
  }
  const legend = ['app', 'out', 'acad', 'opp'].map(k => '<span style="--c:' + KIND[k].color + '"><i></i>' + KIND[k].label + '</span>').join('') + '<span style="--c:var(--good)"><i style="border-radius:50%"></i>AI data saved</span>';
  const saved = Object.keys(S.daily || {}).length;
  $('cal-pop').innerHTML =
    '<div class="cal-head"><div><div class="cal-mo">' + new Date(calY, calM, 1).toLocaleDateString('en-US', { month: 'long' }) + '</div><div class="cal-yr">' + calY + '</div></div>' +
    '<div class="cal-ctl"><button class="icon-btn" onclick="calNav(-1)" aria-label="Previous month">\u2039</button><button class="btn ghost sm" onclick="calToday()">Today</button><button class="icon-btn" onclick="calNav(1)" aria-label="Next month">\u203a</button></div></div>' +
    '<div class="cal-grid">' + cells + '</div><div class="cal-lg">' + legend + '</div>' +
    calDayHTML(calSel, ev) +
    '<div class="cal-ai"><b>' + icon('spark', 14) + ' AI daily task data</b><p>Every morning AI writes a fresh task list from your applications, deadlines, exams and projects, and saves it against that date. Right now the same plan is built on this device and saved daily (' + saved + ' day' + (saved === 1 ? '' : 's') + ' stored). Real AI takes over once the backend is connected.</p></div>';
}
function calToggle() {
  calOpen = !calOpen;
  $('cal-pop').classList.toggle('on', calOpen);
  $('cal-fab').setAttribute('aria-expanded', calOpen);
  if (calOpen) { calSel = iso(0); const d = new Date(); calY = d.getFullYear(); calM = d.getMonth(); calDraw(); }
}
function calPick(k) { calSel = k; calDraw(); }
function calNav(n) { calM += n; if (calM < 0) { calM = 11; calY--; } if (calM > 11) { calM = 0; calY++; } calDraw(); }
function calToday() { const d = new Date(); calY = d.getFullYear(); calM = d.getMonth(); calSel = iso(0); calDraw(); }
document.addEventListener('mousedown', (e) => { if (calOpen && !e.target.closest('#cal-pop') && !e.target.closest('#cal-fab')) calToggle(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && calOpen) calToggle(); });
const _renderBase = render;
function hdrFill() {
  const n = (S.profile.name || (AUTH.user && AUTH.user.name) || 'Guest').trim() || 'Guest';
  const a = $('hdr-av'), b = $('hdr-name');
  if (a) a.textContent = n[0].toUpperCase();
  if (b) b.textContent = n;
}
render = function (f) { _renderBase(f); dailySnapshot(); hdrFill(); if (calOpen) calDraw(); };
calFab();
dailySnapshot();
 
 
/* ================= 10b. FIREBASE LOGIN + GMAIL SEND ================= */
/* One-time setup: Firebase console -> Project settings -> Your apps -> Web app,
   copy the config values here. Authentication -> Sign-in method -> enable Google.
   Users never paste anything. */
const FB_CONFIG = {
  apiKey: "AIzaSyCIXqCDmMDSO8ch451PGCbZjMYCVJLtGNs",
  authDomain: "opagent-3ef8b.firebaseapp.com",
  projectId: "opagent-3ef8b",
  storageBucket: "opagent-3ef8b.firebasestorage.app",
  messagingSenderId: "701157045370",
  appId: "1:701157045370:web:386c270095d7655d5037c3",
  measurementId: "G-G3ZY2JC3WG"
};
const LS_SESSION = 'opa_session';
const GUEST_KEY = 'opa_demo_v3';
const GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.send';
const AUTH = { user: null, guest: false };
const GMAIL = { token: null, exp: 0 };
let FB = null;
 
function fbConfigured() { return !!FB_CONFIG.apiKey && !/^PASTE/.test(FB_CONFIG.apiKey) && !/PASTE/.test(FB_CONFIG.projectId); }
function fbInit() {
  if (FB) return FB;
  if (!window.firebase || !fbConfigured()) return null;
  try { if (!firebase.apps.length) firebase.initializeApp(FB_CONFIG); FB = firebase.auth(); } catch (e) { FB = null; }
  return FB;
}
function gProvider(hint) {
  const p = new firebase.auth.GoogleAuthProvider();
  p.addScope(GMAIL_SCOPE);
  p.setCustomParameters(hint ? { login_hint: hint } : { prompt: 'select_account' });
  return p;
}
function grabToken(res) {
  const t = res && res.credential && res.credential.accessToken;
  if (t) { GMAIL.token = t; GMAIL.exp = Date.now() + 55 * 60 * 1000; }
  return !!t;
}
function gmailToken() { return GMAIL.token && Date.now() < GMAIL.exp ? GMAIL.token : null; }
function authMsg(e) {
  const c = (e && e.code) || '';
  if (c === 'auth/popup-closed-by-user' || c === 'auth/cancelled-popup-request') return 'Sign-in was cancelled.';
  if (c === 'auth/popup-blocked') return 'The popup was blocked. Allow popups for this page and try again.';
  if (c === 'auth/unauthorized-domain') return 'This address is not authorized in Firebase. Add it under Authentication -> Settings -> Authorized domains.';
  if (c === 'auth/operation-not-supported-in-this-environment') return 'Open this page over http://localhost or https, not as a file.';
  if (c === 'auth/user-mismatch') return 'Pick the same Google account you signed in with.';
  if (c === 'auth/network-request-failed') return 'Network problem. Check your connection.';
  return (e && e.message) || 'Sign-in failed.';
}
 
function b64utf8(str) { const b = new TextEncoder().encode(str); let bin = ''; b.forEach(x => bin += String.fromCharCode(x)); return btoa(bin); }
function buildRaw(to, subject, body) {
  const subj = String(subject).replace(/[\r\n]+/g, ' ');
  const head = ['To: ' + to, 'Subject: =?UTF-8?B?' + b64utf8(subj) + '?=', 'MIME-Version: 1.0', 'Content-Type: text/plain; charset="UTF-8"', 'Content-Transfer-Encoding: base64'].join('\r\n');
  const b = b64utf8(String(body).replace(/\r?\n/g, '\r\n')).replace(/(.{76})/g, '$1\r\n');
  return b64utf8(head + '\r\n\r\n' + b).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
 
/* Connect dialog: the OK click is the user gesture that lets the popup open. */
function askGmail(pendingId, msg) {
  openModal('<h3>Connect Gmail</h3><p class="row-s" style="margin-bottom:6px">' + esc(msg || 'OPA needs your OK to send this email from your Gmail account.') + '</p><div class="note">Only the "send email" permission is requested. OPA cannot read your inbox.</div><div class="gate-err" id="gm-err" role="alert"></div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="gm-ok" onclick="gmailOk(\'' + (pendingId || '') + '\')">OK</button></div>');
}
async function gmailOk(pendingId) {
  const btn = $('gm-ok'); if (btn) btn.disabled = true;
  try {
    await connectGmail();
    closeModal();
    if (pendingId) sendViaGmail(pendingId); else { render(); toast('Gmail connected'); }
  } catch (e) {
    if (btn) btn.disabled = false;
    const el = $('gm-err'); if (el) el.textContent = authMsg(e);
  }
}
async function connectGmail() {
  const a = fbInit(); if (!a || !a.currentUser) throw new Error('Sign in with Google first.');
  const res = await a.currentUser.reauthenticateWithPopup(gProvider(a.currentUser.email));
  if (!grabToken(res)) throw new Error('Google did not return send permission. Try again and allow it.');
}
 
/* Gate */
function showGate(err) {
  $('gate').classList.add('on');
  $('gate-err').textContent = err || '';
  $('gate-fine').textContent = fbConfigured() ? 'Guest mode keeps demo data on this device and cannot send email.' : 'Google sign-in is not set up yet: add the Firebase config in the FB_CONFIG block. Guest mode works meanwhile.';
  $('gate-google').disabled = false;
}
function hideGate() { $('gate').classList.remove('on'); }
async function gateGoogle() {
  const a = fbInit();
  if (!a) { showGate('Firebase is not configured yet.'); return; }
  $('gate-google').disabled = true; $('gate-err').textContent = '';
  try {
    const res = await a.signInWithPopup(gProvider());
    grabToken(res);
    if (!AUTH.user || AUTH.user.uid !== res.user.uid) enterUser(res.user);
  } catch (e) { showGate(authMsg(e)); }
}
function gateGuest() {
  AUTH.user = null; AUTH.guest = true;
  try { localStorage.setItem(LS_SESSION, 'guest'); } catch (e) {}
  LS_KEY = GUEST_KEY; S = load(); hideGate(); renderUser(); render(true);
}
function wsKey(uid) { return 'opa_ws_' + uid; }
function enterUser(u) {
  AUTH.user = { uid: u.uid, email: u.email || '', name: u.displayName || '', photo: u.photoURL || '' }; AUTH.guest = false;
  try { localStorage.setItem(LS_SESSION, 'google'); } catch (e) {}
  LS_KEY = wsKey(u.uid);
  let has = false; try { has = !!localStorage.getItem(LS_KEY); } catch (e) {}
  if (has) S = load();
  else {
    let first = false, guestRaw = null;
    try { first = !localStorage.getItem('opa_migrated'); guestRaw = localStorage.getItem(GUEST_KEY); } catch (e) {}
    if (first && guestRaw) { try { S = JSON.parse(guestRaw); } catch (e) { S = seed(); } try { localStorage.setItem('opa_migrated', u.uid); } catch (e) {} }
    else S = seed();
    if (!S.profile.email) S.profile.email = AUTH.user.email;
    if (u.displayName && (!first || !guestRaw)) S.profile.name = u.displayName;
    log('Signed in as ' + AUTH.user.email); save();
  }
  hideGate(); renderUser(); render(true);
}
function renderUser() {
  const c = $('userchip'); if (!c) return;
  c.style.display = '';
  const u = AUTH.user;
  const nm = u ? (u.name || u.email) : 'Guest';
  const av = u && u.photo ? '<img src="' + escA(u.photo) + '" alt="" referrerpolicy="no-referrer">' : esc((nm[0] || 'G').toUpperCase());
  c.innerHTML = '<div class="av">' + av + '</div><div><b>' + esc(nm) + '</b><span>' + (u ? esc(u.email) : 'Demo workspace') + '</span></div><button class="icon-btn" onclick="signOutNow()" aria-label="Sign out" title="Sign out">' + icon('x', 15) + '</button>';
}
function signOutNow() {
  const a = FB;
  AUTH.user = null; AUTH.guest = false; GMAIL.token = null; GMAIL.exp = 0;
  try { localStorage.removeItem(LS_SESSION); } catch (e) {}
  $('userchip').style.display = 'none';
  const done = () => showGate();
  if (a) a.signOut().then(done, done); else done();
}
function accountPanel() {
  const u = AUTH.user;
  const h = '<section class="panel form-panel" style="margin-top:20px"><h3 style="font-family:var(--display);font-size:18px;font-weight:650;margin-bottom:8px">Account</h3>';
  if (!u) return h + '<p class="row-s" style="margin-bottom:16px">You are using a guest workspace. Sign in with Google to get your own workspace and send email from Gmail.</p><div class="data-actions"><button class="btn" onclick="signOutNow()">Sign in with Google</button></div></section>';
  const on = !!gmailToken();
  const until = on ? new Date(GMAIL.exp).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }) : '';
  return h + '<p class="row-s" style="margin-bottom:6px">Signed in as <b>' + esc(u.email) + '</b></p><p class="row-s" style="margin-bottom:16px">Gmail: ' + (on ? 'connected until about ' + until : 'not connected. You will be asked to click OK when you approve a draft.') + '</p><div class="data-actions">' + (on ? '' : '<button class="btn" onclick="askGmail()">Connect Gmail</button>') + '<button class="btn ghost" onclick="signOutNow()">Sign out</button></div></section>';
}
 
/* ================= 11. BOOT ================= */
(function boot() {
  try {
    const n = location.hash.replace('#/', '');
    cur = VIEWS[n] ? n : 'today';
  } catch (e) { cur = 'today'; }
  let sess = null; try { sess = localStorage.getItem(LS_SESSION); } catch (e) {}
  const a = fbInit();
  if (sess === 'guest') { gateGuest(); return; }
  if (!a) { showGate(); return; }
  let first = true;
  a.onAuthStateChanged((u) => {
    if (u) { if (!AUTH.user || AUTH.user.uid !== u.uid) enterUser(u); }
    else if (first && !AUTH.guest) showGate();
    first = false;
  });
})();
</script>
</body>
</html>
