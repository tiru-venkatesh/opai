"""Typed facade over OPA's deterministic SEMS planner."""
from __future__ import annotations

from datetime import date
from uuid import UUID
from sqlalchemy.orm import Session

from agent_service import compute_exam_risk, generate_study_plan


def exam_risk(exam, topics, today: date | None = None) -> dict:
    return compute_exam_risk(exam, topics, today)


def daily_plan(user_id: UUID, db: Session, plan_date: date | None = None, available_minutes: int | None = None):
    return generate_study_plan(user_id, db, plan_date=plan_date, available_minutes=available_minutes)
