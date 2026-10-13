# Deploy order (auth)
1. Copy files over opa-main, `pip install -r backend/requirements.txt`, deploy backend + frontend. Default OPAI_AUTH_MODE=log: nothing is blocked.
2. Use the app for a day. In Render logs search "auth_guard[log] would refuse". Fix/relogin anyone listed.
3. Set OPAI_AUTH_MODE=enforce on Render. Rollback = set it back to log (or off).
Notes: email/password users must have a VERIFIED email (Google sign-in always is); set OPAI_REQUIRE_VERIFIED=0 only as a stop-gap.
Rotate GROQ_API_KEY and DATABASE_URL (they were inside the zip).
