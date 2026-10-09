"""JARVIS as the brief navigator.

JARVIS does not improvise answers for planning questions: it creates or fetches the right brief, speaks a two-sentence
summary, and offers the next executable action. "I only have one hour" re-runs the Daily brief with capacity_override=60.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from . import core, service

_WORDNUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4}


def parse_minutes(text: str) -> Optional[int]:
    t = (text or "").lower()
    if re.search(r"\bhalf an? (hour|hr)\b", t):
        return 30
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b", t)
    if m:
        return int(float(m.group(1)) * 60)
    m = re.search(r"\b(an?|one|two|three|four)\s*(hours?|hrs?)\b", t)
    if m:
        return _WORDNUM[m.group(1)] * 60
    m = re.search(r"(\d+)\s*(minutes?|mins?)\b", t)
    return int(m.group(1)) if m else None


_CAPACITY = re.compile(r"\bi\s*(?:'?ve| have)?\s*(?:only |just )?(?:have |got )?(?:only |just )?(?:about |around )?"
                       r"(?:\d+(?:\.\d+)?|an?|one|two|three|four|half an?)\s*(?:hours?|hrs?|h|minutes?|mins?)\b", re.I)
_DAILY = re.compile(r"\b(what (should|do|can|shall) i (do|work on|focus on)|plan my (day|today)|today'?s (plan|brief)|operating brief|"
                    r"what'?s (on )?(my plan )?today|ivala em cheyali)\b", re.I)


def detect(message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Narrow, high-precision routing for planning-style requests. Everything else falls through to the normal agent."""
    t = " ".join((message or "").lower().split())
    if not t or len(t) > 240:
        return None
    if re.search(r"\b(pending approvals?|needs? my approval|waiting for (my )?approval|anything to approve|what needs approval)\b", t):
        return "approval", {}
    if re.search(r"\b(weekly review|review (of )?my week|how was my week|how did (this|my) week go)\b", t):
        return "weekly_review", {}
    if re.search(r"\b(i missed|fell behind|i'?m behind|behind on (my )?(plan|study|schedule)|got off track|catch up|recovery (brief|plan))\b", t):
        return "recovery", {}
    if re.match(r"^(should i|is it worth|would it be better|shall i)\b", t):
        return "decision", {"question": message.strip(), "estimated_minutes": parse_minutes(t)}
    if re.search(r"\b(exam (brief|readiness|risk|status)|how (ready|prepared) am i|am i ready for)\b", t):
        return "exam_readiness", {}
    if re.search(r"\bdsa (brief|roadmap|today|plan)\b", t):
        return "dsa_roadmap", {}
    tired = bool(re.search(r"\b(tired|exhausted|drained|low energy)\b", t))
    cap = parse_minutes(t) if _CAPACITY.search(t) else None
    if _DAILY.search(t) or cap:
        p: Dict[str, Any] = {}
        if cap:
            p["capacity_override"] = max(10, min(cap, 720))
        if tired:
            p["energy"] = "low"
        return "daily_plan", p
    return None


def _lc(s: str) -> str:
    s = (s or "").strip().rstrip(".")
    return s


def spoken_summary(b: Dict[str, Any]) -> str:
    """Two sentences. Built from the finished brief only."""
    pri = b.get("priorities") or []
    if b["type"] == "daily_plan":
        ctx = b["context"]
        if not pri:
            return b["summary"]
        p = pri[0]
        first = (f"You have {ctx['capacity_min']} minutes today with {ctx['buffer_min']} kept as buffer."
                 if ctx.get("capacity_override") else f"You have {ctx['capacity_min']} minutes available today, with {ctx['buffer_min']} as buffer.")
        return f"{first} Start with {p['title']} for {p['duration_min']} minutes: {_lc(p['reason_text'])}."
    if b["type"] == "decision" and pri:
        return f"{b['summary']} I can add it to your plan if you want."
    nxt = next((a for a in b.get("actions", []) if a.get("primary")), None)
    return b["summary"] + (f" Next: {nxt['label'].lower()}." if nxt else "")


def preview(b: Dict[str, Any]) -> Dict[str, Any]:
    """Small brief card for the popup / WhatsApp / notifications: no brief logic lives in the client."""
    return {"brief_id": b["brief_id"], "type": b["type"], "title": b["title"], "summary": b["summary"], "confidence": b["confidence"],
            "priorities": [{"rank": p["rank"], "title": p["title"], "duration_min": p.get("duration_min"), "reason_text": p.get("reason_text")} for p in b["priorities"][:3]],
            "alerts": [a["title"] for a in b["alerts"][:2]]}


def actions_for(b: Dict[str, Any], limit: int = 3) -> list:
    """Executable actions (same objects as on the brief) + 'open brief' (+ 'adjust plan' for daily). Client-only ones are flagged."""
    ex = [a for a in b["actions"] if a["kind"] != "decision"]
    first = next((a for a in ex if a.get("primary")), ex[0] if ex else None)
    out = [first] if first else []
    top = b["priorities"][0]["actions"] if b["priorities"] else []
    out += [a for a in top if a["action_id"] != (first or {}).get("action_id") and a["kind"] != "decision"][:max(0, limit - 1)]
    out.append({"id": "open:" + b["brief_id"], "action_id": "open:" + b["brief_id"], "brief_id": b["brief_id"], "type": "open_brief", "label": "View brief",
                "kind": "navigate", "risk": "low", "status": "available", "link": f"briefs.html?brief={b['brief_id']}", "client_only": True})
    if b["type"] == "daily_plan":
        out.append({"id": "prompt:adjust", "action_id": "prompt:adjust", "brief_id": b["brief_id"], "type": "adjust_plan", "label": "Adjust plan", "kind": "prompt",
                    "risk": "low", "status": "available", "prompt": "I only have 60 minutes", "client_only": True})
    return out


def respond(db: Session, uid: str, message: str):
    """Returns a JarvisChatResponse, or None when the message is not a brief request."""
    hit = detect(message)
    if not hit:
        return None
    btype, params = hit
    from schemas import JarvisChatResponse
    try:
        brief = service.generate(db, uid, btype, params)
    except core.BriefError as e:
        if e.status in (404, 422):                 # e.g. "no upcoming exams": say so instead of failing
            return JarvisChatResponse(action="chat", reply=str(e.detail))
        raise
    return JarvisChatResponse(action="brief", reply=spoken_summary(brief),
                              payload={"intent": _intent_name(btype), "status": "completed", "brief_id": brief["brief_id"], "brief_type": btype,
                                       "brief": brief, "actions": actions_for(brief)})


def _intent_name(btype: str) -> str:
    return {"daily_plan": "generate_daily_brief", "weekly_review": "weekly_review", "recovery": "recovery_plan", "approval": "show_approvals",
            "decision": "decision_support", "exam_readiness": "generate_exam_brief", "dsa_roadmap": "generate_dsa_brief"}.get(btype, btype)
