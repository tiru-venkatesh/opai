"""Typed SEMS extraction contract."""
from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class ExamExtraction(BaseModel):
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    exam_date: Optional[date] = None
    time: Optional[str] = None
    venue: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
