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


def _extractive_reply(hits, limit: int = 4, max_chars: int = 260) -> str:
    """Direct answer straight from the user's own indexed data - no LLM involved.
    Used when there is no Groq key, or the language layer fails."""
    if not hits:
        return ""
    # Keep only hits close to the best one, so weakly related chunks don't pad the answer.
    top = hits[0]["score"]
    hits = [h for h in hits if h["score"] >= 0.5 * top]
    lines = []
    for h in hits[:limit]:
        title = (h.get("meta") or {}).get("title") or h["source_type"]
        body = " ".join(h["content"].split())
        prefix = f"[{title}] "
        if body.startswith(prefix):
            body = body[len(prefix):]
        if len(body) > max_chars:
            body = body[:max_chars].rsplit(" ", 1)[0] + "..."
        lines.append(f"- {title}: {body}")
    return "Here is what I found in your data:\n" + "\n".join(lines)


def _grounded_chat(user_id: UUID, message: str, db: Session, history=None, doc_ids=None):
    """RAG answer over the user's workspace + uploaded docs, with [n] citations and conversation history."""
    from schemas import JarvisChatResponse
    from rag_api import answer_question

    res = answer_question(db, str(user_id), message, history=history, doc_ids=doc_ids)
    return JarvisChatResponse(
        action="chat",
        reply=res["answer"],
        payload={"sources": res["sources"], "answer_mode": res["mode"]} if res["sources"] else {"answer_mode": res["mode"]},
    )


_TASK_LEAD = None


def extract_task_title(message: str) -> str:
    """'add a task to revise paging tomorrow' -> 'Revise paging'. Falls back to the cleaned sentence."""
    import re as _re
    t = " ".join((message or "").strip().split())
    t = _re.sub(r"^(?:please\s+|can you\s+|could you\s+|pls\s+)*(?:add|create|make|set up|new)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?"
                r"(?:new\s+)?(?:task|todo|to-do|reminder)\s*(?:to|for|called|named|:|-)?\s*", "", t, flags=_re.I)
    t = _re.sub(r"^(?:remind me to|remind me)\s+", "", t, flags=_re.I)
    t = _re.sub(r"\s+(?:by\s+)?(?:today|tomorrow|tonight|tmrw|next week|this week|"
                r"(?:on|by|before)\s+(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)[a-z]*|"
                r"(?:on|by|before)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+[a-z]{3,9})?|"
                r"(?:in|within)\s+\d+\s+(?:days?|weeks?))\s*[.!]?$", "", t, flags=_re.I)
    t = t.strip(" .,:;-")
    return (t[:1].upper() + t[1:]) if t else (message or "")[:300]


def extract_due_date(message: str):
    import re as _re
    from datetime import date as _d, timedelta as _td
    m = (message or "").lower()
    if _re.search(r"\b(tomorrow|tmrw)\b", m):
        return (_d.today() + _td(days=1)).isoformat()
    if _re.search(r"\b(today|tonight)\b", m):
        return _d.today().isoformat()
    return None


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


def handle_message(user_id: UUID, message: str, db: Session, history=None, doc_ids=None):
    from schemas import JarvisChatResponse
    from agent_service import run_jarvis_agent, summarize_recent_activity, _tool_search_opportunities, _tool_draft_outreach
    from .tool_registry import execute as execute_tool

    # Read-only lookups (lists / counts / deadlines / profile) are answered straight from the
    # user's own DB rows: exact, no LLM, no router. Anything that looks like an action falls through.
    try:
        from .direct_db import answer as direct_db_answer
        direct = None if doc_ids else direct_db_answer(db, str(user_id), message)
    except Exception:
        direct = None
    if direct:
        return JarvisChatResponse(action="chat", reply=direct["reply"], payload=direct["payload"])

    if not doc_ids:  # "add a project / exam / application ..." writes to the matching section
        try:
            from .capture import handle as capture_handle
            captured = capture_handle(user_id, message, db)
        except Exception:
            captured = None
        if captured:
            return captured

    if doc_ids:  # "Ask only this doc": skip routing and answer strictly from the selected documents
        return _grounded_chat(user_id, message, db, history, doc_ids)

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
        return _grounded_chat(user_id, message, db, history)

    if decision.intent == "summarize_workspace":
        summary = summarize_recent_activity(user_id, db)
        return JarvisChatResponse(
            action="chat",
            reply="Here is the latest workspace summary.",
            payload={"summary": summary.model_dump()},
        )

    if decision.intent == "create_task":
        import re as _re
        # Guard: the classifier sometimes maps "write/create a prompt/email/code" to create_task.
        if not _re.search(r"\b(tasks?|todos?|to-do|reminders?|remind me|deadline)\b", message.lower()):
            return _grounded_chat(user_id, message, db, history)
        _due = entities.get("due_date")
        if not (isinstance(_due, str) and _re.fullmatch(r"\d{4}-\d{2}-\d{2}", _due)):
            _due = extract_due_date(message)
        tool_args = {
            "title": entities.get("task_title") or entities.get("title") or extract_task_title(message),
            "due_date": _due,
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
