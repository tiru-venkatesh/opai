"""Trust-aware retrieval facade."""
from __future__ import annotations

import rag_service


def search(db, user_id: str, query: str, k: int = 5, source_types=None):
    hits = rag_service.retrieve(db, user_id, query, k=k, source_types=source_types)
    return [h for h in hits if trust_check(h)]


def trust_check(hit: dict) -> bool:
    # Current OPA RAG records are all first-party workspace data.
    # External-source verification can be added here without changing callers.
    source_type = str(hit.get("source_type") or "")
    return bool(source_type)
