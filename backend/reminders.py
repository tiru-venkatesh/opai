"""Karna reminders + notifications.

  * parse_when()      pure natural-language time parser ("2 40pm", "in 20 min", "tomorrow 7am", "14:40")
  * time zones        users have an IANA zone (Asia/Kolkata); the DB and the scheduler only ever compare naive UTC.
                      Recurrence is anchored to LOCAL wall time (07:30 stays 07:30 across daylight-saving changes).
  * fire_due()        scheduler tick: claim due reminders atomically -> idempotent Notification (+ Web Push with delivery records)
  * the daily "today's plan" nudge is a repeating Reminder(kind='daily_brief') whose body is the Daily Brief summary
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import obs
from audit.logger import record as audit
from database import Notification, NotificationDelivery, PushSubscription, Reminder, SessionLocal, User

log = logging.getLogger("opa.reminders")
DEFAULT_BRIEF_TIME = "07:30"
STALE_DAILY_HOURS = 6          # a 'today's plan' nudge that is >6h late is skipped, not sent at night
MAX_PUSH_ATTEMPTS = 3
STATE: Dict[str, Any] = {"ticks": 0, "fired_total": 0, "last_tick_at": None, "last_ok_at": None, "last_error": None, "last_fired": 0}


# ------------------------------------------------------------------ time zones
def valid_zone(name: Optional[str]) -> bool:
    if not name or not isinstance(name, str) or len(name) > 64:
        return False
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:
        return False


def tz_name(db: Session, uid: str) -> Optional[str]:
    u = db.query(User).filter(User.id == uid).first()
    n = (u.preferences or {}).get("timezone") if u else None
    return n if valid_zone(n) else None


def _server_offset() -> int:
    return int((datetime.now().astimezone().utcoffset() or timedelta()).total_seconds() // 60)


def offset_at(db: Session, uid: str, at_utc: Optional[datetime] = None) -> int:
    """UTC offset in minutes for this user at an instant: IANA zone first, then a stored fixed offset, then the server's."""
    at_utc = at_utc or datetime.utcnow()
    name = tz_name(db, uid)
    if name:
        from zoneinfo import ZoneInfo
        return int(at_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(name)).utcoffset().total_seconds() // 60)
    u = db.query(User).filter(User.id == uid).first()
    off = (u.preferences or {}).get("tz_offset_min") if u else None
    return off if isinstance(off, int) and -840 <= off <= 840 else _server_offset()


def tz_offset(db: Session, uid: str, at_utc: Optional[datetime] = None) -> int:       # kept for existing callers
    return offset_at(db, uid, at_utc)


def offset_fn(db: Session, uid: str) -> Callable[[datetime], int]:
    return lambda at: offset_at(db, uid, at)


def set_tz(db: Session, uid: str, off: Optional[int] = None, name: Optional[str] = None) -> None:
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return
    prefs = dict(u.preferences or {})
    if name and valid_zone(name):
        prefs["timezone"] = name
    if off is not None and -840 <= int(off) <= 840:
        prefs["tz_offset_min"] = int(off)
        if not name:
            prefs.pop("timezone", None)         # an explicit fixed offset replaces an older zone name
    u.preferences = prefs
    db.commit()


def local_to_utc(local: datetime, fn: Optional[Callable[[datetime], int]], fallback_off: int) -> datetime:
    """Wall-clock local time -> naive UTC, honouring the zone's offset AT that moment (two-pass for DST edges)."""
    if fn is None:
        return local - timedelta(minutes=fallback_off)
    guess = local - timedelta(minutes=fallback_off)
    return local - timedelta(minutes=fn(local - timedelta(minutes=fn(guess))))


def to_local(dt: datetime, off: int) -> datetime:
    return dt + timedelta(minutes=off)


def fmt_time(local: datetime) -> str:
    return local.strftime("%I:%M %p").lstrip("0")


