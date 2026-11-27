# Measuring retrieval quality

Guessing at chunk sizes and embedders is how RAG projects stall. Measure instead.

## 1. Write a dataset (JSONL)
```json
{"q": "How long is the refund window?", "doc": "handbook.md", "contains": ["14 days"]}
{"q": "How do I reset my password?", "doc": "faq.pdf", "contains": ["reset link"], "page": 3}
{"q": "What is the capital of Australia?", "no_answer": true}
```
- `contains`: phrases (all required, case-insensitive) that must appear in the retrieved chunk.
- `doc` / `page`: optional extra constraints.
- `no_answer`: passes only if retrieval returns nothing, which tests that the system declines to answer
  off-topic questions instead of returning loosely related text.

Start with 20 to 30 real questions from your users. Fewer than ~15 is noise.

## 2. Run
```bash
opai-rag-eval --corpus ./my_docs --dataset my_questions.jsonl --k 5 --chunk-sizes 300,600,900 -v
```
| column | meaning |
|---|---|
| hit@1 / hit@k | share of answerable questions whose expected passage was rank 1 / in the top k |
| MRR | mean of 1/rank of the first correct passage (1.0 = always first) |
| abstain | share of `no_answer` questions where nothing was retrieved |
| p50/p95 ms | retrieval latency (excludes the LLM call) |

`-v` lists every failing question. `--json report.json` saves the full report.

## 3. Gate it in CI
`--min-hit 0.85` exits non-zero if hit@k drops below 0.85 for any run. `.github/workflows/ci.yml` already does this.

## Reading the numbers
- High hit@5 but low hit@1: retrieval finds the passage but ranks it low. Try smaller chunks, or fastembed
  embeddings (`OPAI_RAG_EMBEDDER=fastembed`).
- Low abstain: the relevance floor is too permissive for your embedder. Tune `min_score` in `RAG.search`.
- A change that raises hit@k on 18 questions but not on 100 is not an improvement. Grow the dataset.
