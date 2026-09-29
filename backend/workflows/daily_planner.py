"""Facade for the deterministic + language-assisted daily planner."""
from __future__ import annotations

from datetime import date
from uuid import UUID
from sqlalchemy.orm import Session

from agent_service import workflow_generate_plan


def generate(user_id: UUID, target_date: date, db: Session):
    return workflow_generate_plan(user_id, target_date, db)
