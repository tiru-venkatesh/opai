"""Optional Web Push (VAPID). Needs `pip install pywebpush` and OPAI_VAPID_PUBLIC / OPAI_VAPID_PRIVATE (+ OPAI_VAPID_SUBJECT).
Without them everything still works through the in-app poller / notification centre; push is what delivers while the app is closed.

Every attempt is recorded in notification_deliveries. Failures are retried (3 attempts, growing back-off); endpoints the push
service reports as gone (404/410) are unsubscribed."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy.orm import Session

from database import Notification, NotificationDelivery, PushSubscription

MAX_ATTEMPTS = 3
BACKOFF_MIN = (1, 5, 15)


class PushGone(Exception):
    """The push service says this subscription no longer exists."""


def public_key() -> str:
    return os.getenv("OPAI_VAPID_PUBLIC", "").strip()


def enabled() -> bool:
    if not (public_key() and os.getenv("OPAI_VAPID_PRIVATE", "").strip()):
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except Exception:
        return False


def payload(n: Notification) -> Dict[str, Any]:
    return {"id": n.id, "title": n.title, "body": n.body, "link": n.link, "kind": n.kind, "data": n.data or {}}


def _send_webpush(sub: Dict[str, Any], data: str) -> None:       # the only function that touches the network (tests replace it)
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=sub, data=data, vapid_private_key=os.getenv("OPAI_VAPID_PRIVATE"),
                vapid_claims={"sub": os.getenv("OPAI_VAPID_SUBJECT", "mailto:admin@opai.local")})
    except WebPushException as e:
        if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
            raise PushGone(str(e))
        raise


def _attempt(db: Session, d: NotificationDelivery, n: Notification, sub: PushSubscription, now: datetime) -> bool:
    d.attempts = (d.attempts or 0) + 1
    try:
        _send_webpush({"endpoint": sub.endpoint, "keys": sub.keys or {}}, json.dumps(payload(n)))
        d.status, d.error, d.delivered_at, d.next_retry_at = "ok", None, now, None
    except PushGone as e:
        d.status, d.error, d.next_retry_at = "gone", str(e)[:300], None
        db.delete(sub)                                            # subscription cleanup
    except Exception as e:
        d.error = str(e)[:300]
        if d.attempts >= MAX_ATTEMPTS:
            d.status, d.next_retry_at = "failed", None
        else:
            d.status, d.next_retry_at = "failed", now + timedelta(minutes=BACKOFF_MIN[min(d.attempts - 1, len(BACKOFF_MIN) - 1)])
    db.commit()
    return d.status == "ok"


def send(db: Session, uid: str, n: Notification, now: datetime = None) -> int:
    if not enabled():
        return 0
    now, ok = now or datetime.utcnow(), 0
    for sub in db.query(PushSubscription).filter(PushSubscription.user_id == uid).all():
        d = NotificationDelivery(notification_id=n.id, user_id=uid, channel="web_push", endpoint=sub.endpoint, status="pending", attempts=0)
        db.add(d); db.commit()
        ok += _attempt(db, d, n, sub, now)
    return ok


def retry(db: Session, now: datetime) -> int:
    """Re-send failed deliveries whose back-off has elapsed (skipped once the user already saw the notification)."""
    if not enabled():
        return 0
    done = 0
    rows = (db.query(NotificationDelivery).filter(NotificationDelivery.status == "failed", NotificationDelivery.channel == "web_push",
                                                  NotificationDelivery.next_retry_at.isnot(None), NotificationDelivery.next_retry_at <= now).limit(50).all())
    for d in rows:
        n = db.query(Notification).filter(Notification.id == d.notification_id).first()
        sub = db.query(PushSubscription).filter(PushSubscription.user_id == d.user_id, PushSubscription.endpoint == d.endpoint).first()
        if not n or not sub or n.delivered_at or n.read_at:
            d.status, d.next_retry_at = "gone" if not sub else "ok", None
            db.commit()
            continue
        done += _attempt(db, d, n, sub, now)
    return done
