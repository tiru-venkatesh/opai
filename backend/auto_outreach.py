"""Daily auto-draft of ONE cold email to a professor at the IIT the user picked.

What it does, once per 24 hours per user:
  1. picks the best-matching professor (by the user's own skills/projects) at the selected IIT who has not been
     contacted, is not suppressed and has no pending draft,
  2. adds them to the user's contacts, writes a personalised draft with the normal outreach workflow,
  3. puts it in the Outbox as `pending` and sends the user a notification.

What it never does: send anything. OPAI holds no Gmail credential (the browser passes a short-lived send-only token
with each approved send), and every outreach_guard rule (do-not-contact list, 24h re-contact window, daily cap,
reviewed-hash approval) still applies. The user approves each email.

Safe to call from several workers/ticks: each user is claimed with a compare-and-set UPDATE before any draft is made.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

import faculty_search as F
import outreach_guard as G
from database import (AutoOutreachSetting, Contact, OutboxItem, OutreachHistory, SessionLocal, SuppressedContact, User,
                      outbox_content_hash)

log = logging.getLogger("opa.auto_outreach")

MIN_SCORE = 15            # below this the "match" is mostly noise: better to draft nothing than a generic email
MAX_TRIES = 5             # candidates tried in one run (a candidate can be blocked by the guard or fail to draft)
DRAFT_TTL_HOURS = 48
NOTE_PREFIX = "Auto-draft"


def gap_hours() -> int:
    """Never below 24: the whole point is one email a day."""
    try:
        return max(24, int(os.getenv("OPAI_AUTO_OUTREACH_HOURS", "24")))
    except ValueError:
        return 24


def _backoff(result: Optional[str]) -> timedelta:
    # how long to wait before trying again after a run that did NOT create a draft
    return {"error": timedelta(minutes=60), "no_candidates": timedelta(hours=6),
            "needs_profile": timedelta(hours=6), "waiting_for_approval": timedelta(minutes=30),
            "blocked": timedelta(hours=1)}.get(result or "", timedelta(minutes=30))


def get_setting(db: Session, uid: str, create: bool = False) -> Optional[AutoOutreachSetting]:
    s = db.query(AutoOutreachSetting).filter(AutoOutreachSetting.user_id == uid).first()
    if not s and create:
        s = AutoOutreachSetting(user_id=uid, enabled=False)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _pending_auto(db: Session, uid: str, now: datetime) -> Optional[OutboxItem]:
    q = (db.query(OutboxItem)
         .filter(OutboxItem.user_id == uid, OutboxItem.status == "pending", OutboxItem.channel == "email",
                 OutboxItem.note.like(NOTE_PREFIX + "%"))
         .order_by(OutboxItem.created_at.desc()))
    for it in q.all():
        if not it.expires_at or it.expires_at > now:
            return it
    return None


def _excluded_emails(db: Session, uid: str) -> set:
    """Never auto-pick someone the user already wrote to, drafted for, rejected, or suppressed."""
    out = {x.email for x in db.query(SuppressedContact).filter(SuppressedContact.user_id == uid).all() if x.email}
    rows = (db.query(Contact.email).join(OutreachHistory, OutreachHistory.contact_id == Contact.id)
            .filter(OutreachHistory.user_id == uid).all())
    out |= {G.norm_email(r[0]) for r in rows if r[0]}
    # every status counts: a professor whose draft the user rejected (or let expire) is not picked again
    for it in db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.channel == "email").all():
        to = G.norm_email((it.payload or {}).get("to"))
        if to:
            out.add(to)
    return out


def _query_for(db: Session, u: User) -> str:
    from faculty_api import _auto_query          # lazy: faculty_api imports the opportunities stack
    return _auto_query(db, u)


def _contact_for(db: Session, uid: str, row: Dict[str, Any]) -> Contact:
    c = db.query(Contact).filter(func.lower(Contact.email) == row["email"]).first()
    if c:
        return c
    inst = f"{row['institute']} - {row['department']}" if row.get("department") else row["institute"]
    c = Contact(name=row["name"], institute=inst, email=row["email"], research_areas=row.get("research_areas") or [],
                status="Not started", source_url=row.get("website"), source_checked_on=None, email_verification="unverified")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _finish(db: Session, s: AutoOutreachSetting, now: datetime, result: str, message: str, outbox_id: Optional[str] = None,
            drafted: bool = False) -> Dict[str, Any]:
    s.last_attempt_at, s.last_result, s.last_message = now, result, message[:500]
    if drafted:
        s.last_run_at, s.last_outbox_id = now, outbox_id
    db.commit()
    return {"result": result, "message": message, "outbox_id": outbox_id}


def run_for_user(db: Session, uid: str, now: Optional[datetime] = None, force: bool = False,
                 draft_fn=None) -> Dict[str, Any]:
    """One attempt. `force` skips only the retry back-off, never the 24h gap. `draft_fn(uid, contact_id, db)` is injectable for tests."""
    now = now or datetime.utcnow()
    s = get_setting(db, uid)
    if not s or not s.enabled:
        return {"result": "off", "message": "Daily auto-draft is off."}
    if s.last_run_at and now - s.last_run_at < timedelta(hours=gap_hours()):
        nxt = s.last_run_at + timedelta(hours=gap_hours())
        return {"result": "too_soon", "message": "Already drafted in the last 24 hours.", "next_run_at": nxt.isoformat() + "Z"}
    if not force and s.last_attempt_at and now - s.last_attempt_at < _backoff(s.last_result):
        return {"result": "backoff", "message": s.last_message or "Waiting before the next try."}

    # claim: only one worker/tick proceeds for this user
    old = s.last_attempt_at
    claimed = (db.query(AutoOutreachSetting)
               .filter(AutoOutreachSetting.id == s.id, AutoOutreachSetting.last_attempt_at == old if old is not None
                       else AutoOutreachSetting.last_attempt_at.is_(None))
               .update({"last_attempt_at": now}, synchronize_session=False))
    db.commit()
    if claimed != 1:
        return {"result": "backoff", "message": "Another run is already in progress."}
    db.refresh(s)

    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return _finish(db, s, now, "error", "User not found.")

    if _pending_auto(db, uid, now):
        return _finish(db, s, now, "waiting_for_approval",
                       "Yesterday's draft is still waiting for your review. Approve or reject it and the next one is drafted.")
    if G.sent_last_24h(db, uid) >= G.daily_cap():
        return _finish(db, s, now, "blocked", "Daily outreach limit reached. Trying again later.")

    try:
        query = _query_for(db, u)
    except Exception as e:
        log.warning("auto outreach query failed for %s: %s", uid, e)
        query = ""
    if not query:
        return _finish(db, s, now, "needs_profile",
                       "Add skills or a project to your profile first. Without them OPAI cannot match a professor to you.")

    excluded = _excluded_emails(db, uid)
    cands: List[Dict[str, Any]] = [c for c in F.search(query, s.institute, 60, False, exclude_emails=excluded)
                                   if c["score"] >= MIN_SCORE and c["email"] not in excluded]
    if not cands:
        where = s.institute or "the dataset"
        return _finish(db, s, now, "no_candidates", f"No new professors at {where} match your profile well enough. Try another IIT or add skills.")

    if draft_fn is None:
        from agent_service import workflow_draft_outreach as draft_fn      # lazy: pulls in the LLM client

    last_err = None
    for cand in cands[:MAX_TRIES]:
        row = F.get(cand["id"])
        if not row:
            continue
        contact = _contact_for(db, uid, row)
        try:
            G.check_can_draft(db, uid, contact)
        except G.Blocked as e:
            last_err = e.detail
            continue
        try:
            draft = draft_fn(UUID(uid), UUID(contact.id), db)
        except Exception as e:                                   # LLM down, rate-limited, bad JSON ...
            db.rollback()
            log.warning("auto outreach draft failed for %s: %s", uid, e)
            return _finish(db, s, now, "error", "Could not write the draft right now. OPAI will retry within the hour.")
        item = OutboxItem(user_id=uid, channel="email", status="pending",
                          payload={"to": contact.email, "subject": draft.subject_line, "body": draft.email_body},
                          ref={"kind": "contact", "id": contact.id}, risk_level="high", approval_scope="single_use",
                          expires_at=now + timedelta(hours=DRAFT_TTL_HOURS),
                          note=f"{NOTE_PREFIX} for {contact.name} ({cand['score']}% match). Check the facts, then approve."
                               + (f" {draft.repeat_warning}" if getattr(draft, "repeat_warning", None) else ""))
        if contact.status == "Not started":
            contact.status = "Drafted"
        db.add(item)
        db.flush()
        item.payload_hash = outbox_content_hash(item.channel, item.payload)
        db.commit()
        db.refresh(item)
        _notify_user(db, uid, item, contact)
        return _finish(db, s, now, "drafted", f"Drafted an email to {contact.name} ({contact.institute}). Review it in Outreach.",
                       item.id, drafted=True) | {"professor": contact.name, "institute": contact.institute}
    return _finish(db, s, now, "blocked", last_err or "Every candidate was blocked by the outreach rules.")


def _notify_user(db: Session, uid: str, item: OutboxItem, contact: Contact) -> None:
    try:
        import reminders
        reminders._notify(db, uid, "outreach_draft", "Daily outreach draft is ready",
                          f"A draft to {contact.name} ({contact.institute}) is waiting for your review. Nothing is sent until you approve.",
                          "opportunities.html#outreach", {"outbox_id": item.id}, None, f"auto_outreach:{uid}:{item.id}")
    except Exception as e:                       # the Outbox row is the source of truth; notification is best-effort
        log.warning("auto outreach notify failed: %s", e)


def tick(db: Session, now: Optional[datetime] = None) -> int:
    """Called by the scheduler loop and /v1/system/tick. Returns how many drafts were created."""
    now = now or datetime.utcnow()
    made = 0
    for s in db.query(AutoOutreachSetting).filter(AutoOutreachSetting.enabled.is_(True)).limit(500).all():
        if s.last_run_at and now - s.last_run_at < timedelta(hours=gap_hours()):
            continue
        try:
            if run_for_user(db, s.user_id, now).get("result") == "drafted":
                made += 1
        except Exception as e:
            db.rollback()
            log.warning("auto outreach tick failed for %s: %s", s.user_id, e)
    return made


def tick_standalone() -> int:
    db = SessionLocal()
    try:
        return tick(db)
    finally:
        db.close()


def status(db: Session, uid: str) -> Dict[str, Any]:
    s = get_setting(db, uid)
    now = datetime.utcnow()
    nxt = None
    if s and s.enabled:
        nxt = (s.last_run_at + timedelta(hours=gap_hours())) if s.last_run_at else now
    pend = _pending_auto(db, uid, now)
    return {"enabled": bool(s and s.enabled), "institute": s.institute if s else None,
            "last_run_at": (s.last_run_at.isoformat() + "Z") if s and s.last_run_at else None,
            "next_run_at": (nxt.isoformat() + "Z") if nxt else None, "last_result": s.last_result if s else None,
            "last_message": s.last_message if s else None, "pending_outbox_id": pend.id if pend else None,
            "institutes": F.institutes(), "gap_hours": gap_hours(),
            "policy": "One draft per 24 hours. OPAI never sends it: you review and approve every email."}
