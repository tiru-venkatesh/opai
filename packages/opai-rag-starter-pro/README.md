# OPAI RAG Starter Pro

Everything you need to take a document Q&A prototype to something you can put in front of customers:

| | Lite (free, MIT) | **Pro** |
|---|---|---|
| Hybrid retrieval, citations (file + page), CLI | yes | yes (uses Lite) |
| Storage | single SQLite file | **Postgres + pgvector (HNSW index)**, or **ChromaDB** |
| Retrieval quality measurement | | **`opai-rag-eval`** with hit@k, MRR, abstention, CI gate |
| Multi-tenant API | single shared key | **one API key per customer, tenant isolation, rate limit, daily quota** |
| Deployment | | **Dockerfile, docker-compose, GitHub Actions CI** |

## 1. Install
```bash
pip install opai-rag-starter-lite                 # or: pip install git+https://github.com/<you>/opai-rag-starter-lite
pip install ".[api,claude]"                       # add ,chroma for the Chroma adapter
```
Optional better embeddings: `pip install fastembed` (downloads a ~130 MB model on first use).

## 2. Measure before you tune
```bash
opai-rag-eval --corpus examples/corpus --dataset examples/dataset.jsonl --chunk-sizes 300,600,900 -v
```
Output on the bundled sample (3 documents, 18 questions, hashed embedder, no model download):
```
 chunk  docs   hit@1   hit@5    MRR  abstain   p50ms   p95ms
   300     3    0.80    0.93   0.85     0.67     1.5     2.6
   600     3    0.80    1.00   0.87     1.00     1.0     1.7
   900     3    0.67    0.87   0.75     1.00     0.9     1.5
```
This is a tiny dataset meant to show how the tool works. Run it on your own documents and questions;
see `docs/EVAL.md`.

## 3. Pick a store
```python
from opai_rag import RAG
from opai_rag_pro.stores.pg import PgVectorStore        # Postgres + pgvector
# from opai_rag_pro.stores.chroma import ChromaStore    # or Chroma

rag = RAG(store=PgVectorStore("postgresql://user:pass@localhost/db"), namespace="customer-1")
rag.ingest_file("handbook.pdf")
print(rag.ask("What is the refund policy?")["answer"])
```
Postgres needs the `vector` extension (`pgvector/pgvector:pg16` image has it). Vector search runs in the
database; the final ranking (BM25 + rank fusion + MMR) is the same code as Lite.

## 4. Run the API
```bash
export OPAI_RAG_DSN=postgresql://user:pass@localhost/db
opai-rag-pro keys create --name acme          # prints the key once
uvicorn opai_rag_pro.api:app
```
Routes: `POST/GET /v1/documents`, `DELETE /v1/documents/{id}`, `POST /v1/ask`, `GET /v1/usage`, `GET /health`.
Docker: see `docs/DEPLOY.md`.

## Behaviour you can rely on
- A key's namespace is fixed server-side. Clients cannot read or delete another tenant's documents (tested).
- Keys are stored hashed. Revoking takes effect immediately.
- The daily ask quota is exact under concurrency (tested with 8 parallel workers against Postgres).
- A database holds one embedder. Switching is refused with a clear error instead of silently mixing vectors.
- If the LLM is down or unconfigured, `/v1/ask` still returns an extractive answer with citations.

## Known limits
- Rate limiting is per process (see `docs/DEPLOY.md`).
- Vector search is filtered by tenant after the HNSW scan, so a tenant with very few documents in a very large
  shared database can see slightly lower recall. For thousands of tenants, shard by database or add partitioning.
- No OCR, no reranking model, English-centric tokeniser.
- Keys and quotas require Postgres; the Chroma adapter is a library-level store.

## Tests
```bash
pip install -e ".[dev,chroma]"
OPAI_TEST_PG_DSN=postgresql://user:pass@localhost/db pytest      # Postgres tests skip if unset
```

See `LICENSE.txt`.
