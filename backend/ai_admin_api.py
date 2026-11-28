"""Admin-only aggregate AI telemetry. Deliberately returns no prompts or outputs."""
from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import func

from database import SessionLocal, UsageLedger

router = APIRouter()


def _admin(key: Optional[str]) -> None:
    expected = os.getenv("OPAI_ADMIN_KEY", "") or os.getenv("FEEDBACK_ADMIN_KEY", "")
    if not expected or not key or not hmac.compare_digest(key, expected):
        raise HTTPException(403, "Admin key required")


def _price_table():
    try:
        value = json.loads(os.getenv("KARNA_PRICE_PER_1M_JSON", "{}"))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


@router.get("/v1/admin/ai-analytics")
def ai_analytics(window: str = Query("24h", pattern="^(24h|7d|30d)$"),
                 x_admin_key: Optional[str] = Header(None)):
    _admin(x_admin_key)
    days = {"24h": 1, "7d": 7, "30d": 30}[window]
    cutoff = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        logical = db.query(UsageLedger.provider, UsageLedger.model, UsageLedger.status, UsageLedger.fallback,
                           UsageLedger.tokens_in, UsageLedger.tokens_out, UsageLedger.latency_ms).filter(
                               UsageLedger.created_at >= cutoff, UsageLedger.kind.in_(("llm", "llm_stream"))).all()
        attempts = db.query(UsageLedger.provider, UsageLedger.model, UsageLedger.status, UsageLedger.fallback,
                            UsageLedger.tokens_in, UsageLedger.tokens_out, UsageLedger.latency_ms).filter(
                                UsageLedger.created_at >= cutoff, UsageLedger.kind == "provider_attempt").all()
        active = db.query(func.count(func.distinct(UsageLedger.user_id))).filter(
            UsageLedger.created_at >= cutoff, UsageLedger.user_id != "__system__",
            UsageLedger.kind.in_(("llm", "llm_stream"))).scalar() or 0
    finally:
        db.close()
    by_provider, by_model = {}, {}
    totals = {"requests": len(logical), "successes": 0, "errors": 0, "fallbacks": 0, "tokens_in": 0, "tokens_out": 0,
              "latency_ms_sum": 0}
    prices = _price_table()
    estimated_cost = 0.0
    cost_known = bool(prices)
    for provider, model, status, fallback, ti, to, latency in logical:
        totals["successes"] += int(status == "ok"); totals["errors"] += int(status != "ok")
        totals["fallbacks"] += int(bool(fallback)); totals["tokens_in"] += int(ti or 0)
        totals["tokens_out"] += int(to or 0); totals["latency_ms_sum"] += int(latency or 0)
    provider_rows = attempts or logical  # old ledger records predate per-provider attempt rows
    for provider, model, status, fallback, ti, to, latency in provider_rows:
        name = provider or "unknown"
        stat = by_provider.setdefault(name, {"requests": 0, "successes": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0, "latency_ms_sum": 0, "fallbacks": 0})
        stat["requests"] += 1
        stat["successes"] += int(status == "ok")
        stat["errors"] += int(status != "ok")
        stat["tokens_in"] += int(ti or 0); stat["tokens_out"] += int(to or 0)
        stat["latency_ms_sum"] += int(latency or 0)
        stat["fallbacks"] += int(bool(fallback))
        model_key = f"{name}/{model or ''}"
        by_model[model_key] = by_model.get(model_key, 0) + 1
        rate = prices.get(model_key) or prices.get(name)
        if isinstance(rate, dict):
            estimated_cost += (int(ti or 0) * float(rate.get("input_per_million", 0)) + int(to or 0) * float(rate.get("output_per_million", 0))) / 1_000_000
        else:
            cost_known = False
    for stat in by_provider.values():
        stat["average_latency_ms"] = round(stat.pop("latency_ms_sum") / max(1, stat["requests"]))
    totals["average_latency_ms"] = round(totals.pop("latency_ms_sum") / max(1, totals["requests"]))
    totals["estimated_cost_usd"] = round(estimated_cost, 6) if cost_known else None
    from agent.model_router import health
    from provider_quota import snapshot as quota_snapshot
    return {"window": window, "active_users": int(active), "totals": totals, "providers": by_provider,
            "models": by_model, "provider_health": health(), "remaining_quotas": quota_snapshot(),
            "metrics_note": "Aggregate telemetry only; chat text and documents are never included. Provider quota values appear only when configured from verified account limits."}
