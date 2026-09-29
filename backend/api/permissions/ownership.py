"""Reusable ownership checks for API and agent code."""
from __future__ import annotations

from fastapi import HTTPException


def require_owner(obj, user_id: str, *, detail: str = "Resource not found"):
    if obj is None or str(getattr(obj, "user_id", "")) != str(user_id):
        raise HTTPException(status_code=404, detail=detail)
    return obj
