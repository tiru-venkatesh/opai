# Deploy order (auth)
1. Copy files over opa-main, `pip install -r backend/requirements.txt`, deploy backend + frontend. Default OPAI_AUTH_MODE=log: nothing is blocked.
2. Use the app for a day. In Render logs search "auth_guard[log] would refuse". Fix/relogin anyone listed.
3. Set OPAI_AUTH_MODE=enforce on Render. Rollback = set it back to log (or off).
Notes: email/password users must have a VERIFIED email (Google sign-in always is); set OPAI_REQUIRE_VERIFIED=0 only as a stop-gap.
Rotate GROQ_API_KEY and DATABASE_URL (they were inside the zip).

## Security gate, metering and payments

**Auth.** On Render (or `OPAI_ENV=production`) `OPAI_AUTH_MODE` now defaults to `enforce`. Local dev stays `log`.
If you have not yet watched the `auth_guard[log] would refuse` lines, set `OPAI_AUTH_MODE=log` for the first deploy, watch a day, then remove it.
The app will not boot in production with auth `off`, `OPAI_LOCAL_AUTH_BYPASS` or `ENABLE_DEV_SEED` on (`OPAI_ALLOW_INSECURE_START=1` overrides, loudly).

**Metering.** Every LLM call goes through `agent/llm.py`, which now checks the signed-in user's credits first and writes a row to `usage_ledger` afterwards.
Light call = 1 credit, deep call (Claude / 120b) = 3. Defaults: free 25/day 400/month, pro 250/5000, max 1000/20000.
Start with `OPAI_METERING=log` (records, never blocks), read `usage_ledger` for a few days, adjust `OPAI_PLAN_LIMITS`, then switch to `enforce`.
Over the cap the API answers **429** with a readable message. Failed calls cost nothing. Calls with no signed-in user (scheduler) are not metered.
Grant a plan by hand: `POST /v1/admin/plan` with header `X-Admin-Key` and `{"email":"a@b.com","plan":"pro","months":1}`.

**Payments (Cashfree).** Set `CASHFREE_APP_ID`, `CASHFREE_SECRET_KEY`, `CASHFREE_ENV=sandbox`, `OPAI_PUBLIC_URL`, `OPAI_API_URL`, and add
`{OPAI_API_URL}/v1/billing/webhook` as the webhook in the Cashfree dashboard. Prices come from the server's plan table, the webhook is signature-checked,
checks the paid amount, and is idempotent. This code has NOT been run against live Cashfree from this repo: do one sandbox payment end to end first.
There is no checkout button in the UI yet (`POST /v1/billing/checkout` exists); until you add it, upgrade users with the admin endpoint.

## Moving from SQLite to Postgres

The app already runs on Postgres: set `DATABASE_URL=postgresql://user:pass@host:5432/db` and it creates its own tables on boot.
The whole backend test suite was run against Postgres 16 with the same results as on SQLite. Verified for this change; nothing in the code is SQLite-only.

To bring existing data across (keep the old `opa.db` as your backup):

1. Create an empty Postgres database (Render / Neon / Supabase all work). Copy its connection string.
2. Stop the app, or put it in maintenance, so nothing writes during the copy.
3. `cd backend && python scripts/migrate_sqlite_to_postgres.py --source ./opa.db --target "<connection string>" --dry-run` to see row counts.
4. Run it again without `--dry-run`. It copies every table in order, keeps all ids, strips NUL characters, prints per-table counts, and exits non-zero if rows are missing.
   Rows Postgres refuses (orphans whose parent was deleted) are skipped one at a time and listed, never dropped silently. It is safe to re-run.
5. Set `DATABASE_URL` on the host to the same connection string and start the app. Log in and check your data before deleting anything.

Notes
- **pgvector is not needed.** Embeddings are stored as JSON and compared in Python (see `database.py`, `rag_service.py`). Move to pgvector only if search gets slow with many documents.
- **R2 / object storage is not needed yet.** Uploaded files are turned into text chunks stored in the database; the original file is not kept. Add R2 only if you decide to keep originals.
- Test it yourself: `OPAI_TEST_PG=postgresql://user:pass@localhost:5432/scratch python -m pytest tests/test_migrate_pg.py` (this wipes that database).
