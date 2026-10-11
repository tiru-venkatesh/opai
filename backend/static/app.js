/* OPAI application runtime.
 * Extracted from app.html without changing behavior.
 */

/* =====================================================================
   BACKEND CLIENT — Applications tab only, for now.
   ---------------------------------------------------------------------
   Every other tab (Outreach, Projects, Academics, Requests, Opportunities,
   Outbox, KARNA...) still runs on local demo data via `S`/save()/upsert().
   Applications is now backed by the real FastAPI server: BACKEND.ready
   tells the rest of the app whether that connection is up. If the server
   can't be reached at boot, Applications silently falls back to local
   demo rows so the app never breaks.
   ===================================================================== */
const LS_BASE = 'opa_api_base';
const DEFAULT_API = /^(localhost|127\.0\.0\.1)$/.test(location.hostname) ? 'http://localhost:8000' : 'https://opa-52ug.onrender.com';
const getBase = () => (localStorage.getItem(LS_BASE) || DEFAULT_API).replace(/\/+$/, '');

async function api(path, opts = {}) {
  const res = await fetch(getBase() + path, {
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    ...opts,
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch (e) {}
    throw new Error(res.status + ' ' + res.statusText + (detail ? ' - ' + detail : ''));
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}
function scopedApiPath(path) {
  const uid = BACKEND.userId;
  if (!uid || /(?:^|[?&])user_id=/.test(path)) return path;
  return path + (path.includes('?') ? '&' : '?') + 'user_id=' + encodeURIComponent(uid);
}
const GET   = (p)    => api(scopedApiPath(p));
const POST  = (p, b) => api(scopedApiPath(p), { method: 'POST',  body: b !== undefined ? JSON.stringify(b) : undefined });
const PATCH = (p, b) => api(scopedApiPath(p), { method: 'PATCH', body: JSON.stringify(b) });
const DEL   = (p)    => api(scopedApiPath(p), { method: 'DELETE' });

const BACKEND = { ready: false, userId: null };

/* -- field-name/value translation between this UI's local shape and the API's schemas.py shape -- */
const API_STATUS_OUT = { 'Not started': 'To Apply' };
const API_STATUS_IN  = { 'To Apply': 'Not started' };
const appFromApi = (r) => ({
  id: r.id, company: r.company, role: r.role, type: r.type,
  status: API_STATUS_IN[r.status] || r.status,
  deadline: r.deadline || null, notes: r.notes || '',
  effort_min: r.effort_minutes || 60,
});
const appToApi = (v) => ({
  company: v.company, role: v.role, type: v.type,
  status: API_STATUS_OUT[v.status] || v.status,
  deadline: v.deadline || null, notes: v.notes || '',
  effort_minutes: v.effort_min ? +v.effort_min : 60,
});

async function ensureUser() {
  if (BACKEND.userId) return BACKEND.userId;
  let r;
  if (AUTH.user && AUTH.user.email) {
    r = await POST('/v1/auth/dev-login?email=' + encodeURIComponent(AUTH.user.email) + '&name=' + encodeURIComponent(AUTH.user.name || ''));
  } else {
    throw new Error('Not signed in');
  }
  BACKEND.userId = r.user_id;
  return BACKEND.userId;
}
function updateConnBadge() {
  const el = $('conn-status'); if (!el) return;
  el.innerHTML = BACKEND.ready
    ? '<i style="background:var(--good);animation:none"></i><div><b>Connected</b>Live at ' + esc(getBase()) + '. Your data is saved to the backend.</div>'
    : '<i></i><div><b>Reconnecting\u2026</b>' + esc(getBase()) + ' is waking up or unreachable. Retrying automatically \u2014 no action needed.</div>';
}
/* No "connect" button anywhere: if the backend was unreachable (e.g. Render
   free-tier cold start after being idle), keep retrying silently in the
   background until it answers, then stop. This is what makes the connection
   feel "always on" instead of needing a manual reconnect. */
let _reconnectTimer = null;
function ensureAutoReconnect() {
  if (_reconnectTimer) return;
  _reconnectTimer = setInterval(async () => {
    if (BACKEND.ready) { clearInterval(_reconnectTimer); _reconnectTimer = null; return; }
    await syncBackend(true);
    if (BACKEND.ready) { clearInterval(_reconnectTimer); _reconnectTimer = null; render(true); toast('Backend connected'); }
  }, 15000);
}

/* -- profile: maps 1:1 to schemas.ProfileOut/ProfileUpdate, so no field renaming needed -- */
const PROFILE_FIELDS = ['name', 'branch', 'degree', 'cgpa', 'github', 'skills', 'highlight'];
function profileFromApi(r) {
  // Never let a blank or stale-placeholder backend name overwrite a real
  // name already showing locally (e.g. the person's Google display name).
  const name = (r.name && r.name !== 'Aditya Verma') ? r.name : (S.profile.name || '');
  return { name, branch: r.branch || '', degree: r.degree || '', cgpa: r.cgpa != null ? String(r.cgpa) : '',
    github: r.github || '', skills: r.skills || '', highlight: r.highlight || '', email: r.email || S.profile.email,
    track: [r.degree, r.branch].filter(Boolean).join(' ') };
}
async function loadProfileFromApi() {
  const uid = await ensureUser();
  const r = await GET('/v1/profile?user_id=' + uid);
  S.profile = { ...S.profile, ...profileFromApi(r) };
}
async function saveProfileToApi(v) {
  const uid = await ensureUser();
  const body = { name: v.name, branch: v.branch, degree: v.degree, cgpa: v.cgpa ? parseFloat(v.cgpa) : null, github: v.github, skills: v.skills, highlight: v.highlight };
  const r = await PATCH('/v1/profile?user_id=' + uid, body);
  S.profile = { ...S.profile, ...profileFromApi(r) };
}

let OB = { step: 0, data: {} };
const OB_STEPS = [
  { title: 'Who are you?', sub: 'Basic details so KARNA knows who it is working for.', fields: [
    { k:'name', l:'Full name', req:true },
    { k:'branch', l:'Branch', ph:'e.g. Computer Science', half:true },
    { k:'degree', l:'Degree & year', t:'select', half:true, opts:['B.Tech 1st year','B.Tech 2nd year','B.Tech 3rd year','B.Tech 4th year','M.Tech','B.E','M.E','BSc','MSc','Other'] },
  ]},
  { title: 'Your standing', sub: 'Used to score opportunities and tailor outreach.', fields: [
    { k:'cgpa', l:'CGPA', ph:'e.g. 8.5', half:true },
    { k:'github', l:'GitHub', ph:'github.com/username', half:true },
    { k:'skills', l:'Skills', ph:'React, Python, RAG', hint:'Comma-separated. Matched against opportunities and contacts.' },
  ]},
  { title: 'One highlight', sub: 'A single line KARNA can drop into outreach and cover letters.', fields: [
    { k:'highlight', l:'Resume highlight', t:'textarea', rows:3, ph:'e.g. Built a RAG pipeline used by 200+ students' },
  ]},
];
function showOnboarding() {
  OB = { step: 0, data: { ...S.profile } };
  $('onboard').classList.add('on');
  renderOnboard();
}
function renderOnboard() {
  const s = OB_STEPS[OB.step];
  $('ob-steps').innerHTML = OB_STEPS.map((_, i) => '<i class="' + (i === OB.step ? 'on' : i < OB.step ? 'done' : '') + '"></i>').join('');
  $('ob-body').innerHTML = '<div class="ob-dot-label">Step ' + (OB.step + 1) + ' of ' + OB_STEPS.length + '</div>' +
    '<div class="ob-h">' + esc(s.title) + '</div><div class="ob-sub">' + esc(s.sub) + '</div>' +
    '<div class="fields">' + s.fields.map(f => fieldHTML(f, OB.data)).join('') + '</div>';
  $('ob-nav').innerHTML =
    (OB.step > 0 ? '<button class="btn ghost" onclick="obBack()">Back</button>' : '<span></span>') +
    '<button class="btn" onclick="obNext()">' + (OB.step === OB_STEPS.length - 1 ? 'Finish' : 'Continue') + '</button>';
}
function obCollectStep() {
  const s = OB_STEPS[OB.step];
  let bad = null;
  s.fields.forEach(f => {
    const el = $('f-' + f.k); const v = el ? el.value.trim() : '';
    OB.data[f.k] = v;
    if (f.req && !v) bad = f;
  });
  if (bad) { const w = $('w-' + bad.k); if (w) w.classList.add('bad'); toast('Add ' + bad.l.toLowerCase() + ' to continue', true); return false; }
  return true;
}
function obBack() { if (!obCollectStep()) { /* still let them go back even if invalid */ } OB.step = Math.max(0, OB.step - 1); renderOnboard(); }
async function obNext() {
  if (!obCollectStep()) return;
  if (OB.step < OB_STEPS.length - 1) { OB.step++; renderOnboard(); return; }
  const v = OB.data;
  S.profile = { ...S.profile, ...v, onboarded: true };
  S.profile.track = [v.degree, v.branch].filter(Boolean).join(' ');
  if (BACKEND.ready) { try { await saveProfileToApi(v); } catch (e) { toast('Saved locally — could not sync to backend: ' + e.message, true); } }
  save(); $('onboard').classList.remove('on'); render(); toast('Profile saved — welcome in!'); setTimeout(() => showTutorial('welcome'), 600);
}

/* -- contacts (Outreach tab): maps to schemas.ContactOut/ContactCreate/ContactUpdate -- */
const contactFromApi = (r) => ({
  id: r.id, name: r.name, institute: r.institute, area: r.lab || '',
  tags: (r.research_areas || []).join(', '), email: r.email,
  status: r.status || 'Not started', sent_on: r.sent_on || null,
});
const contactToApi = (v) => ({
  name: v.name, institute: v.institute, lab: v.area || '',
  research_areas: splitList(v.tags), email: v.email,
});
async function loadContactsFromApi() {
  const rows = await GET('/v1/contacts');
  S.contacts = rows.map(contactFromApi);
}
let OUTREACH_DRAFTS = [];
async function loadOutreachFromApi(uid) {
  OUTREACH_DRAFTS = await GET('/v1/outreach?user_id=' + uid);
}
async function approveOutreachBackend(id) {
  try { await POST('/v1/outreach/' + id + '/mark-sent'); await syncBackend(true); toast('Marked as sent'); }
  catch (e) { toast('Could not approve: ' + e.message, true); }
}
async function rejectOutreachBackend(id) {
  try { await POST('/v1/outreach/' + id + '/reject'); await syncBackend(true); toast('Rejected'); }
  catch (e) { toast('Could not reject: ' + e.message, true); }
}
const cap = (x) => x ? x.charAt(0).toUpperCase() + x.slice(1) : '';
const projFromApi = (p, ts) => ({ id: p.id, name: p.title, description: p.description || '',
  tasks: (ts || []).map(t => ({ id: t.id, name: t.title, done: t.status === 'done' })) });
const acadFromApi = (a) => ({ id: a.id, subject: a.subject, task: a.task || '', exam_date: a.exam_date || null,
  effort_min: a.effort_minutes || 60, done: !!a.done });
const reqFromApi = (r) => ({ id: r.id, client: r.client, ask: r.ask || '', scope: r.scope || '', timeline: r.timeline || '',
  price: r.price || '', email: r.email || '', status: r.status || 'New' });
const oppFromApi = (o) => ({ id: o.id, title: o.title, org: o.company_or_lab, type: cap(o.type), tags: (o.tags || []).join(', '),
  deadline: o.deadline || null, status: cap(o.status) || 'New' });
const PUSH = {
  projects: async (v) => { const uid = await ensureUser(); const b = { title: v.name, description: v.description || '' };
    return v.id ? PATCH('/v1/projects/' + v.id, b) : POST('/v1/projects', { user_id: uid, ...b }); },
  academics: async (v) => { const uid = await ensureUser();
    const b = { subject: v.subject, task: v.task || null, exam_date: v.exam_date || null, effort_minutes: v.effort_min ? +v.effort_min : 60 };
    return v.id ? PATCH('/v1/academics/' + v.id, { ...b, done: !!v.done }) : POST('/v1/academics', { user_id: uid, ...b }); },
  requests: async (v) => { const uid = await ensureUser();
    const b = { client: v.client, ask: v.ask || '', scope: v.scope || '', timeline: v.timeline || '', price: v.price || '', email: v.email || '' };
    return v.id ? PATCH('/v1/requests/' + v.id, { ...b, status: v.status || 'New' }) : POST('/v1/requests', { user_id: uid, ...b }); },
  opportunities: async (v) => { if (v.id) throw new Error('editing saved opportunities is not supported by the backend yet');
    return POST('/v1/opportunities', { title: v.title, company_or_lab: v.org || '', type: (v.type || 'internship').toLowerCase(),
      tags: splitList(v.tags || ''), deadline: v.deadline || null, source: 'manual' }); },
};
const DELPATH = { applications: '/v1/applications/', projects: '/v1/projects/', academics: '/v1/academics/', requests: '/v1/requests/', contacts: '/v1/contacts/' };
async function syncBackend(silent) {
  try {
    const uid = await ensureUser();
    const [apps, contacts, projs, acads, reqs, opps] = await Promise.all([
      GET('/v1/applications?user_id=' + uid),
      GET('/v1/contacts'),
      GET('/v1/projects?user_id=' + uid),
      GET('/v1/academics?user_id=' + uid),
      GET('/v1/requests?user_id=' + uid),
      GET('/v1/opportunities').catch(() => []),
    ]);
    const ptasks = await Promise.all(projs.map(p => GET('/v1/tasks?user_id=' + uid + '&project_id=' + p.id).catch(() => [])));
    S.projects = projs.map((p, i) => projFromApi(p, ptasks[i]));
    S.academics = acads.map(acadFromApi);
    S.requests = reqs.map(reqFromApi);
    S.opportunities = (opps || []).map(oppFromApi);
    S.applications = apps.map(appFromApi);
    S.contacts = contacts.map(contactFromApi);
    await loadOutreachFromApi(uid);
    await loadProfileFromApi();
    BACKEND.ready = true;
  } catch (e) {
    BACKEND.ready = false;
    console.warn('Backend unreachable, using local demo data:', e.message);
    ensureAutoReconnect();
  }
  updateConnBadge();
  render();
  if (!silent && !S.profile.onboarded) showOnboarding();
  else if (!silent && !S.profile.tutorialSeen) setTimeout(() => showTutorial('welcome'), 500);
}
 
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
  star:'<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9L12 16.9 6.8 19.7l1-5.9L3.5 9.7l5.9-.8L12 3.5z"/>',
  spark:'<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z"/><path d="M19 16l.7 1.8 1.8.7-1.8.7L19 21l-.7-1.8-1.8-.7 1.8-.7L19 16z"/>',
  moon:'<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  monitor:'<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  dock:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  wide:'<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
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
  grad:'<path d="M2 9.5 12 5l10 4.5-10 4.5-10-4.5z"/><path d="M6 12v4.5c0 1.2 2.7 2.5 6 2.5s6-1.3 6-2.5V12"/>',
  shield:'<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/><path d="m9 12 2 2 4-4"/>'
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
      name: '', track: '', branch: '', degree: '', cgpa: '', github: '', email: '',
      skills: '', highlight: '', onboarded: false
    },
    applications: [],
    opportunities: [],
    contacts: [],
    projects: [],
    academics: [],
    requests: [],
    outbox: [],
    history: [{ id: uid(), at: new Date().toISOString(), text: 'Workspace created' }],
    doneToday: { date: iso(0), items: [] },
    daily: {},
    studyPlanCanvas: { month: { nodes: [], edges: [] }, year: { nodes: [], edges: [] } }
  };
}
function load() {
  try {
    const r = localStorage.getItem(LS_KEY);
    if (r) {
      const o = JSON.parse(r);
      if (!o.demoPurged) { // one-time cleanup of the old built-in sample data
        o.demoPurged = true;
        if ((o.history || []).some(h => /sample data/i.test(h.text || ''))) {
          ['applications','opportunities','contacts','projects','academics','requests'].forEach(k => o[k] = []);
          o.history = [];
        }
      }
      if (!o.studyPlanCanvas) o.studyPlanCanvas = { month: { nodes: [], edges: [] }, year: { nodes: [], edges: [] } };
      return o;
    }
  } catch (e) {}
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
  out:  { label: 'Internships',      color: 'var(--c-out)',  icon: 'mail' },
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
  confirmBox('Delete ' + label + '?', 'Delete', async () => {
    const idx = S[coll].findIndex(x => x.id === id); const snap = S[coll][idx];
    if (DELPATH[coll] && BACKEND.ready) {
      try { await DEL(DELPATH[coll] + id); } catch (e) { toast('Could not delete: ' + e.message, true); return; }
    }
    remove(coll, id); log('Deleted ' + label); save(); render();
    toast('Deleted ' + label, DELPATH[coll] && BACKEND.ready ? false : false, DELPATH[coll] && BACKEND.ready ? undefined : { label: 'Undo', fn: () => { S[coll].splice(Math.min(idx, S[coll].length), 0, snap); S.history.shift(); save(); render(); } });
  });
}
 
