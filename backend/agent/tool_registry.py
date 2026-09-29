"""
Explicit tool registry for OPA.

The registry is intentionally small and backed by the existing audited handlers
in `agent_service.py`. New tools should be added here before models can request
them.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy.orm import Session

from .idempotency import IDEMPOTENT_TOOLS, make_key, recent_success


def available_tools() -> list[str]:
    from agent_service import TOOL_HANDLERS
    return sorted(TOOL_HANDLERS.keys())


def execute(user_id: str, tool_name: str, arguments: Dict[str, Any], db: Session) -> dict:
    from agent_service import TOOL_HANDLERS, _log_activity

    entry = TOOL_HANDLERS.get(tool_name)
    if not entry:
        _log_activity(db, user_id, tool_name, arguments, "blocked: tool not registered", "high", status="blocked")
        return {"ok": False, "error": f"tool '{tool_name}' is not registered"}

    handler, risk = entry
    args = dict(arguments or {})

    if tool_name in IDEMPOTENT_TOOLS:
        key = make_key(user_id, tool_name, args)
        previous = recent_success(db, user_id, tool_name, key)
        if previous:
            return {"ok": True, "already_executed": True, "result": previous}
        args["_idempotency_key"] = key

    try:
        result = handler(user_id, db, args)
        _log_activity(
            db, user_id, tool_name, args, json.dumps(result, default=str)[:400],
            risk, status="ok",
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        _log_activity(db, user_id, tool_name, args, f"error: {exc}", risk, status="error")
        return {"ok": False, "error": str(exc)}
