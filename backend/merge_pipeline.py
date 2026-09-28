#!/usr/bin/env python3
"""
Merges the pipeline-style Study Workflow canvas into OPAI's app.html.

Usage:   python merge_pipeline.py path/to/app.html
         (py merge_pipeline.py app.html on Windows)

What it does (all edits are anchored, and the script aborts without writing
anything if any anchor is missing):
  1. Adds a live "Pipeline" view driven by STUDY_WORKFLOW.tasks: blocks as nodes
     (done / active / queued), curved SVG connectors (animated flow into the
     active block), a running pill, entrance animation after "Generate workflow",
     and an activity log. Click a block to toggle it done.
  2. Keeps your editable 1 Month / 1 Year boards (drag, connect, prompt->boards);
     the tab row now has Pipeline | 1 Month | 1 Year.
  3. Logs "Study ..." events to History so the activity log has real entries.
A backup is saved next to the file as app.html.bak.
"""
import re
import shutil
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "app.html"
src = open(path, encoding="utf-8").read()

if "spcPipelineHTML" in src:
    print("Already merged - nothing to do.")
    sys.exit(0)

CSS = r"""/* ---------- Pipeline canvas (live Study Workflow) ---------- */
.pl-pill{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11.5px;font-weight:600;padding:5px 12px 5px 9px;border-radius:999px;background:var(--good-soft);color:var(--good)}
.pl-pill i{width:7px;height:7px;border-radius:50%;background:currentColor;animation:plBlip 1.4s ease-in-out infinite}
.pl-pill.busy{background:var(--warn-soft);color:var(--warn)}
@keyframes plBlip{0%,100%{opacity:1}50%{opacity:.3}}
.pl-canvas{border:1px solid var(--line);border-radius:12px;background:var(--bg);overflow-x:auto;overflow-y:hidden;position:relative;
  background-image:radial-gradient(var(--line) 1px,transparent 1px);background-size:22px 22px}
.pl-node{position:absolute;text-align:left;display:flex;flex-direction:column;gap:4px;padding:11px 13px;border-radius:12px;
  border:1.5px solid var(--line-2);background:var(--surface-2);color:var(--ink);cursor:pointer;font:inherit;
  transition:transform .15s,border-color .15s,box-shadow .15s,opacity .15s}
.pl-node:hover{transform:translateY(-2px)}
.pl-node:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pl-top{display:flex;justify-content:space-between;align-items:center}
.pl-n{font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}
.pl-st{font-family:var(--mono);font-size:10px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:999px;background:var(--bg);color:var(--ink-2)}
.pl-node b{font-size:13.5px;font-weight:650;line-height:1.25}
.pl-node small{font-size:11.5px;color:var(--ink-2);line-height:1.35;flex:1;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.pl-node em{font-style:normal;font-family:var(--mono);font-size:10.5px;color:var(--ink-3)}
.pl-done{border-color:var(--good)}
.pl-done b{color:var(--ink-2);text-decoration:line-through;text-decoration-color:var(--ink-3)}
.pl-done .pl-st{background:var(--good-soft);color:var(--good)}
.pl-active{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.pl-active .pl-st{background:var(--accent);color:var(--on-accent,var(--bg))}
.pl-queued{border-style:dashed;opacity:.8}
.pl-gen{animation:plIn .42s cubic-bezier(.2,.8,.2,1) both,plGlow 1.8s ease .3s both}
@keyframes plIn{from{opacity:0;transform:translateY(14px) scale(.9)}to{opacity:1;transform:none}}
@keyframes plGlow{0%,100%{box-shadow:0 0 0 0 transparent}40%{box-shadow:0 0 0 5px var(--warn-soft)}}
.pl-e{fill:none;stroke:var(--line-2);stroke-width:2}
.pl-e-done{stroke:var(--good)}
.pl-flow{stroke:var(--accent);stroke-dasharray:7 7;animation:plDash 1s linear infinite}
@keyframes plDash{to{stroke-dashoffset:-14}}
.pl-hint{font-size:12.5px;color:var(--ink-3)}
.pl-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink-2)}
.pl-legend span{display:inline-flex;align-items:center;gap:6px}
.pl-legend i{width:9px;height:9px;border-radius:3px;border:1.5px solid var(--line-2)}
.pl-legend i.d{border-color:var(--good);background:var(--good-soft)}
.pl-legend i.a{border-color:var(--accent);background:var(--accent-soft)}
.pl-legend i.q{border-style:dashed}
.pl-log{border:1px solid var(--line);border-radius:12px;padding:12px 16px}
.pl-log h4{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0 0 6px}
.pl-log-r{display:flex;gap:12px;padding:4px 0;font-size:12.5px;color:var(--ink-2)}
.pl-log-r time{font-family:var(--mono);font-size:11px;color:var(--ink-3);width:64px;flex-shrink:0;padding-top:1px}

"""

