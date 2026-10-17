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

## Shader background (new)
- `frontend/opai-shader.js`: the Stitch glass-orb WebGL shader as a fixed background on 22 pages (every app page + login/onboarding;
  not landing/privacy/terms/today-legacy). Light palette, dark palette follows the theme toggle live.
- Cheap by design: reduced resolution, 30 fps cap, pauses on hidden tabs, single static frame for reduced-motion / Save-Data / weak devices.
- Safe fallback: the page body only turns transparent after the first frame draws; no WebGL or GPU reset = normal solid background.
- Off switches: `?shader=0`, or `localStorage.opai_shader = "0"`. Auto-off for `?embed=1` and print.
- `sw.js` cache bumped to opai-v56 and precaches the script. `backend/static` + a root route in main.py serve it locally too.

## Cleaned out
Stray top-level copies (conversation.py, noise.py, orchestrator.py, main.py.diff), opa.db / -shm / -wal / .backup, t.db-*,
__pycache__, .pytest_cache. Added backend/.gitignore (.env, *.db*, caches). No .env is included.

## Verified
Repo suite 529 passed; the 20 remaining failures/errors exist on your original code too (test_opportunities_api etc.).
Route contract OK. UI smoke (mocked backend) 20/20. Shader: GLSL compiles (glslang, ES 1.00), 27/27 behaviour tests with a mock GPU. Not checked: real-browser / phone appearance.

## Deploy
Redeploy backend (Render) AND frontend (Vercel). Hard-refresh once (service worker caches pages).
