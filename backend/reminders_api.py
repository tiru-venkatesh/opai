"""Reminders + notifications API.
  GET/POST /v1/reminders   POST /v1/reminders/{id}/done|snooze   DELETE /v1/reminders/{id}
  GET /v1/notifications?undelivered=1   POST /v1/notifications/{id}/delivered|read
  GET/PUT /v1/notifications/settings    (daily 'today's plan' time + UTC offset)
  GET /v1/push/key   POST /v1/push/subscribe   DELETE /v1/push/subscribe
  GET/POST /v1/system/tick               (ping every minute from a cron if the host sleeps)
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import obs
import push as PUSH
import reminders as RM
from database import Notification, PushSubscription, Reminder, User, get_db

router = APIRouter()


def _uid(db: Session, user_id: str) -> str:
    if not db.query(User).filter(User.id == str(user_id)).first():
        raise HTTPException(404, "User not found")
    return str(user_id)


def _nf(fn, *a, **k):
    try:
        return fn(*a, **k)
    except LookupError as e:
        raise HTTPException(404, str(e))


class ReminderCreate(BaseModel):
    user_id: str
    title: str = Field(min_length=1, max_length=160)
    at: Optional[datetime] = None                 # ISO; naive = user's local time, aware = converted
    in_minutes: Optional[int] = Field(default=None, ge=1, le=60 * 24 * 30)
    repeat: str = "none"


@router.post("/v1/reminders")
def create_reminder(p: ReminderCreate, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    fn = RM.offset_fn(db, uid)
    if p.in_minutes:
        at = datetime.utcnow() + timedelta(minutes=p.in_minutes)
    elif p.at:
        at = p.at.astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None) if p.at.tzinfo else RM.local_to_utc(p.at, fn, fn(datetime.utcnow()))
    else:
        raise HTTPException(422, "Give `at` or `in_minutes`")
    if p.repeat not in ("none", "daily"):
        raise HTTPException(422, "repeat must be none or daily")
    return RM.view(db, uid, RM.create(db, uid, p.title, at, p.repeat, source="ui"))


@router.get("/v1/reminders")
def list_reminders(user_id: str, status: str = "pending", db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    rows = db.query(Reminder).filter(Reminder.user_id == uid, Reminder.status == status, Reminder.kind == "reminder").order_by(Reminder.remind_at).limit(100).all()
    return [RM.view(db, uid, r) for r in rows]


class Who(BaseModel):
    user_id: str


class Snooze(Who):
    minutes: int = Field(default=10, ge=1, le=1440)


@router.post("/v1/reminders/{rid}/complete")
@router.post("/v1/reminders/{rid}/done")
def reminder_done(rid: str, p: Who, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    return RM.view(db, uid, _nf(RM.mark_done, db, uid, rid))


class ReminderPatch(Who):
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    at: Optional[datetime] = None


@router.patch("/v1/reminders/{rid}")
def reminder_patch(rid: str, p: ReminderPatch, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    fn = RM.offset_fn(db, uid)
    at = None
    if p.at:
        at = p.at.astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None) if p.at.tzinfo else RM.local_to_utc(p.at, fn, fn(datetime.utcnow()))
    try:
        return RM.view(db, uid, RM.update(db, uid, rid, p.title, at))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/v1/reminders/{rid}/snooze")
def reminder_snooze(rid: str, p: Snooze, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    return RM.view(db, uid, _nf(RM.snooze, db, uid, rid, p.minutes))


@router.delete("/v1/reminders/{rid}")
def reminder_delete(rid: str, user_id: str, db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    return RM.view(db, uid, _nf(RM.cancel, db, uid, rid))


def _n(n: Notification) -> Dict[str, Any]:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "data": n.data or {},
            "created_at": n.created_at.isoformat() + "Z" if n.created_at else None, "delivered": bool(n.delivered_at), "read": bool(n.read_at)}


@router.get("/v1/notifications")
def list_notifications(user_id: str, undelivered: bool = False, limit: int = 30, db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    RM.fire_due(db)                                   # catch-up: a sleeping host still delivers on the next poll
    q = db.query(Notification).filter(Notification.user_id == uid)
    if undelivered:
        q = q.filter(Notification.delivered_at.is_(None), Notification.created_at >= datetime.utcnow() - timedelta(hours=12))
    return [_n(n) for n in q.order_by(Notification.created_at.desc()).limit(max(1, min(limit, 100))).all()]


@router.post("/v1/notifications/{nid}/delivered")
def notification_delivered(nid: str, p: Who, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == _uid(db, p.user_id)).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    n.delivered_at = n.delivered_at or datetime.utcnow()
    db.commit()
    return _n(n)


@router.post("/v1/notifications/{nid}/read")
def notification_read(nid: str, p: Who, db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == nid, Notification.user_id == _uid(db, p.user_id)).first()
    if not n:
        raise HTTPException(404, "Notification not found")
    n.read_at = n.delivered_at = datetime.utcnow()
    db.commit()
    obs.emit("notification_clicked", notification_id=n.id, kind=n.kind)
    return _n(n)


class Settings(Who):
    daily_brief: Optional[bool] = None
    daily_brief_time: Optional[str] = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    tz_offset_min: Optional[int] = Field(default=None, ge=-840, le=840)
    timezone: Optional[str] = Field(default=None, max_length=64)       # IANA name, preferred over a fixed offset


@router.get("/v1/notifications/settings")
def get_settings(user_id: str, db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    return {"daily_brief": RM.daily_brief_setting(db, uid), "tz_offset_min": RM.offset_at(db, uid), "timezone": RM.tz_name(db, uid), "push": {"enabled": PUSH.enabled(), "public_key": PUSH.public_key() or None}}


@router.put("/v1/notifications/settings")
def put_settings(p: Settings, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    cur = RM.daily_brief_setting(db, uid)          # read in the OLD zone, then re-anchor the same local time in the new one
    if p.timezone is not None and not RM.valid_zone(p.timezone):
        raise HTTPException(422, "Unknown timezone (use an IANA name like Asia/Kolkata)")
    if p.timezone or p.tz_offset_min is not None:
        RM.set_tz(db, uid, p.tz_offset_min if not p.timezone else None, p.timezone)
    if p.daily_brief is not None or p.daily_brief_time or ((p.tz_offset_min is not None or p.timezone) and cur["enabled"]):
        enabled = cur["enabled"] if p.daily_brief is None else p.daily_brief
        RM.upsert_daily_brief(db, uid, p.daily_brief_time or cur["time"], enabled)
    return get_settings(uid, db)


@router.get("/v1/push/key")
def push_key():
    return {"enabled": PUSH.enabled(), "public_key": PUSH.public_key() or None}


class Sub(Who):
    endpoint: str = Field(max_length=600)
    keys: Dict[str, str]


@router.post("/v1/push/subscribe")
def push_subscribe(p: Sub, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    if not db.query(PushSubscription).filter(PushSubscription.user_id == uid, PushSubscription.endpoint == p.endpoint).first():
        db.add(PushSubscription(user_id=uid, endpoint=p.endpoint, keys=p.keys)); db.commit()
    return {"subscribed": True}


@router.delete("/v1/push/subscribe")
def push_unsubscribe(user_id: str, endpoint: str, db: Session = Depends(get_db)):
    db.query(PushSubscription).filter(PushSubscription.user_id == _uid(db, user_id), PushSubscription.endpoint == endpoint).delete()
    db.commit()
    return {"subscribed": False}


def _require_tick_secret(header: Optional[str], query: Optional[str]) -> None:
    want = os.getenv("OPAI_TICK_SECRET", "")
    if not want:
        raise HTTPException(503, "System tick is disabled: set OPAI_TICK_SECRET")
    if not hmac.compare_digest((header or query or "").encode(), want.encode()):
        raise HTTPException(403, "Bad secret")


@router.api_route("/v1/system/tick", methods=["GET", "POST"])
def tick(x_tick_secret: Optional[str] = Header(default=None), secret: Optional[str] = None, db: Session = Depends(get_db)):
    """For an external cron (also keeps a sleeping free host awake). ALWAYS requires OPAI_TICK_SECRET."""
    _require_tick_secret(x_tick_secret, secret)
    return {"fired": RM.fire_due(db)}


@router.get("/v1/system/health")
def health(db: Session = Depends(get_db)):
    db.execute(__import__("sqlalchemy").text("select 1"))
    return {"status": "ok", "push_enabled": PUSH.enabled(), "tick_configured": bool(os.getenv("OPAI_TICK_SECRET")), **obs.snapshot()}


@router.get("/v1/system/scheduler-status")
def scheduler_status(x_tick_secret: Optional[str] = Header(default=None), secret: Optional[str] = None, db: Session = Depends(get_db)):
    _require_tick_secret(x_tick_secret, secret)
    return RM.status(db)


# ---------------- recurring plan preferences (also reachable through chat: "send me my plan every morning at 7:30")
class DailyPlanIn(Who):
    time: str = Field(default=RM.DEFAULT_BRIEF_TIME, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: Optional[str] = Field(default=None, max_length=64)


@router.post("/v1/preferences/daily-plan")
def enable_daily_plan(p: DailyPlanIn, db: Session = Depends(get_db)):
    uid = _uid(db, p.user_id)
    if p.timezone:
        if not RM.valid_zone(p.timezone):
            raise HTTPException(422, "Unknown timezone (use an IANA name like Asia/Kolkata)")
        RM.set_tz(db, uid, name=p.timezone)
    RM.upsert_daily_brief(db, uid, p.time, True)
    return get_settings(uid, db)


@router.delete("/v1/preferences/daily-plan")
def disable_daily_plan(user_id: str, db: Session = Depends(get_db)):
    uid = _uid(db, user_id)
    RM.upsert_daily_brief(db, uid, None, False)         # also cancels the queued future occurrence; earlier briefs are kept
    return get_settings(uid, db)


@router.get("/v1/preferences/notifications")
def notification_preferences(user_id: str, db: Session = Depends(get_db)):
    return get_settings(user_id, db)
