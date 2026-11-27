.PHONY: setup test test-kits test-app eval export-lite package-pro check-page clean-install check-tutorial covers
PY ?= python3
VENV ?= .venv

setup:            ## one venv with the app deps and both kits (editable)
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r backend/requirements.txt pytest httpx reportlab
	$(VENV)/bin/pip install -q -e packages/opai-rag-starter-lite
	$(VENV)/bin/pip install -q -e "packages/opai-rag-starter-pro[dev,chroma]"

test-kits:        ## set OPAI_TEST_PG_DSN to include the Postgres tests
	OPAI_RAG_EMBEDDER=hash $(VENV)/bin/pytest -q packages/opai-rag-starter-lite
	OPAI_RAG_EMBEDDER=hash $(VENV)/bin/pytest -q packages/opai-rag-starter-pro

test-app:
	cd backend && OPAI_AUTH_MODE=off RAG_EMBEDDER=hash ../$(VENV)/bin/pytest -q tests/test_rag_pipeline.py tests/test_cross_user.py tests/test_auth_guard.py

test: test-kits test-app

eval:
	OPAI_RAG_EMBEDDER=hash $(VENV)/bin/opai-rag-eval --corpus packages/opai-rag-starter-pro/examples/corpus --dataset packages/opai-rag-starter-pro/examples/dataset.jsonl --chunk-sizes 300,600,900 -v

export-lite:      ## make/refresh the PUBLIC repo folder: make export-lite DEST=../opai-rag-starter-lite
	scripts/export_lite.sh $(DEST)

package-pro:      ## build the zip you upload to Gumroad
	scripts/package_pro.sh

check-page:       ## structural checks on the product page; add RELEASE=1 to fail on unfilled placeholders
	python3 scripts/check_product_page.py $(if $(RELEASE),--release,)

clean-install:    ## the "stranger" test: shipped artifacts only, fresh virtualenvs
	scripts/clean_install_test.sh

check-tutorial:   ## excerpts must match the source; snippets are executed. Publish copy: python scripts/check_tutorial.py --release --build GITHUB_URL=https://... ARTICLE_URL=https://...
	$(VENV)/bin/python scripts/check_tutorial.py

covers:           ## regenerate the page image, OG image and Dev.to/Gumroad covers (pip install pillow fonttools brotli)
	python3 scripts/make_covers.py
