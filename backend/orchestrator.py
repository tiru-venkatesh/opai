"""
Unified OPA request orchestration.

Flow:
request -> normalize -> typed router -> retrieve -> workflow/tool -> language
layer -> approval -> audit.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from .router import classify
from .approval_engine import approval_message

log = logging.getLogger("opa.orchestrator")

# Server clock is UTC on most hosts; "today"/"tomorrow" must follow the user's calendar day.
_IST = ZoneInfo("Asia/Kolkata")


def _try(db: Session, label: str, fn):
    """Run one optional pipeline step. On failure: log the traceback, roll the session back
    (an aborted transaction would otherwise fail every later query in this request), return None."""
    t0 = time.perf_counter()
    try:
        out = fn()
        log.info("step=%s ms=%.0f hit=%s", label, (time.perf_counter() - t0) * 1000, bool(out))
        return out
    except Exception:
        log.exception("orchestrator step failed: %s", label)
        try:
            db.rollback()
        except Exception:
            log.exception("rollback failed after step: %s", label)
        return None


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
    from rag_api import answer_question, general_answer, _SMALLTALK, GREETING
    from . import groq_client

    if not doc_ids and _SMALLTALK.match(message or ""):
        return JarvisChatResponse(action="chat", reply=GREETING, payload={"answer_mode": "smalltalk"})

    res = answer_question(db, str(user_id), message, history=history, doc_ids=doc_ids)
    if res["mode"] == "none" and not doc_ids and not res["answer"].startswith("You haven't uploaded") and groq_client.groq_enabled():
        try:
            text = general_answer(message, history)
            if text:
                return JarvisChatResponse(action="chat", reply=text, payload={"answer_mode": "general"})
        except Exception:
            log.exception("general_answer failed; falling back to grounded reply")
            db.rollback()
    return JarvisChatResponse(
        action="chat",
        reply=res["answer"],
        payload={"sources": res["sources"], "answer_mode": res["mode"]} if res["sources"] else {"answer_mode": res["mode"]},
    )


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
    from datetime import datetime as _dt, timedelta as _td
    m = (message or "").lower()
    today = _dt.now(_IST).date()
    if _re.search(r"\b(tomorrow|tmrw)\b", m):
        return (today + _td(days=1)).isoformat()
    if _re.search(r"\b(today|tonight)\b", m):
        return today.isoformat()
    return None


def _clarify(decision, message):
    """Unclear request: plain-language reply only. No internal reason codes or routing debug data go to the user."""
    from schemas import JarvisChatResponse
    return JarvisChatResponse(
        action="chat",
        reply=(
            "I’m not sure what you need yet. Could you say a little more? For example, "
            "“plan my day”, “add a task…”, or ask a question about your notes."
        ),
        payload={"answer_mode": "clarify"},
    )


def handle_message(user_id: UUID, message: str, db: Session, history=None, doc_ids=None):
    from schemas import JarvisChatResponse
    from agent_service import run_jarvis_agent, summarize_recent_activity, _tool_search_opportunities
    from .tool_registry import execute as execute_tool

    # Greetings, thanks, "what can you do" / "help": answered locally, before any DB lookup or LLM call.
    if not doc_ids:
        from . import conversation
        from database import User
        t0 = time.perf_counter()
        if conversation.answer(message) is not None:        # pure match first; only then pay for the name lookup
            row = _try(db, "user_name", lambda: db.query(User.name).filter(User.id == str(user_id)).first())
            conv = conversation.answer(message, (row[0] or "").split(" ")[0] if row else None)
            log.info("handler=conversation mode=%s ms=%.0f", conv["payload"]["answer_mode"], (time.perf_counter() - t0) * 1000)
            return JarvisChatResponse(action="chat", reply=conv["reply"], payload=conv["payload"])

    # Meaningless input never reaches an LLM (saves quota/latency, avoids confident replies to nonsense).
    if not doc_ids:
        from . import noise
        from rag_api import _SMALLTALK
        if noise.is_noise(message):
            return JarvisChatResponse(action="chat", reply=noise.NOISE_REPLY, payload={"answer_mode": "noise"})
        if noise.is_short_unknown(message) and not _SMALLTALK.match(message or ""):
            return JarvisChatResponse(action="chat", reply=noise.short_unknown_reply(message),
                                      payload={"answer_mode": "clarify"})

    # Questions about the user's OWN profile (name, college, year, skills, ...): answered from their rows, no LLM.
    if not doc_ids:
        from .identity import answer as identity_answer
        ident = _try(db, "identity", lambda: identity_answer(db, str(user_id), message))
        if ident:
            return JarvisChatResponse(action="chat", reply=ident["reply"], payload=ident["payload"])

    # Reminders ("remind me at 5pm ...", daily-plan nudges) and brief requests ("what should I do today", "I only have 1 hour")
    # are typed flows: they run before the free-form router and produce the same brief/action objects every surface renders.
    if not doc_ids:
        from . import reminder_chat
        rem = _try(db, "reminder", lambda: reminder_chat.handle(user_id, message, db))
        if rem:
            return rem
        from briefs import jarvis as brief_jarvis
        brief_resp = _try(db, "brief", lambda: brief_jarvis.respond(db, str(user_id), message))
        if brief_resp:
            return brief_resp

    # Read-only lookups (lists / counts / deadlines / profile) are answered straight from the
    # user's own DB rows: exact, no LLM, no router. Anything that looks like an action falls through.
    from .direct_db import answer as direct_db_answer
    direct = None if doc_ids else _try(db, "direct_db", lambda: direct_db_answer(db, str(user_id), message))
    if direct:
        return JarvisChatResponse(action="chat", reply=direct["reply"], payload=direct["payload"])

    if not doc_ids:  # "add a project / exam / application ..." writes to the matching section
        from .capture import handle as capture_handle
        captured = _try(db, "capture", lambda: capture_handle(user_id, message, db))
        if captured:
            return captured

    if not doc_ids and re.search(r"\b(uploaded|documents?|docs?|pdfs?|files?)\b", (message or "").lower()) \
            and not re.search(r"\b(task|todo|remind|outreach|email)\b", (message or "").lower()):
        return _grounded_chat(user_id, message, db, history)  # questions about the user's documents are RAG, not workspace-summary

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
        data = summary.model_dump()
        text = ((data.get("summary") or {}).get("recent_outcomes") if isinstance(data.get("summary"), dict) else None) \
            or "Nothing recorded in the past week yet. Add tasks, applications or notes and I will summarise them."
        return JarvisChatResponse(action="chat", reply=text, payload={"answer_mode": "workspace_summary"})

    if decision.intent == "create_task":
        # Guard: the classifier sometimes maps "write/create a prompt/email/code" to create_task.
        if not re.search(r"\b(tasks?|todos?|to-do|reminders?|remind me|deadline)\b", message.lower()):
            return _grounded_chat(user_id, message, db, history)
        _due = entities.get("due_date")
        if not (isinstance(_due, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", _due)):
            _due = extract_due_date(message)
        _mins = entities.get("duration_min") or entities.get("estimated_minutes")
        try:
            _mins = int(re.match(r"\s*(\d+)", str(_mins)).group(1)) if _mins else 45
        except (AttributeError, ValueError):
            _mins = 45
        tool_args = {
            "title": entities.get("task_title") or entities.get("title") or extract_task_title(message),
            "due_date": _due,
            "estimated_minutes": max(5, min(_mins, 600)),
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
                ("I rebuilt your study plan around the time you have. " if decision.intent == "reschedule_session"
                 else "I generated your study plan. ")
                + "The planner sets durations and conflicts; the language model only explains it."
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
