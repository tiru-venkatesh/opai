# OPAI KARNA: backend architecture (Claude edition)

## Principle
**Claude understands, explains and drafts. The backend validates, decides and executes.**
The model never writes to the database directly. Every write goes through a whitelisted tool, an approval step and the audit log.

## Request flow (`POST /v1/chat`, `POST /v1/chat/general`)

```
Browser (super-chat.html)
   |
   v
FastAPI  ── auth_guard ── rate limit ── chat_api.py / main.py
   |
   v
agent/orchestrator.handle_message            (cheapest path first; the LLM is the LAST resort)
   1. conversation.py   greetings / "what can you do" / help        0 DB, 0 LLM   ~ms
   2. noise.py          gibberish / one-word unknowns               0 LLM
   3. identity.py       "what is my college / year"                 DB only
   4. reminder_chat + briefs.jarvis   "remind me", "plan my 2 hours" typed flows
   5. direct_db.py      lists / counts / deadlines                  DB only, exact
   6. capture.py        "add an exam / project / task ..."          LLM JSON extract (fast tier)
   7. RAG               questions about your documents              retrieval + Claude (balanced tier), [n] citations
   8. router.classify   intent + confidence                         Claude fast tier
        confidence < 0.55 -> conversational answer (RAG, then general knowledge), no dead end
        known intent      -> typed workflow (plan, task, outreach draft, opportunity search)
        otherwise         -> Claude tool-calling loop over the whitelisted tools (agent tier)
   |
   v
Approval boundary (outreach is only ever a DRAFT) -> audit log -> response
```

## LLM gateway (`agent/llm.py`)
All model calls go through one place. It exposes the same shape as the old Groq client, so no call site had to change.

| Tier | Used for | Default model |
|---|---|---|
| fast | intent routing, field extraction, query rewrite | `claude-haiku-5-5` |
| balanced | RAG answers, General chat, plans, outreach drafts, vision | `claude-sonnet-5-5` |
| agent | tool-calling loop | `claude-sonnet-5-5` (`CLAUDE_AGENT_MODEL`) |
| deep | opt-in for the hardest tasks (`tier="deep"`) | `claude-opus-5-5` |

- **Fallback:** if Claude errors or is overloaded and `GROQ_API_KEY` is set, the same call is retried on Groq (`KARNA_FALLBACK=off` disables this).
- **Prompt caching:** the system prompt and tool list are marked cacheable, so repeated turns re-read them cheaply.
- **JSON mode:** Claude has no native `json_object` mode, so the gateway adds an output rule and extracts the first valid JSON object from the reply.
- **Streaming:** `POST /v1/chat/general/stream` (Server-Sent Events: `{"delta": ...}` chunks, then `{"done": true, "reply": ...}`).
- **Observability:** each call logs provider, model, tokens, cache hits and latency (`opa.llm`). `/v1/health` reports the provider and model names (never keys).
- **Errors:** Anthropic errors map to friendly 429/502/503 messages; raw provider text is never echoed to the user.

## Safety boundary (unchanged, and still the reason to trust the agent)
- Tools are a fixed whitelist (`tool_registry`, `TOOL_SPECS`); unknown tool names are refused and logged.
- Per-turn tool-call cap, idempotency keys, emergency stop (`agent_enabled`).
- Outreach is a pending draft until the user approves it; the approval is bound to a content hash.
- User data in prompts is labelled as data, never instructions.

## Deploy (Render)
1. Add env var `ANTHROPIC_API_KEY`. Keep `GROQ_API_KEY` if you want the fallback.
2. Set `DATABASE_URL` to Postgres (SQLite is wiped on every Render deploy).
3. Deploy, then open `/v1/health`: `llm.provider` should read `anthropic`.
4. Hard refresh the site (service worker cache).

## Not done / next steps
- The chat page still calls the non-streaming `/v1/chat/general`; switching it to the stream endpoint is a small front-end change.
- Not run against a live Anthropic key (none available here). The conversion layer is covered by 10 offline tests using a fake client; do one real chat after deploying.
- Larger gains later: per-user conversation summaries in memory, and an evaluation set of real KARNA questions to compare tiers.
