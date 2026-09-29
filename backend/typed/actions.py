"""Typed tool-call contract used at the agent boundary."""
from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    tool: str = Field(min_length=1, max_length=100)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ValidatedAction(BaseModel):
    tool: str
    arguments: Dict[str, Any]
    risk_level: str = "low"
    requires_approval: bool = False