def day_word(local: datetime, now_local: datetime) -> str:
    d = (local.date() - now_local.date()).days
    return "today" if d == 0 else "tomorrow" if d == 1 else local.strftime("%a %d %b")


# ------------------------------------------------------------------ wording (one place for every channel)
def reminder_body(title: str, local_time: str) -> str:
    return f"Time for: {title}. This is your {local_time} reminder."


def confirm_text(title: str, local: datetime, now_local: datetime) -> str:
    t = title[:1].lower() + title[1:] if len(title) > 1 and title[1].islower() else title
    return f"Done - I'll remind you {day_word(local, now_local)} at {fmt_time(local)} about {t}."


def ask_title_text(local: datetime) -> str:
    return f"What should I remind you about at {fmt_time(local)}?"


# ------------------------------------------------------------------ parsing
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}
_REL = re.compile(r"\bin\s+(\d+(?:\.\d+)?|an?|one|two|three|four|five|ten|half an?)\s*(minutes?|mins?|hours?|hrs?)\b", re.I)
_MER = re.compile(r"\b(?:at\s+)?(\d{1,2})(?:\s*[:.]\s*|\s+)?(\d{2})?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.I)
_H24 = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3])\s*[:.]\s*([0-5]\d)\b")
_HOUR_ONLY = re.compile(r"\bat\s+(\d{1,2})(?![\d:.])\b(?!\s*(?:am|pm|a\.m|p\.m|minutes?|mins?|hours?|days?))", re.I)
_FILLER = re.compile(r"\b(please|pls|can you|could you|kindly|remind me|remind|reminder|set a|set an|set|notify me|ping me|tell me|"
                     r"today|tonight|tomorrow|tmrw|about|at|to|that|for|on|in|again)\b", re.I)


def parse_when(text: str, now_utc: datetime, off: int, offset_fn=None) -> Optional[Dict[str, Any]]:
    """Returns {'at_utc', 'rest', 'explicit_day'} or None when no clock time / duration is present."""
    t = " ".join((text or "").split())
    low = t.lower()
    now_local = now_utc + timedelta(minutes=off)
    m = _REL.search(low)
    if m:
        raw = m.group(1)
        n = 0.5 if raw.startswith("half") else float(_WORDS.get(raw, raw)) if not raw.replace(".", "").isdigit() else float(raw)
        mins = n * (60 if m.group(2).startswith(("h")) else 1)
        at_local = now_local + timedelta(minutes=mins)
        rest = (t[:m.start()] + " " + t[m.end():])
        return {"at_utc": at_local - timedelta(minutes=off), "rest": _clean(rest), "explicit_day": False, "relative": True}   # a duration: no wall-clock re-anchoring
    hh = mm = None
    mer = None
    span = None
    m = _MER.search(low)
    if m and 1 <= int(m.group(1)) <= 12:
        hh, mm, mer, span = int(m.group(1)), int(m.group(2) or 0), m.group(3)[0], m.span()
        if mm > 59:
            return None
    else:
        m = _H24.search(low) or None
        if m:
            hh, mm, span = int(m.group(1)), int(m.group(2)), m.span()
        else:
            m = _HOUR_ONLY.search(low)
            if not m or not (1 <= int(m.group(1)) <= 12):
                return None
            hh, mm, span = int(m.group(1)), 0, m.span()
    explicit_day = None
    if re.search(r"\b(tomorrow|tmrw)\b", low):
        explicit_day = 1
    elif re.search(r"\b(today|tonight)\b", low):
        explicit_day = 0
    if mer:
        h24 = (hh % 12) + (12 if mer == "p" else 0)
        cands = [h24]
    elif hh >= 13 or hh == 0 or (_H24.search(low) and low[span[0]:span[1]].strip().startswith(("0", "1", "2")) and hh >= 13):
        cands = [hh % 24]
    else:                                   # ambiguous "2:40": consider am and pm
        cands = sorted({hh % 12, hh % 12 + 12})
    base = now_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=explicit_day or 0)
    options = [base + timedelta(hours=h, minutes=mm) for h in cands]
    future = [o for o in options if o > now_local]
    if future:
        at_local = future[0]
    else:
        at_local = options[-1] + timedelta(days=1)
    rest = t[:span[0]] + " " + t[span[1]:]
    return {"at_utc": local_to_utc(at_local, offset_fn, off), "rest": _clean(rest), "explicit_day": explicit_day is not None, "relative": False}


