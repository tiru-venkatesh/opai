# Merge notes (Opportunities layer + Resume Lab copy)

Base: your `opa-resume-lab-v5` (Resume Lab, purge_guests.py, no guest endpoint, sign-in based pages).
Layered on top: the complete Opportunities pipeline (profile, intake, briefs, applications, professors, Outbox,
follow-ups, reports, Programs & Challenges, optional Gmail send) and the 663-row faculty CSV (ISM merged).

## Behaviour changes you should know about
* **Email approval needs the hash you reviewed** (`reviewed_hash`) on both `/v1/outbox/{id}/approve` and
  `/v1/opp/outbox/{id}/approve`. One hash function, defined in `database.outbox_content_hash`, is used by the
  approval check AND by the database hook that revokes an approval when content changes afterwards.
* **Approve is not send.** Approving no longer marks a contact "Sent" or starts a follow-up. That happens when the
  send is logged (`POST /v1/opp/outbox/{id}/sent`, or `/send` for direct Gmail).
* **Daily cap counts approvals** as well as logged sends (without double counting).
* **Privacy:** `GET /v1/opportunities`, `/intel`, `dismiss` and `convert` only show shared rows plus your own;
  someone else's saved posting looks like a 404. Contact status is per user.
* Resume Lab's "pick a saved posting" dropdown now uses `/v1/opp/saved` (the old route never existed).
* Resume Lab gets its own `_has()` helper; `TECH_TERMS` is exported from `opportunities_api`.

## Database
Union of both column sets (nothing removed). New nullable columns are added by the startup auto-migration:
Application(source_type, answers, submitted_at, contact_ref), Contact(source_checked_on, relevant_work),
Opportunity(requirements, field_sources), OutboxItem(approved_at, sent_via), model ApplicationEvent.

## Not working / not included
* `tests/test_briefs.py`, `test_reminders.py`, `test_refinement.py` cannot import: the models Brief, BriefAction,
  Notification, NotificationDelivery, PushSubscription, Reminder are not defined in any file of this copy, so those
  routers (briefs, reminders, push, notifications) are not wired and briefs.html / notify.js get 404s.
  They need the `database.py` of the session that built them.
* `tests_superseded/` holds the old Opportunities API tests (kept for reference, not collected).

## Run tests
    cd backend
    python -m pytest tests -q --ignore=tests/test_briefs.py --ignore=tests/test_refinement.py --ignore=tests/test_reminders.py

## Theme (opa-main-theme-v2) merged in
* Frontend = the theme zip's frontend (opai-theme.css, opai-ux.js, themed pages, Resume Lab multi-file upload) plus
  two fixes the theme copy lacked: the shell keep-alive ping, and Resume Lab's saved-postings dropdown now uses
  /v1/opp/saved. Service-worker cache bumped (opai-v18) so browsers pick up the new shell.
* Backend additions taken from the theme zip: POST /v1/resume-lab/import-files, import_resumes_dir.py, the
  Tenglish capture regex fix in agent/capture.py, and its updated tests.

## No guest accounts (verified)
* `/v1/auth/guest` does not exist (asserted by `test_frontend_contract.py::test_guest_endpoint_is_gone`).
* No page offers "Continue as guest" and no page creates a guest user.
* `dev-login` now refuses the old `guest-<12 hex>@opa.local` addresses (403) until `python purge_guests.py --apply` deletes them.
* Reminder: `dev-login` still trusts any email it is given. It is the identity bridge for every page. Replace it with a
  server-verified session (verify the Firebase ID token on the backend) before putting real user data behind it.

## KARNA prompt + context packet + reply guard
* `agent/karna_prompt.py`: one stable KARNA system prompt (rules never change per user) and an `OPAI_CONTEXT` packet
  (today's planner picks, exams, open applications, Outbox counts; capped at ~4,500 characters) sent in the USER turn and
  labelled as data. `render_context` is pure; `collect_context` reads the DB section by section and drops a failing section.
* `agent/reply_guard.py`: KARNA cannot claim "I sent / submitted / created / updated ..." unless a tool result in the same
  turn succeeded. Unsupported sentences are removed and a plain note is added. Offers, negations and questions are untouched.
  Applied to the tool-agent reply and to RAG-grounded replies.
* `agent_service.py`: tool loop now uses `karna_prompt.build_for(...)`; grounded replies get `GROUNDED_STYLE` + the guard.
* Tests: `cd backend && python -m pytest tests/test_karna_prompt.py -q` (pure, 6 tests, run and passing here).
  Not run: the endpoint path in `agent_service.py` (needs FastAPI/SQLAlchemy/Groq).
* Not done on purpose: a JSON-schema reply format. The agent already uses native tool calling, which is the structured
  action channel; a second schema would duplicate it.

## Mobile comfort pass (phones)
Measured first with headless Chromium at 360, 390 and 768 px (every main page, stubbed API). No page scrolled sideways;
the real problems were: wide floating KARNA button covering page buttons, floating bottom bar hiding the last content,
sideways tab rows with no edge cue, fields under 16px (iPhones zoom on focus) and 30-34px tap targets.
Fixed in one block at the end of `frontend/opai-shared.css` (`@media (max-width:760px)`):
* fields get 16px text; buttons/selects/summaries/tabs get a 40px minimum height
* the floating KARNA button becomes a compact round icon; pages get bottom padding so the bar never hides content
* `.tabs` rows fade at the edge and snap
* `landing.html`: email field `size="1"` (16px text otherwise widened the page by 23px)
* `sw.js` cache bumped so phones pick up the new CSS (hard refresh once)
Checked in KARNA chat on this base: New and History at the far left, History opens from the left, large centered heading,
dark theme works, phone layout uses the drawer + round compose button, popup chat is a bottom sheet. No change needed.
Not covered: real devices, landscape phones, and Telugu/Hindi text lengths. The audit scripts are not shipped.
