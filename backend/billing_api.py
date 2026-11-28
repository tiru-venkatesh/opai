"""Usage, plans and payments.

  GET  /v1/usage?user_id=            credits used / remaining today and this month for the caller
  GET  /v1/billing/plans             public plan catalogue (limits + price)
  POST /v1/billing/checkout          start a Cashfree order for a plan (price comes from OUR table, never the client)
  POST /v1/billing/webhook           Cashfree payment webhook (signature-verified, idempotent) -> activates the plan
  POST /v1/admin/plan                admin: set a user's plan / bonus credits by hand (header X-Admin-Key)

Env for payments: CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV (sandbox | production, default sandbox),
OPAI_PUBLIC_URL (frontend origin, used for the return page), OPAI_API_URL (this API's public URL, used for notify_url).
Without the Cashfree keys, checkout answers 503 and everything else still works (plans can be set by an admin).
NOTE: the Cashfree request/webhook shapes follow their public PG docs but have not been exercised against the live gateway
from this repo; run one sandbox payment end to end before going live.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import metering
from database import BillingOrder, User, UserPlan, get_db

log = logging.getLogger("opai.billing")
router = APIRouter()
PAID_PLANS = ("pro", "max")


def _user(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


@router.get("/v1/usage")
def get_usage(user_id: str, db: Session = Depends(get_db)):
    _user(db, user_id)
    return metering.usage(db, user_id.strip().lower())


@router.get("/v1/billing/plans")
def get_plans():
    return {"plans": [{"id": k, "label": v.get("label", k), "credits_per_day": v["day"], "credits_per_month": v["month"],
                       "price_inr_per_month": v.get("price_inr", 0)} for k, v in metering.plans().items()],
            "credit_note": f"A light AI request costs 1 credit; a deep-reasoning request costs {metering.HEAVY_CREDITS}.",
            "payments_enabled": bool(_cf_keys())}


# ---------------------------------------------------------------- admin
def _admin(key: Optional[str]):
    want = os.getenv("OPAI_ADMIN_KEY", "") or os.getenv("FEEDBACK_ADMIN_KEY", "")
    if not want or not key or not hmac.compare_digest(key, want):
        raise HTTPException(403, "Admin key required")


class AdminPlan(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    plan: str = Field(default="free", pattern="^(free|pro|max)$")
    months: int = Field(default=1, ge=0, le=36)
    bonus_credits: int = Field(default=0, ge=0, le=1_000_000)


def activate_plan(db: Session, uid: str, plan: str, months: int, bonus: Optional[int] = None) -> UserPlan:
    """Grant `plan` for `months` x 30 days, stacking on top of any time the user still has on the same plan."""
    row = db.query(UserPlan).filter(UserPlan.user_id == uid).first()
    if not row:
        row = UserPlan(user_id=uid, plan="free", bonus_credits=0)
        db.add(row)
    now = datetime.utcnow()
    if plan == "free" or months <= 0:
        row.plan, row.plan_expires_at = "free", None
    else:
        start = row.plan_expires_at if (row.plan == plan and row.plan_expires_at and row.plan_expires_at > now) else now
        row.plan, row.plan_expires_at = plan, start + timedelta(days=30 * months)
    if bonus is not None:
        row.bonus_credits = bonus
    db.commit()
    return row


@router.post("/v1/admin/plan")
def admin_set_plan(b: AdminPlan, x_admin_key: Optional[str] = Header(None), db: Session = Depends(get_db)):
    _admin(x_admin_key)
    from sqlalchemy import func
    u = db.query(User).filter(User.id == b.user_id).first() if b.user_id else \
        db.query(User).filter(func.lower(User.email) == (b.email or "").strip().lower()).first()
    if not u:
        raise HTTPException(404, "User not found")
    row = activate_plan(db, str(u.id).lower(), b.plan, b.months, b.bonus_credits)
    return {"user_id": u.id, "plan": row.plan, "expires_at": row.plan_expires_at.isoformat() if row.plan_expires_at else None,
            "bonus_credits": row.bonus_credits}


# ---------------------------------------------------------------- Cashfree
def _cf_keys():
    a, s = os.getenv("CASHFREE_APP_ID", "").strip(), os.getenv("CASHFREE_SECRET_KEY", "").strip()
    return (a, s) if a and s else None


def _cf_base() -> str:
    return "https://api.cashfree.com/pg" if os.getenv("CASHFREE_ENV", "sandbox").strip().lower() == "production" else "https://sandbox.cashfree.com/pg"


def verify_webhook(raw: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Cashfree signs timestamp + raw body with HMAC-SHA256 (base64) using the account secret key."""
    if not (raw is not None and timestamp and signature and secret):
        return False
    want = base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(want, signature.strip())


