"""Audit facade used by agent/workflow code."""
from __future__ import annotations

import json

from database import AgentActivityLog


def record(db, user_id: str, action: str, arguments: dict, result: dict | str, risk: str, status: str = "ok"):
    summary = result if isinstance(result, str) else json.dumps(result, default=str)
    row = AgentActivityLog(
        user_id=user_id,
        tool_name=action,
        arguments=arguments or {},
        result_summary=summary[:500],
        risk_level=risk,
        status=status,
    )
    db.add(row)
    db.commit()
    return row
