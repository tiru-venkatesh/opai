"""First-login profile setup: 4 small steps, each saved immediately, then a starter workspace.

Endpoints (all take ?user_id= like the rest of this API):
  GET  /v1/onboarding/status      -> {required, completed, step, profile{...}}
  POST /v1/onboarding/basic       full name, optional date of birth, timezone
  POST /v1/onboarding/education   course type, branch, year, semester, college
  POST /v1/onboarding/goals       goals, daily focus minutes, preferred study time
  POST /v1/onboarding/links       optional GitHub / LinkedIn / portfolio
  POST /v1/onboarding/complete    creates the starter workspace; safe to call twice

Accounts created before this shipped have profile_setup_completed = NULL and are treated as
finished, so nobody who already uses OPAI is blocked. The page can still be opened to edit.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from database import Semester, User, get_db

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])

# course_type -> (label stored in User.degree, max year, max semester, branch required)
COURSES = {
    "btech": ("B.Tech / B.E.", 4, 8, True),
    "degree": ("Degree / B.Sc.", 4, 8, True),
    "diploma": ("Diploma", 3, 6, False),
    "mtech": ("M.Tech / M.E.", 2, 4, False),
    "mba_mca": ("MBA / MCA", 3, 6, False),
    "other": ("Other", 5, 10, False),
}
GOALS = {
    "exams": "Semester exam planning",
    "dsa": "DSA and placement practice",
    "internships": "Internship opportunity tracking",
    "research": "Research and professor outreach",
    "projects": "Projects and portfolio",
    "freelance": "Freelance and client work",
}
STUDY_TIMES = {  # preferred time -> (peak_start, peak_end) used by the exam planner
    "morning": ("07:00", "10:00"), "afternoon": ("14:00", "17:00"),
    "evening": ("19:00", "22:00"), "night": ("22:00", "23:59"),
}
MIN_AGE = 13


def _clean(s: Optional[str]) -> Optional[str]:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return s or None


def _url(value: Optional[str], hosts: tuple, label: str) -> Optional[str]:
    """Optional https URL on one of `hosts` (or any host when hosts is empty). Scheme is added if missing."""
    v = _clean(value)
    if not v:
        return None
    if not re.match(r"^[a-z][a-z0-9+.-]*://", v, re.I):
        v = "https://" + v
    u = urlparse(v)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or "." not in host or len(v) > 200 or any(c in v for c in " <>\"'"):
        raise ValueError(f"{label}: enter a valid https link")
    if hosts and not any(host == h or host.endswith("." + h) for h in hosts):
        raise ValueError(f"{label}: must be a {hosts[0]} link")
    return v


class Basic(BaseModel):
    full_name: str
    date_of_birth: Optional[date] = None
    timezone: Optional[str] = Field(default=None, max_length=60)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v):
        v = _clean(v) or ""
        if not 2 <= len(v) <= 80:
            raise ValueError("Full name must be 2 to 80 characters")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v):
        if v is None:
            return v
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if v > today or age < MIN_AGE or age > 100:
            raise ValueError(f"Enter a valid date of birth (you must be at least {MIN_AGE})")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        v = _clean(v)
        if v and not re.fullmatch(r"[A-Za-z_]+(?:/[A-Za-z0-9_+-]+){0,2}", v):
            raise ValueError("Invalid timezone")
        return v


class Education(BaseModel):
    course_type: str
    branch: Optional[str] = Field(default=None, max_length=120)
    current_year: int
    current_semester: Optional[int] = None
    college: Optional[str] = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _check(self):
        if self.course_type not in COURSES:
            raise ValueError("Choose a course type")
        _, max_year, max_sem, need_branch = COURSES[self.course_type]
        self.branch, self.college = _clean(self.branch), _clean(self.college)
        if need_branch and not self.branch:
            raise ValueError("Course / branch is required for this course type")
        if not 1 <= self.current_year <= max_year:
            raise ValueError(f"Year must be between 1 and {max_year} for this course type")
        if self.current_semester is not None and not 1 <= self.current_semester <= max_sem:
            raise ValueError(f"Semester must be between 1 and {max_sem} for this course type")
        return self


class Goals(BaseModel):
    goals: List[str] = Field(min_length=1)
    daily_focus_minutes: int = Field(ge=15, le=480)
    preferred_study_time: Optional[str] = None

    @field_validator("goals")
    @classmethod
    def _goals(cls, v):
        out = []
        for g in v:
            if g not in GOALS:
                raise ValueError(f"Unknown goal: {g}")
            if g not in out:
                out.append(g)
        return out

    @field_validator("preferred_study_time")
    @classmethod
    def _when(cls, v):
        v = _clean(v)
        if v and v not in STUDY_TIMES:
            raise ValueError("Preferred study time must be morning, afternoon, evening or night")
        return v


class Links(BaseModel):
    github: Optional[str] = None
    linkedin: Optional[str] = None
    portfolio: Optional[str] = None

    @field_validator("github")
    @classmethod
    def _gh(cls, v):
        return _url(v, ("github.com",), "GitHub")

    @field_validator("linkedin")
    @classmethod
    def _li(cls, v):
        return _url(v, ("linkedin.com",), "LinkedIn")

    @field_validator("portfolio")
    @classmethod
    def _pf(cls, v):
        return _url(v, (), "Portfolio")


def _user(db: Session, user_id: UUID) -> User:
    u = db.query(User).filter(User.id == str(user_id)).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u


_UNSET_NAMES = {"", "user", "guest"}


def has_minimum(u: User) -> bool:
    """The least OPAI needs to personalise anything: a real name and what the person studies."""
    name_ok = (u.name or "").strip().lower() not in _UNSET_NAMES
    course_ok = bool((u.course_type or u.degree or u.branch or "").strip())
    return name_ok and course_ok


def is_completed(u: User) -> bool:
    """True = finished onboarding. False = must do it.
    NULL means the account predates onboarding: it is treated as done ONLY if it already has the minimum details
    (real name + course), so people who set themselves up are never asked again while half-empty accounts are."""
    if u.profile_setup_completed is None:
        return has_minimum(u)
    return bool(u.profile_setup_completed)


def _profile(u: User) -> dict:
    prefs = (u.preferences or {}).get("today") or {}
    return {
        "full_name": u.name if (u.name and u.name != "User") else "",
        "date_of_birth": u.date_of_birth.isoformat() if u.date_of_birth else None,
        "timezone": u.timezone,
        "course_type": u.course_type, "branch": u.branch, "current_year": u.current_year,
        "current_semester": u.current_semester, "college": u.college_name,
        "goals": u.primary_goals or prefs.get("goals") or [],
        "daily_focus_minutes": u.daily_focus_minutes, "preferred_study_time": u.preferred_study_time,
        "github": u.github, "linkedin": u.linkedin_url, "portfolio": u.portfolio_url,
    }


def _status(u: User) -> dict:
    return {"required": not is_completed(u), "completed": is_completed(u),
            "step": min(int(u.onboarding_step or 0), 4), "profile": _profile(u)}


def _advance(u: User, step: int):
    u.onboarding_step = max(int(u.onboarding_step or 0), step)


@router.get("/status")
def status(user_id: UUID, db: Session = Depends(get_db)):
    return _status(_user(db, user_id))


@router.post("/basic")
def save_basic(user_id: UUID, body: Basic, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    u.name, u.date_of_birth, u.timezone = body.full_name, body.date_of_birth, body.timezone or u.timezone
    _advance(u, 1)
    db.commit()
    return _status(u)


@router.post("/education")
def save_education(user_id: UUID, body: Education, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    u.course_type, u.degree = body.course_type, COURSES[body.course_type][0]
    u.branch, u.current_year, u.current_semester, u.college_name = body.branch, body.current_year, body.current_semester, body.college
    _advance(u, 2)
    db.commit()
    return _status(u)


@router.post("/goals")
def save_goals(user_id: UUID, body: Goals, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    u.primary_goals, u.daily_focus_minutes, u.preferred_study_time = body.goals, body.daily_focus_minutes, body.preferred_study_time
    _advance(u, 3)
    db.commit()
    return _status(u)


@router.post("/links")
def save_links(user_id: UUID, body: Links, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    u.github, u.linkedin_url, u.portfolio_url = body.github, body.linkedin, body.portfolio
    _advance(u, 4)
    db.commit()
    return _status(u)


def _academic_year(today: date) -> str:
    start = today.year if today.month >= 6 else today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


@router.post("/complete")
def complete(user_id: UUID, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    missing = [n for n, ok in (("basic", bool(u.name and u.name != "User")), ("education", bool(u.course_type and u.current_year)),
                               ("goals", bool(u.primary_goals and u.daily_focus_minutes))) if not ok]
    if missing:
        raise HTTPException(status_code=409, detail="Finish these steps first: " + ", ".join(missing))

    goals = list(u.primary_goals or [])
    # Today preferences + goals live in preferences so other modules can read them without new tables
    prefs = dict(u.preferences or {})
    prefs["today"] = {"goals": goals, "daily_focus_minutes": u.daily_focus_minutes, "preferred_study_time": u.preferred_study_time}
    u.preferences = prefs

    # Starter semester (idempotent): only when a semester number is known and it isn't already there
    created_semester = False
    if u.current_semester:
        year = _academic_year(date.today())
        exists = db.query(Semester).filter(Semester.user_id == u.id, Semester.semester_number == u.current_semester,
                                           Semester.academic_year == year).first()
        if not exists:
            peak = STUDY_TIMES.get(u.preferred_study_time or "evening")
            db.query(Semester).filter(Semester.user_id == u.id, Semester.is_current == True).update({"is_current": False})  # noqa: E712
            db.add(Semester(user_id=u.id, college=u.college_name, degree=u.degree, branch=u.branch,
                            semester_number=u.current_semester, academic_year=year, is_current=True,
                            daily_study_minutes=u.daily_focus_minutes, peak_start=peak[0], peak_end=peak[1]))
            created_semester = True

    u.profile_setup_completed = True
    u.onboarding_step = 4
    db.commit()

    first = (u.name or "").split(" ")[0]
    starts = [GOALS[g] for g in goals][:4]
    return {"completed": True, "first_name": first, "starts_with": starts, "semester_created": created_semester,
            "next": "today.html",
            "karna_followup": (f"Welcome, {first}. I've set up {', '.join(s.lower() for s in starts[:2])}. "
                               "Would you like me to add your current semester subjects and upcoming exams now?"
                               if "exams" in goals else f"Welcome, {first}. What would you like to set up first?")}