/* ================= 5. STATUS PILLS ================= */
const TONE = { 'Not started':'', Applied:'brand', Interview:'warn', Offer:'good', Rejected:'bad', New:'brand', Converted:'good', Dismissed:'', Drafted:'warn', Sent:'good', Replied:'good', Scoped:'warn', Quoted:'brand', Won:'good', Declined:'bad', pending:'warn', approved:'good', rejected:'bad' };
const LABEL = { pending:'Needs approval', approved:'Approved', rejected:'Rejected' };
const pill = (s) => '<span class="pill ' + (TONE[s] || '') + '">' + esc(LABEL[s] || s) + '</span>';
const meter = (score) => '<div class="meter' + (score >= 60 ? ' hi' : '') + '" title="' + score + '% skill match"><div><i style="width:' + score + '%"></i></div>' + score + '% match</div>';
const head = (title, sub, action) => '<div class="head"><div><h1>' + title + '</h1>' + (sub ? '<p>' + sub + '</p>' : '') + '</div><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' + (action || '') + '<button class="btn ghost" onclick="showTutorial()" title="Step-by-step guide for this page">? How to use</button></div></div>';
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
    onSave: async (v) => { v.deadline = v.deadline || null;
      if (!BACKEND.ready) { if (id) v.id = id; upsert('applications', v); log((id ? 'Updated ' : 'Added application: ') + v.company); closeModal(); render(); toast('Saved'); return; }
      try {
        if (id) { const r = await PATCH('/v1/applications/' + id, appToApi(v)); const i = S.applications.findIndex(x => x.id === id); if (i > -1) S.applications[i] = appFromApi(r); log('Updated ' + v.company); }
        else { const uid = await ensureUser(); const r = await POST('/v1/applications', { user_id: uid, ...appToApi(v) }); S.applications.unshift(appFromApi(r)); log('Added application: ' + v.company); }
        closeModal(); render(); toast('Saved');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    } });
}
function dragApp(e, id) { e.dataTransfer.setData('text/plain', id); e.dataTransfer.effectAllowed = 'move'; e.currentTarget.classList.add('dragging'); }
async function setAppStatus(a, st) {
  if (!BACKEND.ready) { a.status = st; log(a.company + ' moved to ' + st); save(); render(); toast(a.company + ': ' + st); return; }
  try {
    const r = await PATCH('/v1/applications/' + a.id, { status: API_STATUS_OUT[st] || st });
    const i = S.applications.findIndex(x => x.id === a.id); if (i > -1) S.applications[i] = appFromApi(r);
    log(a.company + ' moved to ' + st); render(); toast(a.company + ': ' + st);
  } catch (e) { toast('Could not update status: ' + e.message, true); render(); }
}
function dropApp(e, st) {
  e.preventDefault();
  const a = byId('applications', e.dataTransfer.getData('text/plain'));
  if (!a || a.status === st) { render(); return; }
  setAppStatus(a, st);
}
function advanceApp(id) { const a = byId('applications', id); if (!a || !APP_NEXT[a.status]) return; setAppStatus(a, APP_NEXT[a.status]); }
 
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
async function convertOpp(id) {
  const o = byId('opportunities', id); if (!o) return;
  const type = ['Internship','Research','Hackathon'].includes(o.type) ? o.type : 'Internship';
  const v = { company: o.org || o.title, role: o.title, type, deadline: o.deadline || null, status: 'Not started', effort_min: 60, notes: '' };
  if (BACKEND.ready) {
    try { const uid = await ensureUser(); const r = await POST('/v1/applications', { user_id: uid, ...appToApi(v) }); S.applications.unshift(appFromApi(r)); }
    catch (e) { toast('Could not add to Applications: ' + e.message, true); return; }
  } else upsert('applications', v);
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
      '<div class="note" style="margin:0 0 16px">Being straight about how this works: a page running in your browser cannot reach iitd.ac.in, iitk.ac.in, etc. directly \u2014 those sites block cross-origin requests from other sites, which is a browser security rule, not something OPAI can bypass. So "full data" here means two things: a small hand-verified starter list below, sourced from public department pages, and a scanner that turns a pasted faculty page into structured contacts in one go. Always double-check an email before sending \u2014 department pages change.</div>' +
      '<h4 style="font-family:var(--display);font-weight:650;font-size:14px;margin-bottom:8px">Verified starter contacts</h4>' +
      '<div class="panel rows" style="margin-bottom:18px">' + seedRows + '</div>' +
      '<h4 style="font-family:var(--display);font-weight:650;font-size:14px;margin-bottom:8px">Scan a full department page</h4>' +
      '<p class="row-s" style="margin-bottom:14px">Open a department\u2019s page below, select-all + copy the faculty section, and paste it here. OPAI pulls out every name, email, and research area it can find in one pass, matches each against your skills, and you pick which ones become outreach contacts.</p>' +
      '<div class="row-m" style="margin-bottom:16px">' + linkRow + '</div>' +
      '<div class="field"><label for="faculty-inst">Institute (used for every row you add)</label><input id="faculty-inst" type="text" placeholder="e.g. IIT Delhi, CSE" value="' + escA(S._facultyInst || '') + '"></div>' +
      '<div class="field"><label for="faculty-paste">Pasted faculty listing</label><textarea id="faculty-paste" rows="6" placeholder="Paste the copied faculty section here \u2014 works best with one professor\u2019s name, research interests, and email per block"></textarea></div>' +
      '<button class="btn soft" onclick="parseFacultyPaste()">Scan for contacts</button>' +
      rowsHTML +
      '</div>' : '') + '</section>';
}
function viewOutreach() {
  const h = head('Internships', 'Professors, founders and recruiters to email for internships. Drafting creates an Outbox item, and nothing goes out until you approve it.', addBtn('Add contact', 'editContact()'));
  const finder = internIntroHTML() + facultyFinderHTML();
  if (!S.contacts.length) return h + finder + demoMailsHTML() + emptyPanel('No contacts yet', 'Add a professor, founder, or recruiter to start drafting, or use the IIT faculty database above.', '<button class="btn" onclick="editContact()">Add contact</button>');
  const rows = S.contacts.map(c => {
    const sc = matchScore(c.tags, S.profile.skills);
    let act = '';
    if (c.status === 'Not started') act = '<button class="btn sm" onclick="draftOutreach(\'' + c.id + '\')">Draft email</button>';
    else if (c.status === 'Drafted') act = '<button class="btn soft sm" onclick="switchTab(\'outbox\')">Open in Outbox</button>';
    else if (c.status === 'Sent') act = '<button class="btn soft sm" onclick="draftOutreach(\'' + c.id + '\')">Draft follow-up</button>';
    return '<div class="row" style="grid-template-columns:auto 1fr auto"><div class="swatch" style="--c:var(--c-out)">' + icon('mail', 16) + '</div><div><div class="row-t">' + esc(c.name) + '</div><div class="row-s">' + esc(c.institute) + (c.area ? ' · ' + esc(c.area) : '') + '</div><div class="row-m">' + pill(c.status) + meter(sc) + (c.sent_on ? '<span class="chip">Sent ' + fmtDate(c.sent_on) + '</span>' : '') + '</div></div><div class="row-a">' + act + rowBtns('editContact(\'' + c.id + '\')', 'confirmDelete(\'contacts\',\'' + c.id + '\',\'' + escA(c.name) + '\')') + '</div></div>';
  }).join('');
  return h + finder + '<div class="panel rows">' + rows + '</div>' + demoMailsHTML();
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
 
/* ---- Exams & Courses (SEMS) ---- */
let SEMS = { loading: false, error: null, semester: null, courses: null, exams: null, openCourse: null, courseTopics: {} };
function semsReset() { SEMS = { loading: false, error: null, semester: null, courses: null, exams: null, openCourse: null, courseTopics: {} }; }
async function loadSems(force) {
  if (!BACKEND.ready) { if (SEMS.error !== 'backend') { SEMS.error = 'backend'; render(true); } return; }
  if (SEMS.loading) return;
  if (!force && SEMS.courses !== null) return;
  SEMS.loading = true; SEMS.error = null; render(true);
  try {
    const uid = await ensureUser();
    SEMS.semester = await GET('/v1/semesters/current?user_id=' + uid).catch(() => null);
    SEMS.courses = await GET('/v1/courses?user_id=' + uid);
    SEMS.exams = await GET('/v1/exams?user_id=' + uid).catch(() => []);
  } catch (e) { SEMS.error = e.message || 'Request failed'; SEMS.courses = SEMS.courses || []; SEMS.exams = SEMS.exams || []; }
  SEMS.loading = false; render(true);
}
function semsCourseExams(cid) { return (SEMS.exams || []).filter(e => e.course_id === cid); }
function semsCourseTopics(cid) { return SEMS.courseTopics[cid] || null; }
async function loadCourseTopics(cid) { try { SEMS.courseTopics[cid] = await GET('/v1/courses/' + cid + '/topics'); } catch (e) { SEMS.courseTopics[cid] = []; } render(true); }
function toggleCourseOpen(cid) { SEMS.openCourse = SEMS.openCourse === cid ? null : cid; if (SEMS.openCourse && !semsCourseTopics(cid)) loadCourseTopics(cid); render(true); }

function editSemester() {
  const s = SEMS.semester || {};
  openForm({ title: SEMS.semester ? 'Edit semester' : 'Set up semester', values: s, saveLabel: 'Save',
    fields: [
      { k: 'college', l: 'College', half: true }, { k: 'degree', l: 'Degree', half: true, ph: 'e.g. B.Tech' },
      { k: 'branch', l: 'Branch', half: true }, { k: 'semester_number', l: 'Semester number', half: true, num: true, ph: 'e.g. 5' },
      { k: 'academic_year', l: 'Academic year', half: true, ph: 'e.g. 2026-27' },
      { k: 'daily_study_minutes', l: 'Daily study minutes', half: true, num: true, ph: '180' },
      { k: 'start_date', l: 'Semester start', t: 'date', half: true }, { k: 'end_date', l: 'Semester end', t: 'date', half: true },
      { k: 'exam_period_start', l: 'Exam period start', t: 'date', half: true }, { k: 'exam_period_end', l: 'Exam period end', t: 'date', half: true },
      { k: 'peak_start', l: 'Peak focus start', half: true, ph: '19:00' }, { k: 'peak_end', l: 'Peak focus end', half: true, ph: '22:00' }
    ],
    onSave: async (v) => {
      try {
        const uid = await ensureUser();
        const body = { ...v };
        ['start_date', 'end_date', 'exam_period_start', 'exam_period_end'].forEach(k => { body[k] = body[k] || null; });
        body.semester_number = v.semester_number ? +v.semester_number : null;
        body.daily_study_minutes = v.daily_study_minutes ? +v.daily_study_minutes : 180;
        const row = SEMS.semester
          ? await PATCH('/v1/semesters/' + SEMS.semester.id, { user_id: uid, ...body })
          : await POST('/v1/semesters', { user_id: uid, ...body });
        SEMS.semester = row; closeModal(); render(true); toast('Semester saved');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    }
  });
}
function editCourse() {
  openForm({ title: 'Add course', saveLabel: 'Add course',
    fields: [
      { k: 'name', l: 'Course name', req: true, ph: 'e.g. Database Systems' },
      { k: 'code', l: 'Course code', half: true, ph: 'e.g. CS301' },
      { k: 'credits', l: 'Credits', half: true, ph: 'e.g. 4' },
      { k: 'faculty', l: 'Faculty', half: true }
    ],
    onSave: async (v) => {
      if (!SEMS.semester) { toast('Set up your semester first', true); return; }
      try {
        const uid = await ensureUser();
        const body = { name: v.name, code: v.code || null, credits: v.credits ? parseFloat(v.credits) : null, faculty: v.faculty || null };
        const row = await POST('/v1/courses', { user_id: uid, semester_id: SEMS.semester.id, source: 'manual', ...body });
        SEMS.courses = [row].concat(SEMS.courses || []);
        closeModal(); render(true); toast('Course added');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    }
  });
}
function editTopic(courseId) {
  openForm({ title: 'Add topic', saveLabel: 'Add topic',
    fields: [
      { k: 'name', l: 'Topic name', req: true },
      { k: 'unit', l: 'Unit', half: true },
      { k: 'estimated_minutes', l: 'Estimated minutes', half: true, num: true, ph: '60' },
      { k: 'difficulty', l: 'Difficulty (1-5)', half: true, num: true, ph: '3' },
      { k: 'exam_weightage', l: 'Exam weightage %', half: true, num: true, ph: '10' },
      { k: 'confidence', l: 'Your confidence (1-5)', half: true, num: true, ph: '1' },
      { k: 'notes', l: 'Notes', t: 'textarea', rows: 2 }
    ],
    onSave: async (v) => {
      try {
        const body = { name: v.name, unit: v.unit || null, estimated_minutes: v.estimated_minutes ? +v.estimated_minutes : 60,
          difficulty: v.difficulty ? +v.difficulty : 3, exam_weightage: v.exam_weightage ? +v.exam_weightage : 10,
          confidence: v.confidence ? +v.confidence : 1, notes: v.notes || null };
        const row = await POST('/v1/courses/' + courseId + '/topics', body);
        SEMS.courseTopics[courseId] = (SEMS.courseTopics[courseId] || []).concat([row]);
        closeModal(); render(true); toast('Topic added');
      } catch (e) { toast('Could not add topic: ' + e.message, true); }
    }
  });
}
function quickTopicUpdate(topicId) {
  let cid = null, cur = null;
  Object.keys(SEMS.courseTopics).forEach(k => { const t = (SEMS.courseTopics[k] || []).find(x => x.id === topicId); if (t) { cid = k; cur = t; } });
  if (!cur) return;
  openForm({ title: 'Update \u201c' + cur.name + '\u201d', saveLabel: 'Save', values: cur,
    fields: [
      { k: 'status', l: 'Status', t: 'select', half: true, opts: ['not_started', 'in_progress', 'done'] },
      { k: 'confidence', l: 'Confidence (1-5)', half: true, num: true },
      { k: 'difficulty', l: 'Difficulty (1-5)', half: true, num: true },
      { k: 'notes', l: 'Notes', t: 'textarea', rows: 2 }
    ],
    onSave: async (v) => {
      try {
        const body = { status: v.status, confidence: v.confidence ? +v.confidence : undefined, difficulty: v.difficulty ? +v.difficulty : undefined, notes: v.notes || undefined };
        const row = await PATCH('/v1/topics/' + topicId, body);
        SEMS.courseTopics[cid] = SEMS.courseTopics[cid].map(x => x.id === topicId ? row : x);
        closeModal(); render(true); toast('Saved');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    }
  });
}
function editExam(courseId, examId) {
  const e = examId ? (SEMS.exams || []).find(x => x.id === examId) : { exam_type: 'End Semester', weightage: 100, status: 'tentative' };
  openForm({ title: examId ? 'Edit exam' : 'Add exam', values: e, saveLabel: examId ? 'Save changes' : 'Add exam',
    fields: [
      { k: 'exam_type', l: 'Exam type', half: true, ph: 'e.g. End Semester' },
      { k: 'status', l: 'Status', t: 'select', half: true, opts: ['tentative', 'confirmed', 'completed'] },
      { k: 'exam_date', l: 'Exam date', t: 'date', half: true },
      { k: 'exam_time', l: 'Exam time', half: true, ph: 'e.g. 10:00 AM' },
      { k: 'venue', l: 'Venue', half: true },
      { k: 'weightage', l: 'Weightage %', half: true, num: true, ph: '100' }
    ],
    onSave: async (v) => {
      try {
        const uid = await ensureUser();
        const body = { exam_type: v.exam_type, exam_date: v.exam_date || null, exam_time: v.exam_time || null, venue: v.venue || null,
          weightage: v.weightage ? +v.weightage : 100, status: v.status || 'tentative' };
        const row = examId ? await PATCH('/v1/exams/' + examId, { user_id: uid, course_id: courseId, ...body }) : await POST('/v1/exams', { user_id: uid, course_id: courseId, ...body });
        SEMS.exams = examId ? SEMS.exams.map(x => x.id === examId ? row : x) : (SEMS.exams || []).concat([row]);
        closeModal(); render(true); toast('Saved');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    }
  });
}
async function viewExamRisk(examId) {
  try {
    const r = await GET('/v1/exams/' + examId + '/risk');
    openModal('<h3>' + esc(r.course_name) + '</h3>' +
      '<div class="row-s" style="margin-bottom:10px">' + (r.exam_date ? 'Exam ' + fmtDate(r.exam_date) + ' \u00b7 ' : '') + (r.days_until != null ? r.days_until + ' days away' : 'No date set') + '</div>' +
      '<div class="score-grid"><div class="score-cell ' + (r.preparation_pct >= 70 ? 'good' : r.preparation_pct >= 40 ? 'warn' : 'bad') + '"><b>' + r.preparation_pct + '%</b><span>Prepared</span></div>' +
      '<div class="score-cell ' + (r.risk_level === 'low' ? 'good' : r.risk_level === 'medium' ? 'warn' : 'bad') + '"><b>' + esc(r.risk_level) + '</b><span>Risk</span></div></div>' +
      (r.weak_topics.length ? '<div class="row-s" style="margin-top:14px">Weak topics: ' + r.weak_topics.map(esc).join(', ') + '</div>' : '') +
      '<div class="foot"><button class="btn ghost" onclick="closeModal()">Close</button></div>');
  } catch (e) { toast('Could not load risk: ' + e.message, true); }
}
let SEMS_IMPORT = null;
function importCoursesOpen() {
  if (!SEMS.semester) { toast('Set up your semester first', true); return; }
  openModal('<h3>Import a timetable</h3><div class="field"><label for="sems-csv">Paste CSV or a copied table</label><textarea id="sems-csv" rows="8" placeholder="course_code,course_name,credits,faculty,exam_date,exam_time,venue"></textarea></div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" onclick="importCoursesPreview()">Preview</button></div>');
}
async function importCoursesPreview() {
  const text = $('sems-csv').value;
  if (!text.trim()) { toast('Paste something first', true); return; }
  try {
    const res = await POST('/v1/courses/import-csv/preview', { csv_text: text });
    SEMS_IMPORT = res.rows;
    const rows = SEMS_IMPORT.map((r) => '<div class="row noicon"><div><div class="row-t">' + esc(r.name) + (r.code ? ' \u00b7 ' + esc(r.code) : '') + '</div><div class="row-s">' + (r.exam_date ? fmtDate(r.exam_date) : 'No date') + (r.faculty ? ' \u00b7 ' + esc(r.faculty) : '') + '</div>' + (r.issues.length ? '<div class="chip warn" style="margin-top:6px">' + esc(r.issues.join('; ')) + '</div>' : '') + '</div><div class="row-a"><span class="chip">' + r.confidence_pct + '% confident</span></div></div>').join('');
    openModal('<h3>Review ' + SEMS_IMPORT.length + ' row' + (SEMS_IMPORT.length === 1 ? '' : 's') + '</h3><div class="panel rows" style="max-height:340px;overflow-y:auto">' + rows + '</div><div class="note">Rows with low confidence or issues can be fixed afterward in Courses. Nothing is saved until you confirm.</div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" onclick="importCoursesConfirm()">Create ' + SEMS_IMPORT.length + ' course' + (SEMS_IMPORT.length === 1 ? '' : 's') + '</button></div>');
  } catch (e) { toast('Could not parse: ' + e.message, true); }
}
async function importCoursesConfirm() {
  try {
    const uid = await ensureUser();
    const rows = await POST('/v1/courses/import-csv/confirm', { user_id: uid, semester_id: SEMS.semester.id, rows: SEMS_IMPORT });
    closeModal(); toast('Imported ' + rows.length + ' course' + (rows.length === 1 ? '' : 's')); loadSems(true);
  } catch (e) { toast('Could not import: ' + e.message, true); }
}
/* ---- PDF timetable: upload -> AI draft -> chat refine -> confirm ---- */
let PDF_TT = null, PDF_HIST = [];
function pdfTtOpen() {
  PDF_TT = null; PDF_HIST = [];
  openModal('<h3>Upload timetable PDF</h3><div class="field"><label for="pdf-file">Exam / semester timetable (text PDF, max 8 MB)</label><input id="pdf-file" type="file" accept="application/pdf"></div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="pdf-go" onclick="pdfTtAnalyze()">Analyze</button></div>');
}
function pdfTtB64(f) { return new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result.split(',')[1]); r.onerror = no; r.readAsDataURL(f); }); }
async function pdfTtAnalyze() {
  const f = $('pdf-file').files[0];
  if (!f) { toast('Choose a PDF first', true); return; }
  if (f.size > 8 * 1024 * 1024) { toast('PDF is over 8 MB', true); return; }
  const b = $('pdf-go'); b.disabled = true; b.textContent = 'Analyzing\u2026';
  try {
    const r = await POST('/v1/timetable/pdf/analyze', { pdf_base64: await pdfTtB64(f) });
    PDF_TT = r; PDF_HIST = [{ role: 'ai', text: r.reply }]; pdfTtRender();
  } catch (e) { b.disabled = false; b.textContent = 'Analyze'; toast('Could not analyze: ' + e.message, true); }
}
function pdfTtRender() {
  const d = PDF_TT.draft, s = d.semester || {};
  const head = [s.degree, s.branch, s.semester_number ? 'Sem ' + s.semester_number : '', s.academic_year].filter(Boolean).map(esc).join(' \u00b7 ') || 'Semester';
  const rows = d.courses.map((c) => '<div class="row noicon"><div><div class="row-t">' + esc(c.name) + (c.code ? ' \u00b7 ' + esc(c.code) : '') + '</div><div class="row-s">' + (c.exam_date ? fmtDate(c.exam_date) : 'No date') + (c.exam_time ? ' \u00b7 ' + esc(c.exam_time) : '') + (c.venue ? ' \u00b7 ' + esc(c.venue) : '') + '</div></div></div>').join('');
  const warns = PDF_TT.warnings.filter((w) => w.level !== 'info').map((w) => '<div class="chip warn" style="margin:4px 4px 0 0">' + esc(w.text) + '</div>').join('');
  const chat = PDF_HIST.map((m) => '<div class="row-s" style="margin:6px 0;' + (m.role === 'me' ? 'text-align:right;font-weight:600' : '') + '">' + esc(m.text) + '</div>').join('');
  openModal('<h3>' + head + '</h3><div class="panel rows" style="max-height:230px;overflow-y:auto">' + rows + '</div>' + warns +
    '<div id="pdf-chat" style="max-height:110px;overflow-y:auto;margin-top:10px">' + chat + '</div>' +
    '<div class="field" style="margin-top:8px"><input id="pdf-msg" placeholder="Ask or change something\u2026 e.g. move DBMS to Nov 22" onkeydown="if(event.key===\'Enter\')pdfTtSend()"></div>' +
    '<div class="note">Nothing is saved until you confirm.</div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn ghost" id="pdf-send" onclick="pdfTtSend()">Send</button><button class="btn" id="pdf-ok" onclick="pdfTtConfirm()">Confirm &amp; create</button></div>');
  const c = $('pdf-chat'); if (c) c.scrollTop = c.scrollHeight;
}
async function pdfTtSend() {
  const el = $('pdf-msg'), msg = el.value.trim();
  if (!msg) return;
  $('pdf-send').disabled = true; el.disabled = true;
  try {
    const r = await POST('/v1/timetable/pdf/refine', { draft: PDF_TT.draft, message: msg, history: PDF_HIST });
    PDF_HIST.push({ role: 'me', text: msg }, { role: 'ai', text: r.reply });
    PDF_TT = { draft: r.draft, warnings: r.warnings, reply: r.reply };
  } catch (e) { toast('Chat failed: ' + e.message, true); }
  pdfTtRender();
}
async function pdfTtConfirm() {
  const b = $('pdf-ok'); b.disabled = true;
  try {
    const uid = await ensureUser();
    const r = await POST('/v1/timetable/pdf/confirm', { user_id: uid, draft: PDF_TT.draft, semester_id: SEMS.semester ? SEMS.semester.id : null });
    closeModal(); toast('Created ' + r.courses + ' courses, ' + r.exams + ' exams'); loadSems(true);
  } catch (e) { b.disabled = false; toast('Could not create: ' + e.message, true); }
}

function viewSems() {
  const h = head('Exams & Courses', 'Set up your semester and courses so Study Workflow can build a real study plan from your syllabus.', '');
  if (!BACKEND.ready) return h + emptyPanel('Needs the backend', 'Semester and course setup is saved on your FastAPI server, which could not be reached.', '<button class="btn" onclick="loadSems(true)">Retry</button>');
  if (SEMS.courses === null) return h + '<div class="empty plain"><h3>Loading\u2026</h3><p>Fetching your semester and courses.</p></div>';
  if (SEMS.error && SEMS.error !== 'backend') return h + emptyPanel('Could not load', esc(SEMS.error), '<button class="btn" onclick="loadSems(true)">Retry</button>');

  const semPanel = SEMS.semester
    ? '<section class="panel" style="padding:18px;margin-bottom:18px"><div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">' +
        '<div><div class="row-t">' + esc([SEMS.semester.degree, SEMS.semester.branch].filter(Boolean).join(' \u00b7 ') || 'Current semester') + '</div>' +
        '<div class="row-s">' + esc(SEMS.semester.academic_year || '') + (SEMS.semester.semester_number ? ' \u00b7 Semester ' + SEMS.semester.semester_number : '') + ' \u00b7 ' + SEMS.semester.daily_study_minutes + ' min/day \u00b7 peak ' + esc(SEMS.semester.peak_start) + '\u2013' + esc(SEMS.semester.peak_end) + '</div></div>' +
        '<button class="btn ghost sm" onclick="editSemester()">Edit</button></div></section>'
    : '<section class="panel" style="padding:18px;margin-bottom:18px"><div class="row-t" style="margin-bottom:4px">No semester set up yet</div><div class="row-s" style="margin-bottom:12px">Set this up once \u2014 it drives your daily study capacity and exam window.</div><button class="btn" onclick="editSemester()">Set up semester</button></section>';

  const courseRows = (SEMS.courses || []).map(c => {
    const exams = semsCourseExams(c.id);
    const topics = semsCourseTopics(c.id);
    const open = SEMS.openCourse === c.id;
    const examChips = exams.map(e => '<span class="chip">' + esc(e.exam_type) + (e.exam_date ? ' \u00b7 ' + fmtDate(e.exam_date) : '') + '</span>').join('');
    const body = open ? (
      '<div style="padding:0 20px 18px">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 8px"><b class="row-s" style="font-weight:650">Topics</b><button class="btn ghost sm" onclick="editTopic(\'' + c.id + '\')">Add topic</button></div>' +
        (topics === null ? '<div class="row-s">Loading\u2026</div>' :
          topics.length ? '<div class="panel rows">' + topics.map(t =>
            '<div class="row noicon"><div><div class="row-t">' + esc(t.name) + (t.unit ? ' \u00b7 ' + esc(t.unit) : '') + '</div><div class="row-m">' + pill(t.status) + '<span class="chip">weight ' + t.exam_weightage + '%</span><span class="chip">difficulty ' + t.difficulty + '/5</span><span class="chip">confidence ' + t.confidence + '/5</span></div></div>' +
            '<div class="row-a"><button class="btn ghost sm" onclick="quickTopicUpdate(\'' + t.id + '\')">Update</button></div></div>'
          ).join('') + '</div>' : '<div class="row-s">No topics yet.</div>') +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin:18px 0 8px"><b class="row-s" style="font-weight:650">Exams</b><button class="btn ghost sm" onclick="editExam(\'' + c.id + '\')">Add exam</button></div>' +
        (exams.length ? '<div class="panel rows">' + exams.map(e =>
          '<div class="row noicon"><div><div class="row-t">' + esc(e.exam_type) + '</div><div class="row-s">' + (e.exam_date ? fmtDate(e.exam_date) : 'No date set') + (e.exam_time ? ' \u00b7 ' + esc(e.exam_time) : '') + (e.venue ? ' \u00b7 ' + esc(e.venue) : '') + '</div></div>' +
          '<div class="row-a"><button class="btn ghost sm" onclick="viewExamRisk(\'' + e.id + '\')">Risk</button><button class="btn ghost sm" onclick="editExam(\'' + c.id + '\',\'' + e.id + '\')">Edit</button></div></div>'
        ).join('') + '</div>' : '<div class="row-s">No exams yet.</div>') +
      '</div>'
    ) : '';
    return '<div class="panel" style="margin-bottom:10px"><div class="row noicon" style="cursor:pointer" onclick="toggleCourseOpen(\'' + c.id + '\')"><div><div class="row-t">' + esc(c.name) + (c.code ? ' \u00b7 ' + esc(c.code) : '') + '</div><div class="row-m">' + (c.faculty ? '<span class="chip">' + esc(c.faculty) + '</span>' : '') + (c.credits != null ? '<span class="chip">' + c.credits + ' credits</span>' : '') + examChips + '</div></div><div class="row-a">' + icon(open ? 'x' : 'plus', 16) + '</div></div>' + body + '</div>';
  }).join('');

  const coursesSection = '<div style="display:flex;justify-content:space-between;align-items:center;margin:22px 0 10px"><h3 style="font-family:var(--display);font-size:18px;font-weight:650">Courses</h3>' + addBtn('Add course', 'editCourse()') + '</div>' +
    (SEMS.courses.length ? courseRows : emptyPanel('No courses yet', 'Add your first course, then add its topics and exams.', addBtn('Add course', 'editCourse()')));

  const importSection = '<section class="panel" style="padding:18px;margin-top:22px"><div class="row-t" style="margin-bottom:4px">Import a timetable</div><div class="row-s" style="margin-bottom:12px">Paste a course/exam timetable (CSV or a copied table) and OPAI will match columns and show a preview before creating anything.</div><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" onclick="pdfTtOpen()">Upload PDF</button><button class="btn ghost" onclick="importCoursesOpen()">Paste a timetable</button></div></section>';

  return h + semPanel + coursesSection + importSection;
}

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

/* ---- Agent Console: live view onto the backend's safety layer (tool
   whitelist / emergency stop, activity log, structured memory). Unlike most
   tabs this is backend-only, no local-demo fallback - if the backend is
   unreachable it says so plainly instead of pretending to work. ---- */
let AGENT_STATE = null, AGENT_LOADING = false;
function viewAgent() {
  return head('Agent Console', 'What KARNA is allowed to do, what it actually did, and everything it remembers about you \u2014 live from the backend.', '') +
    '<div id="agent-body">' + (AGENT_STATE ? agentBodyHTML() : '<div class="empty plain"><h3>Loading\u2026</h3><p>Fetching permissions, activity, and memory from the backend.</p></div>') + '</div>';
}
async function loadAgentConsole() {
  if (AGENT_LOADING) return;
  AGENT_LOADING = true;
  try {
    const uid = await ensureUser();
    const [perm, activity, mem] = await Promise.all([
      GET('/v1/agent/permissions?user_id=' + uid),
      GET('/v1/activity?user_id=' + uid + '&limit=25'),
      GET('/v1/memory/items?user_id=' + uid),
    ]);
    AGENT_STATE = { perm, activity, mem };
    const el = $('agent-body'); if (el) el.innerHTML = agentBodyHTML();
  } catch (e) {
    AGENT_STATE = null;
    const el = $('agent-body');
    if (el) el.innerHTML = emptyPanel('Could not reach the backend', esc(e.message) + ' \u2014 Agent Console needs the FastAPI backend running and reachable (check Settings for the API base URL).', '<button class="btn" onclick="loadAgentConsole()">Retry</button>');
  } finally { AGENT_LOADING = false; }
}
const RISK_TONE = { low: '', medium: 'warn', high: 'bad' };
const MEM_TONE = { unconfirmed: 'warn', active: 'good', forgotten: '' };
function agentBodyHTML() {
  const { perm, activity, mem } = AGENT_STATE;
  const permCard =
    '<div class="panel" style="padding:18px;margin-bottom:18px">' +
    '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">' +
      '<div><b>' + (perm.agent_enabled ? 'Agent is active' : 'Agent is paused') + '</b><div class="row-s">' + (perm.agent_enabled ? 'KARNA can propose and run whitelisted tool calls.' : 'Emergency stop is on \u2014 KARNA refuses every tool call until resumed.') + '</div></div>' +
      '<button class="btn ' + (perm.agent_enabled ? 'danger' : '') + ' sm" onclick="toggleAgentEnabled()">' + (perm.agent_enabled ? 'Pause agent' : 'Resume agent') + '</button>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-top:16px">' +
      '<div><div class="row-s">Can read</div>' + perm.can_read.map(x => '<span class="chip" style="margin:2px 4px 0 0">' + esc(x) + '</span>').join('') + '</div>' +
      '<div><div class="row-s">Can create</div>' + (perm.can_create.length ? perm.can_create.map(x => '<span class="chip" style="margin:2px 4px 0 0">' + esc(x) + '</span>').join('') : '<span class="row-s">None</span>') + '</div>' +
      '<div><div class="row-s">Can send</div>' + (perm.can_send.length ? perm.can_send.map(x => '<span class="chip" style="margin:2px 4px 0 0">' + esc(x) + '</span>').join('') : '<span class="row-s">Nothing \u2014 outreach only ever lands in the Outbox as pending</span>') + '</div>' +
    '</div>' +
    '<div class="row-s" style="margin-top:14px">Max ' + perm.max_tool_calls_per_turn + ' tool calls per message \u00b7 ' + perm.outbox_approvals_used_today + ' / ' + perm.max_outbox_approvals_per_day + ' Outbox approvals used today \u00b7 ' + (perm.connected_integrations.length ? perm.connected_integrations.join(', ') : 'no external integrations connected') + '</div>' +
    '</div>';

  const activityCard = '<h3 style="margin:0 0 10px">Recent activity</h3>' +
    (activity.length
      ? '<div class="panel rows">' + activity.map(a =>
          '<div class="row noicon"><div><div class="row-t">' + esc(a.tool_name) + '</div><div class="row-s">' + esc((a.result_summary || '').slice(0, 140)) + '</div><div class="row-m"><span class="pill ' + (RISK_TONE[a.risk_level] || '') + '">' + esc(a.risk_level) + ' risk</span><span class="pill ' + (a.status === 'ok' ? 'good' : a.status === 'blocked' ? 'bad' : 'warn') + '">' + esc(a.status) + '</span><span class="chip">' + esc(new Date(a.created_at).toLocaleString()) + '</span></div></div></div>'
        ).join('') + '</div>'
      : emptyPanel('No activity yet', 'Every validated tool call KARNA executes will show up here with what it did and why.'));

  const groups = ['profile', 'working', 'learning'];
  const memCard = '<div style="display:flex;justify-content:space-between;align-items:center;margin:26px 0 10px">' +
    '<h3 style="margin:0">Structured memory</h3>' + addBtn('Add memory', 'addMemoryItem()') + '</div>' +
    (mem.length
      ? groups.filter(g => mem.some(m => m.type === g)).map(g =>
          '<div class="row-s" style="margin:14px 0 6px;text-transform:capitalize">' + g + ' memory</div><div class="panel rows">' +
          mem.filter(m => m.type === g).map(m =>
            '<div class="row noicon"><div><div class="row-t">' + esc(m.content) + '</div><div class="row-m"><span class="pill ' + (MEM_TONE[m.status] || '') + '">' + esc(m.status) + '</span><span class="chip">source: ' + esc(m.source) + '</span><span class="chip">confidence ' + Math.round((m.confidence || 0) * 100) + '%</span></div></div><div class="row-a">' +
            (m.status === 'unconfirmed' ? '<button class="btn sm" onclick="confirmMemoryItem(\'' + m.id + '\')">Confirm</button>' : '') +
            '<button class="btn ghost sm" onclick="forgetMemoryItemUI(\'' + m.id + '\',' + escA(JSON.stringify(m.content)) + ')">Forget</button></div></div>'
          ).join('') + '</div>'
        ).join('')
      : emptyPanel('Nothing remembered yet', 'Facts KARNA proposes land here as unconfirmed until you approve them; add your own with "Add memory".'));

  return permCard + activityCard + memCard;
}
async function toggleAgentEnabled() {
  if (!AGENT_STATE) return;
  try {
    const uid = await ensureUser();
    const next = !AGENT_STATE.perm.agent_enabled;
    AGENT_STATE.perm = await POST('/v1/agent/permissions?user_id=' + uid, { agent_enabled: next });
    $('agent-body').innerHTML = agentBodyHTML();
    toast(next ? 'Agent resumed' : 'Agent paused \u2014 emergency stop is on');
  } catch (e) { toast('Could not change agent state: ' + e.message, true); }
}
async function confirmMemoryItem(id) {
  try {
    const uid = await ensureUser();
    await POST('/v1/memory/items/' + id + '/confirm', { status: 'active' });
    await loadAgentConsole(); toast('Memory confirmed');
  } catch (e) { toast('Could not confirm: ' + e.message, true); }
}
function forgetMemoryItemUI(id, label) {
  confirmBox('Forget "' + label + '"?', 'Forget', async () => {
    try { await DEL('/v1/memory/items/' + id); await loadAgentConsole(); toast('Forgotten'); }
    catch (e) { toast('Could not forget: ' + e.message, true); }
  });
}
function addMemoryItem() {
  openForm({
    title: 'Add memory', saveLabel: 'Save',
    values: { type: 'profile' },
    fields: [
      { k:'type', l:'Type', t:'select', opts:[{v:'profile',l:'Profile (skills/goals)'},{v:'working',l:'Working (current tasks/deadlines)'},{v:'learning',l:'Learning (what worked/didn\u2019t)'}] },
      { k:'content', l:'What should KARNA remember?', t:'textarea', req:true, ph:'e.g. Prefers backend/AI internships over pure frontend roles' },
    ],
    onSave: async (v) => {
      try {
        const uid = await ensureUser();
        await POST('/v1/memory/items', { user_id: uid, type: v.type, content: v.content, source: 'user', status: 'active' });
        closeModal(); await loadAgentConsole(); toast('Saved to memory');
      } catch (e) { toast('Could not save: ' + e.message, true); }
    }
  });
}
 
/* ---- Resume Lab (backend) + Quick check (local) ---- */
let resumeText = '';
let resumeTab = null;                       // 'lab' | 'quick'; null = pick a default
const RLAB = { list: null, loading: false, error: null, openId: null, busy: '', ask: {} };

function rlTab() { return resumeTab || (BACKEND.ready ? 'lab' : 'quick'); }
function setResumeTab(t) { resumeTab = t; render(); }

function viewResume() {
  const t = rlTab();
  const tabs = '<div class="rtabs" role="tablist">' +
    '<button role="tab" aria-selected="' + (t === 'lab') + '" class="' + (t === 'lab' ? 'on' : '') + '" onclick="setResumeTab(\'lab\')">Resume Lab</button>' +
    '<button role="tab" aria-selected="' + (t === 'quick') + '" class="' + (t === 'quick' ? 'on' : '') + '" onclick="setResumeTab(\'quick\')">Quick check</button></div>';
  const sub = t === 'lab'
    ? 'Keep up to ten resume versions. Each one is scored by AI, gets suggested bullets, and can be questioned on its own.'
    : 'Paste a resume or project summary. OPAI finds the skills it recognizes so you can add them to your matching profile.';
  const action = (t === 'lab' && BACKEND.ready) ? addBtn('Add version', 'addResumeVersion()') : '';
  return head('Resume Lab', sub, action) + tabs +
    (t === 'lab' ? '<div id="rl-body">' + rlBodyHTML() + '</div>' : quickCheckHTML());
}
function resumeAfterRender() { if (rlTab() === 'lab' && BACKEND.ready && RLAB.list === null) loadResumeLab(); }

/* ---- Lab: data ---- */
async function loadResumeLab(force) {
  if (RLAB.loading) return;
  if (!force && RLAB.list !== null) return;
  RLAB.loading = true; RLAB.error = null;
  const el0 = $('rl-body'); if (el0) el0.innerHTML = rlBodyHTML();
  try {
    const uid = await ensureUser();
    RLAB.list = await GET('/v1/resumes?user_id=' + uid);
  } catch (e) { RLAB.error = e.message || 'Request failed'; RLAB.list = null; }
  finally { RLAB.loading = false; }
  const el = $('rl-body'); if (el) el.innerHTML = rlBodyHTML();
}
function rlReset() { RLAB.list = null; RLAB.openId = null; RLAB.error = null; RLAB.ask = {}; RLAB.busy = ''; }
function rlCur() { return (RLAB.list || []).find(r => r.id === RLAB.openId) || null; }
function rlRefresh() { const el = $('rl-body'); if (el) el.innerHTML = rlBodyHTML(); }
function rlBusy(msg) { RLAB.busy = msg || ''; rlRefresh(); }

/* ---- Lab: rendering ---- */
function rlTone(n) { return n >= 8 ? 'good' : n >= 5 ? 'warn' : 'bad'; }
function rlPill(sc) {
  if (!sc || sc.overall == null) return '<span class="pill">Not scored</span>';
  return '<span class="pill ' + rlTone(sc.overall) + '">' + sc.overall + '/10</span>';
}
function rlBodyHTML() {
  if (!BACKEND.ready) return emptyPanel('Resume Lab needs the backend', 'Scoring, suggested bullets and \u201cask this resume\u201d run on your FastAPI server, which could not be reached. The Quick check tab works offline.', '<button class="btn" onclick="setResumeTab(\'quick\')">Open Quick check</button>');
  if (RLAB.error) return emptyPanel('Could not load your resumes', esc(RLAB.error), '<button class="btn" onclick="loadResumeLab(true)">Retry</button>');
  if (RLAB.list === null) return '<div class="empty plain"><h3>Loading\u2026</h3><p>Fetching your resume versions.</p></div>';
  const busy = RLAB.busy ? '<div class="panel rl-busy" role="status">' + esc(RLAB.busy) + '</div>' : '';
  const r = rlCur();
  if (r) return busy + rlDetailHTML(r);
  if (!RLAB.list.length) return busy + emptyPanel('No resume versions yet', 'Add your first version, for example \u201cSDE Intern v1\u201d, and OPAI will score it and suggest stronger bullets.', addBtn('Add version', 'addResumeVersion()'));
  return busy + '<div class="panel rows">' + RLAB.list.map(x => {
    const id = escA(JSON.stringify(x.id));
    return '<div class="row noicon"><div><div class="row-t">' + esc(x.label) + '</div>' +
      '<div class="row-s">' + (x.target_role ? 'Target: ' + esc(x.target_role) : 'No target role set') + '</div>' +
      '<div class="row-m">' + rlPill(x.score) + '<span class="chip">' + (x.skills || []).length + ' skills</span>' +
      (x.created_at ? '<span class="chip">' + esc(new Date(x.created_at).toLocaleDateString()) + '</span>' : '') + '</div></div>' +
      '<div class="row-a"><button class="btn sm" onclick="openResume(' + id + ')">Open</button>' +
      '<button class="btn ghost sm" onclick="deleteResumeVersion(' + id + ')">Delete</button></div></div>';
  }).join('') + '</div>' + (RLAB.list.length >= 10 ? '<div class="row-s" style="margin-top:10px">You have reached about ten versions. Delete one to keep things tidy.</div>' : '');
}
function rlDetailHTML(r) {
  const sc = r.score || {};
  const cells = [['Overall', 'overall'], ['Clarity', 'clarity'], ['Impact', 'impact'], ['Keywords', 'keyword_match'], ['Structure', 'structure']];
  const grid = '<div class="score-grid">' + cells.map(c => {
    const v = sc[c[1]];
    return '<div class="score-cell ' + (v == null ? '' : rlTone(v)) + '"><b>' + (v == null ? '\u2014' : v) + '</b><span>' + c[0] + '</span></div>';
  }).join('') + '</div>';
  const have = splitList(S.profile.skills).map(x => x.toLowerCase());
  const skills = (r.skills || []).length
    ? r.skills.map((s, i) => have.includes(String(s).toLowerCase())
        ? '<span class="skill added">' + icon('check', 13) + esc(s) + '</span>'
        : '<button class="skill" onclick="addSkill(' + escA(JSON.stringify(s)) + ')">' + icon('plus', 13) + esc(s) + '</button>').join('') + '<div class="row-s" style="margin-top:6px">Select a skill to add it to your profile.</div>'
    : '<div class="row-s">No skills were extracted from this version.</div>';
  const bullets = (r.suggested_bullets || []).length
    ? '<ul class="rl-bullets">' + r.suggested_bullets.map((b, i) => '<li><span>' + esc(b) + '</span><button class="btn ghost sm" onclick="copyResumeBullet(' + i + ')">Copy</button></li>').join('') + '</ul>'
    : '<div class="row-s">No suggestions for this version.</div>';
  const idq = escA(JSON.stringify(r.id));
  const askState = RLAB.ask[r.id] || {};
  const h3 = 'style="font-family:var(--display);font-size:17px;margin-bottom:10px"';
  return '<div style="max-width:820px">' +
    '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:14px">' +
      '<button class="btn ghost sm" onclick="closeResume()">\u2190 All versions</button>' +
      '<div class="row-a"><button class="btn sm" onclick="editResumeVersion(' + idq + ')">Edit</button><button class="btn ghost sm" onclick="reanalyzeResume(' + idq + ')">Reanalyze</button><button class="btn ghost sm" onclick="deleteResumeVersion(' + idq + ')">Delete</button></div></div>' +
    '<section class="panel" style="padding:20px;margin-bottom:14px"><h3 style="font-family:var(--display);font-size:20px;margin-bottom:2px">' + esc(r.label) + '</h3>' +
      '<div class="row-s" style="margin-bottom:14px">' + (r.target_role ? 'Scored against: ' + esc(r.target_role) : 'No target role set') + '</div>' + grid +
      (sc.notes ? '<div class="rl-next"><b>Next change to make</b><p>' + esc(sc.notes) + '</p></div>' : '') + '</section>' +
    (r.summary ? '<section class="panel" style="padding:20px;margin-bottom:14px"><h3 ' + h3 + '>Summary</h3><p style="margin:0;color:var(--ink-2)">' + esc(r.summary) + '</p></section>' : '') +
    '<section class="panel" style="padding:20px;margin-bottom:14px"><h3 ' + h3 + '>Skills (' + (r.skills || []).length + ')</h3>' + skills + '</section>' +
    '<section class="panel" style="padding:20px;margin-bottom:14px"><h3 ' + h3 + '>Suggested bullets</h3>' + bullets + '</section>' +
    '<section class="panel" style="padding:20px"><h3 style="font-family:var(--display);font-size:17px;margin-bottom:4px">Ask this resume</h3>' +
      '<div class="row-s" style="margin-bottom:10px">Answers come only from this version\u2019s text.</div>' +
      '<div class="field"><textarea id="rl-q" rows="2" placeholder="e.g. Which project best shows backend experience?"></textarea></div>' +
      '<div style="margin-top:10px"><button class="btn" id="rl-ask-btn" onclick="askResume(' + idq + ')"' + (askState.loading ? ' disabled' : '') + '>' + (askState.loading ? 'Thinking\u2026' : 'Ask') + '</button></div>' +
      '<div id="rl-a" aria-live="polite" style="margin-top:14px">' + (askState.answer ? rlAnswerHTML(askState) : '') + '</div></section></div>';
}
function rlAnswerHTML(a) {
  return '<div class="rl-answer"><div class="row-s" style="margin-bottom:4px">' + esc(a.q) + '</div><div style="white-space:pre-wrap">' + esc(a.answer) + '</div>' +
    '<div class="row-s" style="margin-top:8px">Based on ' + a.used + ' passage' + (a.used === 1 ? '' : 's') + ' from this version.</div></div>';
}

/* ---- Lab: actions ---- */
function openResume(id) { RLAB.openId = id; rlRefresh(); window.scrollTo(0, 0); }
function closeResume() { RLAB.openId = null; rlRefresh(); }
function addResumeVersion() {
  if (!BACKEND.ready) { toast('Resume Lab needs the backend', true); return; }
  openForm({
    title: 'Add resume version', saveLabel: 'Add and score',
    fields: [
      { k: 'label', l: 'Version name', req: true, half: true, ph: 'e.g. SDE Intern v1' },
      { k: 'target_role', l: 'Target role (optional)', half: true, ph: 'e.g. Backend intern' },
      { k: 'text', l: 'Resume text', t: 'textarea', rows: 10, req: true, ph: 'Paste the full resume text', hint: 'Scoring takes a few seconds.' },
    ],
    onSave: async (v) => {
      closeModal(); rlBusy('Scoring your resume\u2026');
      try {
        const uid = await ensureUser();
        const row = await POST('/v1/resumes', { user_id: uid, label: v.label, target_role: v.target_role || null, text: v.text });
        RLAB.list = [row].concat(RLAB.list || []); RLAB.openId = row.id;
        log('Added resume version: ' + v.label); toast('Resume scored');
      } catch (e) { toast('Could not add resume: ' + e.message, true); }
      rlBusy('');
    }
  });
}
function editResumeVersion(id) {
  const r = (RLAB.list || []).find(x => x.id === id); if (!r) return;
  if (r.raw_text == null) { toast('Editing needs the updated backend (resume text was not returned)', true); return; }
  openForm({
    title: 'Edit \u201c' + r.label + '\u201d', saveLabel: 'Save and re-score',
    values: { label: r.label, target_role: r.target_role || '', text: r.raw_text },
    fields: [
      { k: 'label', l: 'Version name', req: true, half: true },
      { k: 'target_role', l: 'Target role', half: true, ph: 'e.g. Backend intern' },
      { k: 'text', l: 'Resume text', t: 'textarea', rows: 12, req: true, hint: 'Changing the text or role re-scores this version. Renaming alone does not.' },
    ],
    onSave: async (v) => {
      closeModal(); rlBusy('Saving\u2026');
      try {
        const row = await PATCH('/v1/resumes/' + id, { label: v.label, target_role: v.target_role, text: v.text });
        RLAB.list = RLAB.list.map(x => x.id === id ? row : x);
        delete RLAB.ask[id];
        log('Edited resume version: ' + row.label); toast('Saved');
      } catch (e) { toast('Could not save: ' + e.message, true); }
      rlBusy('');
    }
  });
}
function reanalyzeResume(id) {
  const r = (RLAB.list || []).find(x => x.id === id); if (!r) return;
  openForm({
    title: 'Reanalyze \u201c' + r.label + '\u201d', saveLabel: 'Reanalyze',
    values: { target_role: r.target_role || '' },
    fields: [{ k: 'target_role', l: 'Target role', ph: 'e.g. Data analyst intern', hint: 'Re-scores the saved text against this role.' }],
    onSave: async (v) => {
      closeModal(); rlBusy('Re-scoring\u2026');
      try {
        const row = await POST('/v1/resumes/' + id + '/reanalyze', { target_role: v.target_role || null });
        RLAB.list = RLAB.list.map(x => x.id === id ? row : x);
        toast('Resume re-scored');
      } catch (e) { toast('Could not reanalyze: ' + e.message, true); }
      rlBusy('');
    }
  });
}
function deleteResumeVersion(id) {
  const r = (RLAB.list || []).find(x => x.id === id); if (!r) return;
  confirmBox('Delete \u201c' + r.label + '\u201d?', 'Delete', async () => {
    try {
      await DEL('/v1/resumes/' + id);
      RLAB.list = RLAB.list.filter(x => x.id !== id); delete RLAB.ask[id];
      if (RLAB.openId === id) RLAB.openId = null;
      log('Deleted resume version: ' + r.label); rlRefresh(); toast('Deleted');
    } catch (e) { toast('Could not delete: ' + e.message, true); }
  });
}
function copyResumeBullet(i) {
  const r = rlCur(); if (!r || !r.suggested_bullets[i]) return;
  const done = () => toast('Copied');
  try { navigator.clipboard.writeText(r.suggested_bullets[i]).then(done, () => toast('Could not copy', true)); }
  catch (e) { toast('Could not copy', true); }
}
async function askResume(id) {
  const q = ($('rl-q').value || '').trim();
  if (!q) { toast('Type a question first', true); return; }
  RLAB.ask[id] = { loading: true, q };
  const btn = $('rl-ask-btn'); if (btn) { btn.disabled = true; btn.textContent = 'Thinking\u2026'; }
  try {
    const uid = await ensureUser();
    const res = await POST('/v1/resumes/' + id + '/ask', { user_id: uid, question: q });
    RLAB.ask[id] = { q, answer: res.answer, used: res.used_chunks };
  } catch (e) { delete RLAB.ask[id]; toast('Could not get an answer: ' + e.message, true); }
  if (RLAB.openId === id) { const keep = $('rl-q') ? $('rl-q').value : ''; rlRefresh(); if ($('rl-q')) $('rl-q').value = keep; }
}

/* ---- Quick check (local, no backend) ---- */
function quickCheckHTML() {
  return '<div style="max-width:720px"><div class="field"><label for="resume-text">Resume or project text</label><textarea class="resume-box" id="resume-text" placeholder="Paste resume text, a GitHub README, or a project summary" oninput="resumeText=this.value">' + esc(resumeText) + '</textarea></div><div style="display:flex;gap:10px;margin-top:14px"><button class="btn" onclick="analyzeResume()">Analyze</button><button class="btn ghost" onclick="clearResume()">Clear</button></div><div id="resume-results" style="margin-top:22px"></div></div>';
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
function addSkill(s) { const list = splitList(S.profile.skills); if (!list.some(x => x.toLowerCase() === s.toLowerCase())) list.push(s); S.profile.skills = list.join(', '); log('Added skill: ' + s); save(); if (rlTab() === 'quick') analyzeResume(); else rlRefresh(); renderNav(); toast(s + ' added to your profile'); }
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
  return head('Profile', 'Used to personalize skill matching and outreach drafts.' + (BACKEND.ready ? ' Synced with the backend.' : ''), '') +
    '<section class="panel form-panel">' + f('name', 'Name') + f('branch', 'Branch', 'e.g. Computer Science') + f('degree', 'Degree & year', 'e.g. B.Tech 3rd year') + f('cgpa', 'CGPA', 'e.g. 8.5') + f('github', 'GitHub', 'github.com/username') + f('email', 'Email') +
    '<div class="field"><label for="p-skills">Skills</label><input id="p-skills" type="text" value="' + escA(p.skills) + '"><div class="hint">Comma-separated. Used to score opportunities and contacts.</div></div>' +
    '<div class="field"><label for="p-highlight">Resume highlight</label><textarea id="p-highlight" rows="2">' + esc(p.highlight) + '</textarea><div class="hint">One line, used in outreach drafts.</div></div>' +
    '<button class="btn" onclick="saveProfile()">Save profile</button></section>' +
    '<section class="panel form-panel" style="margin-top:20px"><h3 style="font-family:var(--display);font-size:18px;font-weight:650;margin-bottom:8px">Data on this device</h3><p class="row-s" style="margin-bottom:16px">' + (BACKEND.ready ? 'Your workspace is saved to your backend account and loads on any device you sign in from.' : 'The backend could not be reached, so your data is only stored in this browser for now.') + '</p><div class="data-actions"><button class="btn ghost" onclick="exportData()">Download backup</button><button class="btn ghost" onclick="$(\'imp\').click()">Restore from backup</button><button class="btn ghost" onclick="resetData()">Delete all my data</button></div><input type="file" id="imp" accept="application/json,.json" hidden onchange="importData(this)"></section>' + accountPanel();
}
async function saveProfile() {
  const v = {};
  ['name','branch','degree','cgpa','github','email','skills','highlight'].forEach(k => { v[k] = $('p-' + k).value.trim(); });
  S.profile = { ...S.profile, ...v, onboarded: true, track: [v.degree, v.branch].filter(Boolean).join(' ') };
  if (BACKEND.ready) { try { await saveProfileToApi(v); } catch (e) { toast('Saved locally \u2014 could not sync to backend: ' + e.message, true); } }
  save(); render(); toast('Profile saved');
}
function saveGroqKey() {
  const k = $('jv-groqKey').value.trim(); const m = $('jv-groqModel').value;
  S.profile.groqKey = k; S.profile.groqModel = m; save(); render();
  toast(k ? 'Connected \u2014 KARNA will use the live model' : 'Saved');
}
function clearGroqKey() { S.profile.groqKey = ''; save(); render(); toast('Disconnected. KARNA is back on local replies'); }
async function testGroq() {
  toast('Testing connection\u2026');
  try {
    const r = await groqChat([{ role: 'user', content: 'Reply with just: connected' }]);
    toast(r ? 'Groq responded: ' + r.slice(0, 60) : 'No response from Groq', !r);
  } catch (e) { toast('Groq test failed: ' + e.message, true); }
}
function resetData() { confirmBox('Reset all data to the sample workspace?', 'Reset data', () => { S = seed(); save(); render(); toast('Sample data restored'); }); }
 
/* ---- Groq (optional live KARNA) ---- */
const GROQ_MODELS = [
  { v: 'openai/gpt-oss-120b', l: 'GPT-OSS 120B (best quality)' },
  { v: 'openai/gpt-oss-20b', l: 'GPT-OSS 20B (fastest)' },
  { v: 'qwen/qwen3.8-27b', l: 'Qwen3.8 27B' }
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
 
/* ---- KARNA + STUDY WORKFLOW (SEMS) ----
   The Study Workflow tab is backend-driven when the FastAPI server is
   reachable: "Generate Workflow" calls POST /v1/study-plans/generate (the
   real priority/risk engine in agent_service.py), and checking off a task
   calls POST /v1/study-blocks/{id}/complete, which updates topic confidence
   and next-review date server-side. If the backend has no semester/courses
   set up yet, or is unreachable, it falls back to the local Groq/heuristic
   generator so the tab never goes blank. */
let CHAT = [];
const PROMPTS = ['Set up my whole OPAI app', 'What should I focus on today?', 'Summarize my applications and deadlines.', 'Which projects need attention?', 'Help me plan the next 3 hours.'];
let KARNA_MODE = 'chat';
let WORKFLOW_BUSY = false;
let SEMS_COURSES = [];  // [{id, name}] loaded from the backend, if any
let STUDY_WORKFLOW = {
  subject: 'Database Systems',
  duration: '3 hours',
  mode: 'Balanced (Plan + Practice)',
  examDate: '2026-10-01',
  lastUpdated: 'Ready',
  source: 'local',  // 'sems' when tasks came from the real backend plan
  tasks: [
    { id:1, title:'Normalization', desc:'Learn 1NF, 2NF and 3NF with examples.', time:'30 min', done:true },
    { id:2, title:'ER Diagrams', desc:'Understand entities, relationships and mapping.', time:'30 min', done:true },
    { id:3, title:'SQL Queries', desc:'Practice joins, grouping and subqueries.', time:'40 min', done:false },
    { id:4, title:'Transactions', desc:'Study ACID, concurrency and recovery.', time:'30 min', done:false },
    { id:5, title:'Past Questions', desc:'Solve previous exam questions and mark weak areas.', time:'40 min', done:false }
  ]
};

function setJarvisMode(mode) {
  KARNA_MODE = mode === 'study' ? 'study' : 'chat';
  if (KARNA_MODE === 'study' && BACKEND.ready && !SEMS_COURSES.length) loadSemsCourses();
  render(true);
}
async function loadSemsCourses() {
  try {
    const uid = await ensureUser();
    SEMS_COURSES = await GET('/v1/courses?user_id=' + uid);
    render(true);
  } catch (e) { /* fine - subject dropdown just stays on the built-in list */ }
}
function toggleWorkflowTask(idx) {
  const t = STUDY_WORKFLOW.tasks[idx]; if (!t) return;
  t.done = !t.done;
  STUDY_WORKFLOW.lastUpdated = 'Progress updated'; log('Study block ' + (t.done ? 'completed' : 'reopened') + ': ' + t.title); save();
  if (t.blockId && BACKEND.ready) {
    POST('/v1/study-blocks/' + t.blockId + '/complete', { completed: t.done, confidence_now: t.done ? 4 : null })
      .catch(() => { /* local checkbox state still reflects the click either way */ });
  }
  render(true);
}
function workflowExam() {
  return S.academics.find(a => a.subject === STUDY_WORKFLOW.subject) ||
    S.academics.find(a => a.subject.toLowerCase() === STUDY_WORKFLOW.subject.toLowerCase()) || null;
}
function localWorkflowTasks(subject, mode, duration) {
  const base = {
    'Database Systems': [
      ['Normalization','Learn 1NF, 2NF and 3NF with a worked example.','30 min'],
      ['ER Diagrams','Review entities, keys, cardinality and mapping rules.','30 min'],
      ['SQL Queries','Practice joins, grouping, nested queries and edge cases.','40 min'],
      ['Transactions','Review ACID, schedules, locking and recovery.','30 min'],
      ['Past Questions','Solve exam-style DBMS questions and review mistakes.','40 min']
    ],
    'Operating Systems': [
      ['CPU Scheduling','Compare FCFS, SJF, Priority and Round Robin with examples.','30 min'],
      ['Memory Management','Revise paging, segmentation and virtual memory.','30 min'],
      ['Deadlocks','Practice prevention, avoidance and Banker-style questions.','35 min'],
      ['File Systems','Review allocation, directories and disk scheduling.','25 min'],
      ['Past Questions','Solve exam questions and log weak concepts.','40 min']
    ],
    'Computer Networks': [
      ['OSI & TCP/IP','Map protocols, layers and packet flow with examples.','25 min'],
      ['Routing','Review distance-vector, link-state and routing tables.','35 min'],
      ['TCP / UDP','Practice reliability, flow control and connection setup.','35 min'],
      ['Subnetting','Solve CIDR and subnet-mask questions.','30 min'],
      ['Past Questions','Solve exam questions and revisit errors.','35 min']
    ]
  };
  let list = base[subject] || [
    ['Core concepts','Build a compact understanding of the most important concepts.','30 min'],
    ['Worked examples','Study representative examples and edge cases.','30 min'],
    ['Practice','Solve focused questions without notes.','40 min'],
    ['Weak areas','Review errors and revisit difficult concepts.','30 min'],
    ['Past questions','Finish with exam-style questions and a quick recap.','40 min']
  ];
  if (/weak/i.test(mode)) list = [list[2], list[3], list[4], list[0], list[1]];
  if (/sprint/i.test(mode)) list = list.map((x,i) => [x[0], x[1], i === 4 ? '30 min' : '25 min']);
  if (/1 hour/i.test(duration)) list = list.slice(0,3).map((x,i) => [x[0],x[1],i===2?'25 min':'20 min']);
  if (/2 hours/i.test(duration)) list = list.slice(0,4).map((x,i) => [x[0],x[1],i===3?'25 min':'30 min']);
  return list.map((x,i) => ({ id:i+1, title:x[0], desc:x[1], time:x[2], done:i<2 }));
}
function parseWorkflowJSON(text) {
  if (!text) return null;
  const candidates = [];
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i); if (fenced) candidates.push(fenced[1]);
  const a = text.indexOf('{'), b = text.lastIndexOf('}'); if (a >= 0 && b > a) candidates.push(text.slice(a,b+1));
  const c = text.indexOf('['), d = text.lastIndexOf(']'); if (c >= 0 && d > c) candidates.push(text.slice(c,d+1));
  for (const raw of candidates) {
    try {
      const data = JSON.parse(raw.trim());
      const arr = Array.isArray(data) ? data : (Array.isArray(data.tasks) ? data.tasks : (Array.isArray(data.blocks) ? data.blocks : null));
      if (!arr || !arr.length) continue;
      const out = arr.slice(0,5).map((x,i) => ({
        id:i+1,
        title:String(x.title || x.topic || ('Block '+(i+1))).trim(),
        desc:String(x.desc || x.description || x.focus || '').trim(),
        time:String(x.time || x.duration || '30 min').trim(),
        done:i<2
      })).filter(x => x.title);
      if (out.length >= 3) return out;
    } catch(e) {}
  }
  return null;
}
/* Real SEMS plan -> the same {id,title,desc,time,done,blockId} task shape
   the local generators produce, so renderStudyWorkflowBody doesn't care
   which source it came from. */
function semsBlocksToTasks(blocks) {
  const durMin = (m) => m < 60 ? m + ' min' : (m % 60 === 0 ? (m/60) + 'h' : Math.floor(m/60) + 'h ' + (m%60) + 'm');
  return blocks.map((b, i) => ({
    id: i + 1,
    blockId: b.id,
    title: b.topic_name || (b.mode === 'buffer' ? 'Buffer' : 'Study block'),
    desc: b.generated_reason || (b.course_name ? b.course_name : ''),
    time: durMin(b.duration_min),
    done: b.status === 'done',
  }));
}
async function generateWorkflowFromUI() {
  const subjEl = $('sw-select-subject'); const durEl = $('sw-select-time'); const modeEl = $('sw-select-mode');
  if (subjEl) STUDY_WORKFLOW.subject = subjEl.value;
  if (durEl) STUDY_WORKFLOW.duration = durEl.value;
  if (modeEl) STUDY_WORKFLOW.mode = modeEl.value;
  const ex = workflowExam();
  STUDY_WORKFLOW.examDate = (ex && ex.exam_date) || STUDY_WORKFLOW.examDate || '';
  WORKFLOW_BUSY = true;
  STUDY_WORKFLOW.lastUpdated = BACKEND.ready ? 'Generating from your SEMS exam map\u2026' : 'Generating with Groq\u2026';
  KARNA_MODE = 'study';
  render(true);

  const durMinutes = { '1 hour':60, '2 hours':120, '3 hours':180, '4 hours':240 }[STUDY_WORKFLOW.duration] || 180;

  if (BACKEND.ready) {
    try {
      const uid = await ensureUser();
      const blocks = await POST('/v1/study-plans/generate', { user_id: uid, available_minutes: durMinutes });
      if (blocks && blocks.length) {
        STUDY_WORKFLOW.tasks = semsBlocksToTasks(blocks);
        STUDY_WORKFLOW.source = 'sems';
        STUDY_WORKFLOW.lastUpdated = 'Generated from your SEMS exam map (' + blocks.length + ' block' + (blocks.length > 1 ? 's' : '') + ')';
        WORKFLOW_BUSY = false; PL_FRESH = true; log('Study plan generated: ' + STUDY_WORKFLOW.tasks.length + ' blocks for ' + STUDY_WORKFLOW.subject); save(); render(true); return;
      }
      STUDY_WORKFLOW.lastUpdated = 'No SEMS exams set up yet \u2014 set up a semester and courses to get a real plan. Showing a local plan meanwhile.';
    } catch (e) {
      STUDY_WORKFLOW.lastUpdated = 'Could not reach SEMS backend \u2014 showing a local plan.';
    }
  }

  STUDY_WORKFLOW.source = 'local';
  STUDY_WORKFLOW.tasks = localWorkflowTasks(STUDY_WORKFLOW.subject, STUDY_WORKFLOW.mode, STUDY_WORKFLOW.duration);
  if (S.profile.groqKey) {
    try {
      const sys = 'You are KARNA inside OPAI. Create a practical study workflow. Return ONLY JSON with this shape: {"tasks":[{"title":"...","desc":"...","time":"30 min"},...]}. Return exactly 5 tasks. Keep titles concise and descriptions under 16 words. Respect subject, duration, mode and exam date. Do not invent an exam date. Prioritize active learning, recall, practice and review.';
      const user = 'Subject: '+STUDY_WORKFLOW.subject+'\nAvailable time: '+STUDY_WORKFLOW.duration+'\nMode: '+STUDY_WORKFLOW.mode+'\nExam date: '+(STUDY_WORKFLOW.examDate || 'not provided')+'\nCurrent task context: '+STUDY_WORKFLOW.tasks.map(x=>x.title).join(', ');
      const reply = await groqChat([{role:'system',content:sys},{role:'user',content:user}]);
      const parsed = parseWorkflowJSON(reply);
      if (parsed) { STUDY_WORKFLOW.tasks = parsed; STUDY_WORKFLOW.lastUpdated = 'Generated by Groq (local demo subjects)'; }
      else STUDY_WORKFLOW.lastUpdated += ' Groq returned an unreadable plan.';
    } catch(e) { STUDY_WORKFLOW.lastUpdated += ' Groq unavailable.'; }
  } else if (STUDY_WORKFLOW.lastUpdated === 'Ready' || !BACKEND.ready) {
    STUDY_WORKFLOW.lastUpdated = 'Local workflow \u00b7 connect Groq or set up SEMS for live generation';
  }
  WORKFLOW_BUSY = false;
  PL_FRESH = true; log('Study plan generated: ' + STUDY_WORKFLOW.tasks.length + ' blocks for ' + STUDY_WORKFLOW.subject); save();
  render(true);
}
function runQuickAction(action) {
  if (action === 'plan3h') {
    STUDY_WORKFLOW.duration = '3 hours';
    render(true); setTimeout(generateWorkflowFromUI, 0);
  } else if (action === 'weak') {
    STUDY_WORKFLOW.mode = 'Weak-Topic Recovery';
    render(true); setTimeout(generateWorkflowFromUI, 0);
  } else if (action === 'pyq') {
    setJarvisMode('chat'); setTimeout(() => jarvisSend('Generate previous year practice questions for ' + STUDY_WORKFLOW.subject), 60);
  } else if (action === 'explain') {
    setJarvisMode('chat'); setTimeout(() => jarvisSend('Explain ' + (STUDY_WORKFLOW.tasks[0]?.title || 'the first topic') + ' in ' + STUDY_WORKFLOW.subject + ' with examples'), 60);
  } else if (action === 'quiz') {
    setJarvisMode('chat'); setTimeout(() => jarvisSend('Give me a 5-question quick quiz on ' + STUDY_WORKFLOW.subject), 60);
  } else if (action === 'track') {
    const done = STUDY_WORKFLOW.tasks.filter(t => t.done).length;
    toast('Progress: ' + done + '/' + STUDY_WORKFLOW.tasks.length + ' completed');
  }
}
function handleWorkflowPrompt() {
  const inp = $('sw-prompt-input'); if (!inp || !inp.value.trim()) return;
  const q = inp.value.trim(); inp.value = ''; setJarvisMode('chat'); setTimeout(() => jarvisSend(q), 60);
}
function workflowStageData() {
  const first = STUDY_WORKFLOW.tasks[0] || {};
  const second = STUDY_WORKFLOW.tasks[1] || {};
  const third = STUDY_WORKFLOW.tasks[2] || {};
  const last = STUDY_WORKFLOW.tasks[STUDY_WORKFLOW.tasks.length - 1] || {};
  return [
    {n:'1',title:'Goal',icon:'goal',status:'done',body:'Prepare for '+STUDY_WORKFLOW.subject+' and use the available '+STUDY_WORKFLOW.duration+'.'},
    {n:'2',title:'Plan',icon:'plan',status:'done',body:(STUDY_WORKFLOW.source === 'sems' ? 'SEMS ' : 'Groq ') + 'mapped '+STUDY_WORKFLOW.tasks.length+' blocks around your mode and exam timing.',footer:STUDY_WORKFLOW.lastUpdated},
    {n:'3',title:'Focus',icon:'focus',status:'active',body:'Start with '+first.title+'. '+first.desc,loading:WORKFLOW_BUSY},
    {n:'4',title:'Learn',icon:'learn',status:'wait',body:second.title + (second.desc ? ' — '+second.desc : ' — learn the concept clearly.')},
    {n:'5',title:'Practice',icon:'practice',status:'wait',body:third.title + (third.desc ? ' — '+third.desc : ' — test yourself without notes.')},
    {n:'6',title:'Review',icon:'review',status:'wait',body:last.title + (last.desc ? ' — '+last.desc : ' — close with a quick review.')}
  ];
}
function stepIcon(name) {
  const map={
    goal:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>',
    plan:'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M8 13h8M8 17h6"></path>',
    focus:'<circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="6"></circle><circle cx="12" cy="12" r="2"></circle>',
    learn:'<path d="m3 9 9-4 9 4-9 4-9-4z"></path><path d="M6 11v4c2.5 2 9.5 2 12 0v-4"></path>',
    practice:'<polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline>',
    review:'<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'
  }; return map[name] || map.plan;
}
/* ---- Study Plan Canvas: a Figma-style box/arrow board for a 1-month or
   1-year plan the user designs themselves \u2014 separate from the backend
   SEMS-generated task list below it. Pure client-side, saved in S. ---- */
let SPC_MODE = 'month';
let SPC_LINK_FROM = null;
let SPC_DRAG = null;
function spcState() { return S.studyPlanCanvas[SPC_MODE]; }
function spcSetMode(m) { if (m === 'pipeline') { SPC_VIEW = 'pipeline'; } else { SPC_VIEW = 'board'; SPC_MODE = m; } SPC_LINK_FROM = null; render(true); }
const SPC_COLORS = ['#7CA8E0','#4ADE80','#FBBF24','#C084FC','#F87171','#9CA3AF'];
function spcAddNode() {
  const st = spcState();
  const perRow = 3;
  const x = 24 + (st.nodes.length % perRow) * 200;
  const y = 24 + Math.floor(st.nodes.length / perRow) * 130;
  openForm({
    title: 'New ' + (SPC_MODE === 'month' ? 'week / block' : 'month / quarter') + ' box',
    saveLabel: 'Add box',
    fields: [
      { k: 'title', l: 'Title', req: true, ph: SPC_MODE === 'month' ? 'e.g. Week 1 \u2014 Basics' : 'e.g. Q1 \u2014 Foundations' },
      { k: 'note', l: 'Notes', t: 'textarea', rows: 2, ph: 'What happens in this box' }
    ],
    onSave: (v) => {
      st.nodes.push({ id: uid(), title: v.title, note: v.note || '', x, y, color: SPC_COLORS[st.nodes.length % SPC_COLORS.length] });
      save(); closeModal(); render(true); toast('Box added');
    }
  });
}
function spcEditNode(id) {
  const st = spcState(); const nd = st.nodes.find(n => n.id === id); if (!nd) return;
  openForm({
    title: 'Edit box', saveLabel: 'Save changes', values: nd,
    fields: [
      { k: 'title', l: 'Title', req: true },
      { k: 'note', l: 'Notes', t: 'textarea', rows: 3 }
    ],
    onSave: (v) => { nd.title = v.title; nd.note = v.note || ''; save(); closeModal(); render(true); toast('Saved'); }
  });
}
function spcDeleteNode(id) {
  confirmBox('Delete this box?', 'Delete', () => {
    const st = spcState();
    st.nodes = st.nodes.filter(n => n.id !== id);
    st.edges = st.edges.filter(e => e.from !== id && e.to !== id);
    save(); render(true); toast('Deleted');
  });
}
function spcToggleLink(id) {
  if (SPC_LINK_FROM === id) { SPC_LINK_FROM = null; render(true); return; }
  if (!SPC_LINK_FROM) { SPC_LINK_FROM = id; render(true); toast('Now click the link icon on another box to connect an arrow'); return; }
  const st = spcState();
  const dup = st.edges.some(e => (e.from === SPC_LINK_FROM && e.to === id) || (e.from === id && e.to === SPC_LINK_FROM));
  if (!dup) { st.edges.push({ id: uid(), from: SPC_LINK_FROM, to: id }); save(); }
  SPC_LINK_FROM = null; render(true);
}
function spcCancelLink() { SPC_LINK_FROM = null; render(true); }
function spcDeleteEdge(id) { const st = spcState(); st.edges = st.edges.filter(e => e.id !== id); save(); render(true); }
function spcRedrawEdgesLive() {
  const svg = $('spc-svg'); const canvas = $('spc-canvas'); if (!svg || !canvas) return;
  spcState().edges.forEach(e => {
    const line = svg.querySelector('[data-edge="' + e.id + '"]'); if (!line) return;
    const a = canvas.querySelector('.spc-node[data-id="' + e.from + '"]');
    const b = canvas.querySelector('.spc-node[data-id="' + e.to + '"]');
    if (!a || !b) return;
    line.setAttribute('x1', a.offsetLeft + a.offsetWidth / 2); line.setAttribute('y1', a.offsetTop + a.offsetHeight / 2);
    line.setAttribute('x2', b.offsetLeft + b.offsetWidth / 2); line.setAttribute('y2', b.offsetTop + b.offsetHeight / 2);
  });
}
function spcWire() {
  const canvas = $('spc-canvas'); if (!canvas) return;
  canvas.querySelectorAll('.spc-node').forEach(el => {
    el.onpointerdown = (e) => {
      if (e.target.closest('.spc-node-actions')) return;
      SPC_DRAG = { id: el.dataset.id, offX: e.clientX - el.offsetLeft, offY: e.clientY - el.offsetTop };
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
      el.classList.add('spc-dragging');
    };
    el.onpointermove = (e) => {
      if (!SPC_DRAG || SPC_DRAG.id !== el.dataset.id) return;
      const x = Math.max(0, e.clientX - SPC_DRAG.offX), y = Math.max(0, e.clientY - SPC_DRAG.offY);
      el.style.left = x + 'px'; el.style.top = y + 'px';
      spcRedrawEdgesLive();
    };
    const finish = (e) => {
      if (!SPC_DRAG || SPC_DRAG.id !== el.dataset.id) return;
      const nd = spcState().nodes.find(n => n.id === el.dataset.id);
      if (nd) { nd.x = parseFloat(el.style.left) || 0; nd.y = parseFloat(el.style.top) || 0; save(); }
      SPC_DRAG = null; el.classList.remove('spc-dragging');
    };
    el.onpointerup = finish; el.onpointercancel = finish;
  });
}
let SPC_ANIMATE_IDS = null;
let SPC_BUSY = false;
const SPC_TEMPLATES = {
  month: ['Learn the basics', 'Practice with exercises', 'Build a small project', 'Review & mock test'],
  year: ['Foundations', 'Core skills', 'Applied projects', 'Advanced & interview prep']
};
function spcLocalPlan(topic, mode) {
  const unit = mode === 'month' ? 'Week' : 'Quarter';
  const tpl = SPC_TEMPLATES[mode];
  return tpl.map((t, i) => ({ title: unit + ' ' + (i + 1) + ' \u2014 ' + t, note: t + ' for ' + topic }));
}
function spcParseBoxesJSON(text) {
  if (!text) return null;
  const candidates = [];
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i); if (fenced) candidates.push(fenced[1]);
  const a = text.indexOf('{'), b = text.lastIndexOf('}'); if (a >= 0 && b > a) candidates.push(text.slice(a, b + 1));
  for (const raw of candidates) {
    try {
      const data = JSON.parse(raw.trim());
      const arr = Array.isArray(data) ? data : (Array.isArray(data.boxes) ? data.boxes : null);
      if (!arr || !arr.length) continue;
      const out = arr.slice(0, 6).map(x => ({ title: String(x.title || x.name || '').trim(), note: String(x.note || x.desc || '').trim() })).filter(x => x.title);
      if (out.length) return out;
    } catch (e) {}
  }
  return null;
}
async function spcGenerateFromPrompt() {
  if (SPC_BUSY) return;
  const inp = $('spc-prompt'); const q = (inp && inp.value || '').trim();
  if (!q) { toast('Describe what you want to plan first', true); return; }
  SPC_BUSY = true; render(true);
  let boxes = null;
  if (S.profile.groqKey) {
    try {
      const n = SPC_MODE === 'month' ? 4 : 4;
      const sys = 'Turn the user\u2019s goal into exactly ' + n + ' ' + (SPC_MODE === 'month' ? 'weekly' : 'quarterly') +
        ' plan boxes for a visual board. Return ONLY JSON, no prose: {"boxes":[{"title":"...","note":"..."}]}. Titles under 8 words, notes under 16 words.';
      const reply = await groqChat([{ role: 'system', content: sys }, { role: 'user', content: q }]);
      boxes = spcParseBoxesJSON(reply);
    } catch (e) {}
  }
  if (!boxes) boxes = spcLocalPlan(q, SPC_MODE);
  const st = spcState();
  st.nodes = []; st.edges = [];
  const perRow = 3;
  const ids = [];
  boxes.forEach((b, i) => {
    const id = uid();
    st.nodes.push({ id, title: b.title, note: b.note || '', x: 24 + (i % perRow) * 200, y: 24 + Math.floor(i / perRow) * 130, color: SPC_COLORS[i % SPC_COLORS.length] });
    ids.push(id);
  });
  for (let i = 1; i < st.nodes.length; i++) st.edges.push({ id: uid(), from: st.nodes[i - 1].id, to: st.nodes[i].id });
  save();
  SPC_ANIMATE_IDS = new Set(ids);
  SPC_BUSY = false;
  if (inp) inp.value = '';
  render(true);
  toast('Board generated');
}
/* ---- Pipeline view: live, driven by STUDY_WORKFLOW.tasks ---- */
let SPC_VIEW = 'pipeline';   // 'pipeline' | 'board' (board = 1 Month / 1 Year)
let PL_FRESH = false;        // true right after "Generate workflow" -> entrance animation
const PL_W = 214, PL_H = 100;
function plPos(i) { return { x: 28 + i * 254, y: 40 + (i % 2) * 92 }; }
function plStatus(i) {
  const ts = STUDY_WORKFLOW.tasks;
  if (ts[i].done) return 'done';
  return i === ts.findIndex(function (x) { return !x.done; }) ? 'active' : 'queued';
}
const PL_LABEL = { done: 'Done', active: 'Active', queued: 'Queued' };
function plTabs() {
  return '<div class="spc-tabs" role="tablist">' + ['pipeline', 'month', 'year'].map(function (k) {
    const on = k === 'pipeline' ? SPC_VIEW === 'pipeline' : (SPC_VIEW !== 'pipeline' && SPC_MODE === k);
    return '<button role="tab" aria-selected="' + on + '" class="' + (on ? 'on' : '') + '" onclick="spcSetMode(\'' + k + '\')">' +
      (k === 'pipeline' ? 'Pipeline' : k === 'month' ? '1 Month' : '1 Year') + '</button>';
  }).join('') + '</div>';
}
function plLogHTML() {
  const rows = (S.history || []).filter(function (e) { return /^Study /.test(e.text || ''); }).slice(0, 5);
  return '<div class="pl-log-r"><time>now</time><span>' + esc(STUDY_WORKFLOW.lastUpdated) + '</span></div>' +
    rows.map(function (e) {
      return '<div class="pl-log-r"><time>' + esc(new Date(e.at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })) + '</time><span>' + esc(e.text) + '</span></div>';
    }).join('');
}
function spcPipelineHTML() {
  const ts = STUDY_WORKFLOW.tasks, n = ts.length;
  const fresh = PL_FRESH; PL_FRESH = false;
  const done = ts.filter(function (t) { return t.done; }).length;
  const pillTxt = WORKFLOW_BUSY ? 'Generating\u2026' : !n ? 'Idle' : done === n ? 'Complete' : 'Running \u00b7 block ' + (done + 1) + ' of ' + n;
  const W = Math.max(720, 28 + n * 254 + 20), H = 300;
  let edges = '', nodes = '';
  for (let i = 0; i < n; i++) {
    const p = plPos(i), st = plStatus(i), t = ts[i];
    nodes += '<button type="button" class="pl-node pl-' + st + (fresh ? ' pl-gen' : '') + '" style="left:' + p.x + 'px;top:' + p.y + 'px;width:' + PL_W + 'px;height:' + PL_H + 'px' +
      (fresh ? ';animation-delay:' + (i * 130) + 'ms' : '') + '" onclick="toggleWorkflowTask(' + i + ')" aria-label="' + escA(t.title) + ' \u2014 ' + PL_LABEL[st] + '. Click to toggle done">' +
      '<span class="pl-top"><span class="pl-n">' + pad(i + 1) + '</span><span class="pl-st">' + (st === 'done' ? '\u2713 ' : '') + PL_LABEL[st] + '</span></span>' +
      '<b>' + esc(t.title) + '</b><small>' + esc(t.desc || '') + '</small><em>' + esc(t.time) + '</em></button>';
    if (i < n - 1) {
      const q = plPos(i + 1), x1 = p.x + PL_W, y1 = p.y + PL_H / 2, x2 = q.x, y2 = q.y + PL_H / 2;
      const cls = plStatus(i + 1) === 'active' ? 'pl-e pl-flow' : (t.done ? 'pl-e pl-e-done' : 'pl-e');
      edges += '<path class="' + cls + '" d="M' + x1 + ' ' + y1 + ' C' + (x1 + 70) + ' ' + y1 + ' ' + (x2 - 70) + ' ' + y2 + ' ' + x2 + ' ' + y2 + '" marker-end="url(#pl-arrow)"/>';
    }
  }
  const empty = '<div class="spc-empty">No blocks yet \u2014 use \u201cGenerate workflow\u201d below.</div>';
  return '<section class="spc-wrap">' +
    '<div class="spc-top">' + plTabs() + '<span class="pl-pill' + (WORKFLOW_BUSY ? ' busy' : '') + '"><i></i>' + esc(pillTxt) + '</span></div>' +
    '<div class="pl-canvas" id="pl-canvas" style="height:' + H + 'px"><div style="position:relative;width:' + W + 'px;height:' + H + 'px">' +
      '<svg width="' + W + '" height="' + H + '" style="position:absolute;left:0;top:0;pointer-events:none">' +
        '<defs><marker id="pl-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--ink-3)"/></marker></defs>' + edges + '</svg>' +
      (nodes || empty) + '</div></div>' +
    '<div class="pl-legend"><span><i class="d"></i>Done</span><span><i class="a"></i>Active</span><span><i class="q"></i>Queued</span>' +
      '<span class="pl-hint">Click a block to mark it done. Design your own boards in 1 Month / 1 Year.</span></div>' +
    '<div class="pl-log"><h4>Activity</h4>' + plLogHTML() + '</div>' +
  '</section>';
}
function spcRenderHTML() { return SPC_VIEW === 'pipeline' ? spcPipelineHTML() : spcBoardHTML(); }
function spcBoardHTML() {
  const st = spcState();
  const W = Math.max(700, ...(st.nodes.map(n => n.x + 210)), 700);
  const H = Math.max(360, ...(st.nodes.map(n => n.y + 150)), 360);
  const animIds = SPC_ANIMATE_IDS;
  const nodesHTML = st.nodes.map((n, idx) => {
    const isNew = animIds && animIds.has(n.id);
    return '<div class="spc-node' + (SPC_LINK_FROM === n.id ? ' spc-linking' : '') + (isNew ? ' spc-enter' : '') + '" data-id="' + n.id + '" style="left:' + n.x + 'px;top:' + n.y + 'px;border-left-color:' + (n.color || '#7CA8E0') + (isNew ? ';animation-delay:' + (idx * 110) + 'ms' : '') + '">' +
      '<div class="spc-node-h"><b>' + esc(n.title) + '</b><div class="spc-node-actions">' +
        '<button title="Connect an arrow" onclick="spcToggleLink(\'' + n.id + '\')">' + icon('send', 12) + '</button>' +
        '<button title="Edit" onclick="spcEditNode(\'' + n.id + '\')">' + icon('edit', 12) + '</button>' +
        '<button title="Delete" onclick="spcDeleteNode(\'' + n.id + '\')">' + icon('trash', 12) + '</button>' +
      '</div></div>' +
      (n.note ? '<div class="spc-node-note">' + esc(n.note) + '</div>' : '') +
    '</div>';
  }).join('');
  const edgesHTML = st.edges.map((e, idx) => {
    const isNew = animIds && animIds.has(e.to);
    return '<line data-edge="' + e.id + '" x1="0" y1="0" x2="0" y2="0" marker-end="url(#spc-arrow)"' + (isNew ? ' class="spc-edge-enter" style="animation-delay:' + (idx * 110 + 160) + 'ms"' : '') + '/>';
  }).join('');
  SPC_ANIMATE_IDS = null;
  const edgeChips = st.edges.map(e => {
    const a = st.nodes.find(n => n.id === e.from), b = st.nodes.find(n => n.id === e.to);
    return '<span class="spc-edge-chip">' + esc(a ? a.title : '?') + ' \u2192 ' + esc(b ? b.title : '?') + '<button onclick="spcDeleteEdge(\'' + e.id + '\')" aria-label="Remove arrow">' + icon('x', 11) + '</button></span>';
  }).join('');
  return '<section class="spc-wrap">' +
    '<div class="spc-top">' +
      '<div class="spc-tabs" role="tablist">' + '<button role="tab" aria-selected="false" onclick="spcSetMode(\'pipeline\')">Pipeline</button>' +
        '<button role="tab" aria-selected="' + (SPC_MODE === 'month') + '" class="' + (SPC_MODE === 'month' ? 'on' : '') + '" onclick="spcSetMode(\'month\')">1 Month</button>' +
        '<button role="tab" aria-selected="' + (SPC_MODE === 'year') + '" class="' + (SPC_MODE === 'year' ? 'on' : '') + '" onclick="spcSetMode(\'year\')">1 Year</button>' +
      '</div>' +
      '<div class="spc-top-r">' +
        (SPC_LINK_FROM ? '<span class="row-s">Click the link icon on another box &mdash; <button class="btn ghost sm" onclick="spcCancelLink()">Cancel</button></span>' : '') +
        '<button class="btn sm" onclick="spcAddNode()">' + icon('plus', 14) + 'Add box</button>' +
      '</div>' +
    '</div>' +
    '<div class="spc-prompt-row">' +
      '<input type="text" id="spc-prompt" placeholder="Describe your goal \u2014 e.g. \u2018Crack DBMS in 4 weeks\u2019 \u2014 and KARNA lays out the boxes" onkeydown="if(event.key===\'Enter\'){event.preventDefault();spcGenerateFromPrompt()}">' +
      '<button class="btn sm" onclick="spcGenerateFromPrompt()" ' + (SPC_BUSY ? 'disabled' : '') + '>' + (SPC_BUSY ? 'Generating\u2026' : 'Generate board') + '</button>' +
    '</div>' +
    '<div class="spc-canvas" id="spc-canvas" style="width:100%;height:420px;overflow:auto">' +
      '<div style="position:relative;width:' + W + 'px;height:' + H + 'px">' +
        '<svg id="spc-svg" width="' + W + '" height="' + H + '" style="position:absolute;left:0;top:0;pointer-events:none">' +
          '<defs><marker id="spc-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="var(--ink-3)"/></marker></defs>' +
          edgesHTML +
        '</svg>' +
        (nodesHTML || '<div class="spc-empty">No boxes yet \u2014 describe your goal above and tap "Generate board", or add boxes by hand. Drag boxes to arrange them, and use the arrow icon to connect two.</div>') +
      '</div>' +
    '</div>' +
    (edgeChips ? '<div class="spc-edges">' + edgeChips + '</div>' : '') +
  '</section>';
}
function renderStudyWorkflowBody() {
  const totalTasks = STUDY_WORKFLOW.tasks.length; const doneTasks = STUDY_WORKFLOW.tasks.filter(t => t.done).length;
  const pct = totalTasks ? Math.round(doneTasks / totalTasks * 100) : 0;
  const ex = workflowExam();
  const examLabel = ex && ex.exam_date ? 'Exam on ' + fmtDate(ex.exam_date) : (STUDY_WORKFLOW.examDate ? 'Exam on ' + fmtDate(STUDY_WORKFLOW.examDate) : 'No exam date');
  const opt = (v, sel) => '<option ' + (sel ? 'selected' : '') + '>' + esc(v) + '</option>';
  const subjectOptions = SEMS_COURSES.length
    ? SEMS_COURSES.map(c => opt(c.name, STUDY_WORKFLOW.subject === c.name)).join('')
    : ['Database Systems', 'Operating Systems', 'Computer Networks'].map(v => opt(v, STUDY_WORKFLOW.subject === v)).join('');
  const quick = (action, label) => '<button class="chip" style="cursor:pointer" onclick="runQuickAction(\'' + action + '\')">' + esc(label) + '</button>';
  const rowsHTML = STUDY_WORKFLOW.tasks.map((t, idx) =>
    '<div class="row"><input type="checkbox" class="ck" ' + (t.done ? 'checked' : '') + ' aria-label="Mark ' + escA(t.title) + ' done" onchange="toggleWorkflowTask(' + idx + ')">' +
    '<div><div class="row-t" style="' + (t.done ? 'text-decoration:line-through;color:var(--ink-3)' : '') + '">' + (idx + 1) + '. ' + esc(t.title) + '</div>' +
    (t.desc ? '<div class="row-s">' + esc(t.desc) + '</div>' : '') + '</div>' +
    '<div class="row-a"><span class="chip">' + esc(t.time) + '</span><span class="pill ' + (t.done ? 'good' : '') + '">' + (t.done ? 'Completed' : 'Pending') + '</span></div></div>'
  ).join('');
  return '<p class="row-s" style="margin:14px 0 16px">' + (BACKEND.ready ? 'Backed by your real SEMS exam map \u2014 risk and priority computed server-side.' : 'Design your own plan on the board below, or let KARNA generate one from your goal.') + '</p>' +
    '<section class="panel" style="padding:20px;margin-bottom:16px">' + spcRenderHTML() + '</section>' +
    '<section class="panel" style="padding:20px;margin-bottom:16px">' +
      '<div class="fields" style="margin-bottom:4px">' +
        '<div class="field half"><label for="sw-select-subject">Subject</label><select id="sw-select-subject">' + subjectOptions + '</select></div>' +
        '<div class="field half"><label for="sw-select-time">Available time</label><select id="sw-select-time">' + ['1 hour', '2 hours', '3 hours', '4 hours'].map(v => opt(v, STUDY_WORKFLOW.duration === v)).join('') + '</select></div>' +
        '<div class="field half"><label for="sw-select-mode">Study mode</label><select id="sw-select-mode">' + ['Balanced (Plan + Practice)', 'Exam Sprint (Speed & PYQs)', 'Weak-Topic Recovery'].map(v => opt(v, STUDY_WORKFLOW.mode === v)).join('') + '</select></div>' +
        '<div class="field half" style="display:flex;align-items:flex-end"><button class="btn" style="width:100%" onclick="generateWorkflowFromUI()" ' + (WORKFLOW_BUSY ? 'disabled' : '') + '>' + (WORKFLOW_BUSY ? 'Generating\u2026' : 'Generate workflow') + '</button></div>' +
      '</div>' +
    '</section>' +
    '<section class="panel" style="padding:20px;margin-bottom:16px">' +
      '<div class="panel-h" style="padding:0 0 14px;margin-bottom:4px">' +
        '<h3 style="text-transform:none;letter-spacing:0;font-family:var(--display);font-size:16px;font-weight:650;color:var(--ink)">Today\'s study plan</h3>' +
        '<span>' + esc(STUDY_WORKFLOW.subject) + ' \u00b7 ' + esc(STUDY_WORKFLOW.duration) + ' \u00b7 ' + esc(examLabel) + '</span>' +
      '</div>' +
      '<div class="meter hi" style="margin-bottom:14px"><div><i style="width:' + pct + '%"></i></div>' + doneTasks + ' / ' + totalTasks + ' completed \u00b7 ' + pct + '%</div>' +
      '<div class="rows">' + (rowsHTML || '<div class="row-s" style="padding:16px 0">No blocks yet \u2014 generate a workflow above.</div>') + '</div>' +
    '</section>' +
    '<section class="panel" style="padding:18px 20px;margin-bottom:16px">' +
      '<div class="row-s" style="margin-bottom:10px;font-weight:600;color:var(--ink)">Quick actions</div>' +
      '<div class="row-m">' + quick('plan3h', 'Plan for next 3 hours') + quick('weak', 'Focus on weak topics') + quick('pyq', 'Generate PYQs') + quick('explain', 'Explain this topic') + quick('quiz', 'Take a quick quiz') + quick('track', 'Track my progress') + '</div>' +
    '</section>' +
    '<section class="panel" style="padding:8px">' +
      '<div class="cbox"><textarea id="sw-prompt-input" rows="1" placeholder="Ask KARNA about your study goal\u2026" onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();handleWorkflowPrompt()}"></textarea>' +
      '<button class="send" onclick="handleWorkflowPrompt()" title="Send">' + icon('up', 17) + '</button></div>' +
    '</section>';
}

function viewJarvis() {
  /* "Live" now means KARNA is actually answering from an LLM: either the
     backend agent (BACKEND.ready — preferred, has tools + RAG) or, if the
     backend is unreachable, a personal Groq key pasted in Profile. This
     used to only check groqKey, which showed "Local" even while the
     backend agent was working fine. */
  const live = BACKEND.ready || !!S.profile.groqKey;
  const liveLabel = BACKEND.ready ? 'Connected to your OPAI backend' : (S.profile.groqKey ? 'Live on Groq \u00b7 ' + (S.profile.groqModel || GROQ_MODELS[0].v) : '');
  const gm = S.profile.groqModel || GROQ_MODELS[0].v;
  const sub = live ? liveLabel : 'Backend unreachable &amp; no Groq key \u2014 answering from your workspace data';
  const action = '<span class="pill ' + (live ? 'good' : '') + '">' + (live ? 'Live' : 'Local') + '</span>' +
    '<button class="btn ghost sm" onclick="jarvisNew();setJarvisMode(\'chat\')">New chat</button>';
  const tabs = '<div class="rtabs" role="tablist">' +
      '<button role="tab" aria-selected="' + (KARNA_MODE === 'chat') + '" class="' + (KARNA_MODE === 'chat' ? 'on' : '') + '" onclick="setJarvisMode(\'chat\')">Chat</button>' +
      '<button role="tab" aria-selected="' + (KARNA_MODE === 'study') + '" class="' + (KARNA_MODE === 'study' ? 'on' : '') + '" onclick="setJarvisMode(\'study\')">Study Workflow</button>' +
    '</div>';
  const headBlock = head('KARNA', sub, action) + tabs;
  if (KARNA_MODE === 'study') return headBlock + renderStudyWorkflowBody();
  /* No "connect" step shown to the user anymore \u2014 KARNA always tries the
     backend agent first, silently. The Groq-key path only still exists as
     an invisible safety net inside jarvisSend() for the rare case the
     backend is down; nothing here asks the user to paste a key. */
  const connectBanner = live ? '' : '<div class="kw-reconnect">Reconnecting to the backend\u2026 this can take up to a minute if it has been idle.</div>';
  return headBlock + '<div class="jv"><section class="panel jv-main"><div class="jv-top"><div class="orb"></div><div><b>KARNA</b><span>' + (KARNA_SCOPE === 'general' ? 'General chat: ask anything' : (live ? escA(liveLabel) : 'Answering from your workspace data')) + '</span></div>' + karnaScopeHTML() + '<a class="kf-btn" href="/super-chat" title="Upload documents and chat with citations" style="margin-left:8px;text-decoration:none">Knowledge &amp; docs</a></div>' + connectBanner + '<div class="msgs" id="msgs">' + (CHAT.length ? CHAT.map(bubbleHTML).join('') : welcomeHTML()) + '</div><div class="composer"><div class="cbox"><textarea id="jv-input" rows="1" placeholder="' + (KARNA_SCOPE === 'general' ? 'Ask KARNA anything' : 'Ask KARNA about your workspace') + '" aria-label="Message KARNA"></textarea><button class="send" onclick="jarvisSend()" aria-label="Send message">' + icon('up', 17) + '</button></div></div></section><aside class="panel jv-ctx"><h3>Workspace right now</h3><div id="ctx"></div><div class="ctx-note">' + (BACKEND.ready ? 'Connected to your OPAI backend (KARNA agent).' : (S.profile.groqKey ? 'Connected to Groq (' + escA(gm) + ').' : 'Backend is waking up \u2014 retry in a moment.')) + '</div></aside></div>';
}
function welcomeHTML() { return '<div class="welcome" id="welcome"><h2>Start here: set up your whole OPAI app</h2><p>Tap the first option and I will walk you through everything: profile, applications, exams, projects and outreach. Or type your own question.</p><div class="prompts">' + PROMPTS.map(p => '<button onclick="jarvisSend(this.textContent)">' + esc(p) + '</button>').join('') + '</div></div>'; }
function fmtMsg(t) { return esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>'); }
function bubbleHTML(m) { return '<div class="m ' + (m.role === 'user' ? 'you' : '') + '"><div class="bubble">' + fmtMsg(m.text) + '</div></div>'; }
function ctxHTML() {
  const plan = buildPlan(); const mins = plan.reduce((s, i) => s + i.effort, 0);
  const rows = [['Queued today', fmtMins(mins)], ['Open applications', S.applications.filter(a => ['Not started','Applied','Interview'].includes(a.status)).length], ['Emails to write', S.contacts.filter(c => c.status === 'Not started').length], ['Open requests', S.requests.filter(r => r.status === 'New' || r.status === 'Scoped').length], ['Awaiting approval', S.outbox.filter(o => o.status === 'pending').length]];
  return rows.map(r => '<div class="ctx-row"><span>' + r[0] + '</span><b>' + r[1] + '</b></div>').join('');
}
function refreshCtx() { const el = $('ctx'); if (el) el.innerHTML = ctxHTML(); }
function jarvisNew() { CHAT = []; const m = $('msgs'); if (m) m.innerHTML = welcomeHTML(); }
/* ---- KARNA quick-create: chat -> real records ---- */
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
  const qc = quickCreate(t);
  if (qc) {
    setTimeout(() => {
      const ty = $('typing'); if (ty) ty.remove();
      CHAT.push({ role: 'assistant', text: qc });
      box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'assistant', text: qc }));
      box.scrollTop = box.scrollHeight; refreshCtx();
    }, 250);
    return;
  }
  let reply;
  /* Primary path: the real backend agent (run_jarvis_agent) — validated tool
     whitelist, activity log, RAG-grounded answers. This is what actually
     "connects KARNA" instead of the browser talking to Groq directly. */
  if (BACKEND.ready) {
    try {
      const uid = await ensureUser();
      const hist = CHAT.slice(-9, -1).filter(m => m.role === 'user' || m.role === 'assistant').map(m => ({ role: m.role, content: String(m.text).slice(0, 1500) }));
      const res = await POST('/v1/jarvis/chat', { user_id: uid, message: t, history: hist });
      reply = res.reply || 'Done.';
      const srcs = res.payload && Array.isArray(res.payload.sources) ? res.payload.sources.filter(s => s && s.n) : [];
      if (srcs.length) reply += '\n\n**Sources:** ' + srcs.map(s => '[' + s.n + '] ' + s.title + (s.page ? ' p.' + s.page : '')).join(' \u00b7 ');
      if (res.tool_calls && res.tool_calls.length) { syncBackend(true).catch(() => {}); }
    } catch (e) {
      reply = 'KARNA backend call failed (' + e.message + ').';
      if (S.profile.groqKey) {
        try {
          const sys = 'You are KARNA, the AI copilot inside OPAI, ' + (S.profile.name || 'the user') + '\u2019s personal operating agent. ' +
            'Answer from the workspace snapshot below. Be direct and brief \u2014 a few sentences or a short list, not an essay. ' +
            'You cannot send emails or apply anywhere. You CAN create records. When the user asks you to add/create something, confirm in one short sentence and end your reply with one line: ACTION: {"type":"<application|task|project|study|request|contact|mail>","data":{...}}. ' +
            'Data fields: application {company, role, type: Internship|Research|Hackathon, deadline: YYYY-MM-DD or null}; task {name, project}; mail {to: email or contact name}; project {name}; study {subject, task, exam_date: YYYY-MM-DD or null}; request {client, ask}; contact {name, institute, email}. Today is ' + iso(0) + '. Only emit ACTION when the user clearly asked to create something.\n\n' + workspaceSnapshot();
          const msgs = [{ role: 'system', content: sys }, ...CHAT.slice(-10).map(m => ({ role: m.role, content: m.text }))];
          const gReply = await groqChat(msgs);
          if (gReply) { const ex = extractAction(gReply); if (ex.action) { const done = execAction(ex.action); reply += '\n\nFalling back to Groq:\n' + (ex.text ? ex.text + '\n\n' : '') + (done || 'I could not create that record.'); } else reply += '\n\nFalling back to Groq:\n' + ex.text; }
        } catch (e2) { reply += '\n\nFalling back to a local reply:\n' + jarvisReply(t); }
      } else {
        reply += '\n\nFalling back to a local reply:\n' + jarvisReply(t);
      }
    }
    const ty = $('typing'); if (ty) ty.remove();
    CHAT.push({ role: 'assistant', text: reply });
    box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'assistant', text: reply }));
    box.scrollTop = box.scrollHeight; refreshCtx();
    return;
  }
  /* Backend unreachable: same client-side Groq / local-pattern fallback as before. */
  if (S.profile.groqKey) {
    try {
      const sys = 'You are KARNA, the AI copilot inside OPAI, ' + (S.profile.name || 'the user') + '\u2019s personal operating agent. ' +
        'Answer from the workspace snapshot below. Be direct and brief \u2014 a few sentences or a short list, not an essay. ' +
        'You cannot send emails or apply anywhere. You CAN create records. When the user asks you to add/create something, confirm in one short sentence and end your reply with one line: ACTION: {"type":"<application|task|project|study|request|contact|mail>","data":{...}}. ' +
        'Data fields: application {company, role, type: Internship|Research|Hackathon, deadline: YYYY-MM-DD or null}; task {name, project}; mail {to: email or contact name}; project {name}; study {subject, task, exam_date: YYYY-MM-DD or null}; request {client, ask}; contact {name, institute, email}. Today is ' + iso(0) + '. Only emit ACTION when the user clearly asked to create something.\n\n' + workspaceSnapshot();
      const msgs = [{ role: 'system', content: sys }, ...CHAT.slice(-10).map(m => ({ role: m.role, content: m.text }))];
      reply = await groqChat(msgs);
      if (!reply) reply = jarvisReply(t);
      else { const ex = extractAction(reply); if (ex.action) { const done = execAction(ex.action); reply = (ex.text ? ex.text + '\n\n' : '') + (done || 'I could not create that record.'); } else reply = ex.text; }
    } catch (e) { reply = 'Groq call failed (' + e.message + '). Falling back to local reply:\n\n' + jarvisReply(t); }
    const ty = $('typing'); if (ty) ty.remove();
    CHAT.push({ role: 'assistant', text: reply });
    box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'assistant', text: reply }));
    box.scrollTop = box.scrollHeight; refreshCtx();
    return;
  }
  setTimeout(() => {
    const reply = jarvisReply(t);
    const ty = $('typing'); if (ty) ty.remove();
    CHAT.push({ role: 'assistant', text: reply });
    box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'assistant', text: reply }));
    box.scrollTop = box.scrollHeight; refreshCtx();
  }, 550);
}
function clockStrOf(d) { return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); }
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
  return 'I can help with your plan, applications, projects, outreach, client requests, and study tasks. Try "What should I focus on today?" or "Help me plan the next 3 hours."';
}
 
