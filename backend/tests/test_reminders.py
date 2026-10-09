"""Karna reminders + daily plan notification. Run: cd backend && python -m pytest tests/test_reminders.py -q"""
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
from agent import reminder_chat as RC

IST = 330


def utc(y, mo, d, h, mi=0):
    """IST wall-clock -> naive UTC."""
    return datetime(y, mo, d, h, mi) - timedelta(minutes=IST)


NOW = utc(2026, 10, 7, 14, 34)           # the screenshot: Wed 7 Oct, 14:34 IST


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": u, "tz_offset_min": IST})
    return u


def db():
    return D.SessionLocal()


def local(dt):
    return (dt + timedelta(minutes=IST)).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- parser
@pytest.mark.parametrize("text,expected", [
    ("Remind me at 2 40pm", "2026-10-07 14:40"),
    ("remind me at 2:40 pm to call mom", "2026-10-07 14:40"),
    ("remind me at 14:40", "2026-10-07 14:40"),
    ("remind me at 5pm", "2026-10-07 17:00"),
    ("remind me at 9am", "2026-10-08 09:00"),          # already past today -> tomorrow
    ("remind me tomorrow at 7am", "2026-10-08 07:00"),
    ("remind me today at 11pm", "2026-10-07 23:00"),
    ("remind me in 20 minutes", "2026-10-07 14:54"),
    ("remind me in 2 hours", "2026-10-07 16:34"),
    ("remind me in half an hour", "2026-10-07 15:04"),
    ("remind me at 2.40 p.m.", "2026-10-07 14:40"),
    ("remind me at 3:15", "2026-10-07 15:15"),          # ambiguous: next occurrence (3:15 am has passed)
    ("remind me at 12am", "2026-10-08 00:00"),
])
def test_parse_when(text, expected):
    w = RM.parse_when(text, NOW, IST)
    assert w and local(w["at_utc"]) == expected, (text, w)


def test_parse_when_none_without_a_time():
    for t in ("remind me to submit the report", "remind me tomorrow", "what is 2 + 2", "I have 40 apples", "remind me about class 9"):
        assert RM.parse_when(t, NOW, IST) is None, t


def test_parse_extracts_subject():
    assert RM.parse_when("remind me to submit the DS record at 5pm", NOW, IST)["rest"] == "submit the DS record"
    assert RM.parse_when("Remind me at 2 40pm", NOW, IST)["rest"] == ""
    assert RM.clean_title("I have a work datastrcuture record") == "Work datastrcuture record"


# ---------------------------------------------------------------- the screenshot flow
def test_ask_then_answer_then_fire_like_meta_ai(c, uid):
    s = db()
    r1 = RC.handle(uid, "Remind me at 2 40pm", s, now=NOW)
    assert r1.action == "reminder" and r1.reply == "What should I remind you about at 2:40 PM?"
    r2 = RC.handle(uid, "I have a work datastrcuture record", s, now=NOW + timedelta(minutes=1))
    assert r2.reply.startswith("Done - I'll remind you today at 2:40 PM about") and "record" in r2.reply.lower()
    rem = r2.payload["reminder"]
    assert rem["local_time"] == "2:40 PM" and rem["local_day"] == "today" and rem["status"] == "pending"
    # nothing yet at 14:39, fires at 14:40
    RM.fire_due(s, NOW + timedelta(minutes=4))
    assert s.query(D.Notification).filter(D.Notification.user_id == uid).count() == 0
    RM.fire_due(s, NOW + timedelta(minutes=6))
    n = s.query(D.Notification).filter(D.Notification.user_id == uid).one()
    assert n.kind == "reminder" and "2:40 PM" in n.body and "record" in n.body.lower() and n.data["actions"] == ["done", "snooze"]
    RM.fire_due(s, NOW + timedelta(minutes=7))                                # never fires twice
    assert s.query(D.Notification).filter(D.Notification.user_id == uid).count() == 1
    s.close()


def test_one_shot_and_relative_reminders(c, uid):
    s = db()
    r = RC.handle(uid, "remind me to submit the DS record at 5pm", s, now=NOW)
    assert "5:00 PM" in r.reply and "about submit the DS record" in r.reply
    r = RC.handle(uid, "remind me in 20 minutes to stretch", s, now=NOW)
    assert r.payload["reminder"]["local_time"] == "2:54 PM"
    assert len(RC.handle(uid, "what are my reminders", s, now=NOW).payload["reminders"]) == 2
    s.close()


