# New landing page (Nov 27, 2026)

- `frontend/home.html` is the new landing page (single file, no build step, no Tailwind CDN).
- `frontend/vercel.json`: `/` now rewrites to `/home.html` (was `/newdemotiru/index.html`). Roll back by restoring that one line.
- Images: `frontend/assets/landing/*.webp` (your 13 pictures, resized to <=1400px, ~1.1 MB total, corner sparkle trimmed).
- Design tokens follow the Stitch DESIGN.md (Newsreader / Plus Jakarta Sans / Space Grotesk, warm cream + jewel accents).
- Links: Get started -> /signup, Log in -> /login, plus /privacy /terms /feedback.html.
- Old `newdemotiru/` is untouched and still reachable at /newdemotiru/.

## Full app restyle (Nov 27, 2026)
- New `frontend/opai-cream.css` re-themes every app page (tokens, sidebar, buttons, cards, KARNA chat). It is linked last on each app page and re-appended by `opai-shell.js` after `opai-redesign.css`.
- The app now defaults to LIGHT (was dark): `opai-ux.js` default + `super-chat.html` `data-theme`. Users who chose dark keep a warm-dark variant.
- The WebGL shader background script was removed from the app pages (flat cream canvas).
- `sw.js` cache bumped to v75.
- Not restyled: `admin.html` (internal), `agent-console.html` (Tailwind-CDN demo page; unverified here), `today-legacy.html`.
- Roll back: delete the `opai-cream` <link> lines and the one line in `opai-shell.js`.

## Notion-style app UI (Nov 27, 2026)
- `opai-cream.css` now ends with a NOTION LAYER: white canvas, Notion text/greys, system sans type, 900px centred page column, 40px bold titles, Notion tag colours, callouts, underline view-tabs, filter chips, table-style rows (Hackathons), blue primary buttons.
- `opai-notion.js` (loaded by `opai-shell.js`): emoji nav icons, Favorites/Workspace/More groups, sticky 45px breadcrumb bar (page icon + title, theme toggle), big page icon above each page title. Decoration only.
- Dark mode uses Notion's dark palette (#191919 / #202020).
- Roll back to the earlier cream look: delete the NOTION LAYER block at the end of `opai-cream.css` and the opai-notion.js line in `opai-shell.js`.

## Today sprints as a Notion database (Table | Gallery)
- `frontend/opai-cream.css`: block "Today sprints as a Notion database" at the end. Scoped to `#list`; no markup or logic changes in today.html.
- `frontend/opai-notion.js`: last IIFE adds the Table/Gallery switcher (remembered in localStorage `opai_nt_today_view`).
- Cache-bust bumped: `opai-cream.css?v=6`, `opai-notion.js?v=5`.
- Undo: delete that CSS block and the last IIFE in opai-notion.js.

## Opportunities / Your applications as Notion table rows
- `frontend/opai-cream.css`: block "Opportunities / Your applications as a Notion database" (CSS only; `.opp` rows are flat rows with status dot, Notion tag chips, hover-reveal actions).
- Cache-bust: `opai-cream.css?v=7`. Undo: delete that block.

## Projects as a Notion board
- `frontend/projects.html`: new `board()` function; `render()` now shows ALL projects grouped into Planning / In progress / Due soon / Done columns (same `pcard` markup, so checkboxes, add-task and suggestions are unchanged). The old "More projects" fold is removed. Original backed up logic: replace the `board(...)` call with the old `<div class="grid">` list.
- `frontend/opai-cream.css`: "Projects as a Notion board" block + small fixes (progress labels no longer blue, card titles plain).
- Cache-bust: `opai-cream.css?v=10`.

## Dark-mode pass
- `frontend/opai-cream.css` end block "dark-mode fixes": callouts/notes/banners (were light grey with light text), warn pills, coral buttons, opportunity chips.
- Checked in dark: Plan, Academics, Resume Lab, Review, Profile, Briefs, DSA, Coding, Feedback, KARNA, Opportunities, Projects, Today, Internship. Cache-bust `opai-cream.css?v=11`.

## Plan page (was "Coming Soon")
- `frontend/plan.html` is now a read-only week board (Overdue | Today | Tomorrow | next days | Later | No deadline), built from `GET /v1/today` only (items + later + completed_today). No backend changes.
- Backend: `today_engine.build()` now also returns `week` (all open items, max 60: kind, ref_id, title, minutes, due, days, category, link, planned). Additive only; Today ignores it. Test: `test_today_exposes_week_list_with_day_offsets`. Plan uses `week` when present and falls back to items+later on an older backend. The engine only includes tasks due within 14 days.
- Roll back: restore the previous Coming Soon page from the older zip (v5).

