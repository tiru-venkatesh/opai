"""KARNA UX helpers: pure functions (no DB, no LLM) so they are fast, testable and cannot hallucinate.

  briefing(ctx, docs, pending_memory)  -> what the empty screen shows: a greeting, a few "needs attention" cards and starter prompts,
                                          all built from the user's own verified data (karna_prompt.collect_context).
  followups(action, reply, payload, sources, mode, user_text) -> up to 3 short next-step prompts shown under an answer.
Every card carries a `prompt` that the page puts in the composer; nothing is sent or changed by clicking a card.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

_MAX_CARDS = 4


def _when(days: Optional[int]) -> str:
    if days is None:
        return "no date"
    if days < 0:
        return "overdue"
    return "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"


def _greeting(name: Optional[str], hour: Optional[int]) -> str:
    h = datetime.now().hour if hour is None else hour
    part = "Good morning" if 4 <= h < 12 else "Good afternoon" if 12 <= h < 17 else "Good evening"
    first = (name or "").strip().split(" ")[0]
    return f"{part}, {first}" if first else part


def briefing(ctx: Dict[str, Any], docs: int = 0, pending_memory: int = 0, hour: Optional[int] = None) -> Dict[str, Any]:
    cards: List[Dict[str, str]] = []

    pend = int(ctx.get("outbox_pending") or 0)
    if pend:
        cards.append({"kind": "approval", "tone": "warn", "title": f"{pend} draft{'s' if pend != 1 else ''} waiting for you",
                      "detail": "Review and approve before anything is used.", "prompt": "Show my pending drafts"})
    apps = ctx.get("applications") or []
    soon = [a for a in apps if a.get("days") is not None and a["days"] <= 7]
    if soon:
        a = sorted(soon, key=lambda x: x["days"])[0]
        cards.append({"kind": "deadline", "tone": "warn" if a["days"] <= 2 else "info", "title": f"{a['role']} at {a['company']}",
                      "detail": f"Deadline {_when(a['days'])}", "prompt": f"What is left to do for {a['role']} at {a['company']}?"})
    exams = ctx.get("exams") or []
    if exams:
        e = exams[0]
        name = f"{e['course']} {e.get('type', '')}".strip()
        cards.append({"kind": "exam", "tone": "warn" if (e.get("days") is not None and e["days"] <= 3) else "info",
                      "title": name, "detail": f"Exam {_when(e.get('days'))}", "prompt": f"How should I prepare for {e['course']}?"})
    today = ctx.get("today") or []
    if today:
        t = today[0]
        cards.append({"kind": "today", "tone": "ok", "title": t["title"],
                      "detail": f"First on today's plan · {t.get('minutes', '?')} min", "prompt": "What is on my plan today and why?"})
    if pending_memory:
        cards.append({"kind": "memory", "tone": "info", "title": f"{pending_memory} thing{'s' if pending_memory != 1 else ''} to confirm",
                      "detail": "KARNA only remembers what you approve.", "prompt": ""})

    starters: List[str] = []
    if today:
        starters.append("What should I do first today?")
    else:
        starters.append("Plan my next two hours")
    if exams:
        starters.append(f"Quiz me on {exams[0]['course']}")
    if apps:
        starters.append("Draft a follow-up for my open applications")
    if docs:
        starters.append("Summarise my uploaded documents")
    starters += ["Show my upcoming deadlines", "Add a project called My App using React"]
    seen, out = set(), []
    for s in starters:
        if s not in seen:
            seen.add(s)
            out.append(s)

    return {
        "greeting": _greeting(ctx.get("name"), hour),
        "headline": "What do you want to get done?" if (today or exams or apps) else "Tell KARNA what you are working on",
        "cards": cards[:_MAX_CARDS],
        "starters": out[:5],
        "stats": {"today": len(today), "exams": len(exams), "applications": len(apps), "drafts": pend, "docs": int(docs)},
    }


def followups(action: Optional[str], reply: str = "", payload: Any = None, sources: Optional[list] = None,
              mode: str = "ws", user_text: str = "") -> List[str]:
    """Deterministic, honest suggestions: only things KARNA can really do, never claims anything was done."""
    pl = payload if isinstance(payload, dict) else {}
    out: List[str] = []
    low = (user_text or "").lower()

    if mode == "gen":
        return ["Give me an example", "Explain it more simply", "Quiz me on this"]
    if pl.get("intent") == "memory_pending" or pl.get("memory"):
        return []
    if pl.get("answer_mode") == "capabilities":
        return ["What is on my plan today?", "Show my upcoming deadlines"]
    if action == "plan" or "plan" in low:
        out += ["Why this order?", "I only have 1 hour"]
    if action in ("emails", "outreach") or "draft" in low or "email" in low:
        out += ["Make it shorter", "Show my pending drafts"]
    if action == "matches" or "opportunit" in low:
        out += ["Which one fits me best?", "Draft a note for the top one"]
    if sources:
        out += ["Summarise this in 3 bullets", "Where did you find that?"]
    if pl.get("answer_mode") == "capture" and pl.get("created"):
        out += ["What is due next?"]
    if "deadline" in low or "exam" in low:
        out += ["What should I do first?"]
    out += ["What is due next?", "What should I do first today?"]
    seen, res = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res[:3]