/* ---- Overview (everything, one page) ---- */
function ovHead(title, count, tab) {
  return '<div class="panel-h"><h3>' + title + '</h3><button class="tip-btn" data-tip="' + title + '" onclick="showTip(this.dataset.tip)" aria-label="About this section">?</button><span style="display:flex;align-items:center;gap:10px;margin-left:auto">' + (count != null ? count : '') + '<button class="btn ghost sm" onclick="switchTab(\'' + tab + '\')">See all</button></span></div>';
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
 
  return head('Overview', 'Everything across OPAI, on one page. Tap "See all" to open a section in full.', '') + karnaHero() +
    '<div class="grid2">' +
      '<section class="panel">' + ovHead('Applications', S.applications.length, 'applications') + '<div class="rows">' + appsRows + '</div></section>' +
      '<section class="panel">' + ovHead('Opportunities', S.opportunities.length, 'opportunities') + '<div class="rows">' + oppsRows + '</div></section>' +
      '<section class="panel">' + ovHead('Internships', S.contacts.length, 'outreach') + '<div class="rows">' + contactRows + '</div></section>' +
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
  { id:'jarvis', l:'KARNA', i:'spark', g:'Assistant' },
  { id:'superchat', l:'Super Chat', i:'spark', href:'/super-chat' },
  { id:'overview', l:'Overview', i:'layers' },
  { id:'today', l:'Today', i:'sun', g:'Plan' },
  { id:'applications', l:'Applications', i:'brief' },
  { id:'opportunities', l:'Opportunities', i:'target' },
  { id:'outreach', l:'Internships', i:'mail' },
  { id:'projects', l:'Projects', i:'layers', g:'Work' },
  { id:'academics', l:'Academics', i:'book' },
  { id:'dsa', l:'DSA Roadmap', i:'target', href:'dsa.html' },
  { id:'sems', l:'Exams & Courses', i:'grad' },
  { id:'requests', l:'Requests', i:'chat' },
  { id:'outbox', l:'Outbox', i:'send', g:'Tools' },
  { id:'resume', l:'Resume Lab', i:'file' },
  { id:'agent', l:'Agent Console', i:'shield', g:'Safety' },
  { id:'history', l:'History', i:'clock' },
  { id:'review', l:'Review', i:'star' },
  { id:'profile', l:'Profile', i:'user' }
];
const VIEWS = { review: viewReview, jarvis: viewJarvis, overview: viewOverview, today: viewToday, applications: viewApps, opportunities: viewOpps, outreach: viewOutreach, projects: viewProjects, academics: viewAcads, sems: viewSems, requests: viewReqs, outbox: viewOutbox, resume: viewResume, agent: viewAgent, history: viewHistory, profile: viewProfile };
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
    return (n.g ? '<div class="nav-group">' + n.g + '</div>' : '') + '<button class="' + (n.id === cur ? 'on' : '') + '" onclick="' + (n.href ? 'location.href=\'' + n.href + '\'' : 'switchTab(\'' + n.id + '\')') + '"' + (n.id === cur ? ' aria-current="page"' : '') + '>' + icon(n.i, 17) + n.l + (c ? '<span class="count' + (n.id === 'outbox' ? ' alert' : '') + '">' + c + '</span>' : '') + '</button>';
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
  if (cur === 'agent') { loadAgentConsole(); }
  if (cur === 'sems') { loadSems(); }
  if (cur === 'resume') { resumeAfterRender(); }
  if (!fromNav) window.scrollTo(0, y);
}
function wireJarvis() {
  if (KARNA_MODE === 'study') { spcWire(); spcRedrawEdgesLive(); }
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
    } catch (e) { toast('That file is not an OPAI backup', true); }
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
  const n = (S.profile.name || (AUTH.user && AUTH.user.name) || 'User').trim() || 'User';
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
const GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.send';
const AUTH = { user: null };
const GMAIL = { token: null, exp: 0 };
let FB = null;
 
