# v7
- One dark theme everywhere (#0e0e10 / #131315): landing, login (glass skin removed), KARNA, pages. Shared layer: `frontend/opai-shared.css`.
- Mobile: side padding 20 -> 12px, smaller bubbles, compact header, full-width composer (KARNA).
- Guide: header button, `/guide` command, floating "?" on other pages, nav tooltips. Answers "applications kahan hai?" / "exam ela add cheyali?" locally in English, Hinglish, Tenglish (`frontend/guide.js`).
- Language option in KARNA (English / Hinglish / Tenglish): applies to General mode, file analysis, Guide, voice input language. Workspace-mode replies are not yet language-switched (backend change needed).
- Hinglish capture (`backend/agent/capture.py`): "OS ka exam hai 20 Nov ko", "Acme mein ML Intern ke liye apply kar diya", Devanagari basics. 31 tests pass.
- PWA: manifest.json, icons, sw.js (API calls never cached). Backend serves /manifest.json and /sw.js.

# v8 (Phase 1 + design pattern)
- Design: one light "paper" theme everywhere (cream #F6F4EE, deep teal #17504A, coral #E8705A, Geist + JetBrains Mono). Shared `opai-shared.css`; common header, floating dock and focus timer from `opai-shell.js`.
- Today engine (`backend/today_engine.py`): top-3 ranked actions with reason, capacity/buffer, "I have 30 min", low-energy mode, Outbox drafts, control states.
- Typed actions (`backend/action_service.py`): propose -> validate -> risk policy -> execute; high-risk waits for approval bound to a payload hash; send_email only queues the Outbox; idempotent; audited.
- Endpoints: GET /v1/today, POST /v1/today/refresh|act|close, POST /v1/actions/propose|{id}/approve|{id}/reject, GET /v1/actions, GET /v1/history.
- Tests: backend/tests/test_today_actions.py (17).
