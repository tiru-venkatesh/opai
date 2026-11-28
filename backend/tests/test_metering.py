import json
from types import SimpleNamespace

import pytest

import database as D
import metering as M
from agent import llm
from tests.test_auth_guard import c, tok, H, _keys, mail  # noqa: F401


@pytest.fixture()
def uid(c, monkeypatch):
    monkeypatch.setenv("OPAI_METERING", "enforce")
    monkeypatch.setenv("OPAI_PLAN_LIMITS", json.dumps({"free": {"day": 4, "month": 100}}))
    e = mail()
    u = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    M.set_user(u)
    yield u
    M.set_user(None)


def _fake(monkeypatch, fail=False):
    def raw(**kw):
        if fail:
            raise RuntimeError("provider down")
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7), choices=[])
    monkeypatch.setattr(llm, "_create_raw", raw)


def _rows(uid):
    db = D.SessionLocal()
    try:
        return db.query(D.UsageLedger).filter(D.UsageLedger.user_id == uid).all()
    finally:
        db.close()


def test_credit_weights():
    assert M.credits_for("openai/gpt-oss-20b") == 1
    assert M.credits_for("openai/gpt-oss-120b") == M.HEAVY_CREDITS
    assert M.credits_for("claude-sonnet-4-5") == M.HEAVY_CREDITS
    assert M.credits_for(None, "deep") == M.HEAVY_CREDITS


def test_every_call_is_recorded_with_tokens(uid, monkeypatch):
    _fake(monkeypatch)
    llm._create(model="openai/gpt-oss-20b", messages=[])
    r = _rows(uid)
    assert len(r) == 1 and (r[0].credits, r[0].tokens_in, r[0].tokens_out, r[0].status) == (1, 11, 7, "ok")


def test_quota_blocks_with_429_and_a_clear_message(uid, monkeypatch):
    _fake(monkeypatch)
    for _ in range(4):
        llm._create(model="small", messages=[])
    with pytest.raises(M.QuotaExceeded) as e:
        llm._create(model="small", messages=[])
    assert e.value.status_code == 429 and isinstance(e.value.detail, str) and "4/4" in e.value.detail and e.value.info["limit"] == 4
    assert len(_rows(uid)) == 4                         # the blocked call was not charged


def test_heavy_call_needs_enough_credits_left(uid, monkeypatch):
    _fake(monkeypatch)
    for _ in range(2):
        llm._create(model="small", messages=[])           # 2 of 4 used
    with pytest.raises(M.QuotaExceeded):
        llm._create(model="openai/gpt-oss-120b", messages=[])   # costs 3, only 2 left


def test_failed_calls_are_free(uid, monkeypatch):
    _fake(monkeypatch, fail=True)
    for _ in range(6):
        with pytest.raises(RuntimeError):
            llm._create(model="small", messages=[])
    assert M.usage(D.SessionLocal(), uid)["day"]["used"] == 0


def test_log_mode_records_but_never_blocks(uid, monkeypatch):
    monkeypatch.setenv("OPAI_METERING", "log")
    _fake(monkeypatch)
    for _ in range(7):
        llm._create(model="small", messages=[])
    assert len(_rows(uid)) == 7


def test_unsigned_background_calls_are_not_metered(uid, monkeypatch):
    M.set_user(None)
    _fake(monkeypatch)
    llm._create(model="small", messages=[])
    assert _rows(uid) == []


def test_database_trouble_never_blocks_a_user(uid, monkeypatch):
    _fake(monkeypatch)
    monkeypatch.setattr(M, "check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone")))
    llm._create(model="small", messages=[])             # must not raise


def test_paid_plan_raises_the_cap_and_expiry_reverts_to_free(uid, monkeypatch):
    import billing_api as B
    from datetime import datetime, timedelta
    db = D.SessionLocal()
    try:
        assert M.plan_for(db, uid)["name"] == "free" and M.plan_for(db, uid)["day"] == 4
        B.activate_plan(db, uid, "pro", 1)
        assert M.plan_for(db, uid)["name"] == "pro" and M.plan_for(db, uid)["day"] == 250
        row = db.query(D.UserPlan).filter(D.UserPlan.user_id == uid).first()
        row.plan_expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        assert M.plan_for(db, uid)["name"] == "free"
    finally:
        db.close()


def test_usage_endpoint_is_per_user_and_guarded(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    a, b = mail(), mail()
    ua = c.post("/v1/auth/dev-login", params={"email": a}, headers=H(tok(a))).json()["user_id"]
    c.post("/v1/auth/dev-login", params={"email": b}, headers=H(tok(b)))
    ok = c.get("/v1/usage", params={"user_id": ua}, headers=H(tok(a)))
    assert ok.status_code == 200 and ok.json()["plan"] == "free" and ok.json()["day"]["used"] == 0
    assert c.get("/v1/usage", params={"user_id": ua}, headers=H(tok(b))).status_code == 403
    assert c.get("/v1/usage", params={"user_id": ua}).status_code == 401


def test_middleware_tells_metering_who_is_calling(c, monkeypatch):
    """An authenticated request that triggers an LLM call is charged to that user."""
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    monkeypatch.setenv("OPAI_METERING", "enforce")
    e = mail()
    u = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    seen = {}
    import main
    from fastapi import APIRouter
    r = APIRouter()

    @r.get("/v1/_meter_probe")
    def probe(user_id: str):
        seen["u"] = M.current_user()
        return {"ok": 1}
    main.app.include_router(r)
    assert c.get("/v1/_meter_probe", params={"user_id": u}, headers=H(tok(e))).status_code == 200
    assert seen["u"] == u.lower()