function fbConfigured() { return !!FB_CONFIG.apiKey && !/^PASTE/.test(FB_CONFIG.apiKey) && !/PASTE/.test(FB_CONFIG.projectId); }
function fbInit() {
  if (FB) return FB;
  if (!window.firebase || !fbConfigured()) return null;
  try { if (!firebase.apps.length) firebase.initializeApp(FB_CONFIG); FB = firebase.auth(); } catch (e) { FB = null; }
  return FB;
}
function gProvider(hint, withGmailScope) {
  // Login uses plain Google sign-in (no scope) so Google's consent screen
  // shows the normal "Sign in" flow instead of the sensitive-scope warning.
  // Gmail send access is requested separately, only from connectGmail().
  const p = new firebase.auth.GoogleAuthProvider();
  if (withGmailScope) p.addScope(GMAIL_SCOPE);
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
  if (c === 'auth/email-already-in-use') return 'An account with that email already exists — try logging in instead.';
  if (c === 'auth/invalid-email') return 'That email address looks invalid.';
  if (c === 'auth/weak-password') return 'Password should be at least 6 characters.';
  if (c === 'auth/wrong-password' || c === 'auth/invalid-credential') return 'Wrong email or password.';
  if (c === 'auth/user-not-found') return 'No account with that email — try signing up instead.';
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
  openModal('<h3>Connect Gmail</h3><p class="row-s" style="margin-bottom:6px">' + esc(msg || 'OPAI needs your OK to send this email from your Gmail account.') + '</p><div class="note">Only the "send email" permission is requested. OPAI cannot read your inbox.</div><div class="gate-err" id="gm-err" role="alert"></div><div class="foot"><button class="btn ghost" onclick="closeModal()">Cancel</button><button class="btn" id="gm-ok" onclick="gmailOk(\'' + (pendingId || '') + '\')">OK</button></div>');
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
  const res = await a.currentUser.reauthenticateWithPopup(gProvider(a.currentUser.email, true));
  if (!grabToken(res)) throw new Error('Google did not return send permission. Try again and allow it.');
}
 