def test_no_clock_time_falls_through_to_existing_task_flow(c, uid):
    s = db()
    assert RC.handle(uid, "remind me to submit the report tomorrow", s, now=NOW) is None
    assert RC.handle(uid, "hello", s, now=NOW) is None
    s.close()


def test_answer_does_not_hijack_commands_and_cancel_works(c, uid):
    s = db()
    RC.handle(uid, "remind me at 6pm", s, now=NOW)
    assert RC.handle(uid, "add task revise paging", s, now=NOW) is None
    assert RC.handle(uid, "What should I do today?", s, now=NOW) is None
    assert "won't set" in RC.handle(uid, "never mind", s, now=NOW).reply
    assert RC.handle(uid, "gym", s, now=NOW) is None                             # nothing awaiting any more
    s.close()


def test_stale_awaiting_is_ignored(c, uid):
    s = db()
    RC.handle(uid, "remind me at 6pm", s, now=NOW)
    assert RC.handle(uid, "gym", s, now=NOW + timedelta(minutes=30)) is None
    s.close()


def test_time_passes_while_asking_rolls_to_next_day(c, uid):
    s = db()
    RC.handle(uid, "remind me at 2 40pm", s, now=NOW)
    r = RC.handle(uid, "lab record", s, now=NOW + timedelta(minutes=10))        # 14:44, after 14:40
    assert r.payload["reminder"]["local_day"] == "tomorrow"
    s.close()


# ---------------------------------------------------------------- through the real chat endpoint
def test_jarvis_chat_endpoint_sets_reminder(c, uid):
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "remind me in 30 minutes to drink water"}).json()
    assert r["action"] == "reminder" and "drink water" in r["reply"].lower()
    lst = c.get("/v1/reminders", params={"user_id": uid}).json()
    assert len(lst) == 1 and lst[0]["title"].lower() == "drink water"
    acts = c.get("/v1/actions", params={"user_id": uid}).json()
    assert any(a["intent"] == "create_reminder" and a["status"] == "executed" for a in acts)     # typed + audited


def test_chat_two_step_via_endpoint(c, uid):
    a = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "Remind me in 15 minutes"}).json()
    assert a["reply"].startswith("What should I remind you about at")
    b = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "I have a data structure record"}).json()
    assert b["action"] == "reminder" and b["reply"].startswith("Done")


# ---------------------------------------------------------------- notifications API, done/snooze
def test_notifications_inbox_done_and_snooze(c, uid):
    rid = c.post("/v1/reminders", json={"user_id": uid, "title": "Call mom", "in_minutes": 1}).json()["id"]
    s = db(); s.query(D.Reminder).filter(D.Reminder.id == rid).update({"remind_at": datetime.utcnow() - timedelta(seconds=5)}); s.commit(); s.close()
    inbox = c.get("/v1/notifications", params={"user_id": uid, "undelivered": True}).json()      # poll triggers catch-up firing
    assert len(inbox) == 1 and inbox[0]["data"]["reminder_id"] == rid and "Call mom" in inbox[0]["body"]
    nid = inbox[0]["id"]
    assert c.post(f"/v1/notifications/{nid}/delivered", json={"user_id": uid}).json()["delivered"]
    assert c.get("/v1/notifications", params={"user_id": uid, "undelivered": True}).json() == []
    sn = c.post(f"/v1/reminders/{rid}/snooze", json={"user_id": uid, "minutes": 10}).json()
    assert sn["status"] == "pending" and sn["snooze_count"] == 1
    assert c.post(f"/v1/reminders/{rid}/done", json={"user_id": uid}).json()["status"] == "done"
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.post(f"/v1/reminders/{rid}/done", json={"user_id": other}).status_code == 404
    assert c.get("/v1/notifications", params={"user_id": other}).json() == []


def test_reminder_create_validation(c, uid):
    assert c.post("/v1/reminders", json={"user_id": uid, "title": "x"}).status_code == 422
    r = c.post("/v1/reminders", json={"user_id": uid, "title": "Lab", "at": "2030-01-01T09:00:00"}).json()      # naive = user's local time
    assert r["local_time"] == "9:00 AM"


