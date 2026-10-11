# Stability patch: connection layer, route contract, deploy check, version, Gmail claim fix

Applies on top of `opa-main-updated__2_.zip` (sw `opai-v30`, onboarding/privacy/terms). Every change is additive or a few lines;
`stability.patch` is a unified diff (`cd opa-main && patch -p1 < stability.patch`), the new files are also included in tree layout.

## What it adds
| | File | What it does |
|---|---|---|
| Connection layer | `frontend/opai-conn.js` (+ one `<script>` in `<head>` of every page that calls the API; not KARNA chat, login, landing, privacy, terms) | Wraps `fetch` for OPAI calls. **GET** retries with 1-2-4-8-15 s backoff on network error / 502-504 and shows "OPAI is waking up". **POST/PUT/DELETE are never replayed**; before one is sent the layer waits for `/v1/health`, so it goes out once to a backend that is up. A 404 counts as "feature unavailable / version mismatch" only when FastAPI says exactly `{"detail":"Not Found"}`. Gmail 401/403/429 on `/outbox/{id}/send` is reported as `OPAI_CONN.gmail` and never flips OPAI to offline. Banner has Retry / Reload. `window.OPAI_CONN = {state, gmail, on, retry, awake, version}` |
| Version / mismatch | `backend/version_api.py` (`GET /v1/version`), `backend/scripts/stamp_build.py` -> `frontend/build.json` | Bump `API_CONTRACT` by hand when the frontend starts needing a new route/shape; `opai-conn.js` compares it with `build.json` and shows "OPAI is updating" when the backend is older (or has no `/v1/version`). Run `stamp_build.py` as part of the frontend deploy. |
| Route contract | `backend/scripts/route_contract.py`, `backend/tests/test_route_contract_static.py` | Standard library only (no FastAPI). Reads the route table from the Python source, **counting only routers `main.py` registers**, and checks every `/v1/...` path in every frontend page/script. Checks paths, not methods or response shapes. |
| Deploy check | `backend/scripts/check_deploy.py <url> --origin <frontend>` | After a deploy: wake time, `/v1/system/health`, scheduler status, contract vs `build.json`, deployed `/openapi.json` vs frontend paths, CORS preflight, identity-less call refused, Gmail send returns a clean 4xx, tick (skipped when the route does not exist). Exit 1 on any FAIL. |
| Opportunities page | `frontend/opportunities.html` | `p = v.profile \|\| {}` (the reported `Cannot read properties of undefined (reading 'degree')`, reproduced and fixed); a route 404 shows "Feature temporarily unavailable"; failed loads show an error card with **Try again**. |
| Gmail send | `backend/opportunities_api.py`, test in `tests/test_opportunities.py` | The "sending" claim now carries a time and is taken with a compare-and-set. Before: a server restart between claim and Gmail call (Render restarts) left the item on "sending" forever. Now an unfinished claim older than 3 min gives a clear 409, **never auto-resends** (could duplicate), and `POST /v1/opp/outbox/{id}/send/release` frees it after the user checks Gmail's Sent folder. |
| Service worker | `frontend/sw.js` | `opai-v31`, caches `opai-conn.js`. Hard refresh once after deploy. |

## IMPORTANT: what the route contract found in this tree
`python backend/scripts/route_contract.py` exits 1: **14 frontend paths have no backend route**: `briefs.html` (`/v1/briefs/...`, `/v1/actions/{id}/execute`) and `notify.js` (`/v1/notifications...`, `/v1/push/...`, `/v1/reminders/...`).
Cause: `brief_api.py`, `reminders_api.py` and `chat_api.py` exist but `main.py` never registers them, and `database.py` has no `Reminder`, `Notification`, `NotificationDelivery`, `PushSubscription` (and the Brief models) that they import. This is the missing v9 layer in your notes. I did **not** rebuild it: another session is doing exactly that on this same tree, and two versions of `database.py` would collide. The route contract is the acceptance test for that restore: when it exits 0, the layer is wired.

## How it was tested
* Browser (headless Chromium) against a controllable stub backend, on this tree: backend asleep (GET retried, banner, recovers, banner hides), POST while asleep (sent exactly once after wake), POST dying mid-flight (not replayed), 503 retried, route-missing vs handler-404, Gmail 401 isolated from OPAI state, external URLs untouched, version contract 4 cases, profile form with an old-backend `{}` response (original code reproduced the crash), error card + Try again. All 21 pages load; only errors are `tailwind is not defined` where the sandbox blocks the Tailwind CDN.
* `check_deploy.py` against a fake deployment: passes when healthy; fails on a stale one with the missing routes, older contract and broken CORS.
* Static: `route_contract.py` proven to fail on a deliberately wrong path; no undefined names in changed Python.
* **Not run:** the FastAPI app and pytest (not installable in the sandbox). The new Gmail-claim test and the Python side of `/v1/version` are written but unexecuted. Run `cd backend && python -m pytest tests -q` before deploying.

## Things to know
* No token auth exists (`/v1/auth/dev-login?email=`, `user_id` params), so there is no "401 -> refresh token" step; a 401 can only come from Gmail.
* There is no `/v1/system/tick` route in this tree (reminders fire inside `reminders.py`); the deploy check skips that item.
* Gmail uses a short-lived browser token per send (not stored), so "connected until 4:20 PM" and silent refresh are not possible server-side; the UI can only report "needs reconnect" after a send fails. The failed send leaves the draft approved and retryable.
* `backend/static/` is a stale partial copy of `frontend/`; not touched.
* Leftover from an earlier session: `backend/resume_lab_tools.py`, `tests/test_resume_lab_tools.py`, `RESUME_LAB_V3_NOTES.md` are not used by `resume_lab_api.py` (which uses `resume_lab_core.py`) and the notes describe endpoints this tree does not have. Safe to delete: `git rm backend/resume_lab_tools.py backend/tests/test_resume_lab_tools.py RESUME_LAB_V3_NOTES.md`.
* Resume Lab `attach` (in `resume_lab_core`'s API) saves each tailored resume as a normal library version, so after ~10 applications attach fails with "library is full", and tailored copies join matching and the bullet bank. Worth a decision (separate "tailored" kind) but not changed here.
