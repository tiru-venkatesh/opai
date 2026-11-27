"""Postgres + pgvector store with an HNSW cosine index, API keys and per-key daily quotas.

Implements the same interface as opai_rag.store.Store, plus `candidates()`, which lets Postgres do the
vector search so retrieval no longer scans every chunk in Python.

Schema is created automatically (CREATE ... IF NOT EXISTS). One database holds ONE embedder: the first write
records its tag and dimension; mixing embedders is refused with a clear error (re-ingest after switching).
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Dict, List, Optional

from opai_rag.embed import HASH_DIM, using_fastembed

try:
    import psycopg
    from psycopg_pool import ConnectionPool
except ImportError as e:  # pragma: no cover
    raise ImportError('PgVectorStore needs: pip install "opai-rag-starter-pro[pg]"') from e

FASTEMBED_DIM = 384


class EmbedderMismatch(RuntimeError):
    pass


def _vec(v) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class PgVectorStore:
    def __init__(self, dsn: str, dim: Optional[int] = None, ef_search: int = 200, min_size: int = 1, max_size: int = 8):
        self.dim = dim or (FASTEMBED_DIM if using_fastembed() else HASH_DIM)
        self.ef_search = int(ef_search)
        self.pool = ConnectionPool(dsn, min_size=min_size, max_size=max_size, open=True, kwargs={"autocommit": False})
        self._init_schema()

    # ------------------------------------------------------------------ schema
    def _init_schema(self) -> None:
        with self.pool.connection() as c:
            c.execute("SELECT pg_advisory_xact_lock(727001)")  # serialise concurrent first-boots
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            c.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            c.execute(
                "CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, namespace TEXT NOT NULL, filename TEXT NOT NULL,"
                " chunks INTEGER NOT NULL DEFAULT 0, created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()))"
            )
            c.execute(
                f"CREATE TABLE IF NOT EXISTS chunks (id BIGSERIAL PRIMARY KEY, doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,"
                f" namespace TEXT NOT NULL, filename TEXT NOT NULL, idx INTEGER NOT NULL, page INTEGER, content TEXT NOT NULL,"
                f" embedding vector({self.dim}), embedder TEXT)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS ix_chunks_ns ON chunks(namespace)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id, idx)")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_docs_ns_file ON documents(namespace, filename)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_chunks_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")
            c.execute(
                "CREATE TABLE IF NOT EXISTS api_keys (id SERIAL PRIMARY KEY, name TEXT NOT NULL, namespace TEXT NOT NULL,"
                " key_hash TEXT NOT NULL UNIQUE, revoked BOOLEAN NOT NULL DEFAULT FALSE,"
                " created_at DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM now()))"
            )
            c.execute(
                "CREATE TABLE IF NOT EXISTS usage (key_id INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,"
                " day DATE NOT NULL, asks INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (key_id, day))"
            )

    def _check_embedder(self, c, tag: str) -> None:
        row = c.execute("SELECT value FROM meta WHERE key='embedder'").fetchone()
        if row is None:
            c.execute("INSERT INTO meta(key, value) VALUES ('embedder', %s) ON CONFLICT DO NOTHING", (tag,))
            row = c.execute("SELECT value FROM meta WHERE key='embedder'").fetchone()
        if row[0] != tag:
            raise EmbedderMismatch(
                f"this database was built with embedder '{row[0]}' but the current one is '{tag}'. "
                "Re-ingest into a fresh database (or set OPAI_RAG_EMBEDDER back)."
            )

    # --------------------------------------------------------------- documents
    def replace_document(self, namespace: str, filename: str, pieces: List[dict]) -> str:
        if pieces and len(pieces[0]["embedding"]) != self.dim:
            raise EmbedderMismatch(f"embedding has {len(pieces[0]['embedding'])} dims; this store uses {self.dim}")
        with self.pool.connection() as c:
            if pieces:
                self._check_embedder(c, pieces[0]["embedder"])
            c.execute("DELETE FROM documents WHERE namespace=%s AND filename=%s", (namespace, filename))
            doc_id = uuid.uuid4().hex
            c.execute("INSERT INTO documents(id, namespace, filename, chunks) VALUES (%s,%s,%s,%s)",
                      (doc_id, namespace, filename, len(pieces)))
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO chunks(doc_id, namespace, filename, idx, page, content, embedding, embedder)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s)",
                    [(doc_id, namespace, filename, i, p["page"], p["content"], _vec(p["embedding"]), p["embedder"])
                     for i, p in enumerate(pieces)],
                )
        return doc_id

    def list_documents(self, namespace: str) -> List[dict]:
        with self.pool.connection() as c:
            rows = c.execute("SELECT id, filename, chunks, created_at FROM documents WHERE namespace=%s ORDER BY created_at DESC",
                             (namespace,)).fetchall()
        return [{"id": r[0], "filename": r[1], "chunks": r[2], "created_at": r[3]} for r in rows]

    def delete_document(self, namespace: str, doc_id: str) -> bool:
        with self.pool.connection() as c:
            return c.execute("DELETE FROM documents WHERE namespace=%s AND id=%s", (namespace, doc_id)).rowcount > 0

    # ------------------------------------------------------------------ chunks
    _COLS = "id, doc_id, filename, idx, page, content, embedding::text, embedder"

    @staticmethod
    def _row(r) -> Dict:
        return {"id": r[0], "doc_id": r[1], "filename": r[2], "idx": r[3], "page": r[4], "content": r[5],
                "embedding": json.loads(r[6]) if r[6] else None, "embedder": r[7]}

    def chunks(self, namespace: str, doc_ids: Optional[List[str]] = None) -> List[Dict]:
        sql, args = f"SELECT {self._COLS} FROM chunks WHERE namespace=%s", [namespace]
        if doc_ids:
            sql, args = sql + " AND doc_id = ANY(%s)", args + [list(doc_ids)]
        with self.pool.connection() as c:
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def candidates(self, namespace: str, qvec, tag: str, doc_ids: Optional[List[str]], limit: int = 200) -> List[Dict]:
        """Top-`limit` chunks by cosine distance, computed inside Postgres (HNSW)."""
        with self.pool.connection() as c:
            self._check_embedder(c, tag)
            c.execute(f"SET LOCAL hnsw.ef_search = {self.ef_search}")  # int-cast in __init__
            sql = f"SELECT {self._COLS} FROM chunks WHERE namespace=%s"
            args: list = [namespace]
            if doc_ids:
                sql, args = sql + " AND doc_id = ANY(%s)", args + [list(doc_ids)]
            sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
            args += [_vec(qvec), int(limit)]
            return [self._row(r) for r in c.execute(sql, args).fetchall()]

    def update_embeddings(self, updates: List[tuple]) -> None:
        with self.pool.connection() as c, c.cursor() as cur:
            cur.executemany("UPDATE chunks SET embedding=%s::vector, embedder=%s WHERE id=%s",
                            [(_vec(v), tag, cid) for cid, v, tag in updates])

    def neighbors(self, doc_id: str, idxs: List[int]) -> Dict[int, str]:
        if not idxs:
            return {}
        with self.pool.connection() as c:
            rows = c.execute("SELECT idx, content FROM chunks WHERE doc_id=%s AND idx = ANY(%s)", (doc_id, list(idxs))).fetchall()
        return {r[0]: r[1] for r in rows}

    # ----------------------------------------------------------- keys + quotas
    def create_key(self, name: str, namespace: Optional[str] = None) -> str:
        """Returns the raw key ONCE. Only its SHA-256 is stored."""
        raw = "opai_" + secrets.token_urlsafe(32)
        with self.pool.connection() as c:
            c.execute("INSERT INTO api_keys(name, namespace, key_hash) VALUES (%s,%s,%s)",
                      (name, namespace or name, _hash_key(raw)))
        return raw

    def lookup_key(self, raw: str) -> Optional[dict]:
        with self.pool.connection() as c:
            r = c.execute("SELECT id, name, namespace FROM api_keys WHERE key_hash=%s AND NOT revoked", (_hash_key(raw),)).fetchone()
        return {"id": r[0], "name": r[1], "namespace": r[2]} if r else None

    def revoke_key(self, key_id: int) -> bool:
        with self.pool.connection() as c:
            return c.execute("UPDATE api_keys SET revoked=TRUE WHERE id=%s AND NOT revoked", (key_id,)).rowcount > 0

    def list_keys(self) -> List[dict]:
        with self.pool.connection() as c:
            rows = c.execute("SELECT id, name, namespace, revoked, created_at FROM api_keys ORDER BY id").fetchall()
        return [{"id": r[0], "name": r[1], "namespace": r[2], "revoked": r[3], "created_at": r[4]} for r in rows]

    def bump_usage(self, key_id: int, daily_limit: int) -> bool:
        """Atomically count one ask for today. False = quota exhausted (nothing is counted)."""
        with self.pool.connection() as c:
            r = c.execute(
                "INSERT INTO usage(key_id, day, asks) VALUES (%s, CURRENT_DATE, 1) "
                "ON CONFLICT (key_id, day) DO UPDATE SET asks = usage.asks + 1 WHERE usage.asks < %s RETURNING asks",
                (key_id, int(daily_limit)),
            ).fetchone()
        return r is not None

    def usage_today(self, key_id: int) -> int:
        with self.pool.connection() as c:
            r = c.execute("SELECT asks FROM usage WHERE key_id=%s AND day=CURRENT_DATE", (key_id,)).fetchone()
        return r[0] if r else 0

    def close(self) -> None:
        self.pool.close()
