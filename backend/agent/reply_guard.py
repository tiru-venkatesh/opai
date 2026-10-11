"""Reply guard: KARNA may not claim an action happened unless a tool result in THIS turn confirms it.

Pure and deterministic. Sentences that claim an unsupported action are removed and a plain note is appended.
Negations ("I can't send"), questions, offers ("I can draft") and conditionals are left alone.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# verb -> tools whose SUCCESS supports the claim. An empty set means "KARNA can never do this".
_SUPPORT = {
    "sent": set(), "emailed": set(), "mailed": set(), "submitted": set(), "applied": set(), "deleted": set(), "removed": set(),
    "cancelled": set(), "canceled": set(), "booked": set(), "scheduled": set(), "forwarded": set(), "contacted": set(),
    "created": {"create_task", "draft_outreach", "generate_study_plan"}, "added": {"create_task"},
    "updated": {"update_task_status"}, "marked": {"update_task_status"},
    "drafted": {"draft_outreach"}, "prepared": {"draft_outreach", "generate_study_plan"}, "saved": {"create_task", "draft_outreach"},
}
_VERBS = "|".join(sorted(_SUPPORT, key=len, reverse=True))
_ACTIVE = re.compile(rf"\b(?:i|we)(?:'ve|\s+have|'ll have)?\s+(?:just\s+|already\s+|now\s+)?({_VERBS})\b", re.I)
_PASSIVE = re.compile(rf"\b(?:email|mail|message|application|reminder|task|draft|request|invite)s?\s+(?:has|have)?\s*(?:been|was|were|is now|are now)\s+({_VERBS})\b", re.I)
_DONE = re.compile(r"^\s*(?:done|all set|completed)\b", re.I)
_SKIP = re.compile(r"\b(?:not|never|cannot|unable|if|once|unless|let me know|want me to|do you want)\b|n't|\?\s*$", re.I)
SAFE_NOTE = "I haven't sent, submitted or changed anything beyond what the tool results above confirm. Drafts wait in your Outbox for your approval."


def _ok_tools(tool_calls: Optional[List[Dict[str, Any]]]) -> set:
    ok = set()
    for t in tool_calls or []:
        r = t.get("result")
        if t.get("tool") and not (isinstance(r, dict) and r.get("error")):
            ok.add(t["tool"])
    return ok


def _sentences(text: str) -> List[str]:
    return re.split(r"(?<=[.!?\n])\s+", text.strip()) if text and text.strip() else []


def _claim(sentence: str) -> Optional[str]:
    if _SKIP.search(sentence):
        return None
    m = _ACTIVE.search(sentence) or _PASSIVE.search(sentence)
    if m:
        return m.group(1).lower()
    if _DONE.match(sentence):
        return "done"
    return None


def check_reply(reply: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> Tuple[str, List[str]]:
    """Returns (safe_reply, problems). problems lists the removed claims (for logging/tests)."""
    ok = _ok_tools(tool_calls)
    keep, problems = [], []
    for s in _sentences(reply):
        verb = _claim(s)
        if verb == "done":
            if not ok:
                problems.append(s)
                continue
        elif verb is not None:
            need = _SUPPORT.get(verb, set())
            if not (need & ok):
                problems.append(s)
                continue
        keep.append(s)
    if not problems:
        return reply, []
    body = " ".join(keep).strip()
    return (body + " " if body else "") + SAFE_NOTE, problems
