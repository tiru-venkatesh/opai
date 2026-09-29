"""
Small idempotency layer backed by AgentActivityLog.

This avoids introducing another database table while still preventing duplicate
low-risk actions when the same request is retried.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from database import AgentActivityLog


IDEMPOTENT_TOOLS = {"create_task", "generate_study_plan", "update_task_status"}


def make_key(user_id: str, tool: str, arguments: dict) -> str:
    raw = json.dumps(arguments or {}, sort_keys=True, default=str, separators=(",", ":"))
    day = datetime.utcnow().strftime("%Y-%m-%d")
    return hashlib.sha256(f"{user_id}|{tool}|{day}|{raw}".encode("utf-8")).hexdigest()


def recent_success(db: Session, user_id: str, tool: str, key: str, hours: int = 24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(AgentActivityLog)
        .filter(
            AgentActivityLog.user_id == user_id,
            AgentActivityLog.tool_name == tool,
            AgentActivityLog.status == "ok",
            AgentActivityLog.created_at >= cutoff,
        )
        .order_by(AgentActivityLog.created_at.desc())
        .limit(50)
        .all()
    )
    for row in rows:
        args = row.arguments or {}
        if args.get("_idempotency_key") == key:
            try:
                return json.loads(row.result_summary or "{}")
            except Exception:
                return {"message": row.result_summary or "Already executed"}
    return None
