/* opai-conn.js : one place that knows whether the OPAI backend is reachable.
 *
 * Load it as a plain (non-deferred) <script> in <head>, before any page script makes a request.
 * It wraps window.fetch for calls to the OPAI API only; Google fonts, Google sign-in etc. are untouched.
 *
 *   waking   first failure on a sleeping free-tier backend: "OPAI is waking up", retrying with backoff
 *   offline  retries used up (or no network): "Can't reach OPAI", with Retry / Reload buttons
 *   mismatch the backend answered 404 "Not Found" for a /v1 route: a stale or partial deploy, NOT a reconnect problem
 *   online   everything fine (banner hides)
 *
 * Safety rules, on purpose:
 *   - Only GET/HEAD are retried automatically. POST/PUT/PATCH/DELETE are never replayed (a replayed approve or send
 *     could act twice). Before such a request the layer first waits for the backend to wake, so the request is sent once,
 *     to a backend that is up.
 *   - A 404 is "feature unavailable" only when FastAPI says exactly {"detail":"Not Found"} (no such route). A 404 from a
 *     handler ("Resume not found") is a normal answer and is left alone.
 *   - Gmail is a separate service. A 401/403/429 from /outbox/{id}/send is a GMAIL problem (token expired, scope, rate
 *     limit), reported as OPAI_CONN.gmail, and never flips OPAI to offline or triggers a reconnect loop.
 *   - Nothing here changes data, reads tokens or stores anything except a dismissed-banner flag in sessionStorage.
 *
 * API: window.OPAI_CONN = { state, gmail, on(fn), retry(), awake(), version() }
 */
