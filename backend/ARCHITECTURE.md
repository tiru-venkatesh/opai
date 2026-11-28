# OPAI KARNA backend architecture

## Request flow

```text
Browser (frontend/super-chat.html)
  -> Firebase token verification and user ownership guard
  -> FastAPI chat / workspace route
  -> local mode, intent, capability, privacy and quota checks
  -> one eligible provider at a time (Groq, Gemini or OpenRouter)
  -> normalized answer/tool deltas, usage ledger and citation checks
  -> whitelisted workspace tools with existing confirmation and audit rules
```

The local router does not send each prompt to all providers. Auto uses Groq for everyday and coding requests, and Gemini for complex reasoning, study workflows and multimodal tasks where its data policy permits the content. Fast, Think and Expert alter the preferred route. Retries are bounded, provider cooldowns open after repeated errors, and fallback is allowed only before visible stream output starts.

## Provider and privacy boundary

All provider calls use `agent/llm.py`. Groq uses the existing SDK; Gemini and OpenRouter use the OpenAI-compatible adapter in `agent/providers/openai_compat.py`. The adapters normalize completions, tool-call streams, token usage and provider errors.

The gateway defaults to private-workspace routing. Groq is eligible by default. Gemini may receive Workspace data only when the account is on a reviewed paid tier and both `KARNA_ENABLE_PAID_MODELS=true` and `KARNA_GEMINI_WORKSPACE_ALLOWED=true` are set. Legacy Anthropic Workspace routing needs both the paid-model switch and `KARNA_ANTHROPIC_WORKSPACE_ALLOWED=true`. OpenRouter is limited to non-private General chat because its free router may pick downstream providers with different retention terms. If no eligible provider is available, KARNA fails closed. API keys remain in backend environment variables.

User-facing answer paths share the base KARNA system instructions and disclose actual provider/model metadata in the UI. Uploaded and retrieved content is labeled untrusted. RAG filters by the authenticated user's owner ID, removes invalid citations, and does not add private uploads to the central professor catalog.

## Data, identity and tools

`auth_guard.py` verifies Firebase tokens and matches the verified account to any requested `user_id`. Production startup refuses insecure auth settings. Existing owner-filtered queries, file routes, memory/RAG metadata filters, whitelisted tools, action confirmations and audit logging remain in place. Chat transcripts stay in the signed-in user's browser; long-term memory is stored server-side per user and can be edited, deleted or disabled.

SQLAlchemy uses the repository's existing `create_all` plus additive auto-migration path. This version adds `user_memory.enabled`, `usage_ledger.latency_ms` and `usage_ledger.fallback`. Existing memory rows stay enabled. No tables are dropped. Use persistent PostgreSQL for production. For reviewed migration history or schema changes beyond additive columns, move these additions into Alembic.

## Quotas and operations

`provider_quota.py` enforces optional account-specific request/token caps from `KARNA_PROVIDER_LIMITS_JSON` using OPAI's provider-attempt ledger. It does not query or rotate provider keys, and it cannot see usage outside OPAI. Per-user RPM and circuit-breaker state are process-local; use a shared limiter if deploying multiple workers. User plan credits continue through `metering.py`.

`/v1/admin/ai-analytics` is protected by `OPAI_ADMIN_KEY` (or the existing `FEEDBACK_ADMIN_KEY`) and returns aggregate counts, provider health, configured quotas and optional estimated cost. It never returns prompts, responses, documents or memory text. Cost estimates remain blank unless the operator supplies current rates.

See [`KARNA_MULTI_PROVIDER.md`](KARNA_MULTI_PROVIDER.md) for environment setup, privacy choices, quota configuration and deployment steps. Tests mock provider network responses; live account, billing, outage and deployment checks require staging credentials.
