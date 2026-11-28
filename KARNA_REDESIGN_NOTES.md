# KARNA redesign (chat page + backend)

## Frontend: `frontend/super-chat.html` (copy for FastAPI in `backend/static/super-chat.html`)
- Rebuilt in the cream design used by landing/login/onboarding (Newsreader + Plus Jakarta Sans, black primary).
- Self-contained: no longer loads `opai-shell.js`, `opai-cream.css`, `opai-redesign.css`, `opai-notion.js`, `karna-shader.js`, `karna-motion.*`
  (those were re-theming a dark page and caused the clashing look). `karna-*.js/css` files are untouched and unused by this page.
- Header: app menu (replaces the shared sidebar on this page), Workspace/General switch, status, New / History / Memory / Knowledge / Export / Guide.
- Empty state is personalised from `GET /v1/karna/briefing`: greeting, "needs attention" cards (drafts, deadlines, exams, today), starter prompts.
- Answers: clean prose (no card), citations + source chips, tables, code with copy, word-by-word reveal, follow-up chips under the latest answer.
- Progress phases while waiting; Stop button; send button disabled until there is text.
- History drawer: search + Today/Yesterday/Last 7 days grouping. Memory, Knowledge and approval gate restyled; logic unchanged.
- Mobile: single-column cards, compact header, full-width drawers, menu holds Export/Guide.
- Onboarding redirect that the shell used to do is now done by the page itself.

## Backend
- `backend/karna_api.py` (registered in `main.py`)
  - `GET /v1/karna/briefing?user_id=`: greeting, cards, starters, stats from the user's own data.
  - `POST /v1/jarvis/chat/stream`: same request/answer as `/v1/jarvis/chat`, delivered as SSE with progress phases and `followups`.
    The page falls back to `/v1/jarvis/chat` if this route is missing.
- `backend/agent/karna_ux.py`: pure helpers `briefing()` and `followups()`.
- `backend/tests/test_karna_ux.py`: 6 tests.
- `frontend/sw.js` cache `opai-v88`, `backend/static/sw.js` `opai-v15`.

Deploy: backend first (new routes), then frontend. Nothing else changes.
