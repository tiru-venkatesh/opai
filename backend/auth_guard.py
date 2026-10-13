"""Firebase ID-token guard for the OPAI API.

Before this, /v1/auth/dev-login trusted any email and every endpoint trusted ?user_id=, so anyone who knew
an email (or a user id) could read or change that person's data. This middleware closes that:

  * dev-login must carry a valid Firebase ID token whose verified email equals the ?email= asked for.
  * every other /v1/ call that names a user (?user_id= or JSON body "user_id") must belong to the token's email.

OPAI_AUTH_MODE   off | log | enforce      (default: log)
    log      never blocks; writes an `auth_guard` event + warning for every call that WOULD be refused.
             Deploy this first, watch the logs for a day, then switch to enforce.
    enforce  401 = missing/invalid token, 403 = token does not own that user_id / email.
FIREBASE_PROJECT_ID     default opagent-3ef8b (same project the frontend signs in with)
OPAI_REQUIRE_VERIFIED   default 1: the token's email must be verified (Google sign-in always is). This stops
                        someone registering a victim's email with a password and walking into their workspace.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import urllib.request
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs

import jwt
import ownership
from jwt import algorithms  # noqa: F401  (ensures the crypto backend is importable)

log = logging.getLogger("opai.auth")

CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
EXEMPT_PREFIXES = ("/v1/health", "/v1/version", "/v1/system/", "/v1/admin/")   # admin has its own key, system/tick its own secret
MAX_BODY = 1_000_000

_keys: Dict[str, object] = {}
_keys_exp = 0.0
_uid_cache: Dict[str, Tuple[str, float]] = {}


def mode() -> str:
    m = os.getenv("OPAI_AUTH_MODE", "log").strip().lower()
    return m if m in ("off", "log", "enforce") else "log"


def _project() -> str:
    return os.getenv("FIREBASE_PROJECT_ID", "opagent-3ef8b")


def _fetch_keys() -> Dict[str, object]:
    """kid -> RSA public key, from Google's published certificates."""
    from cryptography.x509 import load_pem_x509_certificate
    with urllib.request.urlopen(CERTS_URL, timeout=5) as r:
        raw = json.loads(r.read().decode())
        ttl = 3600
        m = re.search(r"max-age=(\d+)", r.headers.get("Cache-Control", "") or "")
        if m:
            ttl = max(300, min(int(m.group(1)), 86400))
    return {kid: load_pem_x509_certificate(pem.encode()).public_key() for kid, pem in raw.items()}, ttl


_keys_lock = threading.Lock()
_keys_retry_at = 0.0
KEY_RETRY_SECONDS = 30


def get_keys() -> Dict[str, object]:
    """Cached Firebase certs. One thread refreshes at a time, and a failed fetch is not retried on every request
    (each retry can cost the full network timeout, which made every API call slow while Google was unreachable)."""
    global _keys, _keys_exp, _keys_retry_at
    if _keys and time.time() < _keys_exp:
        return _keys
    with _keys_lock:
        if _keys and time.time() < _keys_exp:            # another thread refreshed while we waited
            return _keys
        if time.time() < _keys_retry_at:
            if _keys:
                return _keys
            raise RuntimeError("Firebase certificates unavailable (retrying shortly)")
        try:
            keys, ttl = _fetch_keys()
            _keys, _keys_exp = keys, time.time() + ttl
        except Exception as e:                           # Google unreachable: keep using the last good keys
            _keys_retry_at = time.time() + KEY_RETRY_SECONDS
            log.warning("could not refresh Firebase certs: %s", e)
            if not _keys:
                raise
    return _keys


def warm_keys() -> None:
    """Fetch the certs in the background at boot so the first sign-in does not pay for it."""
    def run():
        try:
            get_keys()
        except Exception:
            pass
    threading.Thread(target=run, name="opa-auth-warm", daemon=True).start()


