"""GET /v1/version: what is deployed, and which API contract it serves.

API_CONTRACT is a whole number you bump BY HAND whenever the frontend starts depending on a route or response shape that an
older backend does not have (a new /v1/opp/... route the pages call, a changed field they read). scripts/stamp_build.py writes
the number the frontend was built against into frontend/build.json; opai-conn.js compares the two in the browser and shows
"OPAI is updating" when the backend is older. That turns a half-finished deploy into one clear notice instead of random 404s.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()

API_CONTRACT = 1
STARTED_AT = datetime.now(timezone.utc)


@router.get("/v1/version")
def version():
    import gmail_send
    return {
        "service": "opai-backend",
        "version": os.getenv("OPAI_VERSION", "dev"),
        "git_sha": (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_SHA") or "")[:12] or None,
        "api_contract": API_CONTRACT,
        "started_at": STARTED_AT.isoformat(),
        "uptime_seconds": int((datetime.now(timezone.utc) - STARTED_AT).total_seconds()),
        "features": {"gmail_send": bool(gmail_send.client_id())},
    }
