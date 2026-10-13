/* OPAI session shim. Load BEFORE any script that calls /v1/auth/dev-login.
   Why: every page fired dev-login 3-5 times in parallel (shell, page, karna-popup, notify, app.js).
   On a sleeping Render server each copy queued and retried on its own, so first load felt like a minute.
   This makes all callers share ONE request, caches a finished-onboarding login for 5 minutes,
   and adds a timeout so a hung connection can't freeze a page. Callers need no changes. */
(function () {
  if (window.__opaiSession) return; window.__opaiSession = 1;
  var baseFetch = window.fetch ? window.fetch.bind(window) : null; if (!baseFetch) return;

  /* ---- Firebase ID token: attached to every /v1/ call so the backend knows WHO is asking ---- */
  var FB_CONFIG = { apiKey: "AIzaSyCIXqCDmMDSO8ch451PGCbZjMYCVJLtGNs", authDomain: "opagent-3ef8b.firebaseapp.com", projectId: "opagent-3ef8b", appId: "1:701157045370:web:386c270095d7655d5037c3" };
  var SDK = 'https://www.gstatic.com/firebasejs/10.12.2/', authP = null;
  function loadScript(src) { return new Promise(function (ok, no) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; (document.head || document.documentElement).appendChild(s); }); }
  function firebaseAuth() {
    if (authP) return authP;
    authP = (async function () {
      if (!window.firebase) await loadScript(SDK + 'firebase-app-compat.js');
      if (!firebase.auth) await loadScript(SDK + 'firebase-auth-compat.js');
      if (!firebase.apps.length) firebase.initializeApp(FB_CONFIG);
      return firebase.auth();
    })().catch(function () { authP = null; return null; });
    return authP;
  }
  function getToken() {
    return firebaseAuth().then(function (a) {
      if (!a) return null;
      if (a.currentUser) return a.currentUser.getIdToken().catch(function () { return null; });   /* SDK refreshes it when it is about to expire */
      return new Promise(function (ok) {                                                         /* first call on this page: wait for Firebase to restore the session */
        var done = false, un = null, t = setTimeout(function () { if (!done) { done = true; ok(null); } }, 8000);
        un = a.onAuthStateChanged(function (u) {
          if (done) return; done = true; clearTimeout(t); if (un) un();
          if (!u) return ok(null);
          u.getIdToken().then(ok, function () { ok(null); });
        });
      });
    });
  }
  function urlOf(input) { return typeof input === 'string' ? input : (input && input.url) || ''; }
  function realFetch(input, init) {
    if (!/\/v1\//.test(urlOf(input))) return baseFetch(input, init);
    return getToken().then(function (tok) {
      if (!tok) return baseFetch(input, init);
      var h = new Headers((init && init.headers) || (input && input.headers) || {});
      if (!h.has('Authorization')) h.set('Authorization', 'Bearer ' + tok);
      return baseFetch(input, Object.assign({}, init, { headers: h }));
    });
  }
  var RE = /\/v1\/auth\/dev-login\?/, TTL = 5 * 60 * 1000, TIMEOUT = 40000, inflight = {};
  function emailOf(url) { try { var e = new URL(url, location.href).searchParams.get('email'); return e ? e.trim().toLowerCase() : ''; } catch (x) { return ''; } }
  function read(k) { try { var o = JSON.parse(localStorage.getItem('opai_sess:' + k) || 'null'); if (o && o.exp > Date.now() && o.d && o.d.user_id && o.d.onboarding_required === false) return o.d; } catch (e) {} return null; }
  function write(k, d) { try { if (d && d.user_id && d.onboarding_required === false) localStorage.setItem('opai_sess:' + k, JSON.stringify({ exp: Date.now() + TTL, d: d })); else localStorage.removeItem('opai_sess:' + k); } catch (e) {} }
  function fake(d) { return new Response(JSON.stringify(d), { status: 200, headers: { 'Content-Type': 'application/json' } }); }
  window.opaiClearSession = function () { try { Object.keys(localStorage).forEach(function (k) { if (k.indexOf('opai_sess:') === 0) localStorage.removeItem(k); }); } catch (e) {} };
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    if (method !== 'POST' || !RE.test(url)) return realFetch(input, init);
    var k = emailOf(url); if (!k) return realFetch(input, init);
    var renaming = /[?&]name=[^&]/.test(url);            /* a name update must reach the server */
    if (!renaming) { var hit = read(k); if (hit) return Promise.resolve(fake(hit)); }
    if (inflight[url]) return inflight[url].then(function (r) { return r.clone(); });
    var ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, TIMEOUT) : null;
    var p = realFetch(input, ctl ? Object.assign({}, init, { signal: ctl.signal }) : init).then(function (r) {
      if (timer) clearTimeout(timer); delete inflight[url];
      if (r.ok) r.clone().json().then(function (d) { write(k, d); }).catch(function () {});
      return r;
    }, function (e) { if (timer) clearTimeout(timer); delete inflight[url]; throw e; });
    inflight[url] = p;
    return p.then(function (r) { return r.clone(); });
  };
})();
