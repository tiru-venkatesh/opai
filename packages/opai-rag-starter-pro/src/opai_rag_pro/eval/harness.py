"""Retrieval evaluation: does the right passage come back in the top k?

Dataset: JSONL, one object per line:
  {"q": "How long is the refund window?", "doc": "handbook.md", "contains": ["14 days"]}
  {"q": "Who won the 1998 World Cup?", "no_answer": true}
A question PASSES at rank r if the r-th retrieved chunk is from `doc` (if given), includes every `contains`
phrase (case-insensitive), and is on `page` (if given). `no_answer` questions pass when NOTHING is retrieved.
"""
from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from opai_rag import RAG, ParseError


@dataclass
class Item:
    q: str
    doc: Optional[str] = None
    contains: List[str] = field(default_factory=list)
    page: Optional[int] = None
    no_answer: bool = False


def load_dataset(path: str) -> List[Item]:
    items = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
                items.append(Item(q=d["q"], doc=d.get("doc"), contains=[c.lower() for c in d.get("contains", [])],
                                  page=d.get("page"), no_answer=bool(d.get("no_answer", False))))
            except (ValueError, KeyError) as e:
                raise ValueError(f"{path}:{n}: bad dataset line ({e})") from e
    if not items:
        raise ValueError("dataset is empty")
    return items


def _matches(item: Item, hit: dict) -> bool:
    if item.doc and hit["filename"] != item.doc:
        return False
    if item.page is not None and hit["page"] != item.page:
        return False
    text = " ".join(hit["content"].lower().split())
    return all(c in text for c in item.contains)


def evaluate(rag: RAG, items: List[Item], k: int = 5) -> dict:
    rows, lat = [], []
    for it in items:
        t0 = time.perf_counter()
        hits = rag.search(it.q, k=k)
        lat.append((time.perf_counter() - t0) * 1000)
        if it.no_answer:
            rows.append({"q": it.q, "kind": "no_answer", "ok": not hits, "rank": None, "retrieved": len(hits)})
            continue
        rank = next((i for i, h in enumerate(hits, 1) if _matches(it, h)), None)
        rows.append({"q": it.q, "kind": "answerable", "ok": rank is not None, "rank": rank, "retrieved": len(hits)})
    ans = [r for r in rows if r["kind"] == "answerable"]
    neg = [r for r in rows if r["kind"] == "no_answer"]
    n = len(ans) or 1
    lat_sorted = sorted(lat)
    return {
        "k": k, "questions": len(rows), "answerable": len(ans), "no_answer": len(neg),
        "hit_at_1": round(sum(1 for r in ans if r["rank"] == 1) / n, 3),
        f"hit_at_{k}": round(sum(1 for r in ans if r["ok"]) / n, 3),
        "mrr": round(sum(1 / r["rank"] for r in ans if r["rank"]) / n, 3),
        "abstain_accuracy": round(sum(1 for r in neg if r["ok"]) / len(neg), 3) if neg else None,
        "latency_ms_p50": round(statistics.median(lat_sorted), 1),
        "latency_ms_p95": round(lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))], 1),
        "failures": [r for r in rows if not r["ok"]],
    }


def ingest_dir(rag: RAG, corpus_dir: str) -> int:
    n = 0
    for name in sorted(os.listdir(corpus_dir)):
        path = os.path.join(corpus_dir, name)
        if os.path.isfile(path):
            try:
                rag.ingest_file(path)
                n += 1
            except ParseError:
                continue
    return n


def run(corpus_dir: str, dataset: str, k: int = 5, chunk_sizes=(600,), store_factory: Optional[Callable[[], object]] = None) -> List[dict]:
    """One result per chunk size. Each run uses a fresh SQLite file unless `store_factory` supplies a store."""
    items, out = load_dataset(dataset), []
    for size in chunk_sizes:
        with tempfile.TemporaryDirectory() as tmp:
            store = store_factory() if store_factory else None
            rag = RAG(os.path.join(tmp, "eval.db"), store=store, chunk_chars=size, chunk_overlap=min(100, size // 5))
            rag._llm_resolved = True  # retrieval eval never calls an LLM
            docs = ingest_dir(rag, corpus_dir)
            res = evaluate(rag, items, k)
            res.update({"chunk_chars": size, "documents": docs})
            out.append(res)
            rag.close()
    return out
