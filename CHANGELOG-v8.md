# v8 — Brief System + Karna reminders

## Brief System ("Chat is an input. Briefs are the output. Actions are the execution.")
10 brief types, one universal schema (`backend/briefs/schema.py`, validated before save):
`daily_plan, exam_readiness, dsa_roadmap, application_opportunity, outreach_research, project, weekly_review, decision, recovery, approval`.

| Endpoint | |
|---|---|
| `POST /v1/briefs/daily` (`?capacity_override=60`) · `GET /v1/briefs/daily?date=` | Daily operating brief (get-or-create) |
| `POST /v1/briefs/exam` · `GET /v1/briefs/exam/{exam_id}` | SEMS exam brief (riskiest exam if no id) |
| `POST/GET /v1/briefs/dsa` | Roadmap brief, external links only |
| `POST /v1/briefs/application/{opportunity_or_application_id}` | Match, gaps, next action |
| `POST /v1/briefs/outreach/{contact_id}` | Research brief **before** any draft |
| `POST /v1/briefs/project/{project_id}` · `/weekly` · `/decision` · `/recovery` · `/approval` | |
| `GET /v1/briefs[/{id}]` · `POST /v1/briefs/{id}/refresh` · `/dismiss` | Lifecycle |
| `POST /v1/actions/{id}/execute` · `/approve` · `/reject` | Execution (typed contract → risk policy → audit) |

Lifecycle: generated → shown → partially_acted → completed | expired | superseded | dismissed.
Risk: **low** runs; **medium** runs after the user confirms on the brief (recorded as the approval); **high** only via `/approve` with the payload hash.
Groq never ranks or decides: it may only fill `explanation.narrative` (`?narrative=true`).
JARVIS routes planning phrases to briefs ("what should I do today", "I only have one hour", "should I …?", "weekly review", "what needs my approval") and replies with a 2-sentence summary + action chips.

## Karna reminders + notifications
* "Remind me at 2 40pm" → Karna asks "What should I remind you about at 2:40 PM?" → your answer sets it. Also `remind me to X at 5pm`, `in 20 minutes`, `tomorrow 7am`. No clock time → old task flow is unchanged.
* "Send me my plan every morning at 7:30" / "stop the daily plan" → repeating *today's plan* notification built from the Daily Brief.
* Scheduler thread (`OPAI_SCHEDULER=0` disables) + `GET/POST /v1/system/tick` for hosts that sleep (ping every minute; set `OPAI_TICK_SECRET`). A morning plan that is >6h late is skipped, never sent at night.
* Frontend `notify.js` (all pages): polls, shows system notifications with **Done / Snooze 10 min**; `briefs.html` is the page a notification opens.
* Closed-app delivery needs Web Push: `pip install pywebpush`, set `OPAI_VAPID_PUBLIC`, `OPAI_VAPID_PRIVATE`, `OPAI_VAPID_SUBJECT` (generate keys with `npx web-push generate-vapid-keys`). Without them everything works while a tab/PWA is open.

New tables: `briefs, brief_actions, reminders, notifications, push_subscriptions` (auto-created).
Tests: `cd backend && python -m pytest tests -q` → 168 passing (71 new).
