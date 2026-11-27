"""OPAI RAG Starter (Lite): ingest documents, ask questions, get cited answers."""
from __future__ import annotations

import os
from typing import List, Optional

from . import answer as _ans
from .embed import HASH_TAG, embed_texts, using_fastembed
from .parse import ParseError, parse_file
from .retrieve import retrieve
from .store import Store
from .text import chunk_text

__all__ = ["RAG", "ParseError", "__version__"]
__version__ = "0.1.2"

MAX_DOC_CHARS = 400_000  # hard cap on text indexed per document


class RAG:
    """
    rag = RAG("my.db")
    rag.ingest_file("handbook.pdf")
    result = rag.ask("What is the refund policy?")
    result["answer"], result["sources"]   # sources carry filename + page

    `llm` is any callable (system_prompt, user_prompt) -> str. If omitted, Claude is used when ANTHROPIC_API_KEY is
    set; otherwise answers fall back to extractive mode (best sentences, still cited). `namespace` separates users.
    """

    def __init__(self, db_path: str = "opai_rag.db", namespace: str = "default", llm: Optional[_ans.LLM] = None,
                 store=None, chunk_chars: int = 600, chunk_overlap: int = 100):
        self.store = store if store is not None else Store(db_path)  # any object with the Store interface
        self.namespace = namespace
        self.chunk_chars, self.chunk_overlap = chunk_chars, chunk_overlap
        self._llm = llm
        self._llm_resolved = llm is not None

    @property
    def llm(self) -> Optional[_ans.LLM]:
        if not self._llm_resolved:
            self._llm, self._llm_resolved = _ans.anthropic_llm(), True
        return self._llm

    # -- ingestion
    def ingest_bytes(self, filename: str, data: bytes) -> dict:
        pages = parse_file(filename, data)
        pieces, total = [], 0
        for pg in pages:
            text = pg["text"][: max(0, MAX_DOC_CHARS - total)]
            total += len(text)
            pieces += [(pg["page"], c) for c in chunk_text(text, self.chunk_chars, self.chunk_overlap)]
            if total >= MAX_DOC_CHARS:
                break
        if not pieces:
            raise ParseError("no text found in file")
        vecs, tag = embed_texts([c for _, c in pieces])
        doc_id = self.store.replace_document(
            self.namespace, filename,
            [{"page": p, "content": c, "embedding": v, "embedder": tag} for (p, c), v in zip(pieces, vecs)],
        )
        return {"doc_id": doc_id, "filename": filename, "chunks": len(pieces), "embedder": tag}

    def ingest_file(self, path: str) -> dict:
        with open(path, "rb") as f:
            return self.ingest_bytes(os.path.basename(path), f.read())

    def ingest_text(self, name: str, text: str) -> dict:
        return self.ingest_bytes(name if "." in name else name + ".txt", text.encode("utf-8"))

    def documents(self) -> List[dict]:
        return self.store.list_documents(self.namespace)

    def delete(self, doc_id: str) -> bool:
        return self.store.delete_document(self.namespace, doc_id)

    # -- querying
    def search(self, question: str, k: int = 5, doc_ids: Optional[List[str]] = None) -> List[dict]:
        floor = 0.30 if using_fastembed() else 0.12  # cosine scales differ between embedders
        return retrieve(self.store, self.namespace, question, k=k, doc_ids=doc_ids, min_score=-1.0 if doc_ids else floor)

    def ask(self, question: str, k: int = 5, doc_ids: Optional[List[str]] = None) -> dict:
        """Returns {"answer", "mode": "llm"|"extractive"|"none", "sources": [{n,title,page,snippet,score}]}"""
        hits = self.search(question, k, doc_ids)
        if not hits:
            return {"answer": "I couldn't find anything relevant in the ingested documents.", "mode": "none", "sources": []}
        sources = _ans.build_sources(hits)
        text, mode = "", "extractive"
        if self.llm:
            try:
                ctx = _ans.numbered_context(sources, _ans.expand_neighbors(self.store, hits))
                raw = self.llm(_ans.SYSTEM_PROMPT, f"Context passages:\n{ctx}\n\nQuestion: {question}")
                text = _ans.prune_citations(raw, len(sources)).strip()
                mode = "llm" if text else "extractive"
            except Exception:
                text = ""  # never fail the request because the LLM is down
        if not text:
            text = _ans.extractive_answer(sources, hits, question)
        return {"answer": text, "mode": mode, "sources": sources}

    def close(self) -> None:
        self.store.close()