JS = r"""/* ---- Pipeline view: live, driven by STUDY_WORKFLOW.tasks ---- */
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
function spcBoardHTML() {"""

problems = []


def once(text, old, new, label):
    if text.count(old) != 1:
        problems.append("%s (found %d, expected 1)" % (label, text.count(old)))
        return text
    return text.replace(old, new)


def once_re(text, pattern, new, label):
    m = re.findall(pattern, text)
    if len(m) != 1:
        problems.append("%s (found %d, expected 1)" % (label, len(m)))
        return text
    return re.sub(pattern, lambda _m: new, text)


s = src
s = once(s, "/* ---------- Floating calendar ---------- */", CSS + "/* ---------- Floating calendar ---------- */", "CSS anchor")
s = once(s, "function spcSetMode(m) { SPC_MODE = m; SPC_LINK_FROM = null; render(true); }",
         "function spcSetMode(m) { if (m === 'pipeline') { SPC_VIEW = 'pipeline'; } else { SPC_VIEW = 'board'; SPC_MODE = m; } SPC_LINK_FROM = null; render(true); }",
         "spcSetMode")
s = once(s, "function spcRenderHTML() {", JS, "spcRenderHTML")

# NOTE: the short anchor '<div class="spc-tabs" role="tablist">' + is no
# longer safe on its own once the JS block above has been inserted, because
# that JS block's own plTabs() function contains the exact same fragment.
# Anchoring on the following line too (unique to the original Study Plan
# Canvas tab row) disambiguates the two.
BOARD_TABS_OLD = ("'<div class=\"spc-tabs\" role=\"tablist\">' +\n"
                  "        '<button role=\"tab\" aria-selected=\"' + (SPC_MODE === 'month')")
BOARD_TABS_NEW = ("'<div class=\"spc-tabs\" role=\"tablist\">' + "
                  "'<button role=\"tab\" aria-selected=\"false\" onclick=\"spcSetMode(\\'pipeline\\')\">Pipeline</button>' +\n"
                  "        '<button role=\"tab\" aria-selected=\"' + (SPC_MODE === 'month')")
s = once(s, BOARD_TABS_OLD, BOARD_TABS_NEW, "board tabs")

s = once(s, "STUDY_WORKFLOW.lastUpdated = 'Progress updated';",
         "STUDY_WORKFLOW.lastUpdated = 'Progress updated'; log('Study block ' + (t.done ? 'completed' : 'reopened') + ': ' + t.title); save();",
         "toggleWorkflowTask log")
s = once(s, "WORKFLOW_BUSY = false; render(true); return;",
         "WORKFLOW_BUSY = false; PL_FRESH = true; log('Study plan generated: ' + STUDY_WORKFLOW.tasks.length + ' blocks for ' + STUDY_WORKFLOW.subject); save(); render(true); return;",
         "generate (SEMS path)")
s = once_re(s, r"WORKFLOW_BUSY = false;\s*render\(true\);\s*\}\s*function runQuickAction",
            "WORKFLOW_BUSY = false;\n  PL_FRESH = true; log('Study plan generated: ' + STUDY_WORKFLOW.tasks.length + ' blocks for ' + STUDY_WORKFLOW.subject); save();\n  render(true);\n}\nfunction runQuickAction",
            "generate (local path)")

if problems:
    print("ABORTED - nothing written. Anchors that did not match:")
    for p in problems:
        print("  -", p)
    sys.exit(1)

shutil.copyfile(path, path + ".bak")
open(path, "w", encoding="utf-8").write(s)
print("Merged OK. Backup: " + path + ".bak")