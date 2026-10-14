"""Outreach safety policy, enforced in code (not in prompts).

Rules from the OPAI plan:
  * never contact someone on the do-not-contact / bounce list
  * never re-email the same recipient inside RECONTACT_HOURS (default 24h)
  * no daily cap on how many different professors you can email (set OPAI_OUTREACH_DAILY_CAP to add one)
  * never keep two pending drafts for the same contact
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Contact, OutboxItem, OutreachHistory, SuppressedContact

def _recontact_hours() -> int:
    try:
        return max(1, int(os.getenv("OPAI_RECONTACT_HOURS", "24")))
    except ValueError:
        return 24


UNLIMITED = 10 ** 6


def daily_cap() -> int:
    """Unlimited by default. Gmail's own sending limits still apply and are shown as errors."""
    raw = os.getenv("OPAI_OUTREACH_DAILY_CAP", "").strip()
    if not raw or raw == "0":
        return UNLIMITED
    try:
        return max(1, int(raw))
    except ValueError:
        return UNLIMITED


class Blocked(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


def norm_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def is_suppressed(db: Session, uid: str, email: str) -> Optional[SuppressedContact]:
    e = norm_email(email)
    if not e:
        return None
    return db.query(SuppressedContact).filter(SuppressedContact.user_id == uid, SuppressedContact.email == e).first()


def sent_last_24h(db: Session, uid: str, exclude_outbox_id: Optional[str] = None) -> int:
    """Emails that count against the daily cap: logged sends AND approved-but-not-yet-logged messages, so the
    cap cannot be dodged by approving many drafts and logging none. max() avoids counting one email twice
    (approved, then logged as sent). `exclude_outbox_id` keeps an item from counting against itself at send time."""
    since = datetime.utcnow() - timedelta(hours=24)
    logged = (db.query(OutreachHistory)
              .filter(OutreachHistory.user_id == uid, OutreachHistory.status == "Sent", OutreachHistory.sent_at >= since)
              .count())
    q = db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.channel == "email", OutboxItem.status == "approved",
                                    func.coalesce(OutboxItem.approved_at, OutboxItem.created_at) >= since)
    if exclude_outbox_id:
        q = q.filter(OutboxItem.id != str(exclude_outbox_id))
    return max(logged, q.count())


def remaining_today(db: Session, uid: str) -> int:
    return max(0, daily_cap() - sent_last_24h(db, uid))


def last_contacted(db: Session, uid: str, email: str) -> Optional[datetime]:
    e = norm_email(email)
    rows = (db.query(OutreachHistory.sent_at)
            .join(Contact, Contact.id == OutreachHistory.contact_id)
            .filter(OutreachHistory.user_id == uid, OutreachHistory.sent_at.isnot(None),
                    OutreachHistory.status.in_(("Sent", "Replied", "No Response")))
            .filter(func.lower(Contact.email) == e).all())
    times = [r[0] for r in rows if r[0]]
    return max(times) if times else None


def check_can_draft(db: Session, uid: str, contact: Contact) -> None:
    """Raises Blocked when a draft must not be created."""
    sup = is_suppressed(db, uid, contact.email)
    if sup:
        raise Blocked(409, "suppressed", f"{contact.email} is on your do-not-contact list ({sup.reason}).")
    last = last_contacted(db, uid, contact.email)
    hrs = _recontact_hours()
    if last and datetime.utcnow() - last < timedelta(hours=hrs):
        ago = int((datetime.utcnow() - last).total_seconds() // 3600)
        raise Blocked(409, "recently_contacted",
                      f"You emailed {contact.email} {ago} hour(s) ago. Wait {hrs} hours before emailing the same professor again. Other professors are not affected.")
    pending = (db.query(OutboxItem)
               .filter(OutboxItem.user_id == uid, OutboxItem.status == "pending")
               .all())
    for p in pending:
        ref = p.ref or {}
        if ref.get("kind") == "contact" and ref.get("id") == contact.id:
            raise Blocked(409, "duplicate_pending", "A draft for this contact is already waiting in your Outbox.")


def check_can_send(db: Session, uid: str, contact: Contact, exclude_outbox_id: Optional[str] = None) -> None:
    """Raises Blocked when an approved email must not be released. Called from Outbox approval."""
    sup = is_suppressed(db, uid, contact.email)
    if sup:
        raise Blocked(409, "suppressed", f"{contact.email} is on your do-not-contact list ({sup.reason}).")
    if sent_last_24h(db, uid, exclude_outbox_id) >= daily_cap():
        raise Blocked(429, "daily_cap", f"Outreach limit reached: {daily_cap()} approved emails per 24 hours. Try again later.")
