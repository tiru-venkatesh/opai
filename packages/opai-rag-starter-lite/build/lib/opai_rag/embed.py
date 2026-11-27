"""Embeddings: fastembed (bge-small) if installed, else a dependency-free hashed bag-of-words fallback.

Every chunk records which embedder produced it, so switching embedders re-embeds lazily and is always safe.
OPAI_RAG_EMBEDDER = auto (default) | hash | fastembed
"""
from __future__ import annotations

import logging
import math
import os
import zlib
from typing import Dict, List, Sequence, Tuple

from .text import tokenize

log = logging.getLogger("opai_rag.embed")

FASTEMBED_TAG = "bge-small-en-v1.5"
HASH_DIM = 512
HASH_TAG = f"hash-{HASH_DIM}-s2"

_model = None
_failed = False


def _mode() -> str:
    return (os.getenv("OPAI_RAG_EMBEDDER") or "auto").lower()


def _load():
    global _model, _failed
    if _model is not None or _failed:
        return _model
    if _mode() == "hash":
        _failed = True
        return None
    try:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    except Exception as e:  # not installed, offline, no disk...
        _failed = True
        if _mode() == "fastembed":
            raise RuntimeError(f"OPAI_RAG_EMBEDDER=fastembed but it could not load: {e}") from e
        log.info("fastembed unavailable (%s); using hashed fallback embedder", e)
    return _model


def using_fastembed() -> bool:
    return _load() is not None


def _hash_embed(text: str) -> List[float]:
    toks = tokenize(text)
    feats: Dict[int, float] = {}
    counts: Dict[str, int] = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    for t, c in counts.items():
        h = zlib.crc32(t.encode())
        sign = 1.0 if (h >> 16) & 1 else -1.0
        feats[h % HASH_DIM] = feats.get(h % HASH_DIM, 0.0) + sign * (1.0 + math.log(c))
    for a, b in zip(toks, toks[1:]):
        h = zlib.crc32(f"{a} {b}".encode())
        sign = 1.0 if (h >> 16) & 1 else -1.0
        feats[h % HASH_DIM] = feats.get(h % HASH_DIM, 0.0) + sign * 0.5
    norm = math.sqrt(sum(v * v for v in feats.values())) or 1.0
    vec = [0.0] * HASH_DIM
    for i, v in feats.items():
        vec[i] = v / norm
    return vec


def embed_texts(texts: Sequence[str]) -> Tuple[List[List[float]], str]:
    """Returns (vectors, embedder_tag)."""
    model = _load()
    if model is not None:
        try:
            return [v.tolist() for v in model.embed(list(texts))], FASTEMBED_TAG
        except Exception as e:
            log.warning("fastembed embed() failed (%s); using hashed fallback", e)
    return [_hash_embed(t) for t in texts], HASH_TAG


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)
