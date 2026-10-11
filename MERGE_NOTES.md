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
