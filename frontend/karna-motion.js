/* KARNA chat motion: watches #thread and animates new messages.
   - outgoing: your bubble flies up from the composer
   - incoming: KARNA's reply slides in and its text materialises word by word
   Non-invasive: never touches chat logic, history loads and streaming stay untouched. */
(function () {
  'use strict';
  var thread = document.getElementById('thread');
  if (!thread) return;
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  var t0 = performance.now();
  var composerRect = null;

  function snap() { var c = document.querySelector('.card-in'); if (c) composerRect = c.getBoundingClientRect(); }
  document.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && e.target && e.target.id === 'q') snap(); }, true);
  document.addEventListener('pointerdown', function (e) {
    var s = e.target.closest && e.target.closest('#send');
    if (s) { snap(); s.classList.remove('k-launch'); void s.offsetWidth; s.classList.add('k-launch'); }
    else if (e.target.closest && e.target.closest('.sugg button')) snap();
  }, true);

  function flyOut(row) {
    var body = row.querySelector('.body'); if (!body || !body.animate) return;
    var r = body.getBoundingClientRect(), c = composerRect || { top: innerHeight - 90, left: innerWidth / 2, width: 300 };
    var dy = Math.max(70, Math.min(240, (c.top - r.top) * 0.9 || 120));
    var dx = Math.max(-60, Math.min(60, (c.left + c.width * 0.6 - (r.left + r.width / 2)) * 0.25));
    body.animate([
      { transform: 'translate(' + dx + 'px,' + dy + 'px) scale(.82)', opacity: 0, filter: 'blur(8px)' },
      { transform: 'translate(0,-6px) scale(1.02)', opacity: 1, filter: 'blur(0)', offset: .7 },
      { transform: 'none', opacity: 1, filter: 'blur(0)' }
    ], { duration: 620, easing: 'cubic-bezier(.2,.9,.25,1)' });
  }

  function reveal(bubble) {
    if (!bubble || bubble.querySelector('.kw')) return;
    var walker = document.createTreeWalker(bubble, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        return n.parentElement.closest('pre,code,button,.cite,table,.tbl,svg') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [], words = 0, n;
    while ((n = walker.nextNode())) { nodes.push(n); words += (n.nodeValue.match(/\S+/g) || []).length; }
    if (!nodes.length || words > 500) return;
    var step = Math.max(8, Math.min(42, 1500 / words)), i = 0;
    nodes.forEach(function (tn) {
      var frag = document.createDocumentFragment();
      tn.nodeValue.split(/(\s+)/).forEach(function (tok) {
        if (!tok) return;
        if (/^\s+$/.test(tok)) { frag.appendChild(document.createTextNode(tok)); return; }
        var s = document.createElement('span'); s.className = 'kw'; s.textContent = tok;
        s.style.animationDelay = (150 + i++ * step) + 'ms'; frag.appendChild(s);
      });
      tn.parentNode.replaceChild(frag, tn);
    });
    setTimeout(function () {                           // restore plain text once finished
      var k = bubble.querySelectorAll('.kw');
      for (var j = 0; j < k.length; j++) k[j].replaceWith(document.createTextNode(k[j].textContent));
      bubble.normalize();
    }, 150 + words * step + 900);
  }

  function enter(row) {
    var role = row.classList.contains('user') ? 'user' : (row.classList.contains('agent') || row.classList.contains('err') || row.classList.contains('sys')) ? 'agent' : '';
    if (!role || row.id === 'typing') return;
    row.classList.add('k-in-' + role);
    if (role === 'user') { flyOut(row); return; }
    var srcs = row.querySelectorAll('.srcs .src'); srcs.forEach(function (s, i) { s.style.setProperty('--i', i); });
    var b = row.querySelector('.bubble');
    var words = b ? (b.textContent.match(/\S+/g) || []).length : 0;
    var d = Math.min(1.6, .3 + Math.min(words, 90) * .012);
    row.style.setProperty('--k-d', d + 's');
    if (!row.classList.contains('live') && !row.classList.contains('err') && !row.classList.contains('sys')) reveal(b);
  }

  var mo = new MutationObserver(function (list) {
    var added = [];
    list.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1 && n.classList.contains('msg')) added.push(n); }); });
    if (!added.length || added.length > 2 || performance.now() - t0 < 1200) return;   // history loads: no fanfare
    added.forEach(enter);
  });
  mo.observe(thread, { childList: true });
})();
