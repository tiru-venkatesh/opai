# packages/

Two sellable products live here, developed together and released separately.

## opai-rag-starter-lite (free, MIT, public)
`make export-lite DEST=../opai-rag-starter-lite` copies only this package into a fresh folder and aborts if any
Pro-only code leaked in. `git init` there and push it as the public repo. Re-run the export for each release
(into an empty folder, then copy `.git` over, or use `git subtree split --prefix=packages/opai-rag-starter-lite`).

## opai-rag-starter-pro (paid, private)
`make package-pro` writes `dist/opai-rag-starter-pro-<version>.zip` (no app code, no git history). Upload that
to your store. Pro depends on Lite; in this repo both install editable (`make setup`).

## Why a monorepo
One change to retrieval (like the stop-word fix that the eval harness found) is made once and tested against
Lite, Pro and the app together. Pro never needs Lite to be published during development.

## Relationship to the app
`backend/rag_service.py` still has its own copy of the retrieval code; it is NOT yet rewired to import
`opai_rag`. The stop-word fix found by the eval harness (question words such as "what/who/how") has been
applied to both. Rewiring the app to depend on Lite is a separate, riskier change, so it is left out.
