"""opai-rag-eval --corpus DIR --dataset FILE [--k 5] [--chunk-sizes 300,600,900] [--min-hit 0.8] [--json out.json]"""
from __future__ import annotations

import argparse
import json
import sys

from .harness import run


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="opai-rag-eval", description="Measure retrieval quality on your own documents.")
    p.add_argument("--corpus", required=True, help="directory of documents to ingest")
    p.add_argument("--dataset", required=True, help="JSONL of questions and expected passages")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--chunk-sizes", default="600", help="comma list, e.g. 300,600,900 to compare")
    p.add_argument("--min-hit", type=float, default=None, help="exit 1 if hit@k is below this for ANY run (for CI)")
    p.add_argument("--json", help="write the full report here")
    p.add_argument("-v", "--verbose", action="store_true", help="list failing questions")
    a = p.parse_args(argv)

    results = run(a.corpus, a.dataset, a.k, [int(x) for x in a.chunk_sizes.split(",")])
    hk = f"hit_at_{a.k}"
    print(f"{'chunk':>6} {'docs':>5} {'hit@1':>7} {'hit@'+str(a.k):>7} {'MRR':>6} {'abstain':>8} {'p50ms':>7} {'p95ms':>7}")
    for r in results:
        ab = "-" if r["abstain_accuracy"] is None else f"{r['abstain_accuracy']:.2f}"
        print(f"{r['chunk_chars']:>6} {r['documents']:>5} {r['hit_at_1']:>7.2f} {r[hk]:>7.2f} {r['mrr']:>6.2f} {ab:>8} "
              f"{r['latency_ms_p50']:>7} {r['latency_ms_p95']:>7}")
    if a.verbose:
        for r in results:
            for f in r["failures"]:
                print(f"  [chunk {r['chunk_chars']}] FAIL ({f['kind']}): {f['q']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
    if a.min_hit is not None and any(r[hk] < a.min_hit for r in results):
        print(f"\nFAILED: {hk} below {a.min_hit}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
