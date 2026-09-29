"""
Unified OPA request orchestration.

Flow:
request -> normalize -> typed router -> retrieve -> workflow/tool -> language
layer -> approval -> audit.
"""
from __future__ import annotations

import json
from typing import Any, Dict
from uuid import UUID
from sqlalchemy.orm import Session

from .router import classify
from .approval_engine import requires_approval, approval_message
from .decision import ActionResult
from .fallback import local_response_for_intent
from .idempotency import IDEMPOTENT_TOOLS, make_key, recent_success


def _grounded_chat(user_id: UUID, message: str, db: Session):
    from agent_service import call_groq_json
    from rag_service import retrieve, format_context
    from schemas import JarvisChatResponse

    hits = retrieve(db, str(user_id), message, k=5)
    if not hits:
        return JarvisChatResponse(
            action="chat",
            reply="I don't have enough indexed OPA context for that yet. Add the relevant project, resume, application, or academic data and I can ground the answer."
        )

    system = (
        "You are KARNA inside OPA. Answer only from the supplied personal context. "
        "Do not invent dates, names, statuses, scores, or plans. If the context is incomplete, "
        "say what is missing. Return JSON with exactly one field: reply."
    )
    try:
        raw = call_groq_json(
            system,
            f"Question: {message}\n\nContext:\n{format_context(hits)}",
            model="openai/gpt-oss-20b",
        )
        reply = json.loads(raw).get("reply", "")
    except Exception:
        reply = "I found relevant OPA data, but the language layer is unavailable right now."

    return JarvisChatResponse(
        action="chat",
        reply=reply,
        payload={
            "sources": [
                {
                    "type": h["source_type"],
                    "title": h["meta"].get("title"),
                    "score": h["score"],
                }
                for h in hits
            ]
        },
    )


def _clarify(decision, message):
    from schemas import JarvisChatResponse
    reason = decision.reason_code or "low_confidence_intent"
    return JarvisChatResponse(
        action="chat",
        reply=(
            f"I’m not confident enough to act on that yet ({reason}). "
            "Tell me the specific course, task, application, contact, or action you mean."
        ),
        payload={"routing": decision.model_dump()},
    )


def handle_message(user_id: UUID, message: str, db: Session):
    from schemas import JarvisChatResponse
    from agent_service import run_jarvis_agent, summarize_recent_activity, _tool_search_opportunities, _tool_draft_outreach
    from .tool_registry import execute as execute_tool

    decision = classify(message, {"user_id": str(user_id)})

    # Confidence policy from the architecture spec.
    if decision.confidence < 0.55:
        return _clarify(decision, message)

    if decision.requires_confirmation and decision.intent in {"delete_record", "approve_action", "update_application"}:
        return JarvisChatResponse(
            action="chat",
            reply=approval_message(decision.intent),
            payload={"routing": decision.model_dump()},
        )

    entities = decision.entities or {}
    tool_args: Dict[str, Any] = {}

    if decision.intent == "chat":
        return _grounded_chat(user_id, message, db)

    if decision.intent == "summarize_workspace":
        summary = summarize_recent_activity(user_id, db)
        return JarvisChatResponse(
            action="chat",
            reply="Here is the latest workspace summary.",
            payload={"summary": summary.model_dump()},
        )

    if decision.intent == "create_task":
        tool_args = {
            "title": entities.get("task_title") or entities.get("title") or message[:300],
            "due_date": entities.get("due_date"),
            "estimated_minutes": entities.get("duration_min") or entities.get("estimated_minutes") or 45,
        }
        executed = execute_tool(str(user_id), "create_task", tool_args, db)
        result = executed.get("result", executed)
        return JarvisChatResponse(
            action="task",
            reply="Created the task." if executed.get("ok") and result.get("created") else executed.get("error", "I couldn't create that task."),
            payload=result,
        )

    if decision.intent in {"generate_exam_plan", "reschedule_session"}:
        tool_args = {"available_minutes": entities.get("duration_min") or entities.get("available_minutes")}
        if tool_args["available_minutes"] is not None:
            try:
                tool_args["available_minutes"] = int(tool_args["available_minutes"])
            except (TypeError, ValueError):
                tool_args["available_minutes"] = None

        executed = execute_tool(str(user_id), "generate_study_plan", tool_args, db)
        result = executed.get("result", executed)
        return JarvisChatResponse(
            action="plan",
            reply=(
                "I generated the deterministic SEMS study plan. "
                "The planner owns durations/conflicts; the language model only explains it."
            ) if executed.get("ok") else executed.get("error", "I couldn't generate the study plan."),
            payload=result,
        )

    if decision.intent == "find_opportunity":
        result = _tool_search_opportunities(
            str(user_id),
            db,
            {"query": entities.get("query") or entities.get("role") or message[:120]},
        )
        return JarvisChatResponse(action="matches", reply="Here are the matching stored opportunities.", payload=result)

    if decision.intent == "draft_outreach":
        contact_id = entities.get("contact_id")
        if not contact_id:
            return _clarify(decision.model_copy(update={"reason_code": "missing_contact_id"}), message)
        executed = execute_tool(str(user_id), "draft_outreach", {"contact_id": contact_id}, db)
        result = executed.get("result", executed)
        return JarvisChatResponse(
            action="emails",
            reply=(
                "Prepared the outreach draft in Outbox. It is pending and will not be sent "
                "without explicit approval."
            ) if executed.get("ok") else executed.get("error", "I couldn't prepare the outreach draft."),
            payload=result,
        )

    # For intents that still need free-form tool selection, keep the proven
    # whitelist/tool-call implementation as the compatibility path.
    return run_jarvis_agent(user_id, message, db)
