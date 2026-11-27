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
