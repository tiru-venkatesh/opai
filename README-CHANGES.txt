OPAI DSA Coach - drop these files over the repo (same paths).

NEW      backend/dsa_coach.py            pure rules: mastery ladder, weakness diagnosis, tomorrow's plan, nudge gate
NEW      backend/dsa_coach_service.py    DB layer + opt-in streak reminder settings
NEW      backend/dsa_coach_api.py        /v1/dsa/attempts, /v1/dsa/coach, /v1/dsa/coach/reminders
NEW      backend/tests/test_dsa_coach.py 24 tests (rules, API, real scheduler path)
CHANGED  backend/database.py             + DsaAttempt, DsaMastery tables (created automatically at startup, nothing existing is altered)
CHANGED  backend/main.py                 + include dsa_coach_router
CHANGED  backend/reminders.py            + "dsa_streak" branch in fire_due (opt-in, idempotent, 45-min staleness cut-off)
CHANGED  backend/reminders_api.py        + re-anchor streak reminders when the user's timezone changes
CHANGED  frontend/dsa.html               + Coach card (plan, log result, pattern strength, reminder opt-in)

Not touched: backend/static/dsa.html is an older copy of the page and was left as is.
