"""
Reliability helpers.

The application must remain useful when both Jev and Groq are unavailable.
"""
from __future__ import annotations

from typing import Any, Dict


def local_response_for_intent(intent: str, entities: Dict[str, Any] | None = None) -> str:
    entities = entities or {}
    if intent == "generate_exam_plan":
        return "AI routing is offline. I can still use the deterministic SEMS planner from the Study Workflow."
    if intent == "create_task":
        return "AI routing is offline. I can still create a task from structured fields."
    if intent == "find_opportunity":
        return "AI routing is offline. I can still search stored opportunities."
    if intent == "draft_outreach":
        return "AI routing is offline. I can prepare a draft only when the contact is explicitly identified."
    return "AI is temporarily unavailable. OPA's core records and deterministic workflows are still available."
