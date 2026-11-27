# New landing page (Nov 27, 2026)

- `frontend/home.html` is the new landing page (single file, no build step, no Tailwind CDN).
- `frontend/vercel.json`: `/` now rewrites to `/home.html` (was `/newdemotiru/index.html`). Roll back by restoring that one line.
- Images: `frontend/assets/landing/*.webp` (your 13 pictures, resized to <=1400px, ~1.1 MB total, corner sparkle trimmed).
- Design tokens follow the Stitch DESIGN.md (Newsreader / Plus Jakarta Sans / Space Grotesk, warm cream + jewel accents).
- Links: Get started -> /signup, Log in -> /login, plus /privacy /terms /feedback.html.
- Old `newdemotiru/` is untouched and still reachable at /newdemotiru/.
