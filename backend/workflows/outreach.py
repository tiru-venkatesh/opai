"""Human-in-the-loop outreach workflow helpers."""
from __future__ import annotations

from uuid import UUID
from sqlalchemy.orm import Session

from agent_service import workflow_draft_outreach


def draft(user_id: UUID, contact_id: UUID, db: Session):
    return workflow_draft_outreach(user_id, contact_id, db)