def _clean(s: str) -> str:
    s = re.sub(r"\b(today|tonight|tomorrow|tmrw)\b", " ", s, flags=re.I)
    s = _FILLER.sub(" ", s)
    s = re.sub(r"[^\w\s'&/+#.-]", " ", s)
    return " ".join(s.split()).strip(" .,-")


def clean_title(text: str) -> str:
    t = " ".join((text or "").split())
    t = re.sub(r"^(?:i\s+(?:have|need|got)\s+(?:to\s+)?(?:a\s+|an\s+|the\s+)?|it'?s\s+|about\s+|to\s+|for\s+)", "", t, flags=re.I).strip(" .,!?")
    return (t[:1].upper() + t[1:])[:160]


# ------------------------------------------------------------------ CRUD
def serialize(r: Reminder, off: int = 0, now: Optional[datetime] = None) -> Dict[str, Any]:
    local = to_local(r.remind_at, off)
    now_local = to_local(now or datetime.utcnow(), off)
    return {"id": r.id, "kind": r.kind, "title": r.title, "status": r.status, "repeat": r.repeat, "at_utc": r.remind_at.isoformat() + "Z",
            "local_time": fmt_time(local), "local_day": day_word(local, now_local), "snooze_count": r.snooze_count or 0,
            "timezone": r.timezone, "snoozed_until": r.snoozed_until.isoformat() + "Z" if r.snoozed_until else None,
            "completed_at": r.completed_at.isoformat() + "Z" if r.completed_at else None}


def view(db: Session, uid: str, r: Reminder, now: Optional[datetime] = None) -> Dict[str, Any]:
    return serialize(r, offset_at(db, uid, r.remind_at), now)


def create(db: Session, uid: str, title: Optional[str], at_utc: datetime, repeat: str = "none", kind: str = "reminder",
           status: str = "pending", source: str = "chat") -> Reminder:
    r = Reminder(user_id=uid, kind=kind, title=(title or "")[:160] or None, remind_at=at_utc, repeat=repeat, status=status, source=source,
                 timezone=tz_name(db, uid))
    db.add(r)
    db.commit()
    db.refresh(r)
    audit(db, uid, f"reminder.create:{kind}", {"reminder_id": r.id, "source": source}, {"at_utc": at_utc.isoformat(), "status": status}, "low")
    if status == "pending":
        obs.emit("reminder_created", reminder_id=r.id, kind=kind, source=source)
    return r


def get(db: Session, uid: str, rid: str) -> Reminder:
    r = db.query(Reminder).filter(Reminder.id == rid, Reminder.user_id == uid).first()
    if not r:
        raise LookupError("Reminder not found")
    return r


def mark_done(db: Session, uid: str, rid: str) -> Reminder:
    r = get(db, uid, rid)
    if r.repeat == "none" or r.kind == "reminder":
        r.status, r.completed_at = "done", datetime.utcnow()
    db.commit()
    return r


def snooze(db: Session, uid: str, rid: str, minutes: int = 10) -> Reminder:
    r = get(db, uid, rid)
    r.remind_at = datetime.utcnow() + timedelta(minutes=max(1, min(int(minutes), 24 * 60)))
    r.snoozed_until = r.remind_at
    r.status, r.snooze_count = "pending", (r.snooze_count or 0) + 1
    db.commit()
    return r


def cancel(db: Session, uid: str, rid: str) -> Reminder:
    r = get(db, uid, rid)
    r.status = "cancelled"
    db.commit()
    return r


