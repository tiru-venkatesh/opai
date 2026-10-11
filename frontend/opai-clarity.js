/* OPAI clarity + motion v2. Plain JS, no dependencies. Load with: <script src="opai-clarity.js" defer></script>
   Adds, on section pages only (never on KARNA):
     - a sliding indicator under tab strips                 - a one-line "what is this tab for" under each strip
     - an "On this page" jump bar with scroll-spy            - a short accent line that draws under section titles
     - back-to-top with a progress ring                      - magnetic primary buttons
     - a loading bar + fade when a Work tab opens its page
   It reads the DOM the pages already render and re-runs when they re-render. It never edits page data. */
(function () {
  if (window.__o2) return; window.__o2 = 1;
  var path = (location.pathname.split('/').pop() || '').toLowerCase();
  if (/super-chat|login|landing/.test(path)) return;          /* KARNA, sign-in and the marketing page are left alone */
  var root = document.documentElement;
  var EMBED = window.top !== window.self || /[?&]embed=1/.test(location.search);
  if (EMBED) root.classList.add('o2-embed');
  var RM = matchMedia('(prefers-reduced-motion:reduce)').matches;
  var $ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };
  var SKIP = '.opai-hd,.opai-dock,.opai-timer,#opai-guide,dialog,.modal,#karna-pop,[id^=karna],.opai-k,.opai-st,[class*=ask-karna],.o2-jump,.o2-help';
  function skip(n) { return !!(n.closest && n.closest(SKIP)); }
  function debounce(fn, ms) { var t; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }

  /* ---------- what each tab is for (one line, plain words) ---------- */
  var HELP = {
    /* Work */
    'internship': 'Find opportunities that fit you, track applications, and handle professor outreach.',
    'dsa': 'Your DSA roadmap, today’s topic and weekly consistency.',
    'projects': 'Your projects and the coding contests you can enter.',
    'resume': 'Keep resume versions, match them to a posting and tailor them.',
    'programs': 'Hackathons and programs you could join.',
    'academics': 'Your courses, exams and assignments.',
    /* Opportunities */
    'today’s matches': 'Opportunities ranked against your profile, with a summary of what needs attention.',
    'saved opportunities': 'Everything you saved, plus a place to paste a LinkedIn or other posting.',
    'applications': 'Your application pipeline, one column per stage.',
    'professor outreach': 'Find professors by research area, add contacts, and see how many sends are left today.',
    'programs & challenges': 'Open-source programs, hackathons and fellowships, tracked by cycle.',
    'email & follow-ups': 'Follow-ups that are due and drafts waiting for your approval.',
    'documents': 'The resume versions and project evidence your applications use.',
    'reports': 'Pipeline counts, response rate and bottlenecks.',
    /* Resume Lab */
    'library': 'Your resume versions, with bulk upload.',
    'match a posting': 'Paste a posting to see which version fits it best.',
    'tailor & export': 'Tailor a resume to a posting using your own bullets, then download it.',
    'ats review': 'Check one version for ATS-readiness.',
    'bullet coach': 'Get a diagnosis and a stronger rewrite of a single bullet.',
    'compare': 'See what is only in one version and what they share.',
    'find a bullet': 'Search across all of your own bullets.',
    'insights': 'Your strongest versions and how your skills are spread.'
  };
  function norm(t) { return String(t || '').replace(/\s+/g, ' ').trim().toLowerCase(); }

  /* ---------- tab strips: sliding indicator + help line ---------- */
  function tabGroups() { return $('[role=tablist],.tabs,.wk-tabs').filter(function (g) { return !skip(g) && g.querySelector('button,[role=tab],a'); }); }
  function activeOf(g) { return g.querySelector('[aria-selected=true]'); }
  function place(g) {
    var ind = g.querySelector(':scope>.o2-ind'), a = activeOf(g);
    if (!ind || !a || !a.offsetWidth) { if (ind && g.classList.contains('o2-on')) g.classList.remove('o2-on'); return; }
    var line = g.classList.contains('o2-line');
    ind.style.width = a.offsetWidth + 'px';
    if (!line) ind.style.height = a.offsetHeight + 'px';
    ind.style.transform = 'translate(' + a.offsetLeft + 'px,' + (line ? 0 : a.offsetTop) + 'px)';
    if (!g.classList.contains('o2-on')) g.classList.add('o2-on');
    if (g.scrollWidth > g.clientWidth + 2) { try { g.scrollTo({ left: Math.max(0, a.offsetLeft - g.clientWidth / 2 + a.offsetWidth / 2), behavior: RM ? 'auto' : 'smooth' }); } catch (e) {} }
  }
  function helpFor(g) {
    var a = activeOf(g); if (!a) return;
    var txt = HELP[norm(a.textContent)];
    var host = g.closest('.wk-bar') || g, el = host.nextElementSibling;
    if (!el || !el.classList.contains('o2-help')) {
      if (!txt) return;
      el = document.createElement('p'); el.className = 'o2-help'; el.setAttribute('aria-live', 'polite');
      if (host.classList.contains('wk-bar')) el.classList.add('o2-flush');
      host.parentNode.insertBefore(el, host.nextSibling);
    }
    if (!txt) { el.hidden = true; return; }
    el.hidden = false;
    if (el.getAttribute('data-k') === norm(a.textContent)) return;
    el.setAttribute('data-k', norm(a.textContent)); el.innerHTML = '<span></span>'; el.firstChild.textContent = txt;
  }
  function setupTabs() {
    tabGroups().forEach(function (g) {
      if (!g.querySelector(':scope>.o2-ind')) {
        var i = document.createElement('span'); i.className = 'o2-ind'; i.setAttribute('aria-hidden', 'true'); g.insertBefore(i, g.firstChild);
      }
      if (!g.classList.contains('o2-hasind')) g.classList.add('o2-hasind', g.classList.contains('wk-tabs') ? 'o2-line' : 'o2-pill');
      place(g); helpFor(g);
      if (!g.__o2) {
        g.__o2 = 1;
        new MutationObserver(function () { place(g); helpFor(g); }).observe(g, { attributes: true, attributeFilter: ['aria-selected'], subtree: true });
        if ('ResizeObserver' in window) new ResizeObserver(function () { place(g); }).observe(g);
      }
    });
  }

  /* ---------- section headings: accent line + jump bar ---------- */
  var hio = 'IntersectionObserver' in window ? new IntersectionObserver(function (es) {
    es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('o2-in'); hio.unobserve(e.target); } });
  }, { threshold: .6 }) : null;
  function headings() {
    var scope = document.querySelector('main') || document.body;
    /* section titles: <h2>, plus the .sec labels some pages use as section titles (short text only) */
    return $('h2,.sec', scope).filter(function (h) {
      var t = norm(h.textContent);
      return !skip(h) && h.offsetParent !== null && t.length > 1 && (h.tagName === 'H2' || (t.length <= 45 && !h.querySelector('h2,button,input,select')));
    });
  }
  function accent(hs) {
    hs.forEach(function (h) {
      if (h.classList.contains('o2-hx')) return;
      h.classList.add('o2-hx');
      if (hio && !RM) hio.observe(h); else h.classList.add('o2-in');
    });
  }
  var jump = null, spyIO = null, spyMap = [];
  function slug(t, i) { return 'sec-' + (norm(t).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 28) || i); }
  function short(t) { t = t.replace(/\s+/g, ' ').trim(); return t.length > 30 ? t.slice(0, 29) + '…' : t; }
  function buildJump() {
    var hs = headings(), main = document.querySelector('main') || document.querySelector('.wrap');
    accent(hs);
    if (!main || hs.length < 3) { if (jump) { jump.remove(); jump = null; } return; }
    hs = hs.slice(0, 12);
    var sig = hs.map(function (h) { return norm(h.textContent); }).join('|');
    if (jump && jump.getAttribute('data-sig') === sig) return;
    var used = {};
    hs.forEach(function (h, i) {
      if (!h.id || /^sec-/.test(h.id)) { var s = slug(h.textContent, i); while (used[s] || (document.getElementById(s) && document.getElementById(s) !== h)) s += '-' + i; h.id = s; }
      used[h.id] = 1;
    });
    if (!jump) {
      jump = document.createElement('nav'); jump.className = 'o2-jump'; jump.setAttribute('aria-label', 'On this page');
      /* sit right under the page intro (title + subtitle); if the first block IS a section, sit above it */
      var kids = [].slice.call(main.children).filter(function (k) { return !k.matches('.deco,.o2-help,script,style,link') && k !== jump; });
      var intro = kids.filter(function (k) { return k.matches('h1') || k.querySelector('h1'); })[0], ref;
      if (!intro) ref = kids[0] || null;
      else if (hs.some(function (h) { return intro.contains(h); })) ref = intro;
      else { ref = intro.nextElementSibling; while (ref && ref.matches('.sub,.lede,p.mut')) ref = ref.nextElementSibling; }
      main.insertBefore(jump, ref);
      jump.addEventListener('click', function (e) {
        var a = e.target.closest('a[href^="#"]'); if (!a) return;
        var t = document.getElementById(a.getAttribute('href').slice(1)); if (!t) return;
        e.preventDefault();
        t.scrollIntoView({ behavior: RM ? 'auto' : 'smooth', block: 'start' });
        var box = t.closest('.card,.panel,section') || t;
        box.classList.remove('o2-flash'); void box.offsetWidth; box.classList.add('o2-flash');
        setTimeout(function () { box.classList.remove('o2-flash'); }, 1400);
      });
    }
    jump.setAttribute('data-sig', sig);
    jump.innerHTML = '<b>On this page</b>' + hs.map(function (h, i) {
      var d = document.createElement('div'); d.textContent = short(h.textContent);
      return '<a href="#' + h.id + '"><i>' + (i + 1 < 10 ? '0' : '') + (i + 1) + '</i>' + d.innerHTML + '</a>';
    }).join('');
    spyMap = hs;
    spy();
  }
  var spyTick = 0;
  function spy() {
    if (!jump || !spyMap.length) return;
    var line = (EMBED ? 0 : 64) + 110, cur = 0;
    spyMap.forEach(function (h, i) { if (h.getBoundingClientRect().top <= line) cur = i; });
    if (innerHeight + scrollY >= root.scrollHeight - 4) cur = spyMap.length - 1;   /* at the very bottom the last section is the one you are in */
    $('a', jump).forEach(function (a, i) {
      var on = i === cur; if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      if (on && jump.scrollWidth > jump.clientWidth) { try { jump.scrollTo({ left: Math.max(0, a.offsetLeft - 90), behavior: RM ? 'auto' : 'smooth' }); } catch (e) {} }
    });
  }

  /* ---------- back to top with progress ring ---------- */
  function topButton() {
    if (EMBED || document.querySelector('.o2-top')) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'o2-top'; b.setAttribute('aria-label', 'Back to top'); b.title = 'Back to top';
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
    b.onclick = function () { scrollTo({ top: 0, behavior: RM ? 'auto' : 'smooth' }); };
    document.body.appendChild(b);
    var t = 0;
    function upd() {
      var h = root.scrollHeight - innerHeight, p = h > 0 ? Math.min(100, scrollY / h * 100) : 0;
      b.style.setProperty('--o2-p', p.toFixed(1)); b.classList.toggle('on', scrollY > 600);
    }
    addEventListener('scroll', function () { if (t) return; t = requestAnimationFrame(function () { t = 0; upd(); }); }, { passive: true });
    upd();
  }

  /* ---------- magnetic primary buttons (fine pointers only) ---------- */
  function magnet() {
    if (RM || !matchMedia('(pointer:fine)').matches) return;
    var MAG = '.pill.teal,.big:not(.out),button.b:not(.alt):not(.dng),a.b:not(.alt)', cur = null;
    function clear(el) { if (!el) return; el.classList.remove('o2-mag-on'); el.style.removeProperty('--o2-tx'); el.style.removeProperty('--o2-ty'); }
    addEventListener('pointermove', function (e) {
      var el = e.target.closest ? e.target.closest(MAG) : null;
      if (el && (skip(el) || el.disabled)) el = null;
      if (cur && cur !== el) { clear(cur); cur = null; }
      if (!el) return;
      cur = el; el.classList.add('o2-mag', 'o2-mag-on');
      var r = el.getBoundingClientRect(), dx = (e.clientX - (r.left + r.width / 2)) / r.width, dy = (e.clientY - (r.top + r.height / 2)) / r.height;
      el.style.setProperty('--o2-tx', (dx * 8).toFixed(1) + 'px'); el.style.setProperty('--o2-ty', (dy * 6).toFixed(1) + 'px');
    }, { passive: true });
    document.addEventListener('pointerleave', function () { clear(cur); cur = null; }, true);
  }

  /* ---------- Work: loading bar + fade while a tab's page loads ---------- */
  function workFrames() {
    var fr = document.getElementById('frames'); if (!fr || !fr.querySelector('iframe')) return;
    var timer = 0;
    function done() { fr.classList.remove('o2-loading'); clearTimeout(timer); }
    $('iframe', fr).forEach(function (f) { f.addEventListener('load', function () { f.setAttribute('data-o2', '1'); done(); }); });
    function check() {
      var on = fr.querySelector('iframe.on');
      if (on && !on.getAttribute('data-o2') && on.getAttribute('src')) { fr.classList.add('o2-loading'); clearTimeout(timer); timer = setTimeout(done, 9000); } else done();
    }
    var tabs = document.getElementById('tabs');
    if (tabs) tabs.addEventListener('click', function () { setTimeout(check, 0); });
    addEventListener('hashchange', function () { setTimeout(check, 0); });
    setTimeout(check, 0);
  }

  /* ---------- boot + re-run when the page re-renders ---------- */
  function refresh() { setupTabs(); buildJump(); }
  var again = debounce(refresh, 160);
  function boot() {
    refresh(); topButton(); magnet(); workFrames();
    [300, 900, 2200].forEach(function (ms) { setTimeout(refresh, ms); });   /* late fetches and web-font swaps */
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(refresh);
    new MutationObserver(function (ms) {
      for (var i = 0; i < ms.length; i++) {
        var t = ms[i].target;
        if (t.nodeType === 1 && (t.closest('.o2-jump,.o2-help') || t.classList.contains('o2-ind'))) continue;
        var added = [].slice.call(ms[i].addedNodes).some(function (n) { return n.nodeType === 1 && !n.classList.contains('o2-ind') && !n.classList.contains('o2-jump') && !n.classList.contains('o2-help') && !n.classList.contains('o2-top') && n.id !== 'o-amb' && n.id !== 'o-prog'; });
        if (added) { again(); break; }
      }
    }).observe(document.body, { childList: true, subtree: true });
    addEventListener('scroll', function () { if (spyTick) return; spyTick = requestAnimationFrame(function () { spyTick = 0; spy(); }); }, { passive: true });
    addEventListener('resize', debounce(function () { tabGroups().forEach(place); }, 120));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
