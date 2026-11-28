import base64
import hashlib
import hmac
import json
import time

import pytest

import billing_api as B
import database as D
import metering as M
from tests.test_auth_guard import c, tok, H, _keys, mail  # noqa: F401

SECRET = "test-secret"


@pytest.fixture()
def shop(c, monkeypatch):
    monkeypatch.setenv("CASHFREE_APP_ID", "app")
    monkeypatch.setenv("CASHFREE_SECRET_KEY", SECRET)
    monkeypatch.setenv("OPAI_ADMIN_KEY", "adm")
    e = mail()
    uid = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    return c, uid, e


def _order(uid, amount=299, plan="pro", months=1):
    oid = "opai_" + hashlib.md5(f"{uid}{time.time()}".encode()).hexdigest()[:20]
    db = D.SessionLocal()
    db.add(D.BillingOrder(order_id=oid, user_id=uid.lower(), plan=plan, months=months, amount_inr=amount))
    db.commit()
    db.close()
    return oid


def _hook(c, oid, amount=299, status="SUCCESS", secret=SECRET, ts="1700000000"):
    raw = json.dumps({"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {"order": {"order_id": oid, "order_amount": amount},
                                                                   "payment": {"payment_status": status}}}).encode()
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw, hashlib.sha256).digest()).decode()
    return c.post("/v1/billing/webhook", content=raw, headers={"x-webhook-timestamp": ts, "x-webhook-signature": sig, "content-type": "application/json"})


def _plan(uid):
    db = D.SessionLocal()
    try:
        return M.plan_for(db, uid.lower())
    finally:
        db.close()


def test_plans_are_public_and_priced_server_side(c):
    r = c.get("/v1/billing/plans")
    ids = {p["id"]: p for p in r.json()["plans"]}
    assert r.status_code == 200 and ids["free"]["price_inr_per_month"] == 0 and ids["pro"]["price_inr_per_month"] > 0


def test_checkout_is_503_until_payments_are_configured(c, monkeypatch):
    monkeypatch.delenv("CASHFREE_APP_ID", raising=False)
    monkeypatch.delenv("CASHFREE_SECRET_KEY", raising=False)
    e = mail()
    uid = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    assert c.post("/v1/billing/checkout", json={"user_id": uid, "plan": "pro", "phone": "9876543210"}).status_code == 503


def test_checkout_rejects_bad_plan_and_phone(shop):
    c, uid, _ = shop
    assert c.post("/v1/billing/checkout", json={"user_id": uid, "plan": "free", "phone": "9876543210"}).status_code == 422
    assert c.post("/v1/billing/checkout", json={"user_id": uid, "plan": "pro", "phone": "123"}).status_code == 422


def test_signed_success_webhook_activates_the_plan(shop):
    c, uid, _ = shop
    r = _hook(c, _order(uid))
    assert r.status_code == 200 and r.json()["activated"] == "pro" and _plan(uid)["name"] == "pro"


def test_bad_or_missing_signature_is_rejected(shop):
    c, uid, _ = shop
    oid = _order(uid)
    assert _hook(c, oid, secret="wrong").status_code == 401
    assert c.post("/v1/billing/webhook", json={}).status_code == 401
    assert _plan(uid)["name"] == "free"


def test_replayed_webhook_does_not_stack_time(shop):
    c, uid, _ = shop
    oid = _order(uid)
    _hook(c, oid)
    first = _plan(uid)["expires_at"]
    again = _hook(c, oid)
    assert again.json().get("duplicate") and _plan(uid)["expires_at"] == first


def test_amount_must_match_our_record(shop):
    c, uid, _ = shop
    assert _hook(c, _order(uid, amount=299), amount=1).status_code == 409
    assert _plan(uid)["name"] == "free"


def test_failed_payment_grants_nothing(shop):
    c, uid, _ = shop
    _hook(c, _order(uid), status="FAILED")
    assert _plan(uid)["name"] == "free"


def test_admin_can_set_plan_only_with_the_key(shop):
    c, uid, email = shop
    body = {"email": email, "plan": "max", "months": 2, "bonus_credits": 500}
    assert c.post("/v1/admin/plan", json=body).status_code == 403
    assert c.post("/v1/admin/plan", json=body, headers={"x-admin-key": "nope"}).status_code == 403
    r = c.post("/v1/admin/plan", json=body, headers={"x-admin-key": "adm"})
    p = _plan(uid)
    assert r.status_code == 200 and p["name"] == "max" and p["month"] == M.plans()["max"]["month"] + 500


def test_buying_the_same_plan_again_extends_it(shop):
    c, uid, _ = shop
    _hook(c, _order(uid))
    a = _plan(uid)["expires_at"]
    _hook(c, _order(uid))
    assert _plan(uid)["expires_at"] > a


def test_order_status_is_visible_only_to_its_owner(shop):
    c, uid, _ = shop
    oid = _order(uid)
    assert c.get("/v1/billing/order", params={"user_id": uid, "order_id": oid}).json()["status"] == "created"
    _hook(c, oid)
    assert c.get("/v1/billing/order", params={"user_id": uid, "order_id": oid}).json()["status"] == "paid"
    other = mail()
    ou = c.post("/v1/auth/dev-login", params={"email": other}, headers=H(tok(other))).json()["user_id"]
    assert c.get("/v1/billing/order", params={"user_id": ou, "order_id": oid}).status_code == 404
