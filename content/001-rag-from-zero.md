---
title: "RAG from zero: hybrid search and cited answers in under 800 lines of Python (and the one-word bug my eval caught)"
published: false
description: "How a small RAG pipeline works end to end: chunking, BM25 + embeddings, rank fusion, MMR, citations. Plus a real retrieval bug found by measuring."
tags: python, ai, rag, tutorial
---

Most RAG tutorials end at "it answered my question". The harder question is **"how do I know it's retrieving the right thing?"**

This post walks through a small, complete RAG pipeline: ingest documents, retrieve with hybrid search, answer with citations. Then it shows a bug that an evaluation run caught and that no demo would have.

The code is [opai-rag-starter-lite]({{GITHUB_URL}}): MIT licensed, pure Python, one SQLite file, under 800 lines in total. Every code block below is either copied verbatim from the repository or executed and checked, so what you read is what runs.

## The pipeline

```
documents -> chunks -> embeddings
question  -> embedding + keywords -> candidates -> fuse ranks -> diversify -> numbered context -> answer with [1] [2]
```

## 1. Chunking

Chunks are packed paragraph-first, so a heading and its body stay together. Paragraphs that are too long fall back to sentence splitting with a small overlap. The paragraph split is one regex:

<!-- excerpt: packages/opai-rag-starter-lite/src/opai_rag/text.py -->
```python
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[\-\u2022*]\s)", text) if p.strip()]
```

Chunk size changes results noticeably. Section 5 has a measured example.

## 2. Embeddings, with a safety net

The embedder is `fastembed` if it's installed, otherwise a hashed bag-of-words vector that needs no download. Every stored chunk records which embedder made it, and retrieval re-embeds anything that doesn't match:

<!-- excerpt: packages/opai-rag-starter-lite/src/opai_rag/retrieve.py -->
```python
    stale = [r for r in rows if r["embedder"] != tag or not r["embedding"]]
```

That one line means you can switch embedders (or fix a tokenizer, see section 5) without a migration: old chunks refresh themselves the next time they're searched.

## 3. Hybrid retrieval

Embeddings are good at meaning and bad at exact terms like product codes, names and "14 days". BM25 is the opposite. So we run both. BM25 is short enough to read in full:

<!-- excerpt: packages/opai-rag-starter-lite/src/opai_rag/retrieve.py -->
```python
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
```

The two signals are combined in two steps. First, a score with a relevance floor, which decides whether a chunk is a candidate at all. Then reciprocal rank fusion, which merges the two *rankings* so you never have to compare a cosine with a BM25 score directly:

<!-- excerpt: packages/opai-rag-starter-lite/src/opai_rag/retrieve.py -->
```python
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
```

Finally MMR picks the top results while penalising near-duplicates, so your five sources aren't the same paragraph five times. Note the `return []` above: if nothing clears the floor, the system returns **nothing**. That is how it can say "I couldn't find anything" instead of making something up.

## 4. Answers that cite their sources

The model gets numbered passages and a system prompt that says to cite only those numbers. Models still occasionally invent a `[7]`, so a one-line guard strips any citation that points at a passage that doesn't exist:

<!-- excerpt: packages/opai-rag-starter-lite/src/opai_rag/answer.py -->
```python
def prune_citations(answer: str, n: int) -> str:
    """Drop [k] markers that point at passages that don't exist."""
    return re.sub(r"\[(\d+)\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= n else "", answer)
```

Here is the whole thing end to end. With no API key set it falls back to extractive answers (the best sentences, still cited); with `ANTHROPIC_API_KEY` set you get a written answer instead.

<!-- run -->
```python
from opai_rag import RAG

rag = RAG(":memory:", chunk_chars=120, chunk_overlap=20)
rag.ingest_text(
    "handbook.md",
    "## Refunds\nCustomers can request a full refund within 14 days of purchase.\n\n"
    "## Support hours\nSupport is available Monday to Friday, 9am to 6pm IST.",
)
result = rag.ask("When is support open?")
print(result["answer"])
print([s["title"] for s in result["sources"]])
```

