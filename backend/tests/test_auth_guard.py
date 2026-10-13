import time
import uuid as _uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

import auth_guard
import main

PROJECT = "opagent-3ef8b"
_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pem = _priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(auth_guard, "get_keys", lambda: {"k1": _priv.public_key()})
    auth_guard._uid_cache.clear()


@pytest.fixture()
def c():
    with TestClient(main.app) as client:     # context manager runs startup (init_db)
        yield client


def tok(email, verified=True, aud=PROJECT, exp=3600, kid="k1"):
    now = int(time.time())
    return jwt.encode({"iss": "https://securetoken.google.com/" + PROJECT, "aud": aud, "sub": "s-" + email, "iat": now,
                       "exp": now + exp, "email": email, "email_verified": verified}, _pem, algorithm="RS256", headers={"kid": kid})


def H(t):
    return {"Authorization": "Bearer " + t}


def mail():
    return "g-" + _uuid.uuid4().hex[:10] + "@test.local"


def test_enforce_blocks_login_without_or_with_wrong_token(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    e = mail()
    assert c.post("/v1/auth/dev-login", params={"email": e}).status_code == 401
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H("garbage.token.here-xxxxxxxx")).status_code == 401
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(mail()))).status_code == 403   # someone else's email
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e, aud="other-project"))).status_code == 401
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e, verified=False))).status_code == 401
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e, exp=-600))).status_code == 401
    assert c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).status_code == 200


def test_enforce_isolates_users_by_query_and_json_body(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    a, b = mail(), mail()
    ua = c.post("/v1/auth/dev-login", params={"email": a}, headers=H(tok(a))).json()["user_id"]
    ub = c.post("/v1/auth/dev-login", params={"email": b}, headers=H(tok(b))).json()["user_id"]
    assert c.get("/v1/profile", params={"user_id": ua}, headers=H(tok(a))).status_code == 200
    assert c.get("/v1/profile", params={"user_id": ua}, headers=H(tok(b))).status_code == 403   # B cannot read A
    assert c.get("/v1/profile", params={"user_id": ua}).status_code == 401
    assert c.patch("/v1/profile", params={"user_id": ua}, json={"cgpa": 9}, headers=H(tok(b))).status_code == 403
    assert c.patch("/v1/profile", params={"user_id": ua}, json={"cgpa": 9}, headers=H(tok(a))).status_code == 200
    # body user_id is checked too, and the body still reaches the endpoint after buffering
    ok = c.post("/v1/feedback", json={"user_id": ua, "type": "general", "title": "hi"}, headers=H(tok(a)))
    assert ok.status_code == 200 and ok.json()["id"]
    assert c.post("/v1/feedback", json={"user_id": ua, "type": "general", "title": "hi"}, headers=H(tok(b))).status_code == 403
    assert c.get("/v1/health").status_code == 200       # exempt


def test_log_mode_never_blocks(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "log")
    e = mail()
    r = c.post("/v1/auth/dev-login", params={"email": e})
    assert r.status_code == 200
    assert c.get("/v1/profile", params={"user_id": r.json()["user_id"]}).status_code == 200


def test_cors_preflight_allows_authorization_header(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    r = c.options("/v1/profile", headers={"Origin": "https://tiru-venkatesh.vercel.app", "Access-Control-Request-Method": "GET",
                                          "Access-Control-Request-Headers": "authorization"})
    assert r.status_code == 200 and "authorization" in r.headers.get("access-control-allow-headers", "").lower()