def update(db: Session, uid: str, rid: str, title: Optional[str] = None, at_utc: Optional[datetime] = None) -> Reminder:
    r = get(db, uid, rid)
    if r.status not in ("pending", "awaiting_text"):
        raise ValueError("Only pending reminders can be edited")
    if title:
        r.title = title[:160]
    if at_utc:
        r.remind_at = at_utc
    if r.title and r.status == "awaiting_text":
        r.status = "pending"
    db.commit()
    return r


def upsert_daily_brief(db: Session, uid: str, hhmm: Optional[str], enabled: bool = True) -> Optional[Reminder]:
    rows = db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "daily_brief", Reminder.status == "pending").all()
    for r in rows:
        r.status = "cancelled"
    db.commit()
    if not enabled:
        return None
    fn, now = offset_fn(db, uid), datetime.utcnow()
    h, m = [int(x) for x in (hhmm or DEFAULT_BRIEF_TIME).split(":")]
    now_local = to_local(now, fn(now))
    at_local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if at_local <= now_local:
        at_local += timedelta(days=1)
    return create(db, uid, "Today's plan", local_to_utc(at_local, fn, fn(now)), repeat="daily", kind="daily_brief", source="settings")


def daily_brief_setting(db: Session, uid: str) -> Dict[str, Any]:
    r = db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "daily_brief", Reminder.status == "pending").first()
    if not r:
        return {"enabled": False, "time": DEFAULT_BRIEF_TIME}
    return {"enabled": True, "time": to_local(r.remind_at, offset_at(db, uid, r.remind_at)).strftime("%H:%M")}


# ------------------------------------------------------------------ firing
def _advance_daily(old_utc: datetime, now: datetime, fn: Callable[[datetime], int]) -> datetime:
    """Next occurrence at the SAME LOCAL wall time (not +24h UTC), strictly after `now`."""
    local = old_utc + timedelta(minutes=fn(old_utc))
    while True:
        local += timedelta(days=1)
        at = local_to_utc(local, fn, fn(old_utc))
        if at > now:
            return at


def _notify(db: Session, uid: str, kind: str, title: str, body: str, link: str, data: Dict[str, Any], rid: Optional[str], key: str) -> Optional[Notification]:
    """Idempotent: the same occurrence key can only ever create one notification (restarts, double ticks, retries)."""
    if db.query(Notification.id).filter(Notification.idempotency_key == key).first():
        return None
    n = Notification(user_id=uid, kind=kind, title=title, body=body, link=link, data=data, reminder_id=rid, idempotency_key=key)
    db.add(n)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(n)
    obs.emit("reminder_delivered", notification_id=n.id, kind=kind)
    try:
        import push
        push.send(db, uid, n)
    except Exception as e:                       # push is best-effort; the inbox row is the source of truth
        log.warning("push failed: %s", e)
    return n


