# v9 — Refinement: one contract, reliable execution

## One pipeline for every channel
`POST /v1/chat` → typed intent (`agent/intents.py`, closed registry with required fields / risk / channels) → clarification if a field is missing → handler → brief + actions → audit.
Response: `{request_id, conversation_id, intent, confidence, status: needs_input|completed|refused, reply, brief, brief_id, actions[], next_input, data}`.
The KARNA popup now uses it (brief preview + action chips, same `/v1/actions/{id}/execute|confirm` as `briefs.html`). `/v1/jarvis/chat` is unchanged.
"add task Submit the DS record" is `create_task` even while KARNA is waiting for a reminder title.

## One action shape everywhere
`{id (=action_id), brief_id, type, label, risk, kind, status, requires_confirmation, requires_approval}`; new 11th brief type `reminder` (the confirmation brief, with Done / Snooze actions).
Endpoints added: `/v1/chat`, `/v1/actions/{id}/confirm`, `PATCH /v1/reminders/{id}`, `/v1/reminders/{id}/complete`, `/v1/preferences/daily-plan` (POST/DELETE), `/v1/preferences/notifications`, `/v1/system/health`, `/v1/system/scheduler-status`.

## Approval binding
* High-risk approve **requires `payload_hash`** (428 otherwise); a changed recipient/subject/body ⇒ 409 and no send. The hash is re-verified at execution time. Approvals are single-use.
* Every brief action stores a hash of its intent+payload; if the row was altered after the brief was shown, execution is refused.

## Time zones
IANA zones (`Asia/Kolkata`) via `timezone` (browser sends it automatically); fixed offsets still work. DB/scheduler use UTC; recurrence is anchored to **local wall time** (07:30 stays 07:30 across DST). "Every morning at 7:30" now means 07:30 (day-part words settle am/pm).

## Reliable scheduling
* Claim = atomic compare-and-set; notifications carry idempotency keys `reminder_due:{id}:{occurrence}` / `daily_plan:{user}:{date}:{HH:MM}` (unique index) so restarts, double ticks and retries cannot duplicate.
* `notification_deliveries` records every push attempt; failures retry (3 attempts, back-off); 404/410 endpoints are unsubscribed.
* **`/v1/system/tick` always requires `OPAI_TICK_SECRET`** (503 if unset, 403 if wrong). Set it, then ping every minute with `x-tick-secret`.
* Structured events (`obs.py`): intent_classified, brief_created/shown, action_proposed/confirmed/approved/executed/failed, reminder_created/delivered, notification_clicked, scheduler_tick/error — counted in `/v1/system/health`.

## briefs.html
Loading / empty / expired / failed+Retry / offline states, `safeUrl()` for every link, sources, context, "Why this brief?", updated/expiry time, stale-brief actions disabled. A test fails the build if API strings are ever injected with `innerHTML`.

Tests: `cd backend && python -m pytest tests -q` → **223 passing** (55 new).

## Not done (needs infrastructure or a decision)
Postgres + `FOR UPDATE SKIP LOCKED` (compare-and-set gives the same guarantee today), Redis/job queue, WhatsApp adapter, `GET /v1/conversations/{id}` + stored transcripts, email fallback for failed push, module re-layout to `app/…`, real-device Web Push testing (Android / installed PWA).
