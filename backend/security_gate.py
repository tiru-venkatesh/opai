"""Production safety gate.

The auth guard already verifies Firebase tokens, but it defaulted to `log` mode, which blocks nothing. On a
production host that is the wrong default. This module:

  * makes OPAI_AUTH_MODE default to `enforce` on Render / OPAI_ENV=production (stays `log` locally);
    an explicit OPAI_AUTH_MODE always wins, so the log -> enforce rollout and the one-line rollback still work;
  * refuses to boot in production when auth is `off`, OPAI_LOCAL_AUTH_BYPASS is on, or ENABLE_DEV_SEED is on
    (set OPAI_ALLOW_INSECURE_START=1 as a loudly logged emergency override);
  * logs warnings for weaker-but-legal settings (log mode, CORS *, SQLite, unverified emails allowed).
"""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

log = logging.getLogger("opai.gate")
_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str, default: str = "") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUE


def is_production() -> bool:
    return bool(os.getenv("RENDER", "").strip()) or os.getenv("OPAI_ENV", "").strip().lower() in ("production", "prod")


def default_auth_mode() -> str:
    return "enforce" if is_production() else "log"


def _auth_mode() -> str:
    m = os.getenv("OPAI_AUTH_MODE", "").strip().lower()
    return m if m in ("off", "log", "enforce") else default_auth_mode()


def problems() -> Tuple[List[str], List[str]]:
    """(blocking errors, warnings) for the current environment. Errors only exist in production."""
    errors: List[str] = []
    warns: List[str] = []
    mode = _auth_mode()
    if is_production():
        if mode == "off":
            errors.append("OPAI_AUTH_MODE=off in production: every endpoint would trust any user_id.")
        if _flag("OPAI_LOCAL_AUTH_BYPASS"):
            errors.append("OPAI_LOCAL_AUTH_BYPASS is on in production: loopback calls skip authentication.")
        if _flag("ENABLE_DEV_SEED"):
            errors.append("ENABLE_DEV_SEED is on in production: demo identities could be recreated.")
        if mode == "log":
            warns.append("OPAI_AUTH_MODE=log in production: bad tokens are only logged, not refused.")
        if os.getenv("CORS_ORIGINS", "*").strip() in ("", "*"):
            warns.append("CORS_ORIGINS is * in production: set it to your frontend origin(s).")
        if os.getenv("DATABASE_URL", "").strip().lower().startswith("sqlite") or not os.getenv("DATABASE_URL", "").strip():
            warns.append("SQLite in production: data is lost on redeploy on most hosts. Use Postgres.")
        if os.getenv("OPAI_REQUIRE_VERIFIED", "1").strip() == "0":
            warns.append("OPAI_REQUIRE_VERIFIED=0: unverified emails can claim an existing account's email.")
    return errors, warns


def enforce_startup() -> None:
    """Call once at boot. Raises RuntimeError when production config is unsafe (unless explicitly overridden)."""
    errors, warns = problems()
    for w in warns:
        log.warning("security gate: %s", w)
    if not errors:
        return
    if _flag("OPAI_ALLOW_INSECURE_START"):
        for e in errors:
            log.error("security gate OVERRIDDEN (OPAI_ALLOW_INSECURE_START=1): %s", e)
        return
    raise RuntimeError("Refusing to start: " + " | ".join(errors) + "  (emergency override: OPAI_ALLOW_INSECURE_START=1)")
