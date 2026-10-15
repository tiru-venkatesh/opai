# What changed (internship section + slow loading)

Slow loading (video): nothing waits forever any more
- frontend/opai-session.js: Firebase token wait is capped (4s), then the request goes without it; health pings never wait;
  a "Waking up the server" notice appears after 5s; the server is warmed up at page load.
- frontend/opai-shell.js: the pill says "Waking up…" after 6s instead of "Connecting…" forever.
- Root cause of the 30-60s waits is Render's free tier sleeping after ~15 min idle. Fix for good: ping
  https://<your-render-url>/v1/health every 5 min (UptimeRobot, free) or use a paid instance.

Internship page: frontend/opportunities.html (redesigned: Discover, Applications, Outreach, Programs, Insights; old #today #saved #apps #prof #email #docs #reports links still work)
Backend fixes: backend/opportunities_api.py
- "java" no longer matches "javascript"; one skill tag can no longer give a "Strong" fit; Strong needs 3+ tags and a confirmed profile
- deleting an application no longer hides the opportunity forever
- lists build the profile/skill pool once (was one set of queries per row)
Tests: backend/tests/test_internship_fixes.py (6 tests). Delete backend/opa.db before running the suite: tests share it and fail on leftovers.