<!-- output -->
```text
Here is what I found in your documents:
- handbook.md: ## Support hours Support is available Monday to Friday, 9am to 6pm IST. [1]
['handbook.md']
```

## 5. The bug: one word that defeated "I don't know"

I built an evaluation harness for this pipeline: a JSONL file of questions with the passage that should answer each, plus a few **off-topic** questions that should return nothing. It reports hit@k, MRR and an "abstain" score (the share of off-topic questions where nothing came back).

The first run on a three-document corpus (a handbook, a note-app FAQ, a security policy) looked fine on answerable questions and bad on the others. `What is the capital of Australia?` returned a passage from a note-taking FAQ.

The cause was one list. Common words are removed before keyword matching, and I'd included "the", "is", "of", but not **"what"**. The FAQ had headings like `## What is Nimbus Notes?`. So the question's only surviving keywords were `what`, `capital` and `australia`, and `what` matched every "What is..." heading. That produced a tiny BM25 score, and because the score is normalised by the best match, even a weak lexical hit earns the full `+0.15` bonus. That's enough to clear the relevance floor on its own.

The fix is one line (adding `what who whom whose when where which why how` to the stop-word list). The tokenizer now gives:

<!-- run -->
```python
from opai_rag.text import tokenize

print(tokenize("What is the capital of Australia?"))
```

<!-- output -->
```text
['capital', 'australia']
```

And a regression test pins it down:

<!-- excerpt: packages/opai-rag-starter-lite/tests/test_core.py -->
```python
def test_question_words_alone_do_not_match(rag):
    # regression: "what"/"who"/"how" matched every "What is..." heading and defeated abstention
    rag.ingest_bytes("faq.md", b"# FAQ\n\n## What is Nimbus?\nNimbus is a note app.\n\n## What are the limits?\nTwo gigabytes.")
    assert rag.ask("What is the capital of Australia?")["sources"] == []
    assert rag.ask("what is nimbus")["sources"]
```

Because chunks remember which embedder version made them (section 2), bumping the tag was all it took for existing databases to re-embed themselves.

### What it did to the numbers

Same corpus, same 18 questions (15 answerable, 3 off-topic), three chunk sizes, before and after the fix:

| Chunk size | hit@5 before | hit@5 after | abstain before | abstain after |
|---|---|---|---|---|
| 300 chars | 1.00 | 0.93 | 0.33 | 0.67 |
| 600 chars | 1.00 | 1.00 | 0.67 | 1.00 |
| 900 chars | 0.87 | 0.87 | 0.67 | 1.00 |

At 600 characters it's a clean win. At 300 it isn't free: "How do I get my notes out of the app?" stopped being found. The matching FAQ heading starts with "How do I export my notes?", so "how" was probably helping that match. That is the usual trade-off of any stop-word change. And at 900, a different question started missing while another was fixed. With 18 questions these are single-question swings, not statistics; the point is that **you only see them if you measure**.

## 6. What's still wrong

- At 300-character chunks one off-topic question (`Who painted the Mona Lisa?`) still returns a result. It has no keyword overlap at all. The hashed fallback embedder produces a cosine of about 0.15 from collisions, which clears the 0.12 floor. A real embedding model has a different score scale (the code uses a higher floor, 0.30, for fastembed), but I haven't measured that, so I won't claim it fixes it.
- Retrieval scans every chunk in the namespace. Fine for thousands of chunks; not for millions.
- No OCR, and the tokenizer is English-centric.

## Try it

```bash
git clone {{GITHUB_URL}}
cd opai-rag-starter-lite
pip install .
opai-rag ingest examples/handbook.md
opai-rag ask "Can I get a refund after three weeks?"
```

The evaluation harness I used above, along with Postgres/pgvector and Chroma stores, per-customer API keys and Docker deployment files, is part of the paid [Pro kit](https://opai.live/products/python-rag-starter). The free version above has everything in sections 1 to 4.

What would you test this pipeline on first? Tell me what breaks.
