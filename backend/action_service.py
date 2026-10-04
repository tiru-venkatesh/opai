"""Typed action contract + risk policy + executor.

Models (Jev/Groq/UI) *propose* an action; this module validates it, applies the risk
policy and is the only place that executes it. External / destructive intents never run
directly: they wait for approval, and even then "send_email" only creates an Outbox item
(sending stays in the Outbox flow). Every step is written to the audit log."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from agent.approval_engine import requires_approval as policy_requires_approval
from audit.logger import record as audit
from database import (ActionRecord, ActionApproval, Application, Academic, OutboxItem,
                      StudyBlock, Task, Topic, Exam)


# ---------- payload contracts (one per intent) ----------
class CreateTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[date] = None
    estimated_minutes: int = Field(default=45, ge=5, le=480)
    type: str = "general"


class CreateStudyBlock(BaseModel):
    exam_id: str
    topic_id: Optional[str] = None
    date: date
    duration_min: int = Field(ge=15, le=180)
    mode: str = "learn"

    @field_validator("mode")
    @classmethod
    def _mode(cls, v):
        if v not in {"learn", "practice", "recall", "revise", "mock_test"}:
            raise ValueError("unknown study mode")
        return v


class TodayOp(BaseModel):
    kind: str                       # study_block | task | application | academic
    ref_id: str
    op: str                         # start | complete | skip | snooze
    actual_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    difficulty_felt: Optional[int] = Field(default=None, ge=1, le=5)
    confidence_now: Optional[int] = Field(default=None, ge=1, le=5)
    days: int = Field(default=1, ge=1, le=14)

    @field_validator("kind")
    @classmethod
    def _k(cls, v):
        if v not in {"study_block", "task", "application", "academic"}:
            raise ValueError("unknown item kind")
        return v

    @field_validator("op")
    @classmethod
    def _o(cls, v):
        if v not in {"start", "complete", "skip", "snooze"}:
            raise ValueError("unknown op")
        return v


class SendEmail(BaseModel):
    to: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)


class UpdateApplicationStatus(BaseModel):
    application_id: str
    status: str = Field(min_length=1, max_length=40)


class DeleteTask(BaseModel):
    task_id: str


# intent -> (contract, base risk)
INTENTS: Dict[str, tuple] = {
    "create_task": (CreateTask, "low"),
    "create_study_block": (CreateStudyBlock, "low"),
    "today_op": (TodayOp, "low"),
    "send_email": (SendEmail, "high"),
    "update_application_status": (UpdateApplicationStatus, "high"),   # "Applied" etc.: user-confirmed, never automatic
    "delete_task": (DeleteTask, "high"),
}


class ActionError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail
        super().__init__(detail)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def idem_key(user_id: str, intent: str, payload: dict, scope: str = "") -> str:
    """Stable per user/intent/payload/day-scope, so a retried request cannot create a duplicate."""
    raw = f"{user_id}|{intent}|{scope}|{payload_hash(payload)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def risk_for(intent: str) -> str:
    return INTENTS[intent][1]


def _owner(db: Session, model, rid: str, uid: str):
    row = db.query(model).filter(model.id == str(rid)).first()
    if row is None or str(getattr(row, "user_id", uid)) != uid:   # models without user_id (Topic) are checked via their exam
        raise ActionError(404, f"{model.__name__} not found")
    return row


def serialize(a: ActionRecord) -> dict:
    return {"action_id": a.id, "intent": a.intent, "risk": a.risk, "status": a.status, "source": a.source,
            "payload": a.payload_json or {}, "result": a.result_json or {}, "reason": a.reason,
            "confidence": float(a.confidence or 0), "requires_approval": bool(a.requires_approval),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "executed_at": a.executed_at.isoformat() if a.executed_at else None}


def propose(db: Session, user_id: str, intent: str, payload: dict, *, source: str = "ui", reason: str = "",
            confidence: float = 1.0, scope: str = "", execute_low_risk: bool = True) -> dict:
    """Validate -> policy -> (execute | wait for approval). Returns the serialized action."""
    uid = str(user_id)
    if intent not in INTENTS:
        raise ActionError(422, f"Unknown intent '{intent}'")
    contract, base_risk = INTENTS[intent]
    try:
        clean = contract(**(payload or {})).model_dump(mode="json")
    except ValidationError as e:
        raise ActionError(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))

    key = idem_key(uid, intent, clean, scope)
    existing = db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.idempotency_key == key).first()
    if existing and existing.status != "failed":
        out = serialize(existing); out["duplicate"] = True
        return out

    needs = base_risk != "low" or policy_requires_approval(intent, tool_name=intent)
    a = existing or ActionRecord(user_id=uid, intent=intent, idempotency_key=key)
    a.risk, a.source, a.payload_json, a.reason = base_risk, source, clean, reason
    a.confidence, a.requires_approval = confidence, needs
    a.status = "pending_approval" if needs else "proposed"
    a.result_json = {}
    if existing is None:
        db.add(a)
    db.commit(); db.refresh(a)
    audit(db, uid, f"action.propose:{intent}", {"action_id": a.id, "source": source}, {"status": a.status}, base_risk)
    if not needs and execute_low_risk:
        return execute(db, a)
    return serialize(a)


def execute(db: Session, a: ActionRecord) -> dict:
    uid = a.user_id
    if a.status == "executed":
        return serialize(a)
    if a.requires_approval and a.status != "approved_pending_exec":
        raise ActionError(409, "Action requires approval before execution")
    try:
        result = _HANDLERS[a.intent](db, uid, a.payload_json or {})
        a.status, a.result_json, a.executed_at = "executed", result, datetime.utcnow()
        db.commit(); db.refresh(a)
        audit(db, uid, f"action.execute:{a.intent}", {"action_id": a.id}, result, a.risk)
    except ActionError:
        db.rollback(); raise
    except Exception as e:  # never leave a half-applied action looking successful
        db.rollback()
        a = db.query(ActionRecord).filter(ActionRecord.id == a.id).first()
        a.status, a.result_json = "failed", {"error": str(e)[:300]}
        db.commit()
        audit(db, uid, f"action.execute:{a.intent}", {"action_id": a.id}, {"error": str(e)[:300]}, a.risk, status="error")
        raise ActionError(500, "Action failed; nothing was changed")
    return serialize(a)


def decide(db: Session, user_id: str, action_id: str, approve: bool, payload_hash_seen: Optional[str] = None) -> dict:
    uid = str(user_id)
    a = db.query(ActionRecord).filter(ActionRecord.id == str(action_id), ActionRecord.user_id == uid).first()
    if not a:
        raise ActionError(404, "Action not found")
    if a.status != "pending_approval":
        raise ActionError(409, f"Action is '{a.status}', not pending approval")
    h = payload_hash(a.payload_json or {})
    if approve and payload_hash_seen and payload_hash_seen != h:
        raise ActionError(409, "The action changed since you reviewed it; review it again")
    db.add(ActionApproval(action_id=a.id, user_id=uid, decision="approved" if approve else "rejected", approved_payload_hash=h))
    audit(db, uid, f"action.{'approve' if approve else 'reject'}:{a.intent}", {"action_id": a.id}, {"payload_hash": h}, a.risk)
    if not approve:
        a.status = "rejected"; db.commit(); db.refresh(a)
        return serialize(a)
    a.status = "approved_pending_exec"; db.commit()
    return execute(db, a)


# ---------- handlers (the only code that mutates records on behalf of an action) ----------
def _h_create_task(db, uid, p):
    t = Task(user_id=uid, title=p["title"], type=p.get("type", "general"), due_date=p.get("due_date") and date.fromisoformat(p["due_date"]),
             estimated_minutes=p.get("estimated_minutes", 45))
    db.add(t); db.commit(); db.refresh(t)
    return {"created": "task", "id": t.id}


def _h_create_study_block(db, uid, p):
    exam = _owner(db, Exam, p["exam_id"], uid)
    if p.get("topic_id"):
        topic = db.query(Topic).filter(Topic.id == p["topic_id"], Topic.course_id == exam.course_id).first()
        if not topic:
            raise ActionError(404, "Topic not found for this exam")
    b = StudyBlock(user_id=uid, exam_id=exam.id, topic_id=p.get("topic_id"), plan_date=date.fromisoformat(p["date"]),
                   duration_min=p["duration_min"], mode=p.get("mode", "learn"), status="planned", generated_reason="Added by you / JARVIS")
    db.add(b); db.commit(); db.refresh(b)
    return {"created": "study_block", "id": b.id}


def _h_today_op(db, uid, p):
    from agent_service import complete_study_block
    kind, rid, op = p["kind"], p["ref_id"], p["op"]
    today = date.today()
    if op == "start":
        return {"state": "in_progress", "kind": kind, "ref_id": rid}
    if kind == "study_block":
        b = _owner(db, StudyBlock, rid, uid)
        if op == "complete":
            complete_study_block(b, db, True, p.get("actual_minutes"), p.get("difficulty_felt"), p.get("confidence_now"))
            return {"state": "completed", "kind": kind, "ref_id": rid}
        b.plan_date = max(b.plan_date, today) + timedelta(days=p.get("days", 1)); b.status = "planned"; db.commit()
        return {"state": "paused", "moved_to": b.plan_date.isoformat(), "kind": kind, "ref_id": rid}
    if kind == "task":
        t = _owner(db, Task, rid, uid)
        if op == "complete":
            t.status = "done"; db.commit(); return {"state": "completed", "kind": kind, "ref_id": rid}
        t.due_date = max(t.due_date or today, today) + timedelta(days=p.get("days", 1)); db.commit()
        return {"state": "paused", "moved_to": t.due_date.isoformat(), "kind": kind, "ref_id": rid}
    if kind == "academic":
        a = _owner(db, Academic, rid, uid)
        if op == "complete":
            a.done = True; db.commit(); return {"state": "completed", "kind": kind, "ref_id": rid}
        return {"state": "paused", "kind": kind, "ref_id": rid}
    ap = _owner(db, Application, rid, uid)           # application: "complete" = preparation done, NEVER submitted
    if op == "complete":
        if (ap.status or "To Apply") == "To Apply":
            ap.status = "Ready to Submit"
        db.commit(); return {"state": "completed", "kind": kind, "ref_id": rid, "note": "Marked ready. Submit it yourself on the company site."}
    ap.follow_up_date = max(ap.follow_up_date or today, today) + timedelta(days=p.get("days", 1)); db.commit()
    return {"state": "paused", "kind": kind, "ref_id": rid}


def _h_send_email(db, uid, p):
    """Never sends. Creates a pending Outbox item; the existing Outbox approval flow (with its daily cap) sends."""
    o = OutboxItem(user_id=uid, channel="email", status="pending", payload={"to": p["to"], "subject": p["subject"], "body": p["body"]},
                   ref={"kind": "action"}, risk_level="high", note="Created from an approved action",
                   expires_at=datetime.utcnow() + timedelta(days=3))
    db.add(o); db.commit(); db.refresh(o)
    return {"queued": "outbox", "outbox_id": o.id}


def _h_update_application(db, uid, p):
    ap = _owner(db, Application, p["application_id"], uid)
    old = ap.status; ap.status = p["status"]; db.commit()
    return {"application_id": ap.id, "from": old, "to": ap.status}


def _h_delete_task(db, uid, p):
    t = _owner(db, Task, p["task_id"], uid)
    db.delete(t); db.commit()
    return {"deleted": "task", "id": p["task_id"]}


_HANDLERS = {"create_task": _h_create_task, "create_study_block": _h_create_study_block, "today_op": _h_today_op,
             "send_email": _h_send_email, "update_application_status": _h_update_application, "delete_task": _h_delete_task}
