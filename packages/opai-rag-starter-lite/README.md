# OPAI RAG Starter (Lite)

Ask questions about your documents and get answers with citations (file + page). Small enough to read in an
afternoon, with no vector database or server to run.

```
Question  ->  hybrid retrieval (embeddings + BM25 -> rank fusion -> MMR)  ->  numbered context
          ->  LLM answer with [1] [2] citations   (or extractive answer if no LLM is configured)
```

## Quickstart (about 2 minutes)

```bash
git clone <this repo> && cd opai-rag-starter-lite
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .

opai-rag ingest examples/handbook.md
opai-rag ask "Can I get a refund after three weeks?"
```

Without an LLM key you get the most relevant sentences, each tagged with its source. For full written answers:

```bash
pip install ".[claude]"
export ANTHROPIC_API_KEY=sk-ant-...        # optional: OPAI_RAG_MODEL=<model name>
opai-rag ask "Summarise the refund and support policies"
```

Better embeddings (downloads a ~130 MB model on first use): `pip install ".[embeddings]"`.

## Use it from Python

```python
from opai_rag import RAG

rag = RAG("my.db", namespace="user-123")      # namespace keeps users' documents separate
rag.ingest_file("handbook.pdf")
result = rag.ask("What is the refund policy?")
print(result["answer"])
for s in result["sources"]:
    print(s["n"], s["title"], s["page"], s["snippet"])
```

Bring any LLM: `RAG(llm=lambda system, user: my_call(system, user))`.

## HTTP API

```bash
pip install ".[api]"
export OPAI_RAG_API_KEY=change-me          # requires "Authorization: Bearer change-me" on all routes except /health
uvicorn opai_rag.api:app
```

| Route | Purpose |
|---|---|
| `POST /documents` | multipart upload, field `files` (PDF, DOCX, TXT, MD, CSV; 10 MB each) |
| `GET /documents` | list |
| `DELETE /documents/{id}` | remove |
| `POST /ask` | `{"question": "...", "k": 5, "doc_ids": [...]}` |

If `OPAI_RAG_API_KEY` is unset the API is open. Fine on localhost, not on the internet.

## How it behaves

- Answers cite only passages that were retrieved; citation numbers that don't exist are stripped.
- Document text is passed to the model as untrusted data, with instructions not to follow commands inside it.
- If the LLM call fails, you still get an extractive cited answer instead of an error.
- Re-ingesting a filename replaces the old version.

## Limits (by design)

- Retrieval scans all chunks in a namespace: fine to roughly tens of thousands of chunks, then you want a vector index.
- No OCR: scanned PDFs are rejected with a clear message.
- English-centric tokeniser and default embedder.
- Single SQLite file; no auth beyond the optional API key; no per-user accounts.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

## Licence

MIT. See `LICENSE`.
