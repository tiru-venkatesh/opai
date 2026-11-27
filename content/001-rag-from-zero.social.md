# Social adaptations for 001-rag-from-zero

Publish order: Dev.to first (the article), then LinkedIn the same day, then the X thread. Put links in the first
comment on LinkedIn and in the last post of the thread, not in the opening line.

## LinkedIn

A one-word bug made my RAG system answer "What is the capital of Australia?" from a note-taking FAQ.

I'd built a small document Q&A pipeline in Python. The demo worked. Then I wrote an evaluation set: 15 questions that have answers in the documents, plus 3 that don't.

The 3 that don't were the problem. The system should say "I couldn't find anything", and it didn't.

The cause: my stop-word list removed "the", "is" and "of", but not "what". The FAQ had headings like "What is X?". Every "what" question matched every heading.

The fix was one line. But the part I found useful was what the numbers did afterwards. At 600-character chunks it was a clean win. At 300 it cost me one answerable question. At 900 a different question started missing.

With 18 questions those are single-question swings, not statistics. The lesson isn't the stop-word list. It's that you only see any of this if you measure.

I wrote up the whole pipeline (chunking, BM25 + embeddings, rank fusion, citations) with the real code and the real before/after numbers. Link in the first comment.

#Python #RAG #LLM

## X thread

1/ A one-word bug made my RAG system answer "What is the capital of Australia?" from a note-taking FAQ.

Here's how an eval caught it, and what the fix did to the numbers. 🧵

2/ The setup: a small Python RAG pipeline. BM25 + embeddings, rank fusion, citations. The demo worked fine.

Then I wrote 18 test questions: 15 with answers in the docs, 3 that should return nothing.

3/ The 3 off-topic ones failed. Cause: my stop-word list had "the", "is", "of". Not "what".

The FAQ had headings like "What is X?". So every "what" question matched every heading, and one weak keyword hit was enough to pass the relevance floor.

4/ The fix: one line. Results at 600-char chunks: abstention 0.67 -> 1.00, hit@5 unchanged.

But at 300 chars it cost one answerable question ("how" had been helping a match). At 900 a different one flipped. 18 questions = single swings, not statistics.

5/ Moral: you only see this if you measure.

Full write-up with the real code (chunking, BM25, rank fusion, citation guard) and the before/after table: {{ARTICLE_URL}}

Code, MIT, under 800 lines: {{GITHUB_URL}}
