"""
Intent router: Jev first, Groq structured fallback, deterministic last resort.

The router returns a typed decision only. It does not mutate the database.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .decision import IntentDecision
from jev_client import classify_message as classify_with_jev


INTENT_ALIASES = {
    "plan": "generate_exam_plan",
    "study": "generate_exam_plan",
    "study_plan": "generate_exam_plan",
    "exam_plan": "generate_exam_plan",
    "create_task": "create_task",
    "task": "create_task",
    "find_opportunity": "find_opportunity",
    "opportunities": "find_opportunity",
    "opportunity": "find_opportunity",
    "draft_outreach": "draft_outreach",
    "email": "draft_outreach",
    "outreach": "draft_outreach",
    "summary": "summarize_workspace",
    "summarize_workspace": "summarize_workspace",
    "chat": "chat",
}


def _normalize(raw: Any, provider: str) -> Optional[IntentDecision]:
    if not isinstance(raw, dict):
        return None
    intent = str(raw.get("intent") or raw.get("action") or "unknown").strip().lower()
    intent = INTENT_ALIASES.get(intent, intent)
    try:
        return IntentDecision(
            intent=intent,
            confidence=float(raw.get("confidence", 0.0)),
            entities=dict(raw.get("entities") or {}),
            requires_confirmation=bool(raw.get("requires_confirmation", False)),
            reason_code=raw.get("reason_code"),
            provider=provider,
        )
    except Exception:
        return None


def _groq_classify(message: str, context: Optional[Dict[str, Any]] = None) -> Optional[IntentDecision]:
    from .groq_client import generate_json

    system = """
You are OPA's intent classifier. Return only a typed routing decision.
Allowed intents:
chat, create_task, generate_exam_plan, reschedule_session, find_opportunity,
draft_outreach, summarize_workspace, update_application, approve_action,
delete_record, unknown.

Extract only entities that are directly supported by the request:
course, topic, exam, duration_min, date, time_window, task_title, due_date,
query, contact_id, application_id, outbox_id, requested_action.

Never invent IDs, dates, names, or deadlines.
Confidence must represent how certain the intent/entity extraction is.
"""
    try:
        raw = generate_json(
            system,
            f"User request:\n{message}\n\nContext:\n{context or {}}",
            model=None,
            temperature=0.0,
        )
        return _normalize(raw, "groq")
    except Exception:
        return None


def _deterministic_classify(message: str) -> IntentDecision:
    text = message.lower().strip()
    if not text:
        return IntentDecision(intent="unknown", confidence=0.0, provider="deterministic")

    if any(k in text for k in ["exam plan", "study plan", "plan my", "study today", "study tomorrow"]):
        return IntentDecision(intent="generate_exam_plan", confidence=0.84, provider="deterministic")
    if any(k in text for k in ["create task", "add task", "add a task", "new task", "todo", "to-do"]):
        return IntentDecision(intent="create_task", confidence=0.86, provider="deterministic")
    if any(k in text for k in ["opportunit", "internship", "hackathon", "research opening"]):
        return IntentDecision(intent="find_opportunity", confidence=0.82, provider="deterministic")
    if any(k in text for k in ["email professor", "draft email", "outreach", "contact professor"]):
        return IntentDecision(intent="draft_outreach", confidence=0.81, provider="deterministic")
    if any(k in text for k in ["summarize my", "summary of my", "summarise my"]):
        return IntentDecision(intent="summarize_workspace", confidence=0.79, provider="deterministic")
    return IntentDecision(intent="chat", confidence=0.60, provider="deterministic")


def classify(message: str, context: Optional[Dict[str, Any]] = None) -> IntentDecision:
    decision = classify_with_jev(message, context)
    if decision is not None:
        normalized = _normalize(decision.model_dump(), "jev")
        if normalized:
            return normalized

    groq_decision = _groq_classify(message, context)
    if groq_decision:
        return groq_decision

    return _deterministic_classify(message)