function wsKey(uid) { return 'opa_ws_' + uid; }
function enterUser(u) {
  BACKEND.userId = null; rlReset(); semsReset();
  AUTH.user = { uid: u.uid, email: u.email || '', name: u.displayName || '', photo: u.photoURL || '' };
  try { localStorage.setItem(LS_SESSION, 'google'); if (u.email) localStorage.setItem('opai_sc_email', u.email); } catch (e) {}
  LS_KEY = wsKey(u.uid);
  let has = false; try { has = !!localStorage.getItem(LS_KEY); } catch (e) {}
  if (has) S = load();
  else {
    S = seed();
    if (!S.profile.email) S.profile.email = AUTH.user.email;
    if (u.displayName) S.profile.name = u.displayName;
    log('Signed in as ' + AUTH.user.email); save();
  }
  renderUser(); render(true);
  syncBackend().then(() => { updateConnBadge(); render(true); });
}
function renderUser() {
  const c = $('userchip'); if (!c) return;
  c.style.display = '';
  const u = AUTH.user;
  const nm = u ? (u.name || u.email) : 'User';
  const av = u && u.photo ? '<img src="' + escA(u.photo) + '" alt="" referrerpolicy="no-referrer">' : esc((nm[0] || 'U').toUpperCase());
  c.innerHTML = '<div class="av">' + av + '</div><div><b>' + esc(nm) + '</b><span>' + (u ? esc(u.email) : '') + '</span></div><button class="icon-btn" onclick="signOutNow()" aria-label="Sign out" title="Sign out">' + icon('x', 15) + '</button>';
}
function signOutNow() {
  BACKEND.userId = null; rlReset(); semsReset();
  const a = FB;
  AUTH.user = null; GMAIL.token = null; GMAIL.exp = 0;
  try { localStorage.removeItem(LS_SESSION); localStorage.removeItem('opai_sc_email'); } catch (e) {}
  $('userchip').style.display = 'none';
  const done = () => location.replace('login.html');
  if (a) a.signOut().then(done, done); else done();
}
function accountPanel() {
  const u = AUTH.user;
  const h = '<section class="panel form-panel" style="margin-top:20px"><h3 style="font-family:var(--display);font-size:18px;font-weight:650;margin-bottom:8px">Account</h3>';
  if (!u) return h + '<p class="row-s" style="margin-bottom:16px">You are not signed in.</p><div class="data-actions"><button class="btn" onclick="signOutNow()">Sign in</button></div></section>';
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
  const a = fbInit();
  if (!a) { location.replace('login.html'); return; }
  let first = true;
  a.onAuthStateChanged((u) => {
    if (u) { if (!AUTH.user || AUTH.user.uid !== u.uid) enterUser(u); }
    else if (first) location.replace('login.html');
    first = false;
  });
})();

