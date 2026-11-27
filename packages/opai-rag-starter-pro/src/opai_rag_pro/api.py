"""Multi-tenant HTTP API.

Tenant = API key. The namespace comes from the key, never from the request, so one customer cannot name
another's data. Per key: in-memory rate limit (per process) and a daily ask quota (in Postgres, shared by workers).

  OPAI_RAG_DSN              postgresql://user:pass@host/db           (required)
  OPAI_RAG_RATE_PER_MIN     default 60   requests per key per minute
  OPAI_RAG_DAILY_ASKS       default 500  LLM-backed /ask calls per key per day
  OPAI_RAG_MAX_UPLOADS      default 10   files per upload request
"""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from opai_rag import RAG, ParseError
from opai_rag.answer import anthropic_llm
from .stores.pg import EmbedderMismatch, PgVectorStore


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)
    doc_ids: Optional[List[str]] = None


class RateLimiter:
    """Token bucket per key. Per-process: behind several workers use a gateway or Redis for a global limit."""

    def __init__(self, per_minute: int, clock=time.monotonic):
        self.rate, self.cap, self.clock = per_minute / 60.0, float(per_minute), clock
        self.state: Dict[int, tuple] = {}
        self.lock = threading.Lock()

    def allow(self, key_id: int) -> bool:
        with self.lock:
            now = self.clock()
            tokens, last = self.state.get(key_id, (self.cap, now))
            tokens = min(self.cap, tokens + (now - last) * self.rate)
            if tokens < 1:
                self.state[key_id] = (tokens, now)
                return False
            self.state[key_id] = (tokens - 1, now)
            return True


def create_app(store: Optional[PgVectorStore] = None, llm=None, rate_per_min: Optional[int] = None,
               daily_asks: Optional[int] = None, clock=time.monotonic) -> FastAPI:
    store = store or PgVectorStore(os.environ["OPAI_RAG_DSN"])
    llm = llm if llm is not None else anthropic_llm()  # resolved once, shared
    limiter = RateLimiter(rate_per_min or int(os.getenv("OPAI_RAG_RATE_PER_MIN", "60")), clock)
    quota = daily_asks if daily_asks is not None else int(os.getenv("OPAI_RAG_DAILY_ASKS", "500"))
    max_uploads = int(os.getenv("OPAI_RAG_MAX_UPLOADS", "10"))
    app = FastAPI(title="OPAI RAG Pro", version="0.1.0")

    def tenant(authorization: Optional[str] = Header(default=None)) -> dict:
        raw = (authorization or "").removeprefix("Bearer ").strip()
        key = store.lookup_key(raw) if raw else None
        if not key:
            raise HTTPException(401, "missing or invalid API key")
        if not limiter.allow(key["id"]):
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "10"})
        return key

    def rag_for(key: dict) -> RAG:
        r = RAG(store=store, namespace=key["namespace"], llm=llm)
        r._llm_resolved = True  # llm may be None: extractive mode
        return r

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/v1/documents")
    async def upload(files: List[UploadFile] = File(...), key: dict = Depends(tenant)):
        if len(files) > max_uploads:
            raise HTTPException(400, f"max {max_uploads} files per request")
        rag, out = rag_for(key), []
        for f in files:
            try:
                out.append(rag.ingest_bytes(f.filename or "upload", await f.read()))
            except ParseError as e:
                out.append({"filename": f.filename, "error": str(e)})
            except EmbedderMismatch as e:
                raise HTTPException(409, str(e))
        return {"results": out}

    @app.get("/v1/documents")
    def documents(key: dict = Depends(tenant)):
        return {"documents": rag_for(key).documents()}

    @app.delete("/v1/documents/{doc_id}")
    def delete(doc_id: str, key: dict = Depends(tenant)):
        if not rag_for(key).delete(doc_id):
            raise HTTPException(404, "document not found")
        return {"deleted": doc_id}

    @app.post("/v1/ask")
    def ask(body: Ask, key: dict = Depends(tenant)):
        if not store.bump_usage(key["id"], quota):
            raise HTTPException(429, f"daily quota of {quota} questions reached", headers={"Retry-After": "3600"})
        try:
            return rag_for(key).ask(body.question, k=body.k, doc_ids=body.doc_ids)
        except EmbedderMismatch as e:
            raise HTTPException(409, str(e))

    @app.get("/v1/usage")
    def usage(key: dict = Depends(tenant)):
        used = store.usage_today(key["id"])
        return {"asks_today": used, "daily_limit": quota, "remaining": max(0, quota - used)}

    return app


def _lazy():  # `uvicorn opai_rag_pro.api:app` needs a module-level app, but importing must not need a DB
    return create_app()


def __getattr__(name):
    if name == "app":
        return _lazy()
    raise AttributeError(name)
