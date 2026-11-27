# Empty by default; the monorepo override supplies the local Lite package as build context "lite".
FROM scratch AS lite

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Where to get the free Lite package from (PyPI name, or e.g. git+https://github.com/<you>/opai-rag-starter-lite)
ARG LITE_SPEC=opai-rag-starter-lite
# 1 = bundle the bge-small embedding model (better retrieval, ~130 MB). 0 = hashed fallback embedder.
ARG WITH_EMBEDDINGS=1

COPY pyproject.toml README.md LICENSE.txt ./
COPY src ./src
COPY --from=lite . /tmp/lite
RUN if [ -f /tmp/lite/pyproject.toml ]; then pip install /tmp/lite; else pip install "${LITE_SPEC}"; fi \
 && pip install ".[api,claude]" \
 && if [ "$WITH_EMBEDDINGS" = "1" ]; then \
      pip install fastembed && python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"; \
    fi

RUN useradd -m app && chown -R app /app
USER app
ENV OPAI_RAG_EMBEDDER=auto
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "opai_rag_pro.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
