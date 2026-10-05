"""Phase 1 endpoints: /v1/today, /v1/today/*, /v1/actions/*, /v1/history."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import action_service as A
import today_engine as T
from audit.logger import record as audit
from database import ActionRecord, AgentActivityLog, MemoryItem, User, get_db

router = APIRouter()


def _user(db: Session, user_id: str) -> str:
    uid = str(user_id)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except A.ActionError as e:
        raise HTTPException(e.status, e.detail)


# ---------------- Today ----------------
@router.get("/v1/today")
def get_today(user_id: str, minutes: Optional[int] = None, energy: str = "normal", narrative: bool = False, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    plan = T.build(db, uid, minutes=minutes, energy=energy)
    if narrative:
        plan["narrative"] = T.narrate(plan)
    return plan


class TodayRefresh(BaseModel):
    user_id: str
    minutes: Optional[int] = Field(default=None, ge=10, le=720)
    energy: str = "normal"
    narrative: bool = True


@router.post("/v1/today/refresh")
def refresh_today(p: TodayRefresh, db: Session = Depends(get_db)):
    """(Re)plans study blocks for today with the given capacity, then returns the plan. Used for first load,
    "I have only 30 minutes" and low-energy replanning. Done blocks are never touched."""
    uid = _user(db, p.user_id)
    from agent_service import generate_study_plan
    avail = T.available_minutes(db, uid, p.minutes)
    generate_study_plan(uid, db, date.today(), available_minutes=avail)
    audit(db, uid, "today.refresh", {"minutes": avail, "energy": p.energy}, {"ok": True}, "low")
    plan = T.build(db, uid, minutes=p.minutes, energy=p.energy)
    if p.narrative:
        plan["narrative"] = T.narrate(plan)
    return plan


class TodayAct(BaseModel):
    user_id: str
    kind: str
    ref_id: str
    op: str
    actual_minutes: Optional[int] = None
    difficulty_felt: Optional[int] = None
    confidence_now: Optional[int] = None
    days: int = 1


@router.post("/v1/today/act")
def today_act(p: TodayAct, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    payload = p.model_dump(exclude={"user_id"}, exclude_none=True)
    reason = {"start": "Started from Today", "complete": "Completed from Today", "skip": "Skipped from Today", "snooze": "Moved from Today"}.get(p.op, "")
    act = _wrap(A.propose, db, uid, "today_op", payload, source="today", reason=reason, scope=date.today().isoformat())
    return {"action": act, "today": T.build(db, uid)}


class DayClose(BaseModel):
    user_id: str
    energy: int = Field(default=3, ge=1, le=5)
    blockers: Optional[str] = Field(default=None, max_length=500)
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/v1/today/close")
def close_day(p: DayClose, db: Session = Depends(get_db)):
    """Evening ritual: records what actually happened so tomorrow is planned from reality."""
    uid = _user(db, p.user_id)
    today = date.today()
    start = T.local_day_start_utc(today)
    ops = (db.query(ActionRecord).filter(ActionRecord.user_id == uid, ActionRecord.intent == "today_op",
                                         ActionRecord.status == "executed", ActionRecord.created_at >= start).all())
    done = sum(1 for o in ops if (o.result_json or {}).get("state") == "completed")
    moved = sum(1 for o in ops if (o.result_json or {}).get("state") == "paused")
    left = T.build(db, uid, today=today)
    summary = (f"Day {today.isoformat()}: {done} completed, {moved} moved, {len(left['items'])} still open. Energy {p.energy}/5."
               + (f" Blocked by: {p.blockers.strip()}." if p.blockers and p.blockers.strip() else ""))
    marker = f"[close:{today.isoformat()}]"
    row = db.query(MemoryItem).filter(MemoryItem.user_id == uid, MemoryItem.type == "working", MemoryItem.content.like(marker + "%")).first()
    if row:
        row.content = f"{marker} {summary}"
    else:
        db.add(MemoryItem(user_id=uid, type="working", content=f"{marker} {summary}", source="daily_close", confidence=1.0, status="confirmed"))
    db.commit()
    audit(db, uid, "today.close", {"energy": p.energy, "has_blockers": bool(p.blockers)}, {"done": done, "moved": moved}, "low")
    tomorrow = T.build(db, uid, today=today + timedelta(days=1), energy="low" if p.energy <= 2 else "normal")
    return {"summary": summary, "completed": done, "moved": moved, "still_open": len(left["items"]), "tomorrow": tomorrow,
            "tip": "Low energy logged: tomorrow starts with shorter sessions." if p.energy <= 2 else "Tomorrow's plan is built from what actually got done."}


# ---------------- Actions ----------------
class ProposeBody(BaseModel):
    user_id: str
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    source: str = "ui"
    confidence: float = Field(default=1.0, ge=0, le=1)


@router.post("/v1/actions/propose")
def propose_action(p: ProposeBody, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    return _wrap(A.propose, db, uid, p.intent, p.payload, source=p.source, reason=p.reason, confidence=p.confidence)


class DecideBody(BaseModel):
    user_id: str
    payload_hash: Optional[str] = None


@router.post("/v1/actions/{action_id}/approve")
def approve_action(action_id: str, p: DecideBody, db: Session = Depends(get_db)):
    return _wrap(A.decide, db, _user(db, p.user_id), action_id, True, p.payload_hash)


@router.post("/v1/actions/{action_id}/reject")
def reject_action(action_id: str, p: DecideBody, db: Session = Depends(get_db)):
    return _wrap(A.decide, db, _user(db, p.user_id), action_id, False)


@router.get("/v1/actions")
def list_actions(user_id: str, status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    q = db.query(ActionRecord).filter(ActionRecord.user_id == uid)
    if status:
        q = q.filter(ActionRecord.status == status)
    rows = q.order_by(ActionRecord.created_at.desc()).limit(max(1, min(limit, 200))).all()
    out = []
    for r in rows:
        d = A.serialize(r); d["payload_hash"] = A.payload_hash(r.payload_json or {}); out.append(d)
    return out


@router.get("/v1/history")
def history(user_id: str, limit: int = 50, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    rows = (db.query(AgentActivityLog).filter(AgentActivityLog.user_id == uid)
            .order_by(AgentActivityLog.created_at.desc()).limit(max(1, min(limit, 200))).all())
    return [{"id": r.id, "event": r.tool_name, "risk": r.risk_level, "status": r.status, "summary": r.result_summary,
             "at": r.created_at.isoformat() if r.created_at else None} for r in rows]