## Plan: reschedule tasks (drag or "Move to…")
- `frontend/plan.html` only. Task cards can be dragged to a LATER day column, or moved with the "Move to…" menu (works on touch). It calls the existing `POST /v1/today/act` with `op: snooze, days: N` (1-14, forward only; shifts the task's due date). No backend change.
- Only `kind=task` is movable. Study blocks, applications and academics stay fixed (their dates mean something else).
- Not verified: auto-scroll of the board edge while dragging to far columns (Move to… covers those).

## FINAL cream/Notion build (Nov 27, 2026)
- Consolidated v8: Notion layer, Today Table/Gallery, Opportunities rows, Projects board, dark-mode pass, Plan week board + drag/"Move to…".
- Cache-bust: `opai-cream.css?v=12`, `opai-notion.js?v=6`, `sw.js` cache `opai-v80`.
- Deploy order: backend (`today_engine.py` with `week`) first, then frontend.

## AURORA 2026 (Nov 27, 2026) — replaces the Notion look
- `frontend/opai-cream.css` end blocks "AURORA 2026" + "Aurora fixes": new palette (Cloud Dancer canvas, Signal Violet accent #5B4BF5, Lime Pulse highlight; dark = Ink Night #0C0E13), aurora background, rounded 22px surfaces, pill buttons/tabs, gradient progress bars.
- Navigation: left sidebar, breadcrumb bar and page cover/icon are hidden. `frontend/opai-notion.js` last block builds a floating dock (Today, KARNA, Plan, Internship, Projects, All sections sheet, Search), a top-left page chip and top-right theme/profile tools. It reads links from the existing sidebar, so NAV stays in `opai-shell.js`. On KARNA chat the dock shrinks to one corner button.
- Landing page, login, signup untouched. Cache-bust: `opai-cream.css?v=15`, `opai-notion.js?v=7`, `sw.js` opai-v81.
- Undo: delete both AURORA CSS blocks and the last block in opai-notion.js.

## GLASS 2026 (Nov 27, 2026) — app matched to landing.html
- Tokens copied from landing's Tailwind theme: surface #F9F9FF, primary #6B34D6 → #8452F0 gradient, indigo glow shadows, lime #CAF165, on-surface #141B2B. Dark = deep indigo #0B0D1A.
- `opai-cream.css` end block "GLASS 2026": frosted cards/columns/inputs (backdrop blur 20px), gradient pill buttons and active tabs, Geist type, full-width frosted header (logo + OPAI + page chip) like landing, glass dock.
- `opai-notion.js`: loads Geist + Material Symbols (same as landing); dock icons are Material Symbols with emoji fallback.
- Cache-bust: `opai-cream.css?v=16`, `opai-notion.js?v=9`, `sw.js` opai-v82. Landing untouched.
- Undo: delete the GLASS 2026 block (Aurora layer remains).

## LANDING MATCH (Nov 27, 2026) — app uses the real landing look
- From the landing hero: cream #FAF8F4 canvas with peach/lavender glow, near-black buttons (#1B1917), peach highlight (#FFCF99), Newsreader serif headlines, Inter body, Space Grotesk labels/buttons. Warm dark = #171513.
- `opai-cream.css` end blocks "LANDING MATCH" + fixes override the earlier Aurora/Glass colours (violet is gone). Header is a floating rounded bar like the landing nav; dock and sheet use the same warm glass.
- `opai-notion.js` font link now loads Inter, Newsreader, Space Grotesk, Material Symbols.
- Cache-bust: `opai-cream.css?v=19`, `opai-notion.js?v=10`, `sw.js` opai-v83.
- Undo to the glass-violet look: delete the "LANDING MATCH" block and the rules after it.

## Backend: security gate + metering + billing (Nov 28, 2026)
- New: `backend/security_gate.py`, `metering.py`, `billing_api.py`; tables `usage_ledger`, `user_plans`, `billing_orders` (database.py, new tables only).
- Hooks: `agent/llm.py` (_create / stream_chat), `auth_guard.py` (sets the caller, prod default `enforce`), `main.py` (startup gate, router).
- Frontend: Profile page "AI usage" card (`profile.html`), sw cache opai-v84.
- Tests: `tests/test_security_gate.py`, `test_metering.py`, `test_billing.py` (32 new). Full suite: 560 passed; the 24 failures + 16 errors were already failing before this change (DSA tests, landing copy tests, 2 files importing a missing `DsaTopic`).

## Upgrade UI + Postgres migration (Nov 28, 2026)
- Profile page: plan cards + "Continue to payment" (Cashfree hosted checkout) + payment-return confirmation; new `GET /v1/billing/order`.
- `backend/scripts/migrate_sqlite_to_postgres.py` (+ `tests/test_migrate_pg.py`, runs when OPAI_TEST_PG is set). Verified on a populated DB: 44 tables, 2402 rows, 32,795 cells, 0 mismatches; orphan row skipped and reported; rerun changes nothing.
- Backend suite on Postgres 16 = same result as SQLite.
