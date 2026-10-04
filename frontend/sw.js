/* OPAI service worker: cache static shell, never cache API calls. */
const V='opai-v8',SHELL=['/login.html','/super-chat.html','/app.html','/today.html','/plan.html','/applications.html','/projects.html','/academics.html','/agent-console.html','/opai-shared.css','/guide.js','/karna-popup.js','/manifest.json'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>Promise.allSettled(SHELL.map(u=>c.add(u)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{const r=e.request,u=new URL(r.url);
  if(r.method!=='GET'||u.origin!==location.origin)return;           // API (other origin) and non-GET go straight to network
  e.respondWith(fetch(r).then(res=>{const cp=res.clone();caches.open(V).then(c=>c.put(r,cp));return res}).catch(()=>caches.match(r).then(m=>m||caches.match('/super-chat.html'))))});
