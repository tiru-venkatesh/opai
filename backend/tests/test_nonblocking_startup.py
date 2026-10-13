"""Slow-request regressions. Run: cd backend && python -m pytest tests/test_nonblocking_startup.py -q
1. A request must never wait for the embedding model to download/load (it used to block PATCH /v1/profile for ~40 s).
2. A failed Firebase certificate fetch is not retried on every request."""
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["GROQ_API_KEY"] = ""

import auth_guard as AG  # noqa: E402
import rag_service as R  # noqa: E402


def _reset_rag(monkeypatch):
    monkeypatch.setattr(R, "_fe_model", None)
    monkeypatch.setattr(R, "_fe_failed", False)
    monkeypatch.setattr(R, "_fe_error", None)
    monkeypatch.setattr(R, "_fe_thread", None)


def test_embedding_never_waits_for_a_slow_model_load(monkeypatch):
    _reset_rag(monkeypatch)
    monkeypatch.delenv("RAG_EMBEDDER", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    gate = threading.Event()

    def slow_worker(mode):                     # stands in for a model download that takes a long time
        gate.wait(5)
    monkeypatch.setattr(R, "_fe_worker", slow_worker)
    t0 = time.time()
    vecs, tag = R.embed_texts(["python and rag projects"])
    assert time.time() - t0 < 1.0, "embed_texts blocked on the model load"
    assert tag == R.HASH_TAG and len(vecs[0]) == R.HASH_DIM       # hashed fallback until the model is ready
    gate.set()


def test_reindex_can_wait_for_the_real_model(monkeypatch):
    _reset_rag(monkeypatch)
    monkeypatch.delenv("RAG_EMBEDDER", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setattr(R, "_fe_worker", lambda mode: (time.sleep(0.2), setattr(R, "_fe_model", object())))
    assert R._load_fastembed() is None
    assert R._load_fastembed(wait=True) is not None


def test_failed_cert_fetch_is_not_retried_every_request(monkeypatch):
    monkeypatch.setattr(AG, "_keys", {}); monkeypatch.setattr(AG, "_keys_exp", 0.0); monkeypatch.setattr(AG, "_keys_retry_at", 0.0)
    calls = []

    def boom():
        calls.append(1)
        raise OSError("network unreachable")
    monkeypatch.setattr(AG, "_fetch_keys", boom)
    for _ in range(5):
        try:
            AG.get_keys()
        except Exception:
            pass
    assert len(calls) == 1                     # one attempt, then back-off instead of 5 x network timeout
