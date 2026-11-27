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
