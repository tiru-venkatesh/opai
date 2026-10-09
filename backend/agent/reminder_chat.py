"""Chat flow for reminders (Karna nudges), in the style users know from WhatsApp assistants:

  "Remind me at 2 40pm"                  -> "What should I remind you about at 2:40 PM?"   (reminder waits as awaiting_text)
  "I have a work datastructure record"   -> "Done - I'll remind you today at 2:40 PM about ..."
  "remind me to submit the record at 5pm", "remind me in 20 minutes to stretch"   -> created straight away
  "send me my plan every morning at 7:30" / "stop the daily plan"                  -> daily 'today's plan' notification
  "my reminders"                                                                   -> list

Messages with no clock time ("remind me to X tomorrow") are NOT handled here: the existing task flow keeps them.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import action_service as A
import reminders as RM
from database import Reminder

AWAIT_MINUTES = 15
_REMIND = re.compile(r"\b(remind me|set (?:a |an )?reminder|reminder (?:at|for|in)|ping me|notify me)\b", re.I)
_DAILY = re.compile(r"\b(every (?:morning|day|daily)|each (?:morning|day)|daily|every day)\b", re.I)
_PLANWORD = re.compile(r"\b(plan|brief|schedule|agenda)\b", re.I)
_OFF = re.compile(r"\b(stop|turn off|disable|cancel|no more|don'?t send)\b", re.I)
_CANCEL = re.compile(r"^(cancel|never ?mind|forget it|no need|leave it)\b", re.I)
_CMD = re.compile(r"^(add|create|show|list|what|how|why|when|where|who|plan|find|draft|email|delete|remove|open|update|mark|make|start)\b", re.I)


def looks_like_command(text: str) -> bool:
    from briefs import jarvis as _bj
    return bool(_CMD.match(text.strip()) or _bj.detect(text))


def _resp(action: str, reply: str, payload=None):
    from schemas import JarvisChatResponse
    return JarvisChatResponse(action=action, reply=reply, payload=payload)


def _hhmm(text: str, now, fn) -> Optional[str]:
    """HH:MM (local) for a recurring time. A day-part word settles am/pm when the user did not: 'every morning at 7:30' is 07:30."""
    w = RM.parse_when(text, now, fn(now), fn)
    if not w:
        return None
    local = RM.to_local(w["at_utc"], fn(w["at_utc"]))
    explicit = re.search(r"\d\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", text, re.I) or re.search(r"\b(1[3-9]|2[0-3]|0\d):[0-5]\d\b", text)
    h = local.hour
    if not explicit:
        if re.search(r"\bmorning\b", text, re.I) and h >= 12:
            h -= 12
        elif re.search(r"\b(evening|night|afternoon)\b", text, re.I) and h < 12:
            h += 12
    return f"{h:02d}:{local.minute:02d}"


def handle(user_id, message: str, db: Session, now: Optional[datetime] = None):
    uid, now = str(user_id), now or datetime.utcnow()
    text = " ".join((message or "").split())
    if not text or len(text) > 300:
        return None
    fn = RM.offset_fn(db, uid)
    off = fn(now)
    low = text.lower()

    # ---- daily plan notification settings
    if _PLANWORD.search(low) and (_DAILY.search(low) or re.search(r"\b(send|notify|message|ping) me\b.*\b(plan|brief)\b.*\bat\b", low)):
        if _OFF.search(low):
            RM.upsert_daily_brief(db, uid, None, enabled=False)
            return _resp("reminder", "Okay, I'll stop the daily plan notification.", {"intent": "stop_daily_plan", "status": "completed", "daily_brief": {"enabled": False}})
        hhmm = _hhmm(low, now, fn) or RM.DEFAULT_BRIEF_TIME
        RM.upsert_daily_brief(db, uid, hhmm)
        pretty = RM.fmt_time(datetime.strptime(hhmm, "%H:%M"))
        return _resp("reminder", f"Done - I'll send you today's plan every day at {pretty}.", {"intent": "enable_daily_plan", "status": "completed", "daily_brief": {"enabled": True, "time": hhmm}})

    # ---- list
    if re.search(r"\b(my reminders|what reminders|list (?:my )?reminders|upcoming reminders)\b", low):
        rows = (db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "reminder", Reminder.status == "pending")
                .order_by(Reminder.remind_at).limit(10).all())
        if not rows:
            return _resp("reminder", "You have no upcoming reminders.", {"reminders": []})
        items = [RM.serialize(r, fn(r.remind_at), now) for r in rows]
        return _resp("reminder", "Your reminders: " + "; ".join(f"{i['title']} ({i['local_day']} {i['local_time']})" for i in items) + ".", {"reminders": items})

    # ---- answering "what should I remind you about?"
    awaiting = (db.query(Reminder).filter(Reminder.user_id == uid, Reminder.status == "awaiting_text",
                                          Reminder.created_at >= now - timedelta(minutes=AWAIT_MINUTES))
                .order_by(Reminder.created_at.desc()).first())
    if awaiting and not _REMIND.search(low):
        if _CANCEL.match(low):
            awaiting.status = "cancelled"; db.commit()
            return _resp("reminder", "No problem, I won't set that reminder.")
        if len(text.split()) <= 14 and not text.endswith("?") and not looks_like_command(text):
            title = RM.clean_title(text)
            if title:
                return _finish(db, uid, awaiting, title, fn, now)

    # ---- new reminder (needs an explicit clock time or duration)
    if not _REMIND.search(low):
        return None
    when = RM.parse_when(text, now, off, fn)
    if not when:
        return None
    title = RM.clean_title(when["rest"])
    local = RM.to_local(when["at_utc"], fn(when["at_utc"]))
    if len(title.split()) < 1 or title.lower() in {"me", "it", "this", "something"}:
        r = RM.create(db, uid, None, when["at_utc"], status="awaiting_text")
        r.created_at = now; db.commit()                    # same clock as the follow-up check below
        return _resp("reminder", RM.ask_title_text(local), {"intent": "create_reminder", "status": "needs_input", "awaiting": r.id,
                                                           "next_input": {"field": "title", "question": "What should I remind you about?"}})
    return _finish(db, uid, None, title, fn, now, when)


def _lead_lower(t: str) -> str:
    """'Submit the DS record' -> 'submit the DS record' (acronyms like 'DS' / 'OS lab' keep their capitals)."""
    return t[:1].lower() + t[1:] if len(t) > 1 and t[1].islower() else t


def _finish(db, uid, awaiting: Optional[Reminder], title: str, fn, now: datetime, when=None):
    at = awaiting.remind_at if awaiting else when["at_utc"]
    if awaiting:
        if at <= now:                                      # the time passed while we were asking: next occurrence
            at = RM._advance_daily(at, now, fn)
        awaiting.status, awaiting.title, awaiting.remind_at = "cancelled", title, at   # superseded by the typed action below
        db.commit()
    try:
        rec = A.propose(db, uid, "create_reminder", {"title": title, "remind_at": at.isoformat(), "repeat": "none"}, source="jarvis", reason="Reminder asked in chat")
    except A.ActionError as e:
        return _resp("chat", f"I couldn't set that reminder: {e.detail}")
    r = RM.get(db, uid, rec["result"]["id"])
    local, now_local = RM.to_local(at, fn(at)), RM.to_local(now, fn(now))
    payload = {"intent": "create_reminder", "status": "completed", "reminder": RM.serialize(r, fn(at), now)}
    try:                                                   # confirmation brief: the same schema/actions every surface uses
        from briefs import jarvis, service
        b = service.generate(db, uid, "reminder", {"reminder_id": r.id})
        payload.update({"brief_id": b["brief_id"], "brief": jarvis.preview(b), "actions": jarvis.actions_for(b)})
    except Exception:
        db.rollback()
    return _resp("reminder", RM.confirm_text(title, local, now_local), payload)
