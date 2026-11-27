"""Optional HTTP API:  pip install "opai-rag-starter-lite[api]"  &&  uvicorn opai_rag.api:app

Set OPAI_RAG_API_KEY to require `Authorization: Bearer <key>` on every route (strongly recommended off localhost).
"""
from __future__ import annotations

import hmac
import os
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import RAG, ParseError


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    k: int = Field(5, ge=1, le=20)
    doc_ids: Optional[List[str]] = None


def create_app(db_path: Optional[str] = None) -> FastAPI:
    rag = RAG(db_path or os.getenv("OPAI_RAG_DB", "opai_rag.db"))
    app = FastAPI(title="OPAI RAG Starter (Lite)", version="0.1.0")

    def auth(authorization: Optional[str] = Header(default=None)):
        key = os.getenv("OPAI_RAG_API_KEY", "")
        if not key:
            return
        supplied = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied, key):
            raise HTTPException(401, "missing or invalid API key")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/documents", dependencies=[Depends(auth)])
    async def upload(files: List[UploadFile] = File(...)):
        if len(files) > 10:
            raise HTTPException(400, "max 10 files per request")
        results = []
        for f in files:
            try:
                results.append(rag.ingest_bytes(f.filename or "upload", await f.read()))
            except ParseError as e:
                results.append({"filename": f.filename, "error": str(e)})
        return {"results": results}

    @app.get("/documents", dependencies=[Depends(auth)])
    def documents():
        return {"documents": rag.documents()}

    @app.delete("/documents/{doc_id}", dependencies=[Depends(auth)])
    def delete(doc_id: str):
        if not rag.delete(doc_id):
            raise HTTPException(404, "document not found")
        return {"deleted": doc_id}

    @app.post("/ask", dependencies=[Depends(auth)])
    def ask(body: Ask):
        return rag.ask(body.question, k=body.k, doc_ids=body.doc_ids)

    return app


app = create_app() if os.getenv("OPAI_RAG_AUTOSTART", "1") == "1" else None
