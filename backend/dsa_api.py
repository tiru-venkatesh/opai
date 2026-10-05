"""DSA Roadmap endpoints: /v1/dsa*. Planning and tracking only; no problems, judge, editor or solutions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import dsa_service as S
from audit.logger import record as audit
from database import User, get_db

router = APIRouter()


def _user(db: Session, user_id: str) -> str:
    uid = str(user_id)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except S.DsaError as e:
        raise HTTPException(e.status, e.detail)


@router.get("/v1/dsa")
def get_dsa(user_id: str, db: Session = Depends(get_db)):
    return S.state(db, _user(db, user_id))


class PlanBody(BaseModel):
    user_id: str
    goal: str = "Placement preparation"
    language: str = "Python"
    daily_minutes: int = Field(default=60, ge=20, le=180)
    days_per_week: int = Field(default=5, ge=1, le=7)


@router.post("/v1/dsa/plan")
def create_plan(p: PlanBody, db: Session = Depends(get_db)):
    """Creates the phase-based roadmap (replaces any existing one)."""
    uid = _user(db, p.user_id)
    _wrap(S.create_plan, db, uid, p.goal, p.language, p.daily_minutes, p.days_per_week)
    audit(db, uid, "dsa.plan_created", {"goal": p.goal, "language": p.language, "daily_minutes": p.daily_minutes}, {"ok": True}, "low")
    return S.state(db, uid)


class SettingsBody(BaseModel):
    user_id: str
    mode_override: Optional[str] = None
    daily_minutes: Optional[int] = Field(default=None, ge=20, le=180)
    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)


@router.patch("/v1/dsa/plan")
def patch_plan(p: SettingsBody, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    _wrap(S.update_settings, db, uid, p.model_dump(exclude={"user_id"}, exclude_unset=True))
    return S.state(db, uid)


@router.delete("/v1/dsa/plan")
def delete_plan(user_id: str, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    S.delete_plan(db, uid)
    audit(db, uid, "dsa.plan_deleted", {}, {"ok": True}, "low")
    return S.state(db, uid)


class TopicPatch(BaseModel):
    user_id: str
    status: Optional[str] = None
    confidence: Optional[int] = Field(default=None, ge=1, le=5)
    learn_url: Optional[str] = Field(default=None, max_length=500)
    practice_url: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None, max_length=2000)


@router.patch("/v1/dsa/topics/{topic_id}")
def patch_topic(topic_id: str, p: TopicPatch, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    _wrap(S.update_topic, db, uid, topic_id, p.model_dump(exclude={"user_id"}, exclude_unset=True))
    return S.state(db, uid)


class CompleteBody(BaseModel):
    user_id: str
    actual_minutes: Optional[int] = Field(default=None, ge=1, le=600)
    confidence: Optional[int] = Field(default=None, ge=1, le=5)


@router.post("/v1/dsa/sessions/{session_id}/complete")
def complete(session_id: str, p: CompleteBody, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    _wrap(S.complete_session, db, uid, session_id, p.actual_minutes, p.confidence)
    return S.state(db, uid)


class UserBody(BaseModel):
    user_id: str


@router.post("/v1/dsa/sessions/{session_id}/skip")
def skip(session_id: str, p: UserBody, db: Session = Depends(get_db)):
    uid = _user(db, p.user_id)
    _wrap(S.skip_session, db, uid, session_id)
    return S.state(db, uid)
