"""Application workflow helpers."""
from __future__ import annotations

from uuid import UUID
from sqlalchemy.orm import Session

from agent_service import workflow_match_opportunities


def match(user_id: UUID, raw_jobs: list[dict], db: Session):
    return workflow_match_opportunities(user_id, raw_jobs, db)