def verify_token(token: str) -> dict:
    """Returns the claims, or raises ValueError with a short reason."""
    try:
        header = jwt.get_unverified_header(token)
        key = get_keys().get(header.get("kid"))
        if header.get("alg") != "RS256" or key is None:
            raise ValueError("unknown signing key")
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=_project(),
                            issuer=f"https://securetoken.google.com/{_project()}", leeway=30,
                            options={"require": ["exp", "iat", "sub"]})
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(type(e).__name__)
    if not claims.get("email"):
        raise ValueError("token has no email")
    if os.getenv("OPAI_REQUIRE_VERIFIED", "1") != "0" and not claims.get("email_verified"):
        raise ValueError("email not verified")
    return claims


def _uid_for(email: str) -> Optional[str]:
    hit = _uid_cache.get(email)
    if hit and hit[1] > time.time():
        return hit[0]
    from sqlalchemy import func
    from database import SessionLocal, User
    db = SessionLocal()
    try:
        u = db.query(User).filter(func.lower(User.email) == email).first()
        uid = str(u.id).lower() if u else None
    finally:
        db.close()
    if uid:
        _uid_cache[email] = (uid, time.time() + 600)
    return uid


def _norm(v) -> str:
    return str(v or "").strip().lower()


class AuthGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        m = mode()
        path = scope.get("path", "")
        if scope["type"] != "http" or m == "off" or scope["method"] == "OPTIONS" \
                or not path.startswith("/v1/") or path.startswith(EXEMPT_PREFIXES):
            return await self.app(scope, receive, send)

        headers = {k.decode().lower(): v.decode("latin-1") for k, v in scope["headers"]}
        qs = parse_qs(scope.get("query_string", b"").decode())
        wanted = {_norm(x) for x in qs.get("user_id", [])}

        # JSON bodies can name the user too; buffer once and replay so the endpoint still reads it.
        replay = receive
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE") and "json" in headers.get("content-type", "") \
                and int(headers.get("content-length", "0") or 0) <= MAX_BODY:
            chunks, more = [], True
            while more:
                msg = await receive()
                chunks.append(msg.get("body", b""))
                more = msg.get("more_body", False)
            body, sent = b"".join(chunks), False
            try:
                j = json.loads(body or b"null")
                if isinstance(j, dict) and j.get("user_id"):
                    wanted.add(_norm(j["user_id"]))
            except ValueError:
                pass

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

        problem: Optional[Tuple[int, str]] = None
        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer ") or len(auth) < 20:
            problem = (401, "Sign in again: no session token was sent.")
        else:
            try:
                claims = await asyncio.to_thread(verify_token, auth[7:].strip())
                email = _norm(claims["email"])
                if path == "/v1/auth/dev-login":
                    asked = _norm((qs.get("email") or [""])[0])
                    if asked != email:
                        problem = (403, "That email does not match the account you are signed in with.")
                else:
                    uid = await asyncio.to_thread(_uid_for, email)
                    scope["opai_uid"] = uid                       # handlers that read multipart forms use assert_same_user()
                    if wanted and (uid is None or wanted != {uid}):
                        problem = (403, "That workspace belongs to a different account.")
                    elif uid and await asyncio.to_thread(ownership.forbidden, path, uid):
                        problem = (404, "Not found.")             # someone else's row: same answer as a missing one
            except ValueError as e:
                problem = (401, "Your session expired or is invalid. Sign in again.")
                log.warning("auth_guard token rejected on %s: %s", path, e)

        if problem:
            try:
                import obs
                obs.emit("auth_guard", mode=m, path=path, status=problem[0])
            except Exception:
                pass
            log.warning("auth_guard[%s] would refuse %s %s -> %s", m, scope["method"], path, problem[0])
            if m == "enforce":
                body_out = json.dumps({"detail": problem[1]}).encode()
                await send({"type": "http.response.start", "status": problem[0],
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body_out)).encode())]})
                return await send({"type": "http.response.body", "body": body_out})
        return await self.app(scope, replay, send)


def assert_same_user(request, user_id) -> None:
    """For multipart routes (the guard cannot read form fields): the user_id the form names must be the token's user."""
    if mode() != "enforce":
        return
    uid = request.scope.get("opai_uid")
    if uid is None or _norm(user_id) != uid:
        from fastapi import HTTPException
        raise HTTPException(403, "That workspace belongs to a different account.")
