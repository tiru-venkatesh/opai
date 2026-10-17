# OPAI clean drop (backend + frontend)

## Frontend
- `frontend/super-chat.html`: new chat-only Stitch design. Same live script and endpoints as before
  (/v1/jarvis/chat, /v1/chat/general, /v1/attach/analyze, /v1/rag/*, /v1/outbox, /v1/memory/items, /feedback, /guide, voice,
  history, export). Firebase session (`opai-session.js`) still loaded. Memory / Knowledge / History are overlay panels.
- Removed: nav, mobile section drawer, WebGL shader, dark/light toggle, cinematic wipe + demo code, unused word-reveal code.

## Backend
- `main.py`: /v1/jarvis/chat and /v1/chat/general answer greetings / thanks / "what can you do" / help locally,
  BEFORE the memory-extraction pass (that pass caused the ~6 s "hi").
- `agent/conversation.py` (new): the local replies. Edit `ENABLED_CAPABILITIES` when features change.
- `agent/orchestrator.py`: `_try()` logs + rolls back failed steps, IST-aware dates, int-safe task minutes,
  natural clarify message, per-step timing logs (grep `step=`).
- `agent/noise.py`: gibberish guard.
- Tests: test_conversation*.py, test_orchestrator_hardening.py, test_noise_guard.py (+ jarvis-route test).

## Cleaned out
Stray top-level copies (conversation.py, noise.py, orchestrator.py, main.py.diff), opa.db / -shm / -wal / .backup, t.db-*,
__pycache__, .pytest_cache. Added backend/.gitignore (.env, *.db*, caches). No .env is included.

## Verified
Repo suite 529 passed; the 20 remaining failures/errors exist on your original code too (test_opportunities_api etc.).
Route contract OK. UI smoke (mocked backend) 20/20. Not checked: real-browser / phone appearance.

## Deploy
Redeploy backend (Render) AND frontend (Vercel). Hard-refresh once (service worker caches pages).
