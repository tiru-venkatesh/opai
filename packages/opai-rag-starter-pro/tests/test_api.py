import pytest
from fastapi.testclient import TestClient
from opai_rag_pro.api import create_app, RateLimiter
from conftest import CORPUS
import os

FILES = lambda: [("files", ("handbook.md", open(os.path.join(CORPUS, "handbook.md"), "rb").read(), "text/markdown"))]


@pytest.fixture
def env(pg_store):
    clock = {"t": 1000.0}
    app = create_app(pg_store, llm=None, rate_per_min=5, daily_asks=3, clock=lambda: clock["t"])
    return TestClient(app), pg_store, clock


def H(key): return {"Authorization": f"Bearer {key}"}


def test_requires_valid_key(env):
    c, store, _ = env
    assert c.get("/v1/documents").status_code == 401
    assert c.get("/v1/documents", headers=H("opai_nope")).status_code == 401
    assert c.get("/health").status_code == 200


def test_tenants_cannot_see_each_other(env):
    c, store, _ = env
    a, b = store.create_key("alice"), store.create_key("bob")
    assert c.post("/v1/documents", files=FILES(), headers=H(a)).status_code == 200
    assert len(c.get("/v1/documents", headers=H(a)).json()["documents"]) == 1
    assert c.get("/v1/documents", headers=H(b)).json()["documents"] == []
    doc_id = c.get("/v1/documents", headers=H(a)).json()["documents"][0]["id"]
    assert c.delete(f"/v1/documents/{doc_id}", headers=H(b)).status_code == 404  # cannot delete another tenant's doc
    assert c.post("/v1/ask", json={"question": "refund window"}, headers=H(b)).json()["sources"] == []
    assert c.post("/v1/ask", json={"question": "refund window"}, headers=H(a)).json()["sources"]


def test_namespace_cannot_be_chosen_by_client(env):
    c, store, _ = env
    a, b = store.create_key("alice"), store.create_key("bob")
    c.post("/v1/documents", files=FILES(), headers=H(a))
    r = c.post("/v1/ask", json={"question": "refund window", "namespace": "alice"}, headers=H(b))
    assert r.json()["sources"] == []


def test_revoked_key_stops_working(env):
    c, store, _ = env
    raw = store.create_key("temp")
    assert c.get("/v1/documents", headers=H(raw)).status_code == 200
    store.revoke_key(store.lookup_key(raw)["id"])
    assert c.get("/v1/documents", headers=H(raw)).status_code == 401


def test_rate_limit_then_refill(env):
    c, store, clock = env
    raw = store.create_key("rl")
    codes = [c.get("/v1/documents", headers=H(raw)).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    clock["t"] += 30  # 30 s at 5/min refills 2.5 tokens
    assert c.get("/v1/documents", headers=H(raw)).status_code == 200


def test_daily_quota_blocks_asks_not_other_routes(env):
    c, store, clock = env
    raw = store.create_key("qt")
    for _ in range(3):
        assert c.post("/v1/ask", json={"question": "x"}, headers=H(raw)).status_code == 200
        clock["t"] += 60  # keep the rate limiter out of the way
    r = c.post("/v1/ask", json={"question": "x"}, headers=H(raw))
    assert r.status_code == 429 and "quota" in r.json()["detail"]
    clock["t"] += 60
    assert c.get("/v1/usage", headers=H(raw)).json() == {"asks_today": 3, "daily_limit": 3, "remaining": 0}


def test_bad_upload_is_reported_not_500(env):
    c, store, _ = env
    raw = store.create_key("u")
    r = c.post("/v1/documents", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))], headers=H(raw))
    assert r.status_code == 200 and "unsupported" in r.json()["results"][0]["error"]


def test_rate_limiter_unit():
    t = {"v": 0.0}
    rl = RateLimiter(60, clock=lambda: t["v"])
    assert all(rl.allow(1) for _ in range(60)) and not rl.allow(1)
    t["v"] += 2
    assert rl.allow(1) and rl.allow(1) and not rl.allow(1)
    assert rl.allow(2)  # other keys unaffected
