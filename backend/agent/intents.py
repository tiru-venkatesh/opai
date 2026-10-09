"""Typed intent layer. A small, explicit registry: the model/regexes can only pick from these names, every intent declares its
required fields, risk, allowed channels and handler, and missing fields turn into a clarification instead of a guess.

    text -> resolve() -> Intent(name, confidence, entities, missing_fields, risk) -> handler (orchestrator / brief / reminder flow)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

ALL_CHANNELS = ("web_chat", "popup", "whatsapp", "api")


@dataclass(frozen=True)
class IntentDef:
    name: str
    required: tuple = ()
    optional: tuple = ()
    risk: str = "low"
    channels: tuple = ALL_CHANNELS
    handler: str = ""
    confirmation_required: bool = False


def _d(name, required=(), optional=(), risk="low", handler="", confirm=False, channels=ALL_CHANNELS):
    return IntentDef(name, tuple(required), tuple(optional), risk, tuple(channels), handler or name + "_handler", confirm)


REGISTRY: Dict[str, IntentDef] = {i.name: i for i in [
    _d("create_reminder", ["title", "due_at"], ["repeat_rule", "timezone"], handler="reminder_chat.handle"),
    _d("complete_reminder", ["reminder_id"], handler="actions.complete_reminder"),
    _d("snooze_reminder", ["reminder_id"], ["minutes"], handler="actions.snooze_reminder"),
    _d("enable_daily_plan", [], ["time"], risk="medium", handler="reminder_chat.handle"),   # explicit chat request = the confirmation
    _d("stop_daily_plan", [], [], risk="medium", handler="reminder_chat.handle"),
    _d("generate_daily_brief", [], ["capacity_override", "energy"], handler="briefs.daily_plan"),
    _d("generate_exam_brief", [], ["exam_id"], handler="briefs.exam_readiness"),
    _d("generate_dsa_brief", [], [], handler="briefs.dsa_roadmap"),
    _d("create_task", ["title"], ["due_date", "estimated_minutes"], handler="orchestrator.capture"),
    _d("create_project", ["title"], [], handler="orchestrator.capture"),
    _d("create_application", ["company", "role"], ["deadline", "link"], handler="orchestrator.capture"),
    _d("draft_outreach", ["contact_id"], [], risk="medium", handler="briefs.outreach_research", confirm=True),
    _d("approve_action", ["action_id", "payload_hash"], [], risk="high", handler="actions.approve", confirm=True),
    _d("reject_action", ["action_id"], [], handler="actions.reject"),
    _d("show_approvals", [], [], handler="briefs.approval"),
    _d("weekly_review", [], [], handler="briefs.weekly_review"),
    _d("recovery_plan", [], [], handler="briefs.recovery"),
    _d("decision_support", ["question"], ["estimated_minutes"], handler="briefs.decision"),
    _d("general_chat", [], [], handler="orchestrator.chat"),
]}


@dataclass
class Intent:
    name: str
    confidence: float
    entities: Dict[str, Any] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    risk: str = "low"
    channel_allowed: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {"intent": self.name, "confidence": round(self.confidence, 2), "entities": self.entities,
                "missing_fields": self.missing_fields, "risk": self.risk}


_BRIEF_MAP = {"daily_plan": "generate_daily_brief", "weekly_review": "weekly_review", "recovery": "recovery_plan", "approval": "show_approvals",
              "decision": "decision_support", "exam_readiness": "generate_exam_brief", "dsa_roadmap": "generate_dsa_brief"}
_TASK = re.compile(r"^\s*(?:please\s+)?(add|create|make)\s+(?:a\s+|an\s+|the\s+)?task\b[:\s-]*(.*)$", re.I)
_PROJECT = re.compile(r"^\s*(?:please\s+)?(add|create|start)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?project\b[:\s-]*(.*)$", re.I)


def build(name: str, confidence: float, entities: Dict[str, Any], channel: str) -> Intent:
    d = REGISTRY[name]                                      # KeyError = the classifier tried to invent an intent: refuse loudly
    missing = [f for f in d.required if entities.get(f) in (None, "", [])]
    return Intent(name, confidence, {k: v for k, v in entities.items() if v is not None}, missing, d.risk, channel in d.channels)


def resolve(db: Session, uid: str, text: str, channel: str = "web_chat", now: Optional[datetime] = None) -> Intent:
    import reminders as RM
    from agent import reminder_chat as RC
    from briefs import jarvis
    from database import Reminder
    now = now or datetime.utcnow()
    t = " ".join((text or "").split())
    low = t.lower()
    fn = RM.offset_fn(db, uid)
    off = fn(now)

    # an explicit command is never an answer to "what should I remind you about?"
    task = _TASK.match(t)
    if task:
        return build("create_task", 0.95, {"title": RM.clean_title(task.group(2)) or None}, channel)
    proj = _PROJECT.match(t)
    if proj:
        return build("create_project", 0.9, {"title": RM.clean_title(proj.group(2)) or None}, channel)

    if RC._PLANWORD.search(low) and (RC._DAILY.search(low) or re.search(r"\b(send|notify|message|ping) me\b.*\b(plan|brief)\b.*\bat\b", low)):
        if RC._OFF.search(low):
            return build("stop_daily_plan", 0.95, {}, channel)
        return build("enable_daily_plan", 0.95, {"time": RC._hhmm(low, now, fn) or RM.DEFAULT_BRIEF_TIME}, channel)

    awaiting = (db.query(Reminder).filter(Reminder.user_id == uid, Reminder.status == "awaiting_text",
                                          Reminder.created_at >= now - timedelta(minutes=RC.AWAIT_MINUTES)).order_by(Reminder.created_at.desc()).first())
    if RC._REMIND.search(low):
        w = RM.parse_when(t, now, off, fn)
        if w:
            return build("create_reminder", 0.98, {"title": RM.clean_title(w["rest"]) or None, "due_at": w["at_utc"].isoformat() + "Z"}, channel)
    elif awaiting and not RC.looks_like_command(t) and len(t.split()) <= 14 and not t.endswith("?") and not RC._CANCEL.match(low):
        return build("create_reminder", 0.9, {"title": RM.clean_title(t), "due_at": awaiting.remind_at.isoformat() + "Z"}, channel)

    hit = jarvis.detect(t)
    if hit and hit[0] in _BRIEF_MAP:
        ent = {k: v for k, v in hit[1].items() if v is not None}
        return build(_BRIEF_MAP[hit[0]], 0.9, ent, channel)
    return build("general_chat", 0.5, {}, channel)