def _brief_for(db: Session, uid: str, btype: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from briefs import service
    return service.generate(db, uid, btype, params)


def fire_due(db: Session, now: Optional[datetime] = None, user_id: Optional[str] = None) -> int:
    """One scheduler tick. Safe with several workers/ticks: each reminder is claimed with a compare-and-set UPDATE
    (on Postgres this is the same guarantee as FOR UPDATE SKIP LOCKED) and notifications are idempotent per occurrence."""
    now = now or datetime.utcnow()
    STATE["ticks"] += 1
    STATE["last_tick_at"] = now.isoformat() + "Z"
    fired = 0
    try:
        q = db.query(Reminder).filter(Reminder.status == "pending", Reminder.remind_at <= now)
        if user_id:
            q = q.filter(Reminder.user_id == user_id)
        for r in q.order_by(Reminder.remind_at).limit(200).all():
            old, uid = r.remind_at, r.user_id
            fn = offset_fn(db, uid)
            nxt = _advance_daily(old, now, fn) if r.repeat == "daily" else None
            upd = {"remind_at": nxt, "fired_at": now} if nxt else {"status": "fired", "fired_at": now}
            if db.query(Reminder).filter(Reminder.id == r.id, Reminder.status == "pending", Reminder.remind_at == old).update(upd) != 1:
                db.rollback()
                continue                                          # another worker/tick claimed it
            db.commit()
            local_old = to_local(old, fn(old))
            if r.kind == "daily_brief":
                if (now - old) > timedelta(hours=STALE_DAILY_HOURS):
                    continue                                      # server was asleep; never send this morning's plan at night
                key = f"daily_plan:{uid}:{local_old.date().isoformat()}:{local_old.strftime('%H:%M')}"
                if db.query(Notification.id).filter(Notification.idempotency_key == key).first():
                    continue
                try:
                    from briefs import jarvis
                    b = _brief_for(db, uid, "daily_plan", {})
                except Exception as e:
                    log.warning("daily brief failed for %s: %s", uid, e)
                    db.rollback()
                    obs.emit("scheduler_error", where="daily_brief", error=str(e)[:200])
                    continue
                n = _notify(db, uid, "daily_brief", "Today's plan", jarvis.spoken_summary(b), f"briefs.html?brief={b['brief_id']}",
                            {"brief_id": b["brief_id"], "reminder_id": r.id}, r.id, key)
            else:
                key = f"reminder_due:{r.id}:{old.isoformat()}"
                if db.query(Notification.id).filter(Notification.idempotency_key == key).first():
                    continue
                link, data = "today.html", {"reminder_id": r.id, "actions": ["done", "snooze"]}
                try:
                    b = _brief_for(db, uid, "reminder", {"reminder_id": r.id})
                    link, data["brief_id"] = f"briefs.html?brief={b['brief_id']}", b["brief_id"]
                except Exception as e:
                    db.rollback()
                    log.warning("reminder brief failed: %s", e)
                n = _notify(db, uid, "reminder", "Reminder due", reminder_body(r.title or "your reminder", fmt_time(local_old)), link, data, r.id, key)
            if n:
                fired += 1
        retry_failed(db, now)
    except Exception as e:
        STATE["last_error"] = {"at": now.isoformat() + "Z", "error": str(e)[:300]}
        obs.emit("scheduler_error", where="tick", error=str(e)[:200])
        db.rollback()
        raise
    STATE["last_ok_at"], STATE["last_fired"] = now.isoformat() + "Z", fired
    STATE["fired_total"] += fired
    obs.emit("scheduler_tick", fired=fired)
    return fired


def retry_failed(db: Session, now: datetime) -> int:
    try:
        import push
    except Exception:
        return 0
    return push.retry(db, now)


def status(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.utcnow()
    due = db.query(Reminder).filter(Reminder.status == "pending", Reminder.remind_at <= now).order_by(Reminder.remind_at).all()
    nxt = db.query(Reminder).filter(Reminder.status == "pending", Reminder.remind_at > now).order_by(Reminder.remind_at).first()
    return {"thread_running": _started, **STATE, "pending_due": len(due), "oldest_due_lag_s": int((now - due[0].remind_at).total_seconds()) if due else 0,
            "next_due_at": nxt.remind_at.isoformat() + "Z" if nxt else None,
            "failed_deliveries": db.query(NotificationDelivery).filter(NotificationDelivery.status == "failed").count()}


# ------------------------------------------------------------------ background loop
_started = False


def start_scheduler(interval: int = 30) -> bool:
    """Daemon thread; disabled with OPAI_SCHEDULER=0. Hosts that sleep should also ping /v1/system/tick every minute."""
    global _started
    if _started or os.getenv("OPAI_SCHEDULER", "1") == "0":
        return False
    _started = True

    def loop():
        while True:
            try:
                s = SessionLocal()
                try:
                    fire_due(s)
                finally:
                    s.close()
            except Exception as e:
                log.warning("scheduler tick failed: %s", e)
            _time.sleep(interval)
    threading.Thread(target=loop, name="opa-reminders", daemon=True).start()
    return True