(function () {
  'use strict';
  if (window.OPAI_CONN) return;
  var API = (localStorage.getItem('opa_api_base') || (/^(localhost|127\.0\.0\.1)$/.test(location.hostname) ? 'http://localhost:8000' : 'https://opa-52ug.onrender.com')).replace(/\/+$/, '');
  var DELAYS = [1000, 2000, 4000, 8000, 15000];
  var realFetch = window.fetch.bind(window);
  var listeners = [];
  var C = { state: 'online', gmail: { state: 'unknown', message: '' }, since: Date.now(), mismatch: [] };
  var banner = null, retrying = null;

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function emit() { listeners.slice().forEach(function (f) { try { f(C); } catch (e) { /* a listener must not break requests */ } }); }
  function isOpai(url) { return typeof url === 'string' && url.indexOf(API + '/v1/') === 0; }
  function urlOf(input) { return typeof input === 'string' ? input : (input && input.url) || ''; }

  /* ---------------- banner ---------------- */
  var CSS = '#opai-conn{position:fixed;left:50%;top:10px;transform:translateX(-50%);z-index:99999;max-width:min(560px,calc(100vw - 20px));' +
    'display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 14px;border-radius:12px;font:500 13px/1.35 system-ui,sans-serif;' +
    'background:var(--card,#fff);color:var(--ink,#1c1b19);border:1px solid var(--line,#DEC6AC);box-shadow:0 6px 24px rgba(0,0,0,.18)}' +
    '#opai-conn[hidden]{display:none}#opai-conn[data-s=waking]{border-color:#c98a1b}#opai-conn[data-s=offline],#opai-conn[data-s=mismatch]{border-color:#b3402f}' +
    '#opai-conn .sp{width:14px;height:14px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:opaiconn 0.9s linear infinite}' +
    '#opai-conn button{font:600 12px system-ui,sans-serif;padding:4px 10px;border-radius:8px;border:1px solid var(--line,#DEC6AC);background:transparent;color:inherit;cursor:pointer}' +
    '#opai-conn button:focus-visible{outline:2px solid currentColor;outline-offset:2px}' +
    '@keyframes opaiconn{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){#opai-conn .sp{animation:none}}';

  function ensureBanner() {
    if (banner) return banner;
    var st = document.createElement('style'); st.textContent = CSS; (document.head || document.documentElement).appendChild(st);
    banner = document.createElement('div'); banner.id = 'opai-conn'; banner.setAttribute('role', 'status'); banner.setAttribute('aria-live', 'polite'); banner.hidden = true;
    var attach = function () { if (!banner.parentNode) document.body.appendChild(banner); };
    if (document.body) attach(); else document.addEventListener('DOMContentLoaded', attach);
    banner.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      if (b.dataset.a === 'retry') C.retry();
      else if (b.dataset.a === 'reload') location.reload();
      else if (b.dataset.a === 'dismiss') { try { sessionStorage.setItem('opai_conn_dismissed', '1'); } catch (x) { /* ignore */ } banner.hidden = true; }
    });
    return banner;
  }

  function paint() {
    var b = ensureBanner(), s = C.state;
    if (s === 'online') { b.hidden = true; return; }
    if (s === 'mismatch' && sessionStorage.getItem('opai_conn_dismissed')) { b.hidden = true; return; }
    b.dataset.s = s; b.hidden = false;
    if (s === 'waking') b.innerHTML = '<span class="sp" aria-hidden="true"></span><span><b>OPAI is waking up.</b> This usually takes less than a minute.</span><button data-a="retry">Retry now</button>';
    else if (s === 'offline') b.innerHTML = '<span><b>Can\u2019t reach OPAI.</b> Check your connection. Nothing you approved or drafted is lost.</span><button data-a="retry">Retry connection</button><button data-a="reload">Reload app</button>';
    else if (s === 'mismatch') b.innerHTML = '<span><b>OPAI is updating.</b> Some features may be unavailable for a moment.</span><button data-a="reload">Reload app</button><button data-a="dismiss" aria-label="Dismiss">\u2715</button>';
  }

  function setState(s) {
    if (C.state === s) return;
    C.state = s; C.since = Date.now(); paint(); emit();
  }

  /* ---------------- wake-up ---------------- */
  /* Pings /v1/health (never has side effects) until it answers or the attempts run out. Shared by concurrent callers. */
  function awake(maxMs) {
    if (retrying) return retrying;
    var deadline = Date.now() + (maxMs || 75000);
    retrying = (async function () {
      var i = 0;
      while (Date.now() < deadline) {
        try {
          var r = await realFetch(API + '/v1/health', { cache: 'no-store' });
          if (r.ok) { if (C.state !== 'mismatch') setState('online'); checkVersion(); return true; }
        } catch (e) { /* still asleep */ }
        if (C.state === 'online') setState('waking');
        await sleep(DELAYS[Math.min(i++, DELAYS.length - 1)]);
      }
      setState('offline');
      return false;
    })().then(function (ok) { retrying = null; return ok; }, function (e) { retrying = null; throw e; });
    return retrying;
  }

  /* ---------------- deployment mismatch: frontend build vs backend contract ---------------- */
  var versionChecked = false;
  function markMismatch(what) { if (C.mismatch.indexOf(what) < 0) C.mismatch.push(what); setState('mismatch'); emit(); }
  function checkVersion() {
    if (versionChecked) return; versionChecked = true;
    realFetch(new URL('build.json', location.href).href, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (b) {
      if (!b || typeof b.api_contract !== 'number') return null;              /* no stamp (e.g. local dev): nothing to compare */
      C.frontend = b;
      return realFetch(API + '/v1/version', { cache: 'no-store' }).then(function (r) {
        if (r.status === 404) { markMismatch('/v1/version'); return null; }   /* backend older than the contract system itself */
        return r.ok ? r.json().then(function (v) {
          C.backend = v;
          if (typeof v.api_contract === 'number' && v.api_contract < b.api_contract) markMismatch('api_contract ' + v.api_contract + ' < ' + b.api_contract);
        }) : null;
      });
    }).catch(function () { /* a failed version check must never affect the app */ });
  }

  /* ---------------- fetch wrapper ---------------- */
  function noteResponse(url, r) {
    if (r.status < 500 && (C.state === 'waking' || C.state === 'offline')) setState('online');   /* any real answer proves the backend is up */
    if (r.status < 500) checkVersion();
    if (r.status === 404 && /\/v1\//.test(url)) {
      /* FastAPI answers an unknown route with exactly {"detail":"Not Found"}; handlers use their own wording. */
      r.clone().json().then(function (d) {
        if (d && d.detail === 'Not Found') {
          var p = url.replace(API, '').split('?')[0];
          if (C.mismatch.indexOf(p) < 0) C.mismatch.push(p);
          setState('mismatch'); emit();
        }
      }).catch(function () { /* not JSON: ignore */ });
      return;
    }
    if (/\/outbox\/[^/]+\/send(\?|$)/.test(url)) {
      if (r.status === 401 || r.status === 403) C.gmail = { state: 'needs_reconnect', message: r.status === 401 ? 'Gmail access expired. Reconnect Gmail to send.' : 'Gmail permission is missing. Reconnect Gmail and allow sending.' };
      else if (r.status === 429) C.gmail = { state: 'rate_limited', message: 'Gmail rate limit reached. Try again later.' };
      else if (r.ok) C.gmail = { state: 'connected', message: '' };
      emit();
    }
  }

  async function wrapped(input, init) {
    var url = urlOf(input);
    if (!isOpai(url)) return realFetch(input, init);
    var method = String((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    var safe = method === 'GET' || method === 'HEAD';
    var signal = init && init.signal;
    if (/\/v1\/health(\?|$)/.test(url)) {           /* pings: pass through, just learn from them */
      try { var h = await realFetch(input, init); if (h.ok && C.state !== 'mismatch') setState('online'); return h; } catch (e) { throw e; }
    }
    if (!safe && (C.state === 'waking' || C.state === 'offline')) {
      /* never fire a side-effecting request at a sleeping backend, and never replay it afterwards */
      var up = await awake();
      if (!up) { var er = new Error('OPAI is not reachable right now. Nothing was sent. Try again in a moment.'); er.code = 'OFFLINE'; throw er; }
    }
    for (var i = 0; ; i++) {
      try {
        var r = await realFetch(input, init);
        if (safe && r.status >= 502 && r.status <= 504 && i < DELAYS.length) {
          setState('waking'); await sleep(DELAYS[i]); if (signal && signal.aborted) throw new DOMException('Aborted', 'AbortError'); continue;
        }
        if (r.status >= 502 && r.status <= 504) { setState(safe ? 'offline' : 'waking'); return r; }
        noteResponse(url, r);
        return r;
      } catch (e) {
        if (e && e.name === 'AbortError') throw e;
        if (!safe) {                                  /* may or may not have reached the server: do not replay */
          setState('offline'); var e2 = new Error('Could not reach OPAI. Check whether it went through before trying again.'); e2.code = 'OFFLINE'; throw e2;
        }
        if (i >= DELAYS.length) { setState('offline'); var e3 = new Error('Could not reach OPAI. Check your connection and retry.'); e3.code = 'OFFLINE'; throw e3; }
        setState('waking'); await sleep(DELAYS[i]);
      }
    }
  }
  window.fetch = function (input, init) { return wrapped(input, init); };

  /* ---------------- public API ---------------- */
  C.on = function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; };
  C.retry = function () { try { sessionStorage.removeItem('opai_conn_dismissed'); } catch (e) { /* ignore */ } setState('waking'); return awake(); };
  C.awake = awake;
  C.version = function () { return realFetch(API + '/v1/version', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); };
  window.OPAI_CONN = C;

  addEventListener('online', function () { if (C.state === 'offline') C.retry(); });
  addEventListener('offline', function () { setState('offline'); });
})();
