/* KARNA notifications: reminders + the daily "today's plan" nudge.
   - polls /v1/notifications every 30s while any OPAI page is open and shows them as system notifications
   - if the backend has Web Push (VAPID) configured, subscribes so they also arrive when the app is closed
   - Done / Snooze buttons on the notification talk to the API through the service worker */
(function () {
  if (window.OPAI_NOTIFY) return; window.OPAI_NOTIFY = 1;
  var API = (localStorage.getItem('opa_api_base') || (/^(localhost|127\.0\.0\.1)$/.test(location.hostname) ? 'http://localhost:8000' : 'https://opa-52ug.onrender.com')).replace(/\/+$/, '');
  var uid = null, shown = {};

  function api(path, opts) {
    opts = opts || {};
    return fetch(API + path, Object.assign({ headers: opts.body ? { 'Content-Type': 'application/json' } : {} }, opts))
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text().then(function (t) { return t ? JSON.parse(t) : null; }); });
  }
  function ensureUser() {
    if (uid) return Promise.resolve(uid);
    var email = localStorage.getItem('opai_sc_email'), gid = localStorage.getItem('opa_guest_uid');
    if (email) return api('/v1/auth/dev-login?email=' + encodeURIComponent(email), { method: 'POST' }).then(function (r) { return (uid = r.user_id); });
    if (gid) { uid = gid; return Promise.resolve(uid); }
    return Promise.resolve(null);                       // not signed in yet; try again on the next tick
  }
  function swReady() { return ('serviceWorker' in navigator) ? navigator.serviceWorker.ready.catch(function () { return null; }) : Promise.resolve(null); }
  function tell(reg) {                                  // give the service worker what it needs to call the API from a notification button
    if (reg && reg.active && uid) reg.active.postMessage({ type: 'opai-cfg', api: API, user_id: uid });
  }

  function toast(n) {
    var el = document.createElement('div');
    el.setAttribute('role', 'status');
    el.style.cssText = 'position:fixed;left:50%;transform:translateX(-50%);bottom:84px;max-width:min(92vw,420px);z-index:99999;background:#14181f;color:#fff;border:1px solid rgba(255,255,255,.18);border-radius:14px;padding:12px 14px;font:14px/1.4 system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.4)';
    var b = document.createElement('b'); b.textContent = n.title; el.appendChild(b);
    el.appendChild(document.createElement('br'));
    el.appendChild(document.createTextNode(n.body));
    var row = document.createElement('div'); row.style.cssText = 'margin-top:8px;display:flex;gap:8px';
    function btn(label, fn) { var x = document.createElement('button'); x.textContent = label; x.style.cssText = 'border:0;border-radius:10px;padding:6px 12px;background:#2d6cdf;color:#fff;font:inherit;cursor:pointer'; x.onclick = function () { fn(); el.remove(); }; row.appendChild(x); }
    if (n.link) btn('Open', function () { location.href = n.link; });
    if (n.data && n.data.reminder_id) {
      btn('Done', function () { api('/v1/reminders/' + n.data.reminder_id + '/done', { method: 'POST', body: JSON.stringify({ user_id: uid }) }); });
      btn('Snooze 10m', function () { api('/v1/reminders/' + n.data.reminder_id + '/snooze', { method: 'POST', body: JSON.stringify({ user_id: uid, minutes: 10 }) }); });
    }
    el.appendChild(row); document.body.appendChild(el); setTimeout(function () { el.remove(); }, 30000);
  }

  function show(n, reg) {
    if (shown[n.id]) return Promise.resolve(); shown[n.id] = 1;
    var canSys = window.Notification && Notification.permission === 'granted' && reg && reg.showNotification;
    var p;
    if (canSys) {
      var acts = (n.data && n.data.reminder_id && n.kind === 'reminder') ? [{ action: 'done', title: 'Done' }, { action: 'snooze', title: 'Snooze 10 min' }] : [];
      p = reg.showNotification(n.title, { body: n.body, tag: n.id, icon: 'icons/icon-192.png', badge: 'icons/icon-192.png', actions: acts,
                                          data: { id: n.id, link: n.link, reminder_id: (n.data || {}).reminder_id, kind: n.kind } });
    } else { toast(n); p = Promise.resolve(); }
    return p.then(function () { return api('/v1/notifications/' + n.id + '/delivered', { method: 'POST', body: JSON.stringify({ user_id: uid }) }); }).catch(function () {});
  }

  function poll() {
    ensureUser().then(function (u) {
      if (!u) return;
      return Promise.all([api('/v1/notifications?user_id=' + encodeURIComponent(u) + '&undelivered=true'), swReady()]).then(function (r) {
        tell(r[1]); return Promise.all(r[0].reverse().map(function (n) { return show(n, r[1]); }));
      });
    }).catch(function () {});
  }

  function urlB64(s) { var p = '='.repeat((4 - s.length % 4) % 4), b = (s + p).replace(/-/g, '+').replace(/_/g, '/'), raw = atob(b), a = new Uint8Array(raw.length); for (var i = 0; i < raw.length; i++) a[i] = raw.charCodeAt(i); return a; }
  function subscribePush(reg) {
    if (!reg || !('PushManager' in window)) return Promise.resolve();
    return api('/v1/push/key').then(function (k) {
      if (!k || !k.enabled) return;
      return reg.pushManager.getSubscription().then(function (s) { return s || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64(k.public_key) }); })
        .then(function (s) { var j = s.toJSON(); return api('/v1/push/subscribe', { method: 'POST', body: JSON.stringify({ user_id: uid, endpoint: j.endpoint, keys: j.keys }) }); });
    }).catch(function () {});
  }

  function setup() {
    ensureUser().then(function (u) {
      if (!u) return;
      var off = -new Date().getTimezoneOffset(), tz = (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || null;
      var first = !localStorage.getItem('opai_notify_init');
      api('/v1/notifications/settings', { method: 'PUT', body: JSON.stringify(tz ? { user_id: u, timezone: tz } : { user_id: u, tz_offset_min: off }) }).catch(function () {});
      swReady().then(function (reg) { tell(reg); if (window.Notification && Notification.permission === 'granted') subscribePush(reg); });
      if (first && window.Notification && Notification.permission === 'default') chip();
    });
  }
  function chip() {
    if (localStorage.getItem('opai_notify_dismissed')) return;
    var b = document.createElement('button');
    b.textContent = 'Turn on reminders & daily plan';
    b.style.cssText = 'position:fixed;left:14px;bottom:14px;z-index:99998;border:1px solid rgba(255,255,255,.25);border-radius:999px;padding:9px 14px;background:#14181f;color:#fff;font:600 13px system-ui,sans-serif;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.35)';
    b.onclick = function () {
      Notification.requestPermission().then(function (p) {
        b.remove();
        if (p !== 'granted') { localStorage.setItem('opai_notify_dismissed', '1'); return; }
        localStorage.setItem('opai_notify_init', '1');
        api('/v1/notifications/settings', { method: 'PUT', body: JSON.stringify({ user_id: uid, daily_brief: true, daily_brief_time: '07:30', timezone: (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone || undefined, tz_offset_min: (Intl.DateTimeFormat().resolvedOptions() || {}).timeZone ? undefined : -new Date().getTimezoneOffset() }) }).catch(function () {});
        swReady().then(subscribePush);
        poll();
      });
    };
    document.body.appendChild(b);
  }

  window.OPAI_NOTIFY = { poll: poll, enable: function () { return Notification.requestPermission(); } };
  function start() { setup(); poll(); setInterval(poll, 30000); document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
