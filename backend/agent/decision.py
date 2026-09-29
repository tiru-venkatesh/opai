"""
Typed agent contracts for OPA.

The contracts are deliberately provider-neutral. Jev may produce the decision,
Groq may provide the fallback, and the backend remains the authority that
validates and executes actions.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field


IntentName = Literal[
    "chat",
    "create_task",
    "generate_exam_plan",
    "reschedule_session",
    "find_opportunity",
    "draft_outreach",
    "summarize_workspace",
    "update_application",
    "approve_action",
    "delete_record",
    "unknown",
]


class IntentDecision(BaseModel):
    intent: str = Field(default="unknown", min_length=1, max_length=80)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: Dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    reason_code: Optional[str] = None
    provider: str = "deterministic"


class ActionResult(BaseModel):
    executed: bool = False
    pending_approval: bool = False
    action: str = "chat"
    result: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None
