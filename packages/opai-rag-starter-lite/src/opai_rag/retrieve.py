"""Hybrid retrieval: dense cosine + BM25, fused with reciprocal-rank fusion, then MMR for diversity."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from .embed import cosine, embed_texts
from .store import Store
from .text import tokenize


def bm25_scores(query_toks: Sequence[str], docs_toks: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> List[float]:
    """Okapi BM25 over the candidate set (IDF computed on the namespace's own chunks)."""
    n = len(docs_toks)
    qs = list(dict.fromkeys(query_toks))
    if not n or not qs:
        return [0.0] * n
    avgdl = (sum(len(d) for d in docs_toks) / n) or 1.0
    df = {t: sum(1 for d in docs_toks if t in d) for t in qs}
    idf = {t: math.log(1.0 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in qs}
    out = []
    for d in docs_toks:
        tf: Dict[str, int] = {}
        for t in d:
            if t in idf:
                tf[t] = tf.get(t, 0) + 1
        dl = len(d) or 1
        out.append(sum(idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl)) for t, f in tf.items()))
    return out


def retrieve(
    store: Store,
    namespace: str,
    query: str,
    k: int = 5,
    doc_ids: Optional[List[str]] = None,
    min_score: float = 0.05,
) -> List[dict]:
    """Returns hits best-first: {score, content, filename, page, doc_id, idx}."""
    if not (query or "").strip():
        return []
    qvecs, tag = embed_texts([query])
    qvec = qvecs[0]
    # Stores with a vector index (see the Pro Kit) can pre-filter candidates in the database; the default
    # store simply returns every chunk in the namespace.
    if hasattr(store, "candidates"):
        rows = store.candidates(namespace, qvec, tag, doc_ids, limit=max(k * 40, 200))
    else:
        rows = store.chunks(namespace, doc_ids)
    if not rows:
        return []

    # self-heal chunks embedded with a different embedder
    stale = [r for r in rows if r["embedder"] != tag or not r["embedding"]]
    if stale:
        vecs, _ = embed_texts([r["content"] for r in stale])
        store.update_embeddings([(r["id"], v, tag) for r, v in zip(stale, vecs)])
        for r, v in zip(stale, vecs):
            r["embedding"], r["embedder"] = v, tag

    seen, uniq = set(), []
    for r in rows:
        key = " ".join(r["content"].split())[:160]
        if key not in seen:
            seen.add(key)
            uniq.append(r)

    qtoks = tokenize(query)
    cos = [cosine(r["embedding"] or [], qvec) for r in uniq]
    bm = bm25_scores(qtoks, [tokenize(r["content"]) for r in uniq])
    bmax = max(bm) or 1.0
    score = [c + 0.15 * (x / bmax) for c, x in zip(cos, bm)]

    keep = [i for i in range(len(uniq)) if score[i] >= min_score]
    if not keep:
        return []
    rrf = {i: 0.0 for i in keep}
    for ranking in (sorted(keep, key=lambda i: -cos[i]), sorted((i for i in keep if bm[i] > 0), key=lambda i: -bm[i])):
        for rank, i in enumerate(ranking):
            rrf[i] += 1.0 / (60 + rank + 1)
    order = sorted(keep, key=lambda i: (-rrf[i], -score[i]))
    pool = order[: max(k * 4, 12)]
    top = max(rrf[i] for i in pool) or 1.0
    rel = {i: rrf[i] / top for i in pool}

    lam, picked, rest = 0.7, [], list(pool)
    while rest and len(picked) < k:
        def mmr(i):
            div = max((cosine(uniq[i]["embedding"], uniq[j]["embedding"]) for j in picked), default=0.0)
            return lam * rel[i] - (1 - lam) * div

        best = max(rest, key=mmr)
        picked.append(best)
        rest.remove(best)
    return [
        {
            "score": round(score[i], 4),
            "content": uniq[i]["content"],
            "filename": uniq[i]["filename"],
            "page": uniq[i]["page"],
            "doc_id": uniq[i]["doc_id"],
            "idx": uniq[i]["idx"],
        }
        for i in picked
    ]
