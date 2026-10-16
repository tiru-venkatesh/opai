"""Deterministic small-talk / capability replies. No LLM, no tools, no retrieval: instant, can't hallucinate features.

Handles ONLY whole-message matches (greeting, thanks, bye, "what can you do", "help", Tenglish variants), so
"help me with my resume" or "hi, add a task" still go through the normal pipeline.
The capability list is the single source of truth for what KARNA says it can do: edit it when features change.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

ENABLED_CAPABILITIES = [
    "Plan your day and build study plans around the time you have",
    "Track exams, tasks, projects and internship applications",
    "Set reminders",
    "Answer questions from your uploaded documents, with citations",
    "Prepare outreach email drafts for your review (nothing is sent without your approval)",
]
EXAMPLES = ["Plan my next two hours", "Show my upcoming deadlines"]

_UNSET_NAMES = {"", "user", "guest"}

_GREET = re.compile(r"(?:hi+|hello+|hey+|hii+|yo|hola|namaste|namaskaram|good (?:morning|afternoon|evening))(?:\s+(?:karna|there))?[\s.!]*", re.I)
_THANKS = re.compile(r"(?:thanks?|thank you|thx|ty|thanks a lot|thank you so much)(?:\s+(?:karna|bro))?[\s.!]*", re.I)
_BYE = re.compile(r"(?:bye+|goodbye|good night|see you|cya)[\s.!]*", re.I)
_CAPS = re.compile(
    r"(?:"
    r"what (?:can|do|all can|all do) (?:you|u)(?: do| handle| help(?: with| me with)?)?"
    r"|what (?:are|r) (?:you|u)(?: capable of)?"
    r"|what (?:is|s) karna|who (?:are|r) (?:you|u)"
    r"|how (?:can|do) (?:you|u) help(?: me)?"
    r"|(?:your|ur|ur) (?:features|capabilities|abilities)|what (?:are|r) (?:your|ur) (?:features|capabilities)"
    r"|help(?: me)?|help menu|menu|commands"
    r"|(?:nee|nuvvu|nuv|ni) (?:features|capabilities) (?:enti|emiti|em unnayi)"
    r"|(?:nuvvu|nuv) (?:em|enti|emi) (?:cheyagalav|chestav|cheyagalavu|chestavu|cheyagalava)"
    r"|(?:nuvvu|nuv) (?:ela|ela ela|ela) help (?:chestav|chestavu|cheyagalav)"
    r"|(?:nuvvu|nuv) evaru"
    r")[\s?.!]*", re.I)


def _norm(msg: str) -> str:
    return " ".join((msg or "").strip().replace("’", "'").split())


def capabilities_reply() -> str:
    lines = "\n".join(f"- {c}" for c in ENABLED_CAPABILITIES)
    ex = " or ".join(f"“{e}”" for e in EXAMPLES)
    return f"I’m KARNA, your assistant inside OPAI. Here’s what I can do:\n{lines}\n\nTry: {ex}."


def answer(message: str, first_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return {reply, payload} for pure conversation, else None (continue the normal pipeline)."""
    m = _norm(message)
    if not m or len(m) > 60:
        return None
    name = (first_name or "").strip()
    name = "" if name.lower() in _UNSET_NAMES else name
    if _GREET.fullmatch(m):
        who = f", {name}" if name else ""
        return {"reply": f"Hi{who}. What would you like to work on today?", "payload": {"answer_mode": "smalltalk"}}
    if _THANKS.fullmatch(m):
        return {"reply": "You’re welcome. Let me know if you need anything else.", "payload": {"answer_mode": "smalltalk"}}
    if _BYE.fullmatch(m):
        return {"reply": "Bye. I’m here whenever you need me.", "payload": {"answer_mode": "smalltalk"}}
    if _CAPS.fullmatch(m):
        return {"reply": capabilities_reply(), "payload": {"answer_mode": "capabilities"}}
    return None
