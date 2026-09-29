# OPA Agent Backend — deploy notes

This is the FastAPI + Groq backend, split out to deploy on its own. It
needs to run as a **persistent process** (not a serverless function) —
see why in the root project's notes on Vercel. Render, Railway, and
Fly.io all work; so does any VPS.

## Local run (unchanged)
```bash
pip install -r requirements.txt
export GROQ_API_KEY="your key"
python main.py
```

## Deploying to Render / Railway / Fly.io

General shape, same on all three:
1. Push this folder to its own git repo.
2. Create a new **Web Service** (Render/Railway) or `fly launch` (Fly.io)
   pointing at that repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `python main.py` (or `uvicorn main:app --host 0.0.0.0 --port $PORT`
   — check which port env var your host expects and adjust `main.py`'s
   `uvicorn.run(..., port=8000)` line, or read `PORT` from the environment)
5. Set the `GROQ_API_KEY` environment variable in the host's dashboard.
6. Once deployed, copy the public URL — that's what you paste into the
   frontend's **Backend URL** field.

## Important: SQLite persistence isn't automatic

`database.py` defaults to a local SQLite file (`./opa.db`). That file
only survives as long as the *same disk* sticks around. On most hosts'
**free tiers**, redeploys or restarts can wipe local files unless you
explicitly attach a persistent volume/disk — check your host's docs for
"persistent disk" or "volume" before you rely on this for real data.

Two ways to get real persistence:
- **Attach a persistent volume/disk** on whichever host you pick, and
  point `DATABASE_URL` nowhere (keep the SQLite default) — the file then
  lives on that volume.
- **Use a hosted Postgres instead** (Neon, Supabase, or the host's own
  managed Postgres all have free tiers) — set `DATABASE_URL` to that
  instance's connection string. No code changes needed; `database.py`
  already works against Postgres, and no pgvector extension is required
  (similarity search runs in Python).

## The other real constraint: the embedding model

`fastembed` downloads the `BAAI/bge-small-en-v1.5` model (a few hundred
MB) the first time it's used. On a host with a small disk/memory
allowance or a strict cold-start timeout, this can be slow or fail. If
that happens, the fix is usually either upgrading the plan's resources
or swapping `get_embedding()` in `agent_service.py` for a call to a
hosted embeddings API instead of the local model — ask if you want that
version.


## RAG (retrieval-augmented generation)

RAG here means *index your data, retrieve it at prompt time* - nothing is fine-tuned.
`rag_service.py` chunks + embeds your resume, projects, weak areas, daily reflections,
sent emails and cover letters into `document_chunks`. Every write endpoint re-indexes
automatically, and each workflow retrieves what it needs:

| Workflow | Retrieves |
|---|---|
| Daily plan | past reflections, weak areas, project notes |
| Opportunity matching | per-opening resume/project evidence + past cover letters |
| Professor outreach | best-matching projects for that lab + a past email that got a reply |
| JARVIS chat | top chunks across everything, answer grounded in them (sources returned in `payload`) |

Endpoints: `POST /v1/rag/reindex`, `GET /v1/rag/search?user_id=&q=`, `GET /v1/rag/stats`.
Embedder: fastembed `bge-small-en-v1.5`; falls back to a hashed bag-of-words embedder if the
model can't load (`RAG_EMBEDDER=hash|fastembed|auto`). After changing embedders, call `/v1/rag/reindex`.
## Database maintenance

The backend uses SQLAlchemy with SQLite for local development and PostgreSQL when `DATABASE_URL` is provided. SQLite connections enable foreign-key enforcement, WAL mode, a busy timeout, and indexed user/date/status lookups.

Audit the local database:

```bash
python db_maintenance.py audit
```

The repair utility is intentionally conservative and is for cleaning development/test contamination without inventing workspace records:

```bash
python db_maintenance.py repair --email "you@example.com" --name "Your Name"
```

For production, set `DATABASE_URL` to managed PostgreSQL so application data survives redeploys independently of the application filesystem.

## Agent architecture

The request path is now:

```text
Jev typed router
   ↓
Groq structured fallback
   ↓
deterministic fallback
   ↓
validated workflow/tool
   ↓
approval/outbox for high-impact actions
   ↓
audit log
```

Set the routing variables in `.env`:

```env
JEV_ENABLED=false
JEV_API_URL=
JEV_API_KEY=
JEV_MODEL=
JEV_TIMEOUT_SECONDS=8
GROQ_ROUTER_MODEL=openai/gpt-oss-20b
GROQ_AGENT_MODEL=openai/gpt-oss-120b
ENABLE_DEV_SEED=false
```

`JEV_ENABLED=false` is the safe default until the production Jev endpoint and
schema are configured. The exact Jev transport remains provider-agnostic.

`POST /v1/seed` is disabled by default and only exists for explicit local testing
when `ENABLE_DEV_SEED=true`.
