Daily auto-draft update. Copy files over the same paths in your repo (backend/ and frontend/ folders).
Backend: new auto_outreach.py + tests/test_auto_outreach.py; changed database.py, faculty_api.py, reminders.py,
reminders_api.py, opportunities_api.py. New table auto_outreach_settings is created on startup.
Frontend: opportunities.html (Professors tab card + badge), sw.js v71. Hard refresh: Ctrl+Shift+R.
Render free tier sleeps: ping /v1/system/tick (needs OPAI_TICK_SECRET) every few minutes; it runs the daily draft too.
Nothing is ever sent automatically: every draft waits in Email Drafts for your approval.