/* ================= BACKEND-BACKED EDITS ================= */
(function () {
  const _upsert = upsert;
  upsert = function (coll, obj) {
    _upsert(coll, obj);
    if (!BACKEND.ready || !PUSH[coll]) return;
    PUSH[coll](obj).then(() => syncBackend(true)).catch(e => toast('Could not save to backend: ' + e.message, true));
  };
  const _toggleAcad = toggleAcad;
  toggleAcad = function (id) {
    _toggleAcad(id);
    const a = byId('academics', id);
    if (BACKEND.ready && a) PATCH('/v1/academics/' + id, { done: !!a.done }).catch(e => toast('Could not sync: ' + e.message, true));
  };
  toggleTask = function (pid, tid) {
    const t = byId('projects', pid).tasks.find(x => x.id === tid); t.done = !t.done;
    if (t.done) log('Finished task: ' + t.name); save(); render();
    if (BACKEND.ready) PATCH('/v1/tasks/' + tid, { status: t.done ? 'done' : 'todo' }).catch(e => toast('Could not sync: ' + e.message, true));
  };
  deleteTask = function (pid, tid) {
    const p = byId('projects', pid); p.tasks = p.tasks.filter(x => x.id !== tid); save(); render();
    if (BACKEND.ready) DEL('/v1/tasks/' + tid).catch(e => toast('Could not sync: ' + e.message, true));
  };
  const _addTask = addTask;
  addTask = async function (pid) {
    if (!BACKEND.ready) return _addTask(pid);
    const el = $('nt-' + pid); const name = el.value.trim(); if (!name) return;
    try { const uid = await ensureUser(); await POST('/v1/projects/' + pid + '/tasks', { user_id: uid, title: name }); await syncBackend(true); const n = $('nt-' + pid); if (n) n.focus(); }
    catch (e) { toast('Could not add task: ' + e.message, true); }
  };
  resetData = function () {
    confirmBox('Delete ALL your data (applications, projects, study tasks, requests)? This cannot be undone.', 'Delete everything', async () => {
      if (BACKEND.ready) {
        try { for (const c of ['applications', 'projects', 'academics', 'requests']) for (const it of S[c]) await DEL(DELPATH[c] + it.id); }
        catch (e) { toast('Some items could not be deleted: ' + e.message, true); }
      }
      const prof = S.profile; S = seed(); S.profile = prof; save(); render(); toast('All data deleted');
    });
  };
})();

/* ================= POPUP TUTORIALS ================= */
const TUTORIALS = {
  welcome: { title: 'Welcome to OPAI', steps: [
    ['What is this?', 'OPAI is your personal operating desk: one place for job and hackathon applications, professor outreach, projects, exams and client requests.'],
    ['Start small', 'Add just one thing: an application with a deadline, or an exam date. Everything else (Today, Overview, the calendar) builds itself from what you add.'],
    ['Today tab', 'Shows what to do right now, ordered by deadline. Tick items as you finish them.'],
    ['Ask KARNA', 'Open the KARNA chat tab (or press Ctrl+J) and type things like "Add an internship at Acme due Friday" or "Plan my next 3 hours". It creates real records for you.'],
    ['Need help later?', 'Every page has a "? How to use" button in the top right. It opens a short guide for that page.'] ] },
  jarvis: { title: 'Using KARNA (chat)', steps: [
    ['Talk normally', 'Write like you would to a person: "I have a DBMS exam on Oct 1" or "Draft an email to Dr. Rao".'],
    ['It acts, you approve', 'KARNA can add applications, projects and study tasks. Anything that sends an email waits in Outbox for your approval first.'],
    ['Quick starts', 'Use the prompt buttons on an empty chat, or Ctrl+J from any page. "New chat" clears the conversation, not your data.'] ] },
  today: { title: 'Today', steps: [
    ['What you see', 'A time-ordered plan built from your deadlines, exams and open tasks.'],
    ['Finish things', 'Tick a task when done. It moves to your history and the plan re-balances.'],
    ['Empty?', 'Nothing here means nothing is due. Add an application, a study task or a project task and it appears.'] ] },
  applications: { title: 'Applications', steps: [
    ['Add one', 'Click "Add application". Company, role and deadline are enough.'],
    ['Move it along', 'Change the status as things happen: Not started, Applied, Interview, Offer or Rejected.'],
    ['Never miss a deadline', 'Deadlines feed Today and the calendar. Applications you applied to also get follow-up reminders.'] ] },
  opportunities: { title: 'Opportunities', steps: [
    ['What these are', 'Openings you have found but not committed to yet: fellowships, internships, hackathons.'],
    ['Match score', 'Each one is scored against the skills in your Profile. Fill your skills in for better matches.'],
    ['Convert', 'Like one? Convert it into an Application. Not interested? Dismiss it.'] ] },
  outreach: { title: 'Internships', steps: [
    ['Add a contact', 'Add a professor or recruiter with their research area or role.'],
    ['Draft with KARNA', 'Use Draft to get a personalised email that uses your profile and projects.'],
    ['Approve, then send', 'Drafts land in Outbox. Nothing is sent until you approve it. Mark it sent to start follow-up reminders.'] ] },
  projects: { title: 'Projects', steps: [
    ['Create a project', 'Give it a name and one line of description.'],
    ['Break it into tasks', 'Type a task in the box under a project and press Enter. Tick tasks off as you go.'],
    ['Why it matters', 'Your projects are used when KARNA writes outreach and cover letters.'] ] },
  academics: { title: 'Academics', steps: [
    ['Add a study task', 'Pick the subject, what to revise, the exam date and how many minutes it needs.'],
    ['Priority by date', 'Closer exams rise to the top of Today automatically.'],
    ['Tick when done', 'Finished study tasks are saved to your history.'] ] },
  requests: { title: 'Client requests', steps: [
    ['Log a request', 'Client name, what they want and their email.'],
    ['Scope it', 'Add scope, timeline and price, then move the status: New, Scoped, Quoted, Won or Declined.'],
    ['Draft a proposal', 'Once scoped, KARNA can draft the proposal email for your approval.'] ] },
  profile: { title: 'Profile', steps: [
    ['Why fill this in', 'Your skills, degree and highlight are used to score opportunities and to write outreach in your voice.'],
    ['Your data', 'It is saved to the backend under your account. "Delete all my data" wipes it.'] ] },
  _default: { title: 'How this page works', steps: [
    ['Getting around', 'Use the left menu to switch pages. Ctrl+K searches everything, Ctrl+J opens KARNA.'],
    ['Need more?', 'Open the "Overview" or "Today" page for the big picture, or ask KARNA in chat.'] ] }
};
let TUT = { key: 'welcome', i: 0 };
function showTutorial(key, i) {
  TUT.key = TUTORIALS[key] ? key : (TUTORIALS[key || cur] ? (key || cur) : '_default'); TUT.i = i || 0;
  const t = TUTORIALS[TUT.key], last = TUT.i === t.steps.length - 1, st = t.steps[TUT.i];
  openModal('<div class="tut-n">Step ' + (TUT.i + 1) + ' of ' + t.steps.length + '</div><h3>' + esc(t.title) + '</h3>' +
    '<div class="tut-step"><b>' + esc(st[0]) + '</b><p>' + esc(st[1]) + '</p></div>' +
    '<div class="tut-dots">' + t.steps.map((_, n) => '<i class="' + (n === TUT.i ? 'on' : '') + '"></i>').join('') + '</div>' +
    '<div class="foot">' + (TUT.i ? '<button class="btn ghost" onclick="showTutorial(TUT.key,' + (TUT.i - 1) + ')">Back</button>' : '<button class="btn ghost" onclick="closeTutorial()">Skip</button>') +
    (last ? '<button class="btn" onclick="closeTutorial()">Got it</button>' : '<button class="btn" onclick="showTutorial(TUT.key,' + (TUT.i + 1) + ')">Next</button>') + '</div>');
}
function closeTutorial() { if (TUT.key === 'welcome') { S.profile.tutorialSeen = true; save(); } closeModal(); }

