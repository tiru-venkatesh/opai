/* Attach & analyze: file / photo / PDF upload + AI analysis in every section. */
(function () {
  var MAX = 8 * 1024 * 1024, MAXN = 5;
  var ST = {};                      // per-section state, survives re-renders
  var CLIP = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21 11-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.6 8.6a2 2 0 0 1-2.8-2.8L15 7.5"/></svg>';
  var ACCEPT = 'image/*,application/pdf,.pdf,.txt,.md,.csv,.json,.docx';
  function st(k) { return ST[k] || (ST[k] = { files: [], q: '', result: '', busy: false, open: false, err: '' }); }
  function sec() { return typeof cur !== 'undefined' ? cur : 'overview'; }
  function b64(f) { return new Promise(function (ok, no) { var r = new FileReader(); r.onload = function () { ok(String(r.result).split(',')[1]); }; r.onerror = no; r.readAsDataURL(f); }); }
  function size(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

  function panelHTML(k) {
    var s = st(k);
    var chips = s.files.map(function (f, i) {
      return '<span class="att-chip">' + esc(f.name) + ' <small>' + size(f.size) + '</small><button type="button" aria-label="Remove ' + esc(f.name) + '" onclick="attRemove(' + i + ')">&times;</button></span>';
    }).join('');
    var res = s.err ? '<div class="att-err">' + esc(s.err) + '</div>' : '';
    if (s.result) res += '<div class="att-res"><div class="att-res-h"><b>Analysis</b><button type="button" class="btn ghost" onclick="attCopy()">Copy</button></div>' + fmtMsg(s.result) + '</div>';
    return '<button type="button" class="att-toggle" onclick="attToggle()" aria-expanded="' + s.open + '">' + CLIP + '<span>Attach file, photo or PDF for analysis</span></button>' +
      '<div class="att-body"' + (s.open ? '' : ' hidden') + '>' +
      '<div class="att-drop" id="att-drop"><span>Drop files here, or</span> <button type="button" class="btn ghost" onclick="attPick(false)">Choose file / PDF</button> <button type="button" class="btn ghost" onclick="attPick(true)">Take / pick photo</button>' +
      '<div class="att-hint">Images, PDF (text), TXT, CSV, JSON · up to ' + MAXN + ' files, 8 MB each</div></div>' +
      (chips ? '<div class="att-chips">' + chips + '</div>' : '') +
      '<div class="att-row"><input id="att-q" placeholder="What should I look for? (optional)" value="' + esc(s.q) + '" oninput="attQ(this.value)" onkeydown="if(event.key===\'Enter\')attGo()">' +
      '<button type="button" class="btn" id="att-go" onclick="attGo()"' + (s.busy ? ' disabled' : '') + '>' + (s.busy ? 'Analyzing\u2026' : 'Analyze') + '</button></div>' + res + '</div>';
  }

  function mount() {
    var v = document.getElementById('view'); if (!v) return;
    var k = sec();
    if (k === 'jarvis') { mountClip(); return; }
    var p = document.getElementById('att-panel');
    if (p && p.getAttribute('data-sec') === k) return;
    if (p) p.remove();
    p = document.createElement('section');
    p.id = 'att-panel'; p.className = 'panel att'; p.setAttribute('data-sec', k);
    p.innerHTML = panelHTML(k);
    var h = v.querySelector(':scope > .head');
    if (h) h.insertAdjacentElement('afterend', p); else v.insertBefore(p, v.firstChild);
    wireDrop();
  }
  function redraw() { var p = document.getElementById('att-panel'); if (p) { p.innerHTML = panelHTML(sec()); wireDrop(); } }
  function wireDrop() {
    var d = document.getElementById('att-drop'); if (!d) return;
    ['dragenter', 'dragover'].forEach(function (e) { d.addEventListener(e, function (ev) { ev.preventDefault(); d.classList.add('over'); }); });
    ['dragleave', 'drop'].forEach(function (e) { d.addEventListener(e, function (ev) { ev.preventDefault(); d.classList.remove('over'); }); });
    d.addEventListener('drop', function (ev) { add(ev.dataTransfer.files); });
  }
  function add(list) {
    var s = st(sec()); s.err = '';
    Array.prototype.forEach.call(list || [], function (f) {
      if (s.files.length >= MAXN) { s.err = 'Max ' + MAXN + ' files.'; return; }
      if (f.size > MAX) { s.err = f.name + ' is larger than 8 MB.'; return; }
      s.files.push(f);
    });
    s.open = true; redraw();
  }
  function picker(cam, cb) {
    var i = document.createElement('input'); i.type = 'file'; i.multiple = !cam; i.accept = cam ? 'image/*' : ACCEPT;
    if (cam) i.setAttribute('capture', 'environment');
    i.onchange = function () { cb(i.files); }; i.click();
  }
  async function analyze(k, files, q) {
    var payload = [];
    for (var i = 0; i < files.length; i++) payload.push({ name: files[i].name, mime: files[i].type || '', data_base64: await b64(files[i]) });
    try {
      var r = await POST('/v1/attach/analyze', { section: k, question: q, files: payload });
      return r.analysis || '';
    } catch (e) {
      // offline fallback: images + text through the browser Groq key (PDFs need the backend)
      if (!(S.profile && S.profile.groqKey)) throw e;
      if (files.some(function (f) { return /pdf$/i.test(f.name) || f.type === 'application/pdf'; })) throw new Error('PDF analysis needs the backend. ' + e.message);
      var parts = [{ type: 'text', text: q || 'Analyze this and tell me what matters.' }];
      for (var j = 0; j < payload.length; j++) {
        if (/^image\//.test(payload[j].mime)) parts.push({ type: 'image_url', image_url: { url: 'data:' + payload[j].mime + ';base64,' + payload[j].data_base64 } });
        else parts[0].text += '\n\n=== ' + payload[j].name + ' ===\n' + atob(payload[j].data_base64).slice(0, 20000);
      }
      var hasImg = parts.length > 1;
      var res = await fetch('https://api.groq.com/openai/v1/chat/completions', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + S.profile.groqKey },
        body: JSON.stringify({ model: hasImg ? 'meta-llama/llama-4-scout-17b-16e-instruct' : (S.profile.groqModel || 'openai/gpt-oss-120b'), messages: [{ role: 'user', content: hasImg ? parts : parts[0].text }], max_tokens: 1200 }) });
      if (!res.ok) throw new Error('Groq ' + res.status);
      return (await res.json()).choices[0].message.content || '';
    }
  }

  window.attToggle = function () { var s = st(sec()); s.open = !s.open; redraw(); };
  window.attPick = function (cam) { picker(cam, add); };
  window.attRemove = function (i) { st(sec()).files.splice(i, 1); redraw(); };
  window.attQ = function (v) { st(sec()).q = v; };
  window.attCopy = function () { var s = st(sec()); try { navigator.clipboard.writeText(s.result); toast('Copied'); } catch (e) {} };
  window.attGo = async function () {
    var k = sec(), s = st(k);
    if (!s.files.length) { s.err = 'Attach a file, photo or PDF first.'; redraw(); return; }
    s.busy = true; s.err = ''; s.result = ''; redraw();
    try { s.result = await analyze(k, s.files, s.q.trim()); if (!s.result) s.err = 'No response from the AI.'; }
    catch (e) { s.err = e.message || 'Analysis failed.'; }
    s.busy = false; if (sec() === k) redraw();
  };

  /* KARNA chat: paperclip in the composer, result lands as chat bubbles */
  function mountClip() {
    var box = document.querySelector('#view .cbox'); if (!box || box.querySelector('.att-clip')) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'att-clip'; b.setAttribute('aria-label', 'Attach file, photo or PDF'); b.innerHTML = CLIP;
    b.onclick = function () { picker(false, chatAttach); };
    box.insertBefore(b, box.firstChild);
  }
  async function chatAttach(list) {
    var files = Array.prototype.filter.call(list || [], function (f) { return f.size <= MAX; }).slice(0, MAXN);
    if (!files.length) { toast('Files must be under 8 MB', true); return; }
    var inp = document.getElementById('jv-input'), q = inp ? inp.value.trim() : '';
    if (inp) { inp.value = ''; inp.style.height = 'auto'; }
    var box = document.getElementById('msgs'); if (!box) return;
    var u = { role: 'user', text: '\uD83D\uDCCE ' + files.map(function (f) { return f.name; }).join(', ') + (q ? ' \u2014 ' + q : '') };
    CHAT.push(u); box.insertAdjacentHTML('beforeend', bubbleHTML(u)); box.scrollTop = box.scrollHeight;
    var out; try { out = await analyze('jarvis', files, q); } catch (e) { out = 'Could not analyze: ' + (e.message || 'error'); }
    var a = { role: 'assistant', text: out || 'No response from the AI.' };
    CHAT.push(a); box.insertAdjacentHTML('beforeend', bubbleHTML(a)); box.scrollTop = box.scrollHeight;
  }

  /* paste a screenshot/photo straight into the question box */
  document.addEventListener('paste', function (e) {
    var t = e.target; if (!t || t.id !== 'att-q' || !e.clipboardData) return;
    var fs = Array.prototype.filter.call(e.clipboardData.files || [], function (f) { return /^image\//.test(f.name ? f.type : f.type); });
    if (fs.length) { e.preventDefault(); add(fs); }
  });

  var v = document.getElementById('view');
  if (v) new MutationObserver(function () { mount(); }).observe(v, { childList: true });
  mount();
})();
