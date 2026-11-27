"""ChromaDB adapter (embedded/persistent). Same interface as the SQLite and pgvector stores.

Vectors are computed by opai_rag (never by Chroma), so Chroma's own embedding function is disabled. Use this
if your team already runs Chroma. For multi-tenant API keys and quotas use PgVectorStore.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

try:
    import chromadb
except ImportError as e:  # pragma: no cover
    raise ImportError('ChromaStore needs: pip install "opai-rag-starter-pro[chroma]"') from e


class ChromaStore:
    def __init__(self, path: Optional[str] = "chroma_data", collection: str = "opai_chunks"):
        self.client = chromadb.PersistentClient(path=path) if path else chromadb.EphemeralClient()
        self.col = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"}, embedding_function=None)

    @staticmethod
    def _where(namespace: str, doc_ids: Optional[List[str]] = None, extra: Optional[dict] = None) -> dict:
        conds: list = [{"namespace": namespace}]
        if doc_ids:
            conds.append({"doc_id": {"$in": list(doc_ids)}})
        if extra:
            conds.append(extra)
        return conds[0] if len(conds) == 1 else {"$and": conds}

    # -- documents
    def replace_document(self, namespace: str, filename: str, pieces: List[dict]) -> str:
        self.col.delete(where=self._where(namespace, extra={"filename": filename}))
        doc_id = uuid.uuid4().hex
        if pieces:
            now = time.time()
            self.col.add(
                ids=[f"{doc_id}:{i}" for i in range(len(pieces))],
                embeddings=[p["embedding"] for p in pieces],
                documents=[p["content"] for p in pieces],
                metadatas=[{"namespace": namespace, "doc_id": doc_id, "filename": filename, "idx": i,
                            "page": p["page"] if p["page"] is not None else -1, "embedder": p["embedder"],
                            "n_chunks": len(pieces), "created_at": now} for i, p in enumerate(pieces)],
            )
        return doc_id

    def list_documents(self, namespace: str) -> List[dict]:
        got = self.col.get(where=self._where(namespace, extra={"idx": 0}), include=["metadatas"])
        docs = [{"id": m["doc_id"], "filename": m["filename"], "chunks": m["n_chunks"], "created_at": m["created_at"]}
                for m in got["metadatas"]]
        return sorted(docs, key=lambda d: -d["created_at"])

    def delete_document(self, namespace: str, doc_id: str) -> bool:
        got = self.col.get(where=self._where(namespace, [doc_id]), include=[])
        if not got["ids"]:
            return False
        self.col.delete(ids=got["ids"])
        return True

    # -- chunks
    @staticmethod
    def _rows(ids, docs, metas, embs) -> List[Dict]:
        out = []
        for i, d, m, e in zip(ids, docs, metas, embs):
            out.append({"id": i, "doc_id": m["doc_id"], "filename": m["filename"], "idx": m["idx"],
                        "page": None if m["page"] == -1 else m["page"], "content": d,
                        "embedding": [float(x) for x in e], "embedder": m["embedder"]})
        return out

    def chunks(self, namespace: str, doc_ids: Optional[List[str]] = None) -> List[Dict]:
        g = self.col.get(where=self._where(namespace, doc_ids), include=["documents", "metadatas", "embeddings"])
        return self._rows(g["ids"], g["documents"], g["metadatas"], g["embeddings"])

    def candidates(self, namespace: str, qvec, tag: str, doc_ids: Optional[List[str]], limit: int = 200) -> List[Dict]:
        where = self._where(namespace, doc_ids)
        total = len(self.col.get(where=where, include=[])["ids"])
        if total == 0:
            return []
        q = self.col.query(query_embeddings=[list(qvec)], n_results=min(limit, total), where=where,
                           include=["documents", "metadatas", "embeddings"])
        return self._rows(q["ids"][0], q["documents"][0], q["metadatas"][0], q["embeddings"][0])

    def update_embeddings(self, updates: List[tuple]) -> None:
        for cid, vec, tag in updates:
            self.col.update(ids=[str(cid)], embeddings=[list(vec)], metadatas=[{"embedder": tag}])

    def neighbors(self, doc_id: str, idxs: List[int]) -> Dict[int, str]:
        if not idxs:
            return {}
        g = self.col.get(ids=[f"{doc_id}:{i}" for i in idxs if i >= 0], include=["documents", "metadatas"])
        return {m["idx"]: d for d, m in zip(g["documents"], g["metadatas"])}

    def close(self) -> None:
        pass
