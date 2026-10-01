/* KARNA full-window mode: hides the app chrome and adds a Back button. */
(function () {
  var PREV = 'today';
  var _sw = window.switchTab;
  window.switchTab = function (n) {
    try { if (typeof cur !== 'undefined' && cur !== 'jarvis') PREV = cur; } catch (e) {}
    return _sw.apply(this, arguments);
  };
  function btn(label, fn, cls) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'kf-btn ' + (cls || ''); b.textContent = label; b.onclick = fn;
    return b;
  }
  function sync() {
    var jv = document.querySelector('#view .jv');
    document.body.classList.toggle('karna-full', !!jv);
    if (!jv) return;
    var top = jv.querySelector('.jv-top');
    if (!top || top.querySelector('.kf-back')) return;
    var back = btn('\u2190 Back', function () { switchTab(PREV || 'today'); }, 'kf-back');
    back.setAttribute('aria-label', 'Back to the app');
    top.insertBefore(back, top.firstChild);
    var seg = top.querySelector('.scope-seg');
    var study = btn('Study workflow', function () { setJarvisMode('study'); }, 'kf-study');
    var fresh = btn('New chat', function () { jarvisNew(); }, 'kf-new');
    var sp = document.createElement('span'); sp.style.flex = '1';
    top.insertBefore(sp, seg || null);
    top.insertBefore(study, seg || null);
    top.insertBefore(fresh, seg || null);
    if (seg) seg.style.marginLeft = '0';
  }
  var v = document.getElementById('view');
  if (v) new MutationObserver(sync).observe(v, { childList: true, subtree: true });
  sync();
})();
