import pytest
from opai_rag import RAG

HANDBOOK = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "examples", "corpus", "handbook.md"), "rb").read()


def mk(store, ns="a"):
    r = RAG(store=store, namespace=ns)
    r._llm_resolved = True
    return r


def test_contract_ingest_answer_cite(any_store):
    r = mk(any_store)
    assert r.ingest_bytes("handbook.md", HANDBOOK)["chunks"] == 3
    out = r.ask("how long is the refund window")
    assert "14 days" in out["answer"] and out["sources"][0]["title"] == "handbook.md"


def test_contract_namespace_isolation(any_store):
    mk(any_store, "alice").ingest_bytes("secret.txt", b"The vault code is swordfish.")
    bob = mk(any_store, "bob")
    assert bob.documents() == [] and bob.ask("vault code")["sources"] == []
    assert mk(any_store, "alice").ask("vault code")["sources"]


def test_contract_replace_and_delete(any_store):
    r = mk(any_store)
    r.ingest_bytes("a.txt", b"Alpha policy applies.")
    d = r.ingest_bytes("a.txt", b"Beta policy applies.")
    assert len(r.documents()) == 1 and "Beta" in r.ask("which policy applies")["answer"]
    assert r.delete(d["doc_id"]) and not r.delete(d["doc_id"]) and r.documents() == []


def test_contract_doc_scoped_ask(any_store):
    r = mk(any_store)
    a = r.ingest_bytes("a.txt", b"Pelicans eat fish near the harbour.")
    r.ingest_bytes("b.txt", b"Pelicans nest on cliffs in spring.")
    out = r.ask("pelicans", doc_ids=[a["doc_id"]])
    assert {s["title"] for s in out["sources"]} == {"a.txt"}


def test_pg_embedder_mismatch_is_refused(pg_store):
    from opai_rag_pro.stores.pg import EmbedderMismatch
    r = mk(pg_store)
    r.ingest_bytes("a.txt", b"hello world document")
    with pytest.raises(EmbedderMismatch):
        pg_store.replace_document("a", "b.txt", [{"page": None, "content": "x", "embedding": [0.0] * 512, "embedder": "other-model"}])


def test_pg_uses_hnsw_candidates_not_full_scan(pg_store):
    r = mk(pg_store)
    for i in range(30):
        r.ingest_bytes(f"d{i}.txt", f"Document number {i} talks about topic{i} in detail.".encode())
    from opai_rag.embed import embed_texts
    vec, tag = embed_texts(["topic7"])
    cands = pg_store.candidates("a", vec[0], tag, None, limit=5)
    assert len(cands) == 5 and cands[0]["filename"] == "d7.txt"


def test_pg_key_lifecycle_stores_only_hash(pg_store):
    raw = pg_store.create_key("acme")
    assert raw.startswith("opai_") and pg_store.lookup_key(raw)["namespace"] == "acme"
    import psycopg
    with pg_store.pool.connection() as c:
        stored = c.execute("SELECT key_hash FROM api_keys").fetchone()[0]
    assert raw not in stored and len(stored) == 64
    kid = pg_store.lookup_key(raw)["id"]
    assert pg_store.revoke_key(kid) and pg_store.lookup_key(raw) is None and not pg_store.revoke_key(kid)


def test_pg_quota_is_exact_under_concurrency(pg_store):
    import concurrent.futures as cf
    pg_store.create_key("q")
    kid = pg_store.list_keys()[0]["id"]
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: pg_store.bump_usage(kid, 10), range(40)))
    assert results.count(True) == 10 and pg_store.usage_today(kid) == 10