/* ================= KARNA HOME (Overview) ================= */
const SETUP_STEPS = [
  { l: 'Fill your profile (name, skills, highlight)', tab: 'profile', hint: 'Open Profile and add your name, skills and one highlight line.', done: () => !!(S.profile.name && S.profile.skills) },
  { l: 'Add your first application', tab: 'applications', hint: 'Open Applications and add a job, internship or hackathon with its deadline.', done: () => S.applications.length > 0 },
  { l: 'Add an exam or study task', tab: 'academics', hint: 'Open Academics and add a subject with its exam date.', done: () => S.academics.length > 0 },
  { l: 'Create a project with tasks', tab: 'projects', hint: 'Open Projects, create one and add its first tasks.', done: () => S.projects.length > 0 },
  { l: 'Add an outreach contact', tab: 'outreach', hint: 'Open Outreach and add a professor or recruiter to contact.', done: () => S.contacts.length > 0 },
  { l: 'Connect a live model (optional)', tab: 'profile', hint: 'In Profile, paste your Groq key so KARNA gives smarter answers.', done: () => !!S.profile.groqKey }
];
const KARNA_CAN = ['Plan the next 3 hours', 'What is due this week?', 'Draft an email to a professor', 'Add an internship at Acme due Friday', 'Which projects need attention?', 'Help me prepare for my exam'];
function karnaGo(t) { switchTab('jarvis'); setTimeout(() => jarvisSend(t), 120); }
function karnaAsk() { const i = $('kh-input'); const t = i && i.value.trim(); if (t) karnaGo(t); }
function karnaHero() {
  const soon = (d) => d && (new Date(d) - new Date()) / 864e5 <= 7;
  const due = S.applications.filter(a => soon(a.deadline) && a.status === 'Not started').length + S.academics.filter(a => !a.done && soon(a.exam_date)).length;
  const pend = (S.outbox || []).filter(o => o.status === 'pending').length;
  const open = S.projects.reduce((n, p) => n + p.tasks.filter(t => !t.done).length, 0);
  const done = SETUP_STEPS.filter(x => x.done()).length, pct = Math.round(done / SETUP_STEPS.length * 100);
  const name = (S.profile.name || '').split(' ')[0];
  return '<section class="kh"><h2>Hi' + (name ? ' ' + esc(name) : '') + ', I am KARNA, your OPAI chat assistant</h2>' +
    '<p>Your operating agent. I read your applications, exams, projects and contacts, then tell you what to do next and do the busywork for you.</p>' +
    '<div class="kh-stats"><span><b>' + due + '</b> due in 7 days</span><span><b>' + open + '</b> open project tasks</span><span><b>' + pend + '</b> waiting for your approval</span><span>' + (BACKEND.ready ? 'Backend connected' : 'Offline mode') + '</span></div>' +
    '<div class="kh-ask"><input id="kh-input" placeholder="Ask KARNA anything, e.g. what should I do today?" onkeydown="if(event.key===\'Enter\')karnaAsk()"><button class="btn" onclick="karnaAsk()">Ask</button></div>' +
    '<div class="kh-cols"><div><h4>Setup · ' + done + ' of ' + SETUP_STEPS.length + ' done</h4><div class="kh-bar"><b style="width:' + pct + '%"></b></div>' +
    SETUP_STEPS.map(x => '<div class="kh-step ' + (x.done() ? 'done' : '') + '"><i>' + (x.done() ? '✓' : '') + '</i><span>' + esc(x.l) + '</span>' + (x.done() ? '' : '<button class="btn ghost sm" onclick="switchTab(\'' + x.tab + '\')">Go</button>') + '</div>').join('') +
    '<div style="margin-top:12px"><button class="btn" onclick="karnaGo(\'Set up my whole OPAI app\')">Start chat: set up my whole OPAI app</button></div></div>' +
    '<div><h4>Try asking me</h4><div class="kh-can">' + KARNA_CAN.map(q => '<button onclick="karnaGo(this.textContent)">' + esc(q) + '</button>').join('') + '</div>' +
    '<h4 style="margin-top:16px">What I can do</h4><p style="margin:0;font-size:14px">Plan your day, add records from plain sentences, draft outreach and proposals, score opportunities, and remember your preferences. Anything that sends email waits for your approval.</p></div></div></section>';
}
(function () {
  const _js = jarvisSend;
  jarvisSend = function (text) {
    const inp = $('jv-input'); const t = (text || (inp ? inp.value : '')).trim();
    if (t && t.length < 90 && /\b(set\s?up|setup|get started)\b/i.test(t)) return setupChat(t);
    return _js(text);
  };
})();
function setupChat(t) {
  const input = $('jv-input'); if (input) { input.value = ''; input.style.height = 'auto'; }
  const box = $('msgs'); const w = $('welcome'); if (w) w.remove();
  const todo = SETUP_STEPS.filter(x => !x.done()), n = SETUP_STEPS.length - todo.length;
  const msg = todo.length
    ? 'Let us set up your whole OPAI app. ' + n + ' of ' + SETUP_STEPS.length + ' steps are done.\n\n' + SETUP_STEPS.map(x => (x.done() ? '✓ ' : '○ ') + x.l).join('\n') + '\n\nNext: ' + todo[0].hint + ' You can also just tell me in a sentence, like "add an internship at Acme due Friday" or "I have a DBMS exam on Oct 1", and I will create it for you.'
    : 'Everything is set up. Ask me to plan your day, or open Today to start.';
  CHAT.push({ role: 'user', text: t }, { role: 'assistant', text: msg });
  box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'user', text: t }) + bubbleHTML({ role: 'assistant', text: msg }) +
    '<div class="prompts" style="margin:8px 0 16px">' + todo.slice(0, 4).map(x => '<button onclick="switchTab(\'' + x.tab + '\')">' + esc(x.l.replace(/ \(.*\)/, '')) + '</button>').join('') + '</div>');
  box.scrollTop = box.scrollHeight;
}

/* ================= MORE TUTORIALS + SECTION TIPS ================= */
Object.assign(TUTORIALS, {
  overview: { title: 'Overview (home)', steps: [
    ['Meet KARNA', 'The card at the top is your agent. It shows what is due, what needs approval and your setup progress.'],
    ['Setup checklist', 'Tick off the six setup steps. Each "Go" button opens the right page. Or tap "Start chat" and KARNA walks you through it.'],
    ['Sections below', 'Each panel is a summary of one page. Press "See all" to open the full page, or "?" for what the section does.'] ] },
  outbox: { title: 'Outbox (approvals)', steps: [
    ['Why it exists', 'KARNA never sends anything by itself. Drafts wait here for you.'],
    ['Approve or reject', 'Read the draft, edit if needed, then approve to send or reject to discard.'],
    ['After sending', 'Sent emails get follow-up reminders on the related contact or application.'] ] },
  resume: { title: 'Resume Lab', steps: [
    ['Add a version', 'Paste a resume and name it, for example \u201cSDE Intern v1\u201d. Add a target role so it is scored against the right job.'],
    ['Read the scores', 'You get overall, clarity, impact, keyword and structure scores, plus the single next change worth making.'],
    ['Edit in place', 'Use Edit to fix the text, rename it or change the role. Changing text or role re-scores that version.'],
    ['Use the extras', 'Copy suggested bullets, add recognised skills to your profile, or ask questions answered only from that version.'],
    ['Quick check', 'The Quick check tab is the offline skill scanner. It works without the backend.'] ] },
  agent: { title: 'Agent console', steps: [
    ['Permissions', 'Shows whether the agent is active. The emergency stop pauses every action.'],
    ['Activity', 'Every action KARNA actually took is logged here with a reason.'],
    ['Memory', 'Facts KARNA learns wait for your confirmation. Confirm what is right, delete what is not.'] ] },
  history: { title: 'History', steps: [
    ['What is logged', 'Everything you and KARNA did: tasks finished, items added or deleted.'],
    ['Use it', 'Handy for weekly reviews and to check what changed.'] ] }
});
const TIPS = {
  applications: 'Jobs, internships and hackathons you are going for. Status and deadlines here drive Today and reminders.',
  opportunities: 'Openings you found but have not committed to. Each one is scored against your skills; convert the good ones to applications.',
  outreach: 'Professors and recruiters you plan to email. Draft with KARNA, approve in Outbox, then follow up.',
  projects: 'Things you are building. Add tasks and tick them off. KARNA uses your projects in emails and cover letters.',
  academics: 'Exams and study tasks. Nearer exam dates rise to the top of your plan.',
  'client requests': 'Freelance or client asks. Scope them, quote them and draft proposals.',
  'workspace right now': 'A live count of what is open across all your pages.',
  'recent activity': 'The latest things done in your workspace.',
  'structured memory': 'Facts KARNA remembers about you. Confirm the right ones and delete the wrong ones.',
  account: 'Who you are signed in as. Sign out here to switch accounts.',
  'data on this device': 'Backup, restore or delete your data.',
  'connect gmail': 'Lets approved emails be sent from your Gmail. Nothing is sent without your approval.',
  'how the draft reads': 'A preview of how KARNA will sound in the email. Edit anything before approving.',
  'skills recognized': 'Skills detected in your resume. They power opportunity matching.'
};
function showTip(t) {
  const k = (t || '').toLowerCase().replace(/\s*\(.*\)/, '').trim();
  const txt = TIPS[k] || 'This section summarises this part of your workspace. Use the buttons beside it to add or open items, and the "? How to use" button at the top for the full page guide.';
  openModal('<h3>' + esc(t) + '</h3><p style="color:var(--ink-2);line-height:1.6;margin:10px 0">' + esc(txt) + '</p><div class="foot"><button class="btn ghost" onclick="showTutorial()">Full guide for this page</button><button class="btn" onclick="closeModal()">Got it</button></div>');
}
function addTips() {
  document.querySelectorAll('#view .panel-h:not(.tipd) > h3, #view .panel > h3, #view .panel h3').forEach(h => {
    if (h.parentNode.querySelector('.tip-btn')) return;
    const b = document.createElement('button'); b.className = 'tip-btn'; b.textContent = '?'; b.setAttribute('aria-label', 'About this section');
    b.onclick = () => showTip(h.textContent); h.insertAdjacentElement('afterend', b);
  });
}
(function () {
  const _render = render; render = function (f) { _render(f); try { addTips(); } catch (e) {} };
  const _sw = switchTab;
  switchTab = function (n) {
    _sw(n);
    if (S.profile.onboarded && S.profile.tutorialSeen && TUTORIALS[n]) {
      S.profile.seenTabs = S.profile.seenTabs || {};
      if (!S.profile.seenTabs[n]) { S.profile.seenTabs[n] = true; save(); setTimeout(() => showTutorial(n), 450); }
    }
  };
  let tx = null;
  document.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', e => {
    if (tx === null) return; const dx = e.changedTouches[0].clientX - tx, open = document.body.classList.contains('nav-open');
    if (!open && tx < 28 && dx > 70) document.body.classList.add('nav-open'); else if (open && dx < -70) document.body.classList.remove('nav-open'); tx = null;
  }, { passive: true });
})();

/* ================= KARNA SECTION PANEL =================
   Every section is linked to KARNA. "Ask KARNA" (page header / Overview cards)
   opens a side panel with a thread for THAT section. When KARNA is about to add
   something (from the panel or the main KARNA chat) it never writes silently:
   it asks "Can I add this in the <Section> section?" as a card in this panel,
   and only creates the record after you tap "Yes, add it". */
const KP_SEC = {
  today:         { kw: 'focus today',       chips: ['Plan the next 3 hours', 'What should I focus on today?'] },
  applications:  { kw: 'application deadline', chips: ['What is due this week?', 'Add internship application to Acme for backend intern by Friday'], bare: t => 'add application to ' + t },
  opportunities: { kw: 'application',       chips: ['Which opportunities should I apply to first?'] },
  outreach:      { kw: 'outreach email',    chips: ['Who is waiting for a first email?', 'Add contact Prof Rao at IIT Madras'], bare: t => 'add contact ' + t },
  projects:      { kw: 'project task',      chips: ['Which projects need attention?', 'Add project OPA landing page', 'Add task fix login bug to OPA landing page'], bare: t => 'add project ' + t },
  academics:     { kw: 'exam study',        chips: ['What should I study first?', 'Add study DBMS: revise normalization by 12 Oct'], bare: t => 'add study ' + t },
  sems:          { kw: 'exam study',        chips: ['Which exam is most at risk?'] },
  requests:      { kw: 'client request',    chips: ['Which client requests are open?', 'Add request from Ravi: needs a portfolio website'] },
  outbox:        { kw: 'email',             chips: ['What is waiting for my approval?'] },
  resume:        { kw: 'project',           chips: ['Which projects should go on my resume?'] },
  agent:         { kw: '',                  chips: ['What did KARNA do recently?'] },
  history:       { kw: '',                  chips: ['What did I finish this week?'] },
  profile:       { kw: '',                  chips: ['What is missing in my profile?'] },
  overview:      { kw: 'focus today',       chips: ['What should I do today?', 'Add project called my new idea'] }
};
const KP_SEC_OF = { application: 'applications', task: 'projects', project: 'projects', study: 'academics', request: 'requests', contact: 'outreach', mail: 'outbox' };
const KP = { open: false, sec: 'today', msgs: {}, props: {}, direct: false, busy: false, auto: false, dock: false, wide: false };
try { const pf = JSON.parse(localStorage.getItem('opa_kp_prefs') || '{}'); KP.auto = !!pf.auto; KP.dock = !!pf.dock; KP.wide = !!pf.wide; } catch (e) {}
function kpSavePrefs() { try { localStorage.setItem('opa_kp_prefs', JSON.stringify({ auto: KP.auto, dock: KP.dock, wide: KP.wide })); } catch (e) {} }
function kpApplyLayout() {
  document.documentElement.style.setProperty('--kpw', KP.wide ? '580px' : '400px');
  document.body.classList.toggle('kp-open', KP.open);
  document.body.classList.toggle('kp-docked', KP.dock);
}
function kpToggle(k) { KP[k] = !KP[k]; kpSavePrefs(); kpApplyLayout(); kpDrawShell(); }
const _kpExec = execAction;
function kpLabel(id) { const n = NAV.find(x => x.id === id); return n ? n.l : 'this page'; }
function kpThread(sec) { return KP.msgs[sec] || (KP.msgs[sec] = []); }
function kpEnsure() {
  if ($('kp')) return;
  const el = document.createElement('aside');
  el.id = 'kp'; el.className = 'kp'; el.setAttribute('role', 'complementary'); el.setAttribute('aria-label', 'KARNA panel');
  document.body.appendChild(el);
}
function kpOpen(sec) {
  kpEnsure();
  KP.sec = (sec && VIEWS[sec]) ? sec : (VIEWS[cur] ? cur : 'today');
  KP.open = true; $('kp').classList.add('on'); kpApplyLayout();
  kpDrawShell();
  setTimeout(() => { const i = $('kp-in'); if (i) i.focus(); }, 60);
}
function kpClose() { KP.open = false; const el = $('kp'); if (el) el.classList.remove('on'); kpApplyLayout(); }
function kpDrawShell() {
  const el = $('kp'); if (!el) return;
  const cfg = KP_SEC[KP.sec] || { chips: [] };
  el.innerHTML =
    '<div class="kp-h"><div class="kp-orb"></div><div class="kp-t"><b>KARNA</b><span>' + esc(kpLabel(KP.sec)) + ' section</span></div>' +
      '<button class="icon-btn kp-tg' + (KP.dock ? ' on' : '') + '" onclick="kpToggle(\'dock\')" aria-pressed="' + KP.dock + '" title="' + (KP.dock ? 'Docked beside the page. Click to float' : 'Floating. Click to dock beside the page') + '" aria-label="Dock panel">' + icon('dock', 17) + '</button>' +
      '<button class="icon-btn kp-tg' + (KP.wide ? ' on' : '') + '" onclick="kpToggle(\'wide\')" aria-pressed="' + KP.wide + '" title="Wide panel" aria-label="Wide panel">' + icon('wide', 17) + '</button>' +
      '<button class="icon-btn" onclick="kpClose()" aria-label="Close KARNA panel">' + icon('x', 18) + '</button></div>' +
    '<label class="kp-mode"><span><b>' + (KP.auto ? 'Add directly' : 'Ask before adding') + '</b><i>' + (KP.auto ? 'KARNA adds records right away' : 'You approve every add') + '</i></span>' +
      '<input type="checkbox" role="switch" ' + (KP.auto ? 'checked' : '') + ' onchange="kpToggle(\'auto\')" aria-label="Add directly without asking"><em class="kp-sw"></em></label>' +
    '<div class="kp-msgs" id="kp-msgs"></div>' +
    '<div class="kp-chips">' + cfg.chips.map(c => '<button onclick="kpSend(this.textContent)">' + esc(c) + '</button>').join('') + '</div>' +
    '<div class="kp-comp"><textarea id="kp-in" rows="1" placeholder="Ask about ' + esc(kpLabel(KP.sec)) + ' or tell me what to add" aria-label="Message KARNA"></textarea>' +
      '<button class="send" onclick="kpSend()" aria-label="Send">' + icon('up', 17) + '</button></div>';
  const inp = $('kp-in');
  inp.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); kpSend(); } });
  inp.addEventListener('input', () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 110) + 'px'; });
  kpDrawMsgs();
}
function kpPropHTML(id) {
  const p = KP.props[id]; if (!p) return '';
  const lbl = kpLabel(p.sec), d = p.a.data || {};
  if (p.status === 'done') return '<div class="kp-prop done"><div class="kp-q">' + fmtMsg(p.result) + '</div><div class="kp-act"><button class="btn ghost sm" onclick="switchTab(\'' + p.sec + '\');kpClose()">Open ' + esc(lbl) + '</button></div></div>';
  if (p.status === 'no') return '<div class="kp-prop no"><div class="kp-q">Okay, I did not add it to <b>' + esc(lbl) + '</b>.</div></div>';
  const rows = Object.entries(d).filter(([k, v]) => v != null && String(v).trim() !== '').map(([k, v]) => '<div><dt>' + esc(k.replace(/_/g, ' ')) + '</dt><dd>' + esc(v) + '</dd></div>').join('');
  return '<div class="kp-prop"><div class="kp-q">Can I add this in the <b>' + esc(lbl) + '</b> section?</div><dl>' + rows + '</dl>' +
    '<div class="kp-act"><button class="btn sm" onclick="kpConfirm(\'' + id + '\')">Yes, add it</button><button class="btn ghost sm" onclick="kpDecline(\'' + id + '\')">No</button></div></div>';
}
function kpDrawMsgs() {
  const box = $('kp-msgs'); if (!box) return;
  const th = kpThread(KP.sec);
  const welcome = '<div class="kp-m"><div class="kp-b">You are on <b>' + esc(kpLabel(KP.sec)) + '</b>. Ask me about it, or tell me what to add here. I will always check with you before adding anything.</div></div>';
  box.innerHTML = welcome + th.map(m => {
    if (m.role === 'prop') return '<div class="kp-m">' + kpPropHTML(m.id) + '</div>';
    if (m.typing) return '<div class="kp-m"><div class="kp-b"><span class="typing"><i></i><i></i><i></i></span></div></div>';
    return '<div class="kp-m' + (m.role === 'user' ? ' you' : '') + '"><div class="kp-b">' + fmtMsg(m.text) + '</div></div>';
  }).join('');
  box.scrollTop = box.scrollHeight;
}
function kpOffer(a) {
  const sec = KP_SEC_OF[a.type] || KP.sec;
  const id = 'p' + Date.now().toString(36) + Math.floor(Math.random() * 1000);
  KP.props[id] = { a, sec, status: 'pending' };
  kpThread(sec).push({ role: 'prop', id });
  kpOpen(sec);
  return 'Can I add this in the **' + kpLabel(sec) + '** section? I opened the KARNA panel on the right. Tap **Yes, add it** there to confirm.';
}
function kpConfirm(id) {
  const p = KP.props[id]; if (!p || p.status !== 'pending') return;
  let res;
  KP.direct = true;
  try { res = _kpExec(p.a); } catch (e) { res = 'I could not add that (' + e.message + ').'; } finally { KP.direct = false; }
  p.status = 'done'; p.result = res || 'Done.';
  try { render(); renderNav(); refreshCtx(); } catch (e) {}
  kpDrawMsgs();
}
function kpDecline(id) { const p = KP.props[id]; if (!p) return; p.status = 'no'; kpDrawMsgs(); }
execAction = function (a) {
  if (KP.direct || KP.auto || !a || !QC_TYPES.includes(a.type) || !a.data) return _kpExec(a);
  return kpOffer(a);
};
async function kpAnswer(t, sec) {
  const cfg = KP_SEC[sec] || {};
  const tagged = '[The user is on the ' + kpLabel(sec) + ' page] ' + t;
  if (BACKEND.ready) {
    try {
      const uid = await ensureUser();
      const res = await POST('/v1/jarvis/chat', { user_id: uid, message: tagged });
      if (res.tool_calls && res.tool_calls.length) { syncBackend(true).catch(() => {}); try { render(); renderNav(); } catch (e) {} }
      return res.reply || 'Done.';
    } catch (e) { /* fall through to local */ }
  }
  if (S.profile.groqKey) {
    try {
      const sys = 'You are KARNA inside OPAI, helping ' + (S.profile.name || 'the user') + ' on the ' + kpLabel(sec) + ' page. Be direct and brief. You cannot send emails. If the user asks to add something, reply in one short sentence and end with one line: ACTION: {"type":"<application|task|project|study|request|contact|mail>","data":{...}}. Today is ' + iso(0) + '.';
      const g = await groqChat([{ role: 'system', content: sys }, ...kpThread(sec).filter(m => m.text && !m.typing).slice(-8).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.text }))]);
      if (g) { const ex = extractAction(g); if (ex.action) { execAction(ex.action); return ex.text || 'I can add that. Please confirm in the card below.'; } return ex.text; }
    } catch (e) { /* fall through */ }
  }
  return jarvisReply((cfg.kw || '') + ' ' + t);
}
async function kpSend(text) {
  const inp = $('kp-in');
  const t = (text || (inp ? inp.value : '')).trim(); if (!t || KP.busy) return;
  if (inp) { inp.value = ''; inp.style.height = 'auto'; }
  let a = parseQuick(t);
  const cfg = KP_SEC[KP.sec] || {};
  if (!a && cfg.bare && t.length <= 60 && !/[?]/.test(t) && !/^(what|which|who|when|where|why|how|plan|show|list|help|draft|summar|tell|give|is|are|do|does|can)\b/i.test(t)) a = parseQuick(cfg.bare(t));
  const sec = a ? (KP_SEC_OF[a.type] || KP.sec) : KP.sec;
  kpThread(sec).push({ role: 'user', text: t });
  if (a && KP.auto) {
    let res; try { res = _kpExec(a); } catch (e) { res = 'I could not add that (' + e.message + ').'; }
    kpThread(sec).push({ role: 'ai', text: res || 'Done.' });
    try { render(); renderNav(); refreshCtx(); } catch (e) {}
    if (KP.open) kpDrawMsgs(); return;
  }
  if (a) { kpOffer(a); return; }
  const th = kpThread(sec); const typing = { role: 'ai', typing: true }; th.push(typing); KP.busy = true; kpDrawMsgs();
  let reply;
  try { reply = await kpAnswer(t, sec); } catch (e) { reply = 'Something went wrong (' + e.message + ').'; }
  KP.busy = false;
  const i = th.indexOf(typing); if (i > -1) th.splice(i, 1);
  th.push({ role: 'ai', text: reply });
  if (KP.open && KP.sec === sec) kpDrawMsgs();
}
function kpDecorate() {
  const v = $('view'); if (!v || cur === 'jarvis') return;
  const hd = v.querySelector('.head > div:last-child');
  if (hd && !hd.querySelector('.kp-ask')) {
    const b = document.createElement('button'); b.className = 'btn soft kp-ask'; b.title = 'Ask KARNA about this section';
    b.innerHTML = icon('spark', 15) + ' Ask KARNA'; b.onclick = () => kpOpen(cur); hd.insertBefore(b, hd.firstChild);
  }
  if (cur === 'overview') v.querySelectorAll('.panel-h').forEach(ph => {
    if (ph.querySelector('.kp-ask-s')) return;
    const h = ph.querySelector('h3'); if (!h) return;
    const n = NAV.find(x => x.l.toLowerCase() === h.textContent.trim().toLowerCase());
    if (!n || n.id === 'overview' || n.id === 'jarvis') return;
    const b = document.createElement('button'); b.className = 'kp-ask-s'; b.title = 'Ask KARNA about ' + n.l; b.setAttribute('aria-label', 'Ask KARNA about ' + n.l);
    b.innerHTML = icon('spark', 13); b.onclick = () => kpOpen(n.id); h.insertAdjacentElement('afterend', b);
  });
}
(function () {
  const _r = render; render = function (f) { _r(f); try { kpDecorate(); } catch (e) {} };
  const _s = switchTab; switchTab = function (n) { _s(n); if (KP.open) { KP.sec = VIEWS[cur] ? cur : KP.sec; kpDrawShell(); } };
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && KP.open && !$('overlay').classList.contains('on') && !$('palette').classList.contains('on')) kpClose(); });
})();

