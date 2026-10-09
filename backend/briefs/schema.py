"""Universal OPAI brief schema. Every workflow returns this shape; type-specific blocks ride along as extra keys."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Risk = Literal["low", "medium", "high"]


class ActionModel(BaseModel):
    """The ONE action shape every surface (briefs.html, KARNA popup, chat chips, notifications) consumes. `id` == `action_id`."""
    model_config = ConfigDict(extra="allow")
    id: Optional[str] = None
    action_id: str
    brief_id: Optional[str] = None
    requires_approval: bool = False
    type: str
    label: str = Field(min_length=1, max_length=120)
    risk: Risk = "low"
    kind: Literal["execute", "navigate", "decision"] = "navigate"
    requires_confirmation: bool = False
    primary: bool = False
    link: Optional[str] = None
    entity_id: Optional[str] = None
    status: str = "available"


class Priority(BaseModel):
    model_config = ConfigDict(extra="allow")
    rank: int = Field(ge=1)
    entity_type: str
    entity_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=240)
    duration_min: Optional[int] = Field(default=None, ge=0, le=1440)
    urgency: Literal["high", "medium", "low"] = "medium"
    reason_codes: List[str] = Field(default_factory=list)
    reason_text: str = ""
    next_action: Optional[str] = None
    actions: List[ActionModel] = Field(default_factory=list)


class Alert(BaseModel):
    model_config = ConfigDict(extra="allow")
    severity: Literal["info", "warning", "critical"] = "info"
    title: str = Field(min_length=1, max_length=240)
    detail: Optional[str] = None
    entity_id: Optional[str] = None
    action: Optional[str] = None          # action type the UI can offer, e.g. "open_outbox"
    link: Optional[str] = None


class ApprovalItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    approval_id: str
    source: Literal["action", "outbox"]
    title: str
    risk: Risk = "high"
    preview: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: Optional[str] = None
    expires_at: Optional[str] = None


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str
    type: str = "workspace"
    url: Optional[str] = None
    checked_on: Optional[str] = None


class Explanation(BaseModel):
    model_config = ConfigDict(extra="allow")
    short: str = ""
    details_available: bool = True
    reason_codes: List[str] = Field(default_factory=list)
    narrative: Optional[str] = None       # the ONLY field a language model may write


class BriefDoc(BaseModel):
    model_config = ConfigDict(extra="allow")
    brief_id: str
    type: str
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=600)
    generated_at: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: str = "ready"
    context: Dict[str, Any] = Field(default_factory=dict)
    priorities: List[Priority] = Field(default_factory=list)
    alerts: List[Alert] = Field(default_factory=list)
    actions: List[ActionModel] = Field(default_factory=list)
    approval_items: List[ApprovalItem] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    explanation: Explanation

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        from . import BRIEF_TYPES
        if v not in BRIEF_TYPES:
            raise ValueError(f"unknown brief type '{v}'")
        return v

    @model_validator(mode="after")
    def _ranks(self):
        ranks = [p.rank for p in self.priorities]
        if ranks != sorted(ranks) or len(set(ranks)) != len(ranks):
            raise ValueError("priority ranks must be unique and ascending")
        ids = [a.action_id for a in self.actions]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate action ids")
        return self


def validate(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the finished brief and return a clean JSON-safe dict (extra type-specific keys preserved)."""
    return BriefDoc.model_validate(doc).model_dump(mode="json")