class Checkout(BaseModel):
    user_id: str
    plan: str = Field(pattern="^(pro|max)$")
    months: int = Field(default=1, ge=1, le=12)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")       # Cashfree requires a 10-digit Indian mobile number


@router.post("/v1/billing/checkout")
def checkout(b: Checkout, db: Session = Depends(get_db)):
    keys = _cf_keys()
    if not keys:
        raise HTTPException(503, "Payments are not switched on yet. Ask the admin to upgrade your plan.")
    u = _user(db, b.user_id)
    price = int(metering.plans().get(b.plan, {}).get("price_inr", 0))
    if price <= 0:
        raise HTTPException(400, "That plan is not for sale.")
    amount = price * b.months
    order_id = "opai_" + uuid.uuid4().hex[:20]
    db.add(BillingOrder(order_id=order_id, user_id=str(u.id).lower(), plan=b.plan, months=b.months, amount_inr=amount))
    db.commit()
    front, api = os.getenv("OPAI_PUBLIC_URL", "").rstrip("/"), os.getenv("OPAI_API_URL", "").rstrip("/")
    body = {"order_id": order_id, "order_amount": float(amount), "order_currency": "INR",
            "customer_details": {"customer_id": str(u.id).replace("-", "")[:40], "customer_email": u.email, "customer_phone": b.phone},
            "order_meta": {k: v for k, v in {"return_url": f"{front}/profile.html?order={order_id}" if front else None,
                                             "notify_url": f"{api}/v1/billing/webhook" if api else None}.items() if v}}
    req = urllib.request.Request(_cf_base() + "/orders", data=json.dumps(body).encode(), method="POST", headers={
        "content-type": "application/json", "x-api-version": "2023-08-01", "x-client-id": keys[0], "x-client-secret": keys[1]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        log.warning("cashfree order failed: %s", e)
        raise HTTPException(502, "The payment provider did not respond. Try again in a minute.")
    return {"order_id": order_id, "payment_session_id": data.get("payment_session_id"), "amount_inr": amount, "env": os.getenv("CASHFREE_ENV", "sandbox")}


@router.get("/v1/billing/order")
def order_status(user_id: str, order_id: str, db: Session = Depends(get_db)):
    """Status of the caller's own order (the page polls this after Cashfree sends the user back)."""
    _user(db, user_id)
    o = db.query(BillingOrder).filter(BillingOrder.order_id == order_id, BillingOrder.user_id == user_id.strip().lower()).first()
    if not o:
        raise HTTPException(404, "Order not found")
    return {"order_id": o.order_id, "status": o.status, "plan": o.plan, "months": o.months, "amount_inr": o.amount_inr}


@router.post("/v1/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    keys = _cf_keys()
    raw = await request.body()
    if not keys or not verify_webhook(raw, request.headers.get("x-webhook-timestamp", ""), request.headers.get("x-webhook-signature", ""), keys[1]):
        raise HTTPException(401, "bad signature")
    try:
        evt = json.loads(raw.decode() or "{}")
        oid = str(evt["data"]["order"]["order_id"])
        status = str((evt["data"].get("payment") or {}).get("payment_status", "")).upper()
        paid_amount = float(evt["data"]["order"].get("order_amount", 0))
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, "unreadable webhook")
    if not re.fullmatch(r"opai_[0-9a-f]{20}", oid):
        return {"ok": True, "ignored": "not our order"}
    o = db.query(BillingOrder).filter(BillingOrder.order_id == oid).first()
    if not o:
        return {"ok": True, "ignored": "unknown order"}
    if o.status == "paid":
        return {"ok": True, "duplicate": True}                 # gateways retry; granting twice would double the time
    if status == "SUCCESS":
        if abs(paid_amount - float(o.amount_inr)) > 0.01:
            log.error("billing amount mismatch on %s: paid %s expected %s", oid, paid_amount, o.amount_inr)
            raise HTTPException(409, "amount mismatch")
        o.status, o.paid_at = "paid", datetime.utcnow()
        db.commit()
        activate_plan(db, o.user_id, o.plan, o.months)
        return {"ok": True, "activated": o.plan}
    if status in ("FAILED", "USER_DROPPED", "CANCELLED"):
        o.status = "failed"
        db.commit()
    return {"ok": True}
