"""Usage metering: plan quotas, a usage ledger, and a check before every LLM call.

Credits, not tokens, are the unit users see. A light call (small/fast model) costs 1 credit, a heavy call
(Claude, 120b-class models) costs HEAVY_CREDITS. Every call is also logged with its token counts so real cost
can be compared against what you charge.

OPAI_METERING   off | log | enforce   (default: enforce on production hosts, log elsewhere)
    log      records usage, never blocks.
    enforce  raises QuotaExceeded (HTTP 429) once the day or month cap is reached.
Plan caps are env-overridable as JSON, e.g. OPAI_PLAN_LIMITS='{"free":{"day":30,"month":500}}'.

The metering is fail-open for infrastructure problems (a DB hiccup never blocks a user) and fail-closed for quota.
Calls with no signed-in user (scheduler, system ticks) are not metered.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException

log = logging.getLogger("opai.metering")

DEFAULT_PLANS: Dict[str, Dict[str, Any]] = {
    "free": {"day": 25,   "month": 400,   "label": "Free",  "price_inr": 0},
    "pro":  {"day": 250,  "month": 5000,  "label": "Pro",   "price_inr": 299},
    "max":  {"day": 1000, "month": 20000, "label": "Max",   "price_inr": 899},
}
HEAVY_CREDITS = 3
_user: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar("opai_meter_user", default=None)


class QuotaExceeded(HTTPException):
    def __init__(self, plan: str, window: str, used: int, limit: int, resets: str):
        self.info = {"plan": plan, "window": window, "used": used, "limit": limit, "resets_at": resets}
        super().__init__(429, f"You have used your {window} AI credits ({used}/{limit}) on the {plan} plan. "
                              f"They reset at {resets}. Upgrade for more.",
                         headers={"X-Quota-Window": window, "X-Quota-Plan": plan})


def mode() -> str:
    m = os.getenv("OPAI_METERING", "").strip().lower()
    if m in ("off", "log", "enforce"):
        return m
    import security_gate
    return "enforce" if security_gate.is_production() else "log"


def plans() -> Dict[str, Dict[str, Any]]:
    out = {k: dict(v) for k, v in DEFAULT_PLANS.items()}
    raw = os.getenv("OPAI_PLAN_LIMITS", "").strip()
    if raw:
        try:
            for k, v in json.loads(raw).items():
                out.setdefault(k, {"label": k.title(), "price_inr": 0}).update({a: int(b) if a in ("day", "month", "price_inr") else b for a, b in v.items()})
        except (ValueError, TypeError, AttributeError):
            log.warning("OPAI_PLAN_LIMITS is not valid JSON; using defaults")
    return out


# ---- who is the caller -------------------------------------------------------------------------------
def set_user(uid: Optional[str]) -> None:
    _user.set((uid or "").strip().lower() or None)


def current_user() -> Optional[str]:
    return _user.get()


# ---- cost of one call --------------------------------------------------------------------------------
def credits_for(model: Optional[str], tier: Optional[str] = None) -> int:
    m = (model or "").lower()
    heavy = any(x in m for x in ("claude", "opus", "sonnet", "120b", "70b", "405b")) or (tier or "") in ("deep", "heavy", "best")
    return HEAVY_CREDITS if heavy else 1


# ---- plan + usage lookups ----------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.utcnow()


def _windows(now: Optional[datetime] = None):
    now = now or _now()
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month0 = day0.replace(day=1)
    next_day = day0 + timedelta(days=1)
    next_month = (month0.replace(day=28) + timedelta(days=4)).replace(day=1)
    return day0, month0, next_day, next_month


def plan_for(db, uid: str) -> Dict[str, Any]:
    from database import UserPlan
    row = db.query(UserPlan).filter(UserPlan.user_id == uid).first()
    name, bonus = "free", 0
    if row:
        bonus = int(row.bonus_credits or 0)
        if (row.plan or "free") != "free" and (row.plan_expires_at is None or row.plan_expires_at > _now()):
            name = row.plan
    table = plans()
    p = table.get(name) or table["free"]
    return {"name": name if name in table else "free", "label": p.get("label", name), "day": int(p["day"]),
            "month": int(p["month"]) + bonus, "bonus": bonus, "expires_at": row.plan_expires_at.isoformat() if row and row.plan_expires_at else None}


def _sum(db, uid: str, since: datetime) -> int:
    from sqlalchemy import func
    from database import UsageLedger
    v = db.query(func.coalesce(func.sum(UsageLedger.credits), 0)).filter(
        UsageLedger.user_id == uid, UsageLedger.created_at >= since, UsageLedger.status == "ok").scalar()
    return int(v or 0)


def usage(db, uid: str) -> Dict[str, Any]:
    day0, month0, next_day, next_month = _windows()
    p = plan_for(db, uid)
    d, m = _sum(db, uid, day0), _sum(db, uid, month0)
    return {"plan": p["name"], "plan_label": p["label"], "plan_expires_at": p["expires_at"],
            "day": {"used": d, "limit": p["day"], "remaining": max(0, p["day"] - d), "resets_at": next_day.isoformat() + "Z"},
            "month": {"used": m, "limit": p["month"], "remaining": max(0, p["month"] - m), "resets_at": next_month.isoformat() + "Z"},
            "metering": mode()}


def check(db, uid: str, credits: int) -> None:
    """Raise QuotaExceeded if this call would push the user past a cap (enforce mode only)."""
    if mode() != "enforce":
        return
    u = usage(db, uid)
    for win in ("day", "month"):
        w = u[win]
        if w["used"] + credits > w["limit"]:
            raise QuotaExceeded(u["plan"], win, w["used"], w["limit"], w["resets_at"])


def record(db, uid: str, *, model: Optional[str], provider: Optional[str], credits: int, tokens_in: int = 0,
           tokens_out: int = 0, kind: str = "llm", status: str = "ok") -> None:
    from database import UsageLedger
    db.add(UsageLedger(user_id=uid, kind=kind, provider=provider, model=(model or "")[:80], credits=credits,
                       tokens_in=int(tokens_in or 0), tokens_out=int(tokens_out or 0), status=status))
    db.commit()


# ---- the hooks used by agent/llm.py ------------------------------------------------------------------
def begin(model: Optional[str], tier: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Call before an LLM request. Returns a token for finish(), or None when the call is not metered."""
    uid = current_user()
    if not uid or mode() == "off":
        return None
    credits = credits_for(model, tier)
    try:
        from database import SessionLocal
        db = SessionLocal()
        try:
            check(db, uid, credits)
        finally:
            db.close()
    except QuotaExceeded:
        raise
    except Exception as e:                       # infrastructure problem: never block the user because of it
        log.warning("metering check skipped: %s", e)
    return {"uid": uid, "model": model, "credits": credits}


def finish(tok: Optional[Dict[str, Any]], resp: Any = None, *, provider: Optional[str] = None, kind: str = "llm",
           error: bool = False, tokens_in: int = 0, tokens_out: int = 0) -> None:
    if not tok:
        return
    try:
        u = getattr(resp, "usage", None)
        ti = tokens_in or int(getattr(u, "prompt_tokens", 0) or 0)
        to = tokens_out or int(getattr(u, "completion_tokens", 0) or 0)
        from database import SessionLocal
        db = SessionLocal()
        try:
            record(db, tok["uid"], model=tok["model"], provider=provider, credits=tok["credits"], tokens_in=ti,
                   tokens_out=to, kind=kind, status="error" if error else "ok")
        finally:
            db.close()
    except Exception as e:
        log.warning("metering record skipped: %s", e)
