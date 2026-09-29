"""Typed study-block contract."""
from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class StudyBlockAction(BaseModel):
    course_id: str
    topic_id: Optional[str] = None
    date: date
    start_time: Optional[str] = None
    duration_min: int = Field(ge=15, le=180)
    mode: str