/* ===== Theme: auto / light / dark ===== */
const THEME_MODES = ['auto', 'light', 'dark'];
const THEME_ICON = { auto: 'monitor', light: 'sun', dark: 'moon' };
function getThemeMode() { try { const t = localStorage.getItem('opa_theme'); return THEME_MODES.includes(t) ? t : 'auto'; } catch (e) { return 'auto'; } }
function setTheme(m) {
  if (!THEME_MODES.includes(m)) m = 'auto';
  try { localStorage.setItem('opa_theme', m); } catch (e) {}
  if (m === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', m);
  themeDraw();
}
function themeCycle() { const m = getThemeMode(); setTheme(THEME_MODES[(THEME_MODES.indexOf(m) + 1) % 3]); }
function themeDraw() {
  const m = getThemeMode();
  const hb = $('theme-btn'); if (hb) { hb.innerHTML = icon(THEME_ICON[m], 18); hb.title = 'Theme: ' + m + ' (click to change)'; hb.setAttribute('aria-label', 'Theme: ' + m); }
  const seg = $('theme-seg'); if (seg) seg.innerHTML = THEME_MODES.map(x => '<button class="' + (x === m ? 'on' : '') + '" onclick="setTheme(\'' + x + '\')" aria-pressed="' + (x === m) + '">' + icon(THEME_ICON[x], 14) + x + '</button>').join('');
}
function themeInit() {
  const m = getThemeMode(); if (m !== 'auto') document.documentElement.setAttribute('data-theme', m);
  const bell = document.querySelector('.hdr .icon-btn[aria-label="Notifications"]');
  if (bell && !$('theme-btn')) { const b = document.createElement('button'); b.id = 'theme-btn'; b.className = 'icon-btn'; b.onclick = themeCycle; bell.parentNode.insertBefore(b, bell); }
  const foot = document.querySelector('.side-foot');
  if (foot && !$('theme-seg')) { const s = document.createElement('div'); s.id = 'theme-seg'; s.className = 'theme-seg'; s.setAttribute('role', 'group'); s.setAttribute('aria-label', 'Theme'); foot.insertBefore(s, foot.firstChild); }
  themeDraw();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', themeInit); else themeInit();


/* ===== KARNA main chat: Workspace / General scope ===== */
let KARNA_SCOPE = 'workspace';
try { if (localStorage.getItem('opa_karna_scope') === 'general') KARNA_SCOPE = 'general'; } catch (e) {}
function karnaScopeHTML() {
  const b = (v, l) => '<button class="' + (KARNA_SCOPE === v ? 'on' : '') + '" aria-pressed="' + (KARNA_SCOPE === v) + '" onclick="setKarnaScope(\'' + v + '\')">' + l + '</button>';
  return '<div class="scope-seg" role="group" aria-label="KARNA scope">' + b('workspace', 'Workspace') + b('general', 'General') + '</div>' +
    (KARNA_SCOPE === 'workspace' ? '<label class="scope-add" title="Add records without asking"><input type="checkbox" role="switch" ' + (KP.auto ? 'checked' : '') + ' onchange="kpToggle(\'auto\');render(true)" aria-label="Add directly"><em class="kp-sw"></em><span>Add directly</span></label>' : '');
}
function setKarnaScope(v) {
  KARNA_SCOPE = v === 'general' ? 'general' : 'workspace';
  try { localStorage.setItem('opa_karna_scope', KARNA_SCOPE); } catch (e) {}
  render(true);
}
async function generalSend(t) {
  const input = $('jv-input'); if (input) { input.value = ''; input.style.height = 'auto'; }
  const box = $('msgs'); const w = $('welcome'); if (w) w.remove();
  CHAT.push({ role: 'user', text: t }); box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'user', text: t }));
  box.insertAdjacentHTML('beforeend', '<div class="m" id="typing"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>');
  box.scrollTop = box.scrollHeight;
  let reply;
  const sys0 = 'You are KARNA, a friendly, knowledgeable general-purpose assistant chatting with ' + (S.profile.name || 'the user') + '. Answer any question helpfully and concisely (code, study help, ideas, writing, general knowledge). Reply in the language the user writes in. You have no access to their workspace in this mode; if they ask to add or change records, tell them to switch to Workspace. Today is ' + iso(0) + '.';
  if (BACKEND.ready) {
    try {
      const r = await POST('/v1/chat/general', { system: sys0, messages: CHAT.slice(-12).map(m => ({ role: m.role, content: m.text })) });
      reply = r.reply || 'No reply came back. Try again.';
    } catch (e) {
      if (S.profile.groqKey) { try { reply = (await groqChat([{ role: 'system', content: sys0 }, ...CHAT.slice(-12).map(m => ({ role: m.role, content: m.text }))])) || 'No reply came back. Try again.'; } catch (e2) { reply = 'Groq call failed (' + e2.message + ').'; } }
      else reply = 'General chat failed (' + e.message + ').';
    }
  } else if (!S.profile.groqKey) reply = 'General chat needs the backend connection or a Groq key (Profile, Groq). Until then, switch to Workspace for questions about your own data.';
  else {
    try {
      const sys = 'You are KARNA, a friendly, knowledgeable general-purpose assistant chatting with ' + (S.profile.name || 'the user') + '. Answer any question helpfully and concisely (code, study help, ideas, writing, general knowledge). Reply in the language the user writes in. You have no access to their workspace in this mode; if they ask to add or change records, tell them to switch to Workspace. Today is ' + iso(0) + '.';
      const msgs = [{ role: 'system', content: sys }, ...CHAT.slice(-12).map(m => ({ role: m.role, content: m.text }))];
      reply = (await groqChat(msgs)) || 'No reply came back. Try again.';
    } catch (e) { reply = 'Groq call failed (' + e.message + ').'; }
  }
  const ty = $('typing'); if (ty) ty.remove();
  CHAT.push({ role: 'assistant', text: reply });
  box.insertAdjacentHTML('beforeend', bubbleHTML({ role: 'assistant', text: reply }));
  box.scrollTop = box.scrollHeight;
}
(function () {
  const _js2 = jarvisSend;
  jarvisSend = function (text) {
    if (KARNA_SCOPE === 'general') { const inp = $('jv-input'); const t = (text || (inp ? inp.value : '')).trim(); if (!t) return; return generalSend(t); }
    return _js2(text);
  };
})();


/* ===== Review: about OPAI + your feedback ===== */
let REV_STARS = 0;
const REV_MODS = [
  ['KARNA', 'Chat copilot. Workspace mode knows your data and adds records (you approve). General mode answers anything.'],
  ['Today', 'One queue of what to do now, built from deadlines, exams and tasks.'],
  ['Applications & Opportunities', 'Track internships, research and hackathons, and score what is worth your time.'],
  ['Internships & Outbox', 'Draft internship emails to professors and clients. Nothing sends without your approval.'],
  ['Projects & Requests', 'Client asks turn into projects and tasks you can track.'],
  ['Academics & Exams', 'Exams, courses and study workflow with confidence-based revision.'],
  ['Resume Lab', 'Keep your resume and tailor it per application.'],
  ['Agent Console & History', 'See what KARNA did and a log of everything you approved.']
];
function viewReview() {
  S.reviews = S.reviews || [];
  const n = (a) => (a || []).length;
  const stats = [['Applications', n(S.applications)], ['Projects', n(S.projects)], ['Contacts', n(S.contacts)], ['Requests', n(S.requests)], ['Exams', n(S.academics)], ['History', n(S.history)]];
  const avg = S.reviews.length ? (S.reviews.reduce((t, r) => t + r.stars, 0) / S.reviews.length).toFixed(1) : null;
  const stars = (k, on) => Array.from({ length: 5 }, (_, i) => '<button type="button" class="rv-star ' + (i < k ? 'on' : '') + '" ' + (on ? 'onclick="revStar(' + (i + 1) + ')"' : 'tabindex="-1"') + ' aria-label="' + (i + 1) + ' star">' + icon('star', 22) + '</button>').join('');
  return head('Review', 'What OPAI is, what it can do, and how it is working for you.', '') +
    '<section class="panel rv-hero"><h2>OPAI, your operating agent</h2><p>OPAI keeps your applications, projects, exams and outreach in one place, and KARNA helps you run them. It acts, you approve: KARNA can prepare records and drafts, but adds, sends and applies wait for your yes.</p>' +
    '<div class="rv-stats">' + stats.map(x => '<div><b>' + x[1] + '</b><span>' + x[0] + '</span></div>').join('') + '</div></section>' +
    '<div class="grid2">' + REV_MODS.map(m => '<section class="panel rv-mod"><h3>' + esc(m[0]) + '</h3><p>' + esc(m[1]) + '</p></section>').join('') + '</div>' +
    revShape() +
    '<section class="panel rv-form"><h3>Rate OPAI' + (avg ? ' <span class="pill good">' + avg + ' / 5 avg</span>' : '') + '</h3><div class="rv-stars" id="rv-stars">' + stars(REV_STARS, true) + '</div>' +
    '<div class="field"><label for="rv-text">What works, what should change?</label><textarea id="rv-text" rows="3" placeholder="Your feedback on OPAI"></textarea></div>' +
    '<button class="btn" onclick="revSubmit()">Save review</button></section>' +
    (S.reviews.length ? '<section class="panel"><h3>Your reviews</h3>' + S.reviews.slice().reverse().map(r => '<div class="rv-item"><div class="rv-stars sm">' + stars(r.stars, false) + '<time>' + new Date(r.at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + '</time></div>' + (r.text ? '<p>' + esc(r.text) + '</p>' : '') + '</div>').join('') + '</section>' : '');
}
function revStar(k) {
  REV_STARS = k; const el = $('rv-stars'); if (!el) return;
  el.querySelectorAll('.rv-star').forEach((b, i) => b.classList.toggle('on', i < k));
}
function revSubmit() {
  const t = ($('rv-text') || {}).value || '';
  if (!REV_STARS) { toast('Pick a star rating first', true); return; }
  S.reviews = S.reviews || []; S.reviews.push({ stars: REV_STARS, text: t.trim(), at: new Date().toISOString() });
  REV_STARS = 0; save(); render(true); toast('Review saved');
}

/* ===== Review: Shape OPAI (suggest + roadmap + what's new in one section) ===== */
let REV_TAB = 'suggest';
const REV_CATS = ['Feature idea', 'Bug', 'UI / Design', 'KARNA answers', 'Other'];
const REV_PAGES = ['Any page', 'KARNA', 'Today', 'Applications', 'Internships', 'Projects', 'Academics', 'Requests', 'Outbox', 'Resume'];
const REV_ROAD = [
  ['gmail', 'Gmail sending (OAuth)', 'Approve in Outbox and the email really sends. Today approving only marks it as sent.', 'Planned'],
  ['replies', 'Reply tracking', 'Internships moves a mail to Replied on its own and reminds you to follow up.', 'Planned'],
  ['peritem', 'Ask KARNA on any item', 'Click a project or application and ask KARNA about just that one.', 'Next'],
  ['weekly', 'Weekly summary', 'What you finished, what is pending, what needs attention this week.', 'Next'],
  ['voice', 'Voice input for KARNA', 'Speak your request instead of typing.', 'Idea'],
  ['rag', 'RAG over your notes', 'KARNA answers from your own documents and resume.', 'Planned']
];
const REV_LOG = [
  ['Sep 2026', 'Review section', 'About OPAI, ratings, and this Shape OPAI area.'],
  ['Sep 2026', 'Internships', 'Outreach renamed to Internships, with an explainer and 4 sample emails.'],
  ['Sep 2026', 'KARNA modes', 'Workspace and General chat, plus Ask before adding / Add directly.'],
  ['Sep 2026', 'Ask KARNA panel', 'Every section has its own KARNA panel, dock and wide options.'],
  ['Sep 2026', 'Theme', 'Auto, Light and Dark theme toggle.']
];
function revShape() {
  S.ideas = S.ideas || []; S.rvVotes = S.rvVotes || {};
  const tabs = [['suggest', 'Suggest'], ['road', 'Roadmap'], ['new', 'What\u2019s new']];
  let body = '';
  if (REV_TAB === 'suggest') {
    body = '<div class="rv-row"><div class="field"><label for="rv-cat">Type</label><select id="rv-cat">' + REV_CATS.map(c => '<option>' + c + '</option>').join('') + '</select></div>' +
      '<div class="field"><label for="rv-pg">Which page?</label><select id="rv-pg">' + REV_PAGES.map(c => '<option>' + c + '</option>').join('') + '</select></div></div>' +
      '<div class="field"><label for="rv-idea">Your suggestion</label><textarea id="rv-idea" rows="3" placeholder="What should OPAI do, fix or change?"></textarea></div>' +
      '<button class="btn" onclick="revIdeaAdd()">Submit suggestion</button>' +
      (S.ideas.length ? '<div class="rv-list">' + S.ideas.slice().sort((a, b) => b.votes - a.votes).map(i => '<div class="rv-item rv-idea"><button class="rv-up ' + (i.mine ? 'on' : '') + '" onclick="revIdeaVote(\'' + i.id + '\')" aria-label="Upvote">\u25B2<b>' + i.votes + '</b></button><div><div class="rv-tags"><span class="pill">' + esc(i.cat) + '</span><span class="pill">' + esc(i.page) + '</span><span class="pill ' + (i.status === 'Done' ? 'good' : '') + '">' + i.status + '</span></div><p>' + esc(i.text) + '</p></div><button class="btn ghost sm" onclick="revIdeaStatus(\'' + i.id + '\')">' + (i.status === 'New' ? 'Mark planned' : i.status === 'Planned' ? 'Mark done' : 'Reopen') + '</button></div>').join('') + '</div>' : '<div class="row-s" style="margin-top:12px">No suggestions yet. Yours will show here and are saved on this device.</div>');
  } else if (REV_TAB === 'road') {
    body = '<div class="rv-list">' + REV_ROAD.map(r => '<div class="rv-item rv-idea"><button class="rv-up ' + (S.rvVotes[r[0]] ? 'on' : '') + '" onclick="revRoadVote(\'' + r[0] + '\')" aria-label="I want this">\u25B2<b>' + (S.rvVotes[r[0]] ? 1 : 0) + '</b></button><div><div class="rv-tags"><span class="pill ' + (r[3] === 'Next' ? 'good' : '') + '">' + r[3] + '</span></div><h4>' + esc(r[1]) + '</h4><p>' + esc(r[2]) + '</p></div></div>').join('') + '</div><div class="row-s" style="margin-top:10px">Tap the arrow on what you want first.</div>';
  } else {
    body = '<div class="rv-list">' + REV_LOG.map(l => '<div class="rv-item"><div class="rv-tags"><time>' + l[0] + '</time><b>' + esc(l[1]) + '</b></div><p>' + esc(l[2]) + '</p></div>').join('') + '</div>';
  }
  return '<section class="panel rv-form"><h3>Shape OPAI</h3><div class="row-s" style="margin-bottom:10px">Suggest changes, see what is coming, and what shipped recently.</div>' +
    '<div class="rv-tabs" role="tablist">' + tabs.map(t => '<button role="tab" class="' + (REV_TAB === t[0] ? 'on' : '') + '" onclick="revTab(\'' + t[0] + '\')">' + t[1] + '</button>').join('') + '</div>' + body + '</section>';
}
function revTab(t) { REV_TAB = t; render(true); }
function revIdeaAdd() {
  const t = (($('rv-idea') || {}).value || '').trim(); if (!t) { toast('Write your suggestion first', true); return; }
  S.ideas = S.ideas || [];
  S.ideas.push({ id: 'i' + Date.now(), cat: ($('rv-cat') || {}).value || 'Other', page: ($('rv-pg') || {}).value || 'Any page', text: t, votes: 1, mine: true, status: 'New', at: new Date().toISOString() });
  save(); render(true); toast('Suggestion saved');
}
function revIdeaVote(id) { const i = (S.ideas || []).find(x => x.id === id); if (!i) return; i.mine = !i.mine; i.votes = Math.max(0, i.votes + (i.mine ? 1 : -1)); save(); render(true); }
function revIdeaStatus(id) { const i = (S.ideas || []).find(x => x.id === id); if (!i) return; i.status = i.status === 'New' ? 'Planned' : i.status === 'Planned' ? 'Done' : 'New'; save(); render(true); }
function revRoadVote(k) { S.rvVotes = S.rvVotes || {}; S.rvVotes[k] = !S.rvVotes[k]; save(); render(true); }


/* ===== Internships: explainer + demo emails ===== */
const DEMO_MAILS = [
  { st: 'Sent', to: 'Prof. Anita Rao <anita.rao@demo-iitm.example>', org: 'IIT Madras, Dept. of CSE', on: '3 days ago', subj: 'Summer research internship: retrieval-augmented QA',
    body: 'Dear Prof. Rao,\n\nI am a B.Tech Computer Science student at JNTU. I read your recent paper on retrieval-augmented question answering and built a small RAG prototype inspired by it (link in my resume).\n\nI would like to apply for a summer research internship in your group. I can contribute on evaluation, data cleaning and experiments, and I am comfortable with Python, FastAPI and LLM APIs.\n\nMay I share my resume and a one-page project note?\n\nThank you for your time,\nTiru' },
  { st: 'Replied', to: 'Rahul Mehta <rahul@demo-startup.example>', org: 'Demo Startup, founder', on: 'Yesterday', subj: 'Re: Frontend / AI engineering internship',
    body: 'Hi Tiru,\n\nThanks for reaching out. Your dashboard project looks good. Can you do a 20 minute call on Thursday at 4 PM IST? We are looking for someone who can ship UI quickly and wire it to LLM APIs.\n\nRahul' },
  { st: 'Drafted', to: 'Dr. Suresh Kumar <s.kumar@demo-iith.example>', org: 'IIT Hyderabad, Dept. of AI', on: 'Today', subj: 'Internship enquiry: LLM evaluation',
    body: 'Dear Dr. Kumar,\n\nI am writing to ask if your lab has openings for an undergraduate intern on LLM evaluation. I have built an AI agent dashboard with tool calling and an approval flow, and I would like to learn from your group.\n\nCould I send my resume for your consideration?\n\nRegards,\nTiru' },
  { st: 'Follow-up due', to: 'Priya Nair <priya@demo-labs.example>', org: 'Demo Labs, recruiter', on: '7 days ago', subj: 'Following up: AI intern application',
    body: 'Hi Priya,\n\nA quick follow-up on my application for the AI intern role. Since my last email I have added a RAG demo to my portfolio. Happy to share it or answer any questions.\n\nThanks,\nTiru' }
];
function internIntroHTML() {
  return '<section class="panel in-intro"><h3>Internships: what we are building here</h3>' +
    '<p>This section is the internship pipeline of OPAI. We were working on turning cold, scattered emailing into one tracked flow: find the right person, draft a good email, approve it, send it, and follow up. Everything is prepared by KARNA and nothing goes out without your approval.</p>' +
    '<div class="in-steps">' +
    [['1. Find people', 'Add a professor, founder or recruiter by hand, or pull from the IIT faculty database below. Tags are matched against your profile skills so the best fits show first.'],
     ['2. Draft', 'Draft email creates an item in Outbox, written from your profile, projects and highlight. You can edit it before anything else happens.'],
     ['3. Approve and send', 'You review the draft in Outbox and approve. Gmail sending through OAuth is planned; for now approving marks it as sent.'],
     ['4. Follow up', 'After a week with no reply, the contact shows Draft follow-up. Status moves Not started, Drafted, Sent, then Replied.']]
      .map(x => '<div><b>' + x[0] + '</b><span>' + x[1] + '</span></div>').join('') + '</div>' +
    '<p class="in-note"><b>Ask KARNA:</b> try "Add contact Prof Rao at IIT Madras" or "Who is waiting for a first email?". <b>Coming next:</b> Gmail OAuth sending, reply tracking, and RAG so drafts cite the professor\'s actual papers.</p></section>';
}
function demoMailsHTML() {
  let hide = false; try { hide = localStorage.getItem('opa_hide_demo_mail') === '1'; } catch (e) {}
  if (hide) return '<div class="in-demo-off"><button class="btn ghost sm" onclick="demoMailsToggle()">Show demo emails</button></div>';
  const tone = { Sent: '', Replied: 'good', Drafted: '', 'Follow-up due': 'warn' };
  return '<section class="panel in-demo"><div class="in-demo-h"><h3>Demo emails <span class="pill">Sample data</span></h3><button class="btn ghost sm" onclick="demoMailsToggle()">Hide</button></div>' +
    '<p class="row-s">These are dummy emails to show how the section looks once you start sending. The names and addresses are fake and they are not stored in your data.</p>' +
    DEMO_MAILS.map(m => '<details class="in-mail"><summary><span class="pill ' + (tone[m.st] || '') + '">' + m.st + '</span><b>' + esc(m.subj) + '</b><em>' + esc(m.on) + '</em></summary>' +
      '<div class="in-mail-b"><div class="row-s">To: ' + esc(m.to) + ' &middot; ' + esc(m.org) + '</div><pre>' + esc(m.body) + '</pre></div></details>').join('') + '</section>';
}
function demoMailsToggle() {
  let h = false; try { h = localStorage.getItem('opa_hide_demo_mail') === '1'; localStorage.setItem('opa_hide_demo_mail', h ? '0' : '1'); } catch (e) {}
  render(true);
}
