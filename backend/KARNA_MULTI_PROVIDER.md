# KARNA multi-provider deployment

KARNA keeps its existing OPAI authentication, personal workspace, RAG and chat routes. User-facing answers now share the KARNA system identity and pass through a local router that chooses a provider from the selected mode, prompt intent, model availability, configured quota and privacy requirements.

## Providers and privacy

| Provider | Default use | Private workspace data |
| --- | --- | --- |
| Groq | Everyday chat, coding, fast fallback | Allowed by default; confirm the retention/privacy terms for the account and key you deploy. |
| Gemini | Complex reasoning, study planning, vision | Blocked unless both `KARNA_ENABLE_PAID_MODELS=true` and `KARNA_GEMINI_WORKSPACE_ALLOWED=true`. |
| OpenRouter | General-chat fallback | Blocked for private data because the free router may select different downstream providers. |
| Anthropic (legacy) | Existing selectable Claude models | Disabled unless `KARNA_ENABLE_PAID_MODELS=true`; Workspace use also requires `KARNA_ANTHROPIC_WORKSPACE_ALLOWED=true`. |

The default model IDs are `openai/gpt-oss-120b`, `gemini-3.8-flash`, and `openrouter/free`. Model IDs and availability change, so the provider model catalog and account dashboard remain authoritative. KARNA does not hardcode account quotas. Its provider quota checks only run when an operator supplies verified account-specific limits in `KARNA_PROVIDER_LIMITS_JSON`.

General chat uses Gemini Free only for prompts that KARNA classifies as non-private. Google says Free-tier prompts and responses may be used to improve Google products; Paid-tier content is not used for that purpose. OpenRouter can route to downstream model providers with different policies, so private user data is never sent there. If no configured provider passes the privacy check, KARNA returns an error instead of forwarding that content. `KARNA_ENABLE_PAID_MODELS=false` keeps paid-only choices such as Claude and paid-tier Gemini routing disabled; it cannot detect whether a provider's own key or plan will bill for Groq or other enabled API calls. Provider billing still follows the account's terms and dashboard.

The router uses local keyword/capability checks, not an additional model call. Transient network/5xx failures get a bounded retry with short exponential backoff, and provider fallbacks happen before the first streamed token; after output begins, KARNA returns the partial-stream error rather than switching models and duplicating text. Circuit-breaker and user-RPM state are process-local. Configured provider quota usage is read from this OPAI database, so it does not include requests made by other applications using the same provider key.

## Environment setup

Copy `backend/.env.example` to `backend/.env` locally, or add the values in the hosting provider's encrypted environment settings. Keep real credentials out of Git and frontend files.

Minimum configuration:

```env
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free
KARNA_DEFAULT_MODE=auto
KARNA_ENABLE_FALLBACK=true
KARNA_ENABLE_PAID_MODELS=false
KARNA_ENABLE_MEMORY=true
KARNA_ENABLE_RAG=true
KARNA_GEMINI_WORKSPACE_ALLOWED=false
KARNA_ANTHROPIC_WORKSPACE_ALLOWED=false
```

Set only keys for providers you intend to use. Paid models stay disabled by default. Do not enable Gemini or Anthropic Workspace routing until the account and model terms have been reviewed for the OPAI data handled by this deployment. OpenRouter remains blocked for private workspace data.

Optional quota and cost settings accept JSON:

```env
KARNA_PROVIDER_LIMITS_JSON={"groq":{"requests_per_minute":60,"tokens_per_day":1000000}}
KARNA_PRICE_PER_1M_JSON={"groq/openai/gpt-oss-120b":{"input_per_million":0.15,"output_per_million":0.60}}
```

Use values shown for the specific provider account and model. These limits are an OPAI-side guard based on recorded OPAI provider attempts, not a live provider quota API. Token totals for streamed responses are estimates; the dashboard marks cost as estimated and leaves it blank unless a price table is configured.

For the administrator dashboard, set `OPAI_ADMIN_KEY` (preferred) or the existing `FEEDBACK_ADMIN_KEY`. Use a long random secret. The key is entered into the admin page for the current tab and sent only in the `X-Admin-Key` header. Never place it in a public link or frontend source.

## Deployment

1. Deploy the existing backend service and frontend build together as before. Add the provider keys and KARNA settings in the host environment; do not commit `.env`.
2. Set `DATABASE_URL` to persistent PostgreSQL in production. The existing health endpoint warns when Render is using ephemeral SQLite, which loses user data on restart.
3. Set `CORS_ORIGINS` to the exact OPAI frontend origin(s), rather than `*`.
4. Deploy `backend/static/super-chat.html` with the current `frontend/super-chat.html`. The modes are persisted per device; chat history remains device-local and is keyed by authenticated user.
5. Deploy `backend/static/admin-ai.html` with `frontend/admin-ai.html`. Open `/static/admin-ai.html`, enter the admin key, and review only aggregate telemetry.
6. Check `/v1/health`, then test each provider with a non-sensitive prompt. Check the admin page for provider attempts, health and configured quota readings.
7. Enable Gemini or Anthropic workspace access only after checking the account's tier and policy. Check the provider's live model IDs before changing either model setting.

The database uses the repository's existing `create_all` and additive auto-migration path. This change adds `user_memory.enabled` plus nullable usage telemetry fields (`latency_ms` and `fallback`) to existing databases; old memory rows are backfilled as enabled. No user tables are dropped or replaced. For production deployments that require reviewed/versioned migrations, convert these additive changes into the project's standard Alembic workflow before release.

## Admin API

`GET /v1/admin/ai-analytics?window=24h|7d|30d` returns request and token totals, active users, provider/model counts, error/fallback counts, latency, circuit health and configured quota estimates. It accepts `X-Admin-Key`. The response contains no prompts, generated responses, files, or memory text.

## Verification and limitations

The automated provider tests mock network responses and verify the adapter contracts, streaming, missing-key errors, rate-limit fallback, privacy routing and memory opt-out. Live-provider tests require working provider keys and consume account quota; run those from a staging environment with non-sensitive prompts. Existing OPAI cross-user tests cover ownership isolation across workspaces, files, resumes, memory and study data.

Provider health and per-user RPM state are local to each backend worker, while provider usage rows are shared through the SQL database. Quota checks are advisory under simultaneous requests, and usage by other services on the same provider key is invisible to OPAI. OpenRouter's selected downstream model can change, and its data policies vary. Browser chat history stays local to the signed-in browser; it is not synchronized between devices. Live provider outage, deployment, mobile browser, and billed spend checks still require a staging environment and active provider credentials.