# ---------------------------------------------------------------- daily plan notification
def seed_exam(uid):
    s = db()
    sem = D.Semester(user_id=uid, is_current=True, daily_study_minutes=180); s.add(sem); s.flush()
    co = D.Course(user_id=uid, semester_id=sem.id, name="Operating Systems"); s.add(co); s.flush()
    s.add(D.Exam(user_id=uid, course_id=co.id, exam_date=date.today() + timedelta(days=5), weightage=100, status="confirmed"))
    for i in range(3):
        s.add(D.Topic(course_id=co.id, name=f"Topic {i}", estimated_minutes=45, difficulty=4, exam_weightage=25, confidence=1))
    s.commit(); s.close()


def test_daily_plan_notification_contains_the_brief(c, uid):
    seed_exam(uid)
    r = c.put("/v1/notifications/settings", json={"user_id": uid, "daily_brief": True, "daily_brief_time": "07:30"}).json()
    assert r["daily_brief"] == {"enabled": True, "time": "07:30"}
    s = db()
    row = s.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "daily_brief", D.Reminder.status == "pending").one()
    due = row.remind_at
    RM.fire_due(s, due + timedelta(minutes=1))
    n = s.query(D.Notification).filter(D.Notification.user_id == uid, D.Notification.kind == "daily_brief").one()
    assert n.title == "Today's plan" and "Start with" in n.body and n.link.startswith("briefs.html?brief=brf_")
    brief = c.get(f"/v1/briefs/{n.data['brief_id']}", params={"user_id": uid}).json()
    assert brief["type"] == "daily_plan"
    # repeats tomorrow at the same local time
    row = s.query(D.Reminder).filter(D.Reminder.id == row.id).one()
    assert row.status == "pending" and row.remind_at == due + timedelta(days=1)
    s.close()


def test_stale_daily_plan_is_skipped_not_sent_at_night(c, uid):
    seed_exam(uid)
    c.put("/v1/notifications/settings", json={"user_id": uid, "daily_brief": True, "daily_brief_time": "07:30"})
    s = db()
    row = s.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "daily_brief", D.Reminder.status == "pending").one()
    before = row.remind_at
    RM.fire_due(s, before + timedelta(hours=9))                                     # host was asleep until 4:30pm
    assert s.query(D.Notification).filter(D.Notification.user_id == uid).count() == 0
    s.refresh(row)
    assert row.status == "pending" and row.remind_at > before                          # rolled forward to the next morning
    s.close()


def test_chat_sets_and_stops_the_daily_plan(c, uid):
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "send me my plan every morning at 7:30am"}).json()
    assert r["action"] == "reminder" and "7:30 AM" in r["reply"]
    assert c.get("/v1/notifications/settings", params={"user_id": uid}).json()["daily_brief"] == {"enabled": True, "time": "07:30"}
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "stop the daily plan notification"}).json()
    assert "stop" in r["reply"].lower() and c.get("/v1/notifications/settings", params={"user_id": uid}).json()["daily_brief"]["enabled"] is False


def test_changing_time_zone_keeps_local_time(c, uid):
    c.put("/v1/notifications/settings", json={"user_id": uid, "daily_brief": True, "daily_brief_time": "07:30"})
    s = c.put("/v1/notifications/settings", json={"user_id": uid, "tz_offset_min": 0}).json()
    assert s["daily_brief"]["time"] == "07:30" and s["tz_offset_min"] == 0


# ---------------------------------------------------------------- push + tick
def test_push_disabled_by_default(c, uid):
    assert c.get("/v1/push/key").json()["enabled"] is False
    assert c.post("/v1/push/subscribe", json={"user_id": uid, "endpoint": "https://push.example/x", "keys": {"p256dh": "a", "auth": "b"}}).json()["subscribed"]


def test_push_is_called_when_enabled(c, uid, monkeypatch):
    import push
    sent = []
    monkeypatch.setattr(push, "enabled", lambda: True)
    monkeypatch.setattr(push, "send", lambda db_, u, n: sent.append((u, n.title)) or 1)
    rid = c.post("/v1/reminders", json={"user_id": uid, "title": "Ping", "in_minutes": 1}).json()["id"]
    s = db(); RM.fire_due(s, datetime.utcnow() + timedelta(minutes=2)); s.close()
    assert sent == [(uid, "Reminder due")]
