"""LeetCode streak reminder: one daily line + a Done tap. Run: cd backend && python -m pytest tests/test_leetcode_streak.py -q"""
import uuid as _uuid
import os, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"; os.environ["GROQ_API_KEY"] = ""; os.environ["OPAI_SCHEDULER"] = "0"
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import database as D
import reminders as RM
import leetcode_streak as LC


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": u, "tz_offset_min": 330})
    return u


def test_count_streak():
    t = date(2026, 10, 18)
    d = lambda n: (t - timedelta(days=n)).isoformat()
    assert LC.count_streak([], t) == 0
    assert LC.count_streak([d(0), d(1), d(2)], t) == 3
    assert LC.count_streak([d(1), d(2)], t) == 2            # today not done yet: still alive
    assert LC.count_streak([d(2), d(3)], t) == 0            # missed yesterday: broken


def test_off_by_default_then_enable_done_and_nudge(c, uid):
    s = c.get("/v1/leetcode/streak", params={"user_id": uid}).json()
    assert s == {"enabled": False, "time": "21:00", "done_today": False, "streak": 0}
    assert c.put("/v1/leetcode/streak", json={"user_id": uid, "enabled": True, "time": "25:99"}).status_code == 422
    s = c.put("/v1/leetcode/streak", json={"user_id": uid, "enabled": True, "time": "20:30"}).json()
    assert s["enabled"] and s["time"] == "20:30"

    sess = D.SessionLocal()
    rows = sess.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "leetcode_streak", D.Reminder.status == "pending").all()
    assert len(rows) == 1 and rows[0].repeat == "daily"
    due = rows[0].remind_at

    RM.fire_due(sess, due + timedelta(minutes=1), user_id=uid)           # not done yet: one notification with a Done action
    n = sess.query(D.Notification).filter(D.Notification.user_id == uid, D.Notification.kind == "leetcode_streak").all()
    assert len(n) == 1 and n[0].data["actions"] == ["done"] and "streak" in n[0].body

    d = c.post("/v1/leetcode/done", json={"user_id": uid}).json()
    assert d["done_today"] and d["streak"] == 1
    assert c.post("/v1/leetcode/done", json={"user_id": uid}).json()["streak"] == 1      # idempotent per day

    RM.fire_due(sess, due + timedelta(days=1, minutes=1), user_id=uid)  # next day, but day-1 done does not cover day 2
    assert sess.query(D.Notification).filter(D.Notification.user_id == uid, D.Notification.kind == "leetcode_streak").count() == 2
    sess.close()


def test_already_done_means_no_nudge(c, uid):
    c.put("/v1/leetcode/streak", json={"user_id": uid, "enabled": True, "time": "20:30"})
    c.post("/v1/leetcode/done", json={"user_id": uid})
    sess = D.SessionLocal()
    r = sess.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "leetcode_streak", D.Reminder.status == "pending").one()
    due = r.remind_at
    fn = RM.offset_fn(sess, uid)
    local_due = RM.to_local(due, fn(due))
    today_local = (datetime.utcnow() + timedelta(minutes=330)).date()
    if local_due.date() != today_local:                                # the next slot is tomorrow; test the hook directly for today
        assert LC.nudge(sess, uid, datetime.combine(today_local, datetime.min.time().replace(hour=20, minute=30))) is None
    else:
        RM.fire_due(sess, due + timedelta(minutes=1), user_id=uid)
        assert sess.query(D.Notification).filter(D.Notification.user_id == uid, D.Notification.kind == "leetcode_streak").count() == 0
    sess.close()


def test_turning_off_cancels(c, uid):
    c.put("/v1/leetcode/streak", json={"user_id": uid, "enabled": True})
    c.put("/v1/leetcode/streak", json={"user_id": uid, "enabled": False})
    sess = D.SessionLocal()
    assert sess.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "leetcode_streak", D.Reminder.status == "pending").count() == 0
    sess.close()
