"""SQLite store (stdlib only). One file, no server. Vectors are JSON; retrieval scans the namespace's chunks.

That is deliberate for a starter: zero setup, easy to read. It is fine up to roughly tens of thousands of chunks.
Beyond that, swap in a vector index (the Pro Kit ships pgvector and Chroma adapters).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, namespace TEXT NOT NULL, filename TEXT NOT NULL,
  chunks INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  namespace TEXT NOT NULL, filename TEXT NOT NULL, idx INTEGER NOT NULL, page INTEGER,
  content TEXT NOT NULL, embedding TEXT, embedder TEXT
);
CREATE INDEX IF NOT EXISTS ix_chunks_ns ON chunks(namespace);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
"""


class Store:
    def __init__(self, path: str = "opai_rag.db"):
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    # -- documents
    def replace_document(self, namespace: str, filename: str, pieces: List[dict]) -> str:
        """pieces: [{page, content, embedding, embedder}]. Re-ingesting the same filename replaces it."""
        with self._lock, self.db:
            self.db.execute("DELETE FROM documents WHERE namespace=? AND filename=?", (namespace, filename))
            doc_id = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO documents(id, namespace, filename, chunks, created_at) VALUES (?,?,?,?,?)",
                (doc_id, namespace, filename, len(pieces), time.time()),
            )
            self.db.executemany(
                "INSERT INTO chunks(doc_id, namespace, filename, idx, page, content, embedding, embedder) VALUES (?,?,?,?,?,?,?,?)",
                [
                    (doc_id, namespace, filename, i, p["page"], p["content"], json.dumps(p["embedding"]), p["embedder"])
                    for i, p in enumerate(pieces)
                ],
            )
        return doc_id

    def list_documents(self, namespace: str) -> List[dict]:
        with self._lock:
            rows = self.db.execute(
                "SELECT id, filename, chunks, created_at FROM documents WHERE namespace=? ORDER BY created_at DESC",
                (namespace,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_document(self, namespace: str, doc_id: str) -> bool:
        with self._lock, self.db:
            cur = self.db.execute("DELETE FROM documents WHERE namespace=? AND id=?", (namespace, doc_id))
            return cur.rowcount > 0

    # -- chunks
    def chunks(self, namespace: str, doc_ids: Optional[List[str]] = None) -> List[Dict]:
        sql = "SELECT id, doc_id, filename, idx, page, content, embedding, embedder FROM chunks WHERE namespace=?"
        args: list = [namespace]
        if doc_ids:
            sql += f" AND doc_id IN ({','.join('?' * len(doc_ids))})"
            args += list(doc_ids)
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["embedding"] = json.loads(d["embedding"]) if d["embedding"] else None
            out.append(d)
        return out

    def update_embeddings(self, updates: List[tuple]) -> None:
        """updates: [(chunk_id, embedding, embedder)]"""
        with self._lock, self.db:
            self.db.executemany(
                "UPDATE chunks SET embedding=?, embedder=? WHERE id=?",
                [(json.dumps(v), tag, cid) for cid, v, tag in updates],
            )

    def neighbors(self, doc_id: str, idxs: List[int]) -> Dict[int, str]:
        if not idxs:
            return {}
        with self._lock:
            rows = self.db.execute(
                f"SELECT idx, content FROM chunks WHERE doc_id=? AND idx IN ({','.join('?' * len(idxs))})",
                [doc_id, *idxs],
            ).fetchall()
        return {r["idx"]: r["content"] for r in rows}

    def close(self) -> None:
        self.db.close()
