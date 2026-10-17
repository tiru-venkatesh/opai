"""DSA Coach endpoints: /v1/dsa/attempts, /v1/dsa/coach, /v1/dsa/coach/reminders. Metadata only; no problems, judge or code."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import dsa_coach_service as S
import reminders as RM
from audit.logger import record as audit
from database import DsaAttempt, User, get_db

router = APIRouter()


def _user(db: Session, user_id: str) -> str:
    uid = str(user_id)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


def _today(db: Session, uid: str) -> date:
    """The learner's LOCAL date (an attempt at 11:50 PM must count for that day, not for the UTC day)."""
    now = datetime.utcnow()
    return (now + timedelta(minutes=RM.offset_at(db, uid, now))).date()


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except S.CoachError as e:
        raise HTTPException(e.status, e.detail)


class AttemptBody(BaseModel):
    user_id: str
    title: Optional[str] = Field(default=None, max_length=200)
    url: Optional[str] = Field(default=None, max_length=500)
    platform: Optional[str] = None
    pattern: Optional[str] = None
    difficulty: Optional[str] = None
    result: Literal["solved", "hinted", "failed"]
    hints_used: int = Field(default=0, ge=0, le=20)
    saw_solution: bool = False
    minutes: Optional[int] = Field(default=None, ge=1, le=600)
    mistakes: List[str] = Field(default_factory=list, max_length=5)
    time_complexity: Optional[str] = Field(default=None, max_length=40)
    space_complexity: Optional[str] = Field(default=None, max_length=40)
    predicted_pattern: Optional[str] = None
    approach_note: Optional[str] = Field(default=None, max_length=500)
    slot: Optional[Literal["new", "revision", "mixed", "manual"]] = None


@router.post("/v1/dsa/attempts")
def log_attempt(p: AttemptBody, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    out = _wrap(S.log_attempt, db, uid, p.model_dump(exclude={"user_id"}), _today(db, uid))
    audit(db, uid, "dsa.attempt_logged", {"key": out["mastery"]["key"], "result": out["attempt"]["result"]}, {"ok": True}, "low")
    return {**out, "coach": S.coach(db, uid, _today(db, uid))}


@router.get("/v1/dsa/attempts")
def list_attempts(user_id: str, limit: int = 30, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    rows = db.query(DsaAttempt).filter(DsaAttempt.user_id == uid).order_by(DsaAttempt.attempted_on.desc(), DsaAttempt.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [S.attempt_view(a) for a in rows]


@router.delete("/v1/dsa/attempts/{attempt_id}")
def delete_attempt(attempt_id: str, user_id: str, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    _wrap(S.delete_attempt, db, uid, attempt_id, _today(db, uid))
    return S.coach(db, uid, _today(db, uid))


@router.get("/v1/dsa/coach")
def get_coach(user_id: str, when: Literal["today", "tomorrow"] = "tomorrow", db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    return S.coach(db, uid, _today(db, uid), when)


class ReminderSettings(BaseModel):
    user_id: str
    enabled: Optional[bool] = None
    times: Optional[List[str]] = Field(default=None, max_length=3)
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None


@router.get("/v1/dsa/coach/reminders")
def get_reminders(user_id: str, db: Session = Depends(get_db)):
    return S.streak_settings(db, _user(db, user_id))


@router.put("/v1/dsa/coach/reminders")
def put_reminders(p: ReminderSettings, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    out = _wrap(S.set_streak_settings, db, uid, p.enabled, p.times, p.quiet_start, p.quiet_end)
    audit(db, uid, "dsa.streak_reminders", {"enabled": out["enabled"], "times": out["times"]}, {"ok": True}, "low")
    return out
