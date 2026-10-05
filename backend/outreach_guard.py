"""Outreach safety policy, enforced in code (not in prompts).

Rules from the OPAI plan:
  * never contact someone on the do-not-contact / bounce list
  * never re-email the same recipient inside RECONTACT_DAYS
  * cap manually approved emails per rolling 24h (default 5)
  * never keep two pending drafts for the same contact
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Contact, OutboxItem, OutreachHistory, SuppressedContact

RECONTACT_DAYS = int(os.getenv("OPAI_RECONTACT_DAYS", "30"))


def daily_cap() -> int:
    try:
        return max(1, int(os.getenv("OPAI_OUTREACH_DAILY_CAP", "5")))
    except ValueError:
        return 5


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


def sent_last_24h(db: Session, uid: str) -> int:
    since = datetime.utcnow() - timedelta(hours=24)
    return (db.query(OutreachHistory)
            .filter(OutreachHistory.user_id == uid, OutreachHistory.status == "Sent", OutreachHistory.sent_at >= since)
            .count())


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
    if last and datetime.utcnow() - last < timedelta(days=RECONTACT_DAYS):
        days = (datetime.utcnow() - last).days
        raise Blocked(409, "recently_contacted",
                      f"You emailed {contact.email} {days} day(s) ago. Wait {RECONTACT_DAYS} days between emails to the same person.")
    pending = (db.query(OutboxItem)
               .filter(OutboxItem.user_id == uid, OutboxItem.status == "pending")
               .all())
    for p in pending:
        ref = p.ref or {}
        if ref.get("kind") == "contact" and ref.get("id") == contact.id:
            raise Blocked(409, "duplicate_pending", "A draft for this contact is already waiting in your Outbox.")


def check_can_send(db: Session, uid: str, contact: Contact) -> None:
    """Raises Blocked when an approved email must not be released. Called from Outbox approval."""
    sup = is_suppressed(db, uid, contact.email)
    if sup:
        raise Blocked(409, "suppressed", f"{contact.email} is on your do-not-contact list ({sup.reason}).")
    if sent_last_24h(db, uid) >= daily_cap():
        raise Blocked(429, "daily_cap", f"Outreach limit reached: {daily_cap()} approved emails per 24 hours. Try again later.")
