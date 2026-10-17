"""LeetCode streak reminder: one daily nudge, one "Done" tap. Nothing else is stored (no problems, no code).

State lives in User.preferences["leetcode_streak"] = {enabled, time, done_days: [ISO dates, newest last]}.
The nudge is a normal daily Reminder (kind "leetcode_streak") and is skipped on days already marked done."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import reminders as RM
from database import Reminder, User, get_db

router = APIRouter()
KIND = "leetcode_streak"
DEFAULT_TIME = "21:00"
KEEP_DAYS = 400
_HHMM = __import__("re").compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _user(db: Session, uid: str) -> User:
    u = db.query(User).filter(User.id == str(uid)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _today(db: Session, uid: str) -> date:
    now = datetime.utcnow()
    return (now + timedelta(minutes=RM.offset_at(db, uid, now))).date()


def _prefs(u: User) -> Dict[str, Any]:
    return dict((u.preferences or {}).get(KIND) or {})


def _save(db: Session, u: User, p: Dict[str, Any]) -> None:
    prefs = dict(u.preferences or {})
    prefs[KIND] = p
    u.preferences = prefs
    db.commit()


def count_streak(days: List[str], today: date) -> int:
    """Consecutive days ending today, or ending yesterday if today is not done yet (the streak is still alive)."""
    s = {date.fromisoformat(d) for d in days}
    cur = today if today in s else today - timedelta(days=1)
    n = 0
    while cur in s:
        n += 1
        cur -= timedelta(days=1)
    return n


def view(db: Session, uid: str) -> Dict[str, Any]:
    u = _user(db, uid)
    p, today = _prefs(u), _today(db, uid)
    days = p.get("done_days") or []
    return {"enabled": bool(p.get("enabled")), "time": p.get("time") or DEFAULT_TIME,
            "done_today": today.isoformat() in days, "streak": count_streak(days, today)}


def _reschedule(db: Session, uid: str, enabled: bool, hhmm: str) -> None:
    for r in db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == KIND, Reminder.status == "pending").all():
        r.status = "cancelled"
    db.commit()
    if not enabled:
        return
    fn, now = RM.offset_fn(db, uid), datetime.utcnow()
    now_local = RM.to_local(now, fn(now))
    h, m = int(hhmm[:2]), int(hhmm[3:])
    at_local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if at_local <= now_local:
        at_local += timedelta(days=1)
    RM.create(db, uid, KIND, RM.local_to_utc(at_local, fn, fn(now)), repeat="daily", kind=KIND, source="settings")


def set_settings(db: Session, uid: str, enabled: Optional[bool], hhmm: Optional[str]) -> Dict[str, Any]:
    u = _user(db, uid)
    if hhmm is not None and not _HHMM.match(hhmm):
        raise HTTPException(422, "Time must be HH:MM")
    p = _prefs(u)
    p["enabled"] = bool(p.get("enabled")) if enabled is None else bool(enabled)
    p["time"] = hhmm or p.get("time") or DEFAULT_TIME
    _save(db, u, p)
    _reschedule(db, str(uid), p["enabled"], p["time"])
    return view(db, uid)


def mark_done(db: Session, uid: str) -> Dict[str, Any]:
    u = _user(db, uid)
    p, today = _prefs(u), _today(db, uid).isoformat()
    days = sorted(set(p.get("done_days") or []) | {today})[-KEEP_DAYS:]
    p["done_days"] = days
    _save(db, u, p)
    return view(db, uid)


def nudge(db: Session, uid: str, local_old: datetime) -> Optional[Dict[str, Any]]:
    """Scheduler hook. Returns {title, body} or None (off, or already done that day)."""
    p = _prefs(_user(db, uid))
    if not p.get("enabled") or local_old.date().isoformat() in (p.get("done_days") or []):
        return None
    n = count_streak(p.get("done_days") or [], local_old.date())
    body = f"Solve one problem to keep your {n}-day streak." if n else "Solve one problem to start your streak."
    return {"title": "LeetCode today?", "body": body}


class Who(BaseModel):
    user_id: str


class Settings(Who):
    enabled: Optional[bool] = None
    time: Optional[str] = Field(default=None, max_length=5)


@router.get("/v1/leetcode/streak")
def get_streak(user_id: str, db: Session = Depends(get_db)):
    return view(db, user_id)


@router.put("/v1/leetcode/streak")
def put_streak(p: Settings, db: Session = Depends(get_db)):
    return set_settings(db, p.user_id, p.enabled, p.time)


@router.post("/v1/leetcode/done")
def post_done(p: Who, db: Session = Depends(get_db)):
    return mark_done(db, p.user_id)
