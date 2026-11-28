"""Provider-wide quota checks backed by successful and failed provider attempts.

Provider limits are optional because provider plans and quotas change. Configure only
limits from the account that owns each key using KARNA_PROVIDER_LIMITS_JSON.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

log = logging.getLogger("opai.provider_quota")
_WINDOWS = {"requests_per_minute": 60, "requests_per_day": 86400,
            "tokens_per_minute": 60, "tokens_per_day": 86400}


def limits() -> Dict[str, Dict[str, int]]:
    try:
        raw = json.loads(os.getenv("KARNA_PROVIDER_LIMITS_JSON", "{}"))
    except (ValueError, TypeError):
        log.warning("KARNA_PROVIDER_LIMITS_JSON is invalid; provider quotas are not enforced")
        return {}
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Dict[str, int]] = {}
    for provider, values in raw.items():
        if provider not in {"groq", "gemini", "openrouter", "anthropic"} or not isinstance(values, dict):
            continue
        clean = {}
        for name in _WINDOWS:
            value = values.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                clean[name] = value
        if clean:
            result[provider] = clean
    return result


def _usage(provider: str) -> Dict[str, int]:
    """Read attempted provider calls from the shared ledger; failures count as requests too."""
    from database import SessionLocal, UsageLedger
    now = datetime.utcnow()
    since = now - timedelta(days=1)
    db = SessionLocal()
    try:
        rows = db.query(UsageLedger.created_at, UsageLedger.tokens_in, UsageLedger.tokens_out).filter(
            UsageLedger.kind == "provider_attempt", UsageLedger.provider == provider,
            UsageLedger.created_at >= since).all()
        minute = now - timedelta(minutes=1)
        return {
            "requests_per_minute": sum(row.created_at >= minute for row in rows),
            "requests_per_day": len(rows),
            "tokens_per_minute": sum(int(row.tokens_in or 0) + int(row.tokens_out or 0) for row in rows if row.created_at >= minute),
            "tokens_per_day": sum(int(row.tokens_in or 0) + int(row.tokens_out or 0) for row in rows),
        }
    finally:
        db.close()


def available(provider: str, *, reserved_tokens: int = 0) -> bool:
    configured = limits().get(provider)
    if not configured:
        return True
    try:
        used = _usage(provider)
    except Exception as exc:  # Provider service fails open; provider 429s still trigger fallback.
        log.warning("provider quota lookup failed for %s (%s)", provider, type(exc).__name__)
        return True
    for name, cap in configured.items():
        current = used.get(name, 0)
        if name.startswith("tokens_"):
            if current + max(0, int(reserved_tokens)) > cap:
                return False
        elif current >= cap:
            return False
    return True


def snapshot() -> Dict[str, Dict[str, Any]]:
    out = {}
    for provider, configured in limits().items():
        try:
            used = _usage(provider)
            out[provider] = {"configured": True, "limits": configured, "used": used,
                             "remaining": {k: max(0, v - used.get(k, 0)) for k, v in configured.items()},
                             "available": all(used.get(k, 0) < v for k, v in configured.items())}
        except Exception as exc:
            out[provider] = {"configured": True, "limits": configured, "available": None,
                             "error": type(exc).__name__}
    return out
