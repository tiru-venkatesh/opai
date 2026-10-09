"""Brief System API.  Chat is an input method. Briefs are the product output. Actions are the execution method.

  POST /v1/briefs/{daily|exam|dsa|weekly|decision|recovery|approval}
  POST /v1/briefs/{application/{opportunity_id}|outreach/{contact_id}|project/{project_id}}
  GET  /v1/briefs/daily?date=  /v1/briefs/exam/{exam_id}  /v1/briefs/dsa  /v1/briefs  /v1/briefs/{id}
  POST /v1/briefs/{id}/refresh  /v1/briefs/{id}/dismiss
  POST /v1/actions/{action_id}/execute        (approve / reject live in today_api and understand brief action ids)

user_id is accepted in the query string or the JSON body (same convention as the rest of the API).
"""
from __future__ import annotations

from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from briefs import core, service
from database import User, get_db

router = APIRouter()


def _uid(db: Session, *ids: Optional[str]) -> str:
    uid = next((str(i) for i in ids if i), None)
    if not uid:
        raise HTTPException(422, "user_id is required")
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except core.BriefError as e:
        raise HTTPException(e.status, e.detail)


class Body(BaseModel):
    user_id: Optional[str] = None
    narrative: bool = False


class DailyBody(Body):
    date: Optional[Date] = None
    capacity_override: Optional[int] = Field(default=None, ge=10, le=720)
    energy: str = "normal"


class ExamBody(Body):
    exam_id: Optional[str] = None


class DecisionBody(Body):
    question: str = Field(min_length=4, max_length=300)
    estimated_minutes: Optional[int] = Field(default=None, ge=5, le=480)
    deadline_days: Optional[int] = Field(default=None, ge=0, le=365)


class ApprovalBody(Body):
    action_id: Optional[str] = None


# ---------------- daily
@router.post("/v1/briefs/daily")
def post_daily(body: Optional[DailyBody] = None, user_id: Optional[str] = None, capacity_override: Optional[int] = Query(default=None, ge=10, le=720),
               db: Session = Depends(get_db)):
    b = body or DailyBody()
    uid = _uid(db, b.user_id, user_id)
    return _run(service.generate, db, uid, "daily_plan", {"date": b.date.isoformat() if b.date else None,
                                                          "capacity_override": b.capacity_override or capacity_override, "energy": b.energy}, b.narrative)


@router.get("/v1/briefs/daily")
def get_daily(user_id: str, date: Optional[Date] = None, narrative: bool = False, db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    d = service.daily_scope(date)
    return _run(service.get_or_create, db, uid, "daily_plan", d, {"date": d}, narrative)


# ---------------- exam
@router.post("/v1/briefs/exam")
def post_exam(body: Optional[ExamBody] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or ExamBody()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "exam_readiness", {"exam_id": b.exam_id}, b.narrative)


@router.get("/v1/briefs/exam/{exam_id}")
def get_exam(exam_id: str, user_id: str, narrative: bool = False, db: Session = Depends(get_db)):
    return _run(service.get_or_create, db, _uid(db, user_id), "exam_readiness", exam_id, {"exam_id": exam_id}, narrative)


# ---------------- dsa
@router.post("/v1/briefs/dsa")
def post_dsa(body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "dsa_roadmap", {}, b.narrative)


@router.get("/v1/briefs/dsa")
def get_dsa(user_id: str, db: Session = Depends(get_db)):
    return _run(service.get_or_create, db, _uid(db, user_id), "dsa_roadmap", "dsa", {})


# ---------------- entity briefs
@router.post("/v1/briefs/application/{opportunity_id}")
def post_application(opportunity_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "application_opportunity", {"entity_id": opportunity_id}, b.narrative)


@router.post("/v1/briefs/outreach/{contact_id}")
def post_outreach(contact_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "outreach_research", {"entity_id": contact_id}, b.narrative)


@router.post("/v1/briefs/project/{project_id}")
def post_project(project_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "project", {"entity_id": project_id}, b.narrative)


@router.post("/v1/briefs/reminder/{reminder_id}")
def post_reminder_brief(reminder_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "reminder", {"reminder_id": reminder_id}, False)


# ---------------- review / decision / recovery / approval
@router.post("/v1/briefs/weekly")
def post_weekly(body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "weekly_review", {}, b.narrative)


@router.post("/v1/briefs/decision")
def post_decision(body: DecisionBody, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    return _run(service.generate, db, _uid(db, body.user_id, user_id), "decision",
                {"question": body.question, "estimated_minutes": body.estimated_minutes, "deadline_days": body.deadline_days}, body.narrative)


@router.post("/v1/briefs/recovery")
def post_recovery(body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "recovery", {}, b.narrative)


@router.post("/v1/briefs/approval")
def post_approval(body: Optional[ApprovalBody] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or ApprovalBody()
    return _run(service.generate, db, _uid(db, b.user_id, user_id), "approval", {"action_id": b.action_id}, False)


# ---------------- generic
@router.get("/v1/briefs")
def list_briefs(user_id: str, type: Optional[str] = None, status: Optional[str] = None, limit: int = 30, db: Session = Depends(get_db)):
    return core.listing(db, _uid(db, user_id), type, status, limit)


@router.get("/v1/briefs/{brief_id}")
def get_brief(brief_id: str, user_id: str, db: Session = Depends(get_db)):
    return _run(core.fetch, db, _uid(db, user_id), brief_id)


@router.post("/v1/briefs/{brief_id}/refresh")
def refresh_brief(brief_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(service.refresh, db, _uid(db, b.user_id, user_id), brief_id, b.narrative)


@router.post("/v1/briefs/{brief_id}/dismiss")
def dismiss_brief(brief_id: str, body: Optional[Body] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    b = body or Body()
    return _run(core.dismiss, db, _uid(db, b.user_id, user_id), brief_id)


# ---------------- actions
class ExecBody(BaseModel):
    user_id: str
    confirm: bool = False


@router.post("/v1/actions/{action_id}/execute")
def execute_action(action_id: str, body: ExecBody, db: Session = Depends(get_db)):
    return _run(core.execute_action, db, _uid(db, body.user_id), action_id, body.confirm)


@router.post("/v1/actions/{action_id}/confirm")
def confirm_action(action_id: str, body: ExecBody, db: Session = Depends(get_db)):
    """Explicit confirmation of a medium-risk action shown on a brief (same as execute with confirm=true)."""
    return _run(core.execute_action, db, _uid(db, body.user_id), action_id, True)
