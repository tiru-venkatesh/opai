"""Refinement plan: typed intents, one chat contract, timezones, durable scheduling, payload binding, observability.
Run: cd backend && python -m pytest tests/test_refinement.py -q"""
import os, re, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"; os.environ["GROQ_API_KEY"] = ""; os.environ["OPAI_SCHEDULER"] = "0"
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import action_service as A
import database as D
import push
import reminders as RM
from agent import intents as I
from agent import reminder_chat as RC

IST = timedelta(minutes=330)
FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")


def utc(y, mo, d, h, mi=0, s=0):
    """IST wall-clock -> naive UTC."""
    return datetime(y, mo, d, h, mi, s) - IST


NOW = utc(2026, 10, 7, 14, 34)


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    assert c.put("/v1/notifications/settings", json={"user_id": u, "timezone": "Asia/Kolkata"}).status_code == 200
    return u


def db():
    return D.SessionLocal()


def mk_reminder(c, uid, title="Call mom", due=None, repeat="none"):
    rid = c.post("/v1/reminders", json={"user_id": uid, "title": title, "in_minutes": 5, "repeat": repeat}).json()["id"]
    due = due or datetime.utcnow() - timedelta(seconds=5)
    s = db(); s.query(D.Reminder).filter(D.Reminder.id == rid).update({"remind_at": due}); s.commit(); s.close()
    return rid


def notifs(uid, kind=None):
    s = db(); q = s.query(D.Notification).filter(D.Notification.user_id == uid)
    n = (q.filter(D.Notification.kind == kind) if kind else q).all(); s.close(); return n


# ================================================================= intents
def test_registry_is_closed_and_declares_contracts():
    with pytest.raises(KeyError):
        I.build("drop_database", 1.0, {}, "api")
    d = I.REGISTRY["create_reminder"]
    assert d.required == ("title", "due_at") and d.risk == "low" and "whatsapp" in d.channels and not d.confirmation_required
    assert I.REGISTRY["approve_action"].risk == "high" and I.REGISTRY["approve_action"].confirmation_required
    for name in ("complete_reminder", "snooze_reminder", "stop_daily_plan", "enable_daily_plan", "generate_daily_brief", "generate_exam_brief", "generate_dsa_brief",
                 "create_task", "create_project", "create_application", "draft_outreach", "approve_action", "reject_action", "weekly_review", "recovery_plan", "decision_support"):
        assert name in I.REGISTRY


def test_missing_title_is_a_clarification_not_a_guess(c, uid):
    s = db()
    it = I.resolve(s, uid, "Remind me at 2:40 PM", "web_chat", now=NOW)
    assert it.name == "create_reminder" and it.missing_fields == ["title"] and it.entities["due_at"] == "2026-10-07T09:10:00Z" and it.risk == "low"
    full = I.resolve(s, uid, "remind me to submit the record at 5 PM", "web_chat", now=NOW)
    assert full.missing_fields == [] and full.entities["title"] == "Submit the record"
    s.close()


@pytest.mark.parametrize("text,name", [
    ("What should I do today?", "generate_daily_brief"), ("I only have one hour", "generate_daily_brief"), ("weekly review", "weekly_review"),
    ("I missed yesterday's session", "recovery_plan"), ("what needs my approval", "show_approvals"), ("Should I take the gig?", "decision_support"),
    ("how ready am I for my exam", "generate_exam_brief"), ("dsa today", "generate_dsa_brief"), ("send me my plan every morning at 7:30", "enable_daily_plan"),
    ("stop the daily plan", "stop_daily_plan"), ("add task Submit the DS record", "create_task"), ("create a project Alpha", "create_project"),
    ("what is a deadlock", "general_chat")])
def test_intent_routing_table(c, uid, text, name):
    s = db(); assert I.resolve(s, uid, text, "web_chat", now=NOW).name == name; s.close()


# ================================================================= one chat contract
def test_chat_contract_needs_input_then_completed_with_actions(c, uid):
    a = c.post("/v1/chat", json={"user_id": uid, "text": "Remind me in 25 minutes", "channel": "popup", "timezone": "Asia/Kolkata"}).json()
    assert a["status"] == "needs_input" and a["intent"] == "create_reminder" and a["next_input"] == {"field": "title", "question": "What should I remind you about?"}
    assert a["reply"].startswith("What should I remind you about at") and a["actions"] == [] and a["brief"] is None and a["request_id"].startswith("req_")
    b = c.post("/v1/chat", json={"user_id": uid, "text": "Submit the data structures record", "conversation_id": a["conversation_id"]}).json()
    assert b["status"] == "completed" and b["intent"] == "create_reminder" and b["reply"].startswith("Done - I'll remind you today at") and b["conversation_id"] == a["conversation_id"]
    assert b["brief_id"].startswith("brf_") and b["brief"]["type"] == "reminder"
    types = [x["type"] for x in b["actions"]]
    assert types[:2] == ["complete_reminder", "snooze_reminder"] and types[-1] == "open_brief"
    done = b["actions"][0]
    assert done["id"] == done["action_id"] and done["brief_id"] == b["brief_id"] and done["requires_approval"] is False
    r = c.post(f"/v1/actions/{done['id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed"
    assert c.get("/v1/reminders", params={"user_id": uid, "status": "done"}).json()[0]["title"].lower().startswith("submit")


def test_chat_task_followup_is_never_swallowed_as_a_reminder_title(c, uid):
    a = c.post("/v1/chat", json={"user_id": uid, "text": "Remind me in 40 minutes"}).json()
    assert a["status"] == "needs_input"
    t = c.post("/v1/chat", json={"user_id": uid, "text": "add task Submit the DS record"}).json()
    assert t["intent"] == "create_task"
    assert any("submit the ds record" in x["title"].lower() for x in c.get("/v1/tasks", params={"user_id": uid}).json())
    assert c.get("/v1/reminders", params={"user_id": uid}).json() == []                                       # no reminder was created from it
    s = db(); assert s.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.status == "awaiting_text").count() == 1; s.close()


def test_chat_brief_response_has_preview_and_same_action_schema(c, uid):
    s = db()
    sem = D.Semester(user_id=uid, is_current=True, daily_study_minutes=180); s.add(sem); s.flush()
    co = D.Course(user_id=uid, semester_id=sem.id, name="Operating Systems"); s.add(co); s.flush()
    s.add(D.Exam(user_id=uid, course_id=co.id, exam_date=date.today() + timedelta(days=5), weightage=100, status="confirmed"))
    for i in range(3):
        s.add(D.Topic(course_id=co.id, name=f"Deadlocks {i}", estimated_minutes=45, difficulty=4, exam_weightage=25, confidence=1))
    s.commit(); s.close()
    r = c.post("/v1/chat", json={"user_id": uid, "text": "What should I do today?", "channel": "popup"}).json()
    assert r["intent"] == "generate_daily_brief" and r["status"] == "completed" and r["brief"]["priorities"][0]["rank"] == 1 and len(r["brief"]["priorities"]) <= 3
    first = r["actions"][0]
    assert first["type"] == "start_focus" and first["id"].startswith("act_") and first["brief_id"] == r["brief_id"]
    assert any(a["type"] == "open_brief" and a["client_only"] for a in r["actions"])
    assert c.post(f"/v1/actions/{first['id']}/execute", json={"user_id": uid}).json()["status"] == "executed"   # popup uses the SAME endpoint as briefs.html
    full = c.get(f"/v1/briefs/{r['brief_id']}", params={"user_id": uid}).json()
    assert {a["id"] for a in full["actions"]} >= {first["id"]}


def test_chat_validates_input_and_user(c, uid):
    assert c.post("/v1/chat", json={"user_id": uid, "text": ""}).status_code == 422
    assert c.post("/v1/chat", json={"user_id": uid, "text": "hi", "channel": "fax"}).status_code == 422
    assert c.post("/v1/chat", json={"user_id": "nope", "text": "hi"}).status_code == 404


def test_chat_daily_plan_intents_and_unknown_timezone_ignored(c, uid):
    on = c.post("/v1/chat", json={"user_id": uid, "text": "send me my plan every morning at 7:30", "timezone": "Not/AZone"}).json()
    assert on["intent"] == "enable_daily_plan" and "7:30 AM" in on["reply"] and on["data"]["daily_brief"]["enabled"]
    off = c.post("/v1/chat", json={"user_id": uid, "text": "stop the daily plan"}).json()
    assert off["intent"] == "stop_daily_plan" and off["data"]["daily_brief"]["enabled"] is False
    assert c.get("/v1/preferences/notifications", params={"user_id": uid}).json()["timezone"] == "Asia/Kolkata"


# ================================================================= time zones
def test_ist_input_utc_storage_ist_display_on_a_utc_server(c, uid):
    s = db()
    r = RC.handle(uid, "Remind me at 2:40 PM to call mom", s, now=NOW)
    rem = r.payload["reminder"]
    assert rem["at_utc"] == "2026-10-07T09:10:00Z" and rem["local_time"] == "2:40 PM" and rem["local_day"] == "today" and rem["timezone"] == "Asia/Kolkata"
    row = s.query(D.Reminder).filter(D.Reminder.id == rem["id"]).one()
    assert row.remind_at == datetime(2026, 10, 7, 9, 10)                                                       # stored as UTC
    s.close()


def test_user_zone_differs_from_server_zone(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": u, "timezone": "America/Los_Angeles"})
    s = db()
    r = RC.handle(u, "remind me at 9am to call", s, now=datetime(2026, 10, 7, 20, 0))            # 1pm PDT
    assert r.payload["reminder"]["at_utc"] == "2026-10-08T16:00:00Z" and r.payload["reminder"]["local_day"] == "tomorrow"
    s.close()


def test_tomorrow_across_midnight(c, uid):
    s = db()
    r = RC.handle(uid, "remind me in 20 minutes to stretch", s, now=utc(2026, 10, 7, 23, 50))
    assert r.payload["reminder"]["local_day"] == "tomorrow" and r.payload["reminder"]["local_time"] == "12:10 AM"
    r = RC.handle(uid, "remind me tomorrow at 7am to run", s, now=utc(2026, 10, 7, 23, 50))
    assert r.payload["reminder"]["at_utc"] == "2026-10-08T01:30:00Z"
    s.close()


def test_daily_recurrence_keeps_local_wall_time_across_dst_change(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": u, "timezone": "America/New_York"})
    s = db(); fn = RM.offset_fn(s, u)
    old = datetime(2026, 10, 31, 11, 30)                                                                      # 07:30 EDT
    nxt = RM._advance_daily(old, old + timedelta(minutes=1), fn)
    assert nxt == datetime(2026, 11, 1, 12, 30)                                                               # 07:30 EST (DST ended 2:00am)
    assert RM.to_local(nxt, fn(nxt)).strftime("%H:%M") == "07:30"
    spring = RM._advance_daily(datetime(2027, 3, 13, 12, 30), datetime(2027, 3, 13, 12, 31), fn)              # 07:30 EST -> 07:30 EDT
    assert spring == datetime(2027, 3, 14, 11, 30)
    s.close()


def test_wall_time_in_a_dst_zone_is_parsed_with_the_offset_at_that_instant(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": u, "timezone": "America/New_York"})
    s = db(); fn = RM.offset_fn(s, u)
    now = datetime(2026, 10, 31, 20, 0)                                                                       # still EDT
    w = RM.parse_when("remind me tomorrow at 7am", now, fn(now), fn)
    assert w["at_utc"] == datetime(2026, 11, 1, 12, 0)                                                        # 7am EST, not 7am EDT
    s.close()


def test_invalid_timezone_rejected_and_fixed_offset_still_supported(c, uid):
    assert c.put("/v1/notifications/settings", json={"user_id": uid, "timezone": "Mars/Base"}).status_code == 422
    r = c.put("/v1/notifications/settings", json={"user_id": uid, "tz_offset_min": 0}).json()
    assert r["timezone"] is None and r["tz_offset_min"] == 0


def test_daily_plan_time_survives_a_timezone_change(c, uid):
    c.put("/v1/notifications/settings", json={"user_id": uid, "daily_brief": True, "daily_brief_time": "07:30"})
    r = c.put("/v1/notifications/settings", json={"user_id": uid, "timezone": "Europe/London"}).json()
    assert r["daily_brief"] == {"enabled": True, "time": "07:30"}


# ================================================================= scheduler
def test_one_second_before_and_after_due(c, uid):
    due = datetime(2030, 1, 1, 9, 0, 0)
    rid = mk_reminder(c, uid, due=due)
    s = db()
    RM.fire_due(s, due - timedelta(seconds=1), user_id=uid); assert notifs(uid) == []
    RM.fire_due(s, due + timedelta(seconds=1), user_id=uid); assert len(notifs(uid)) == 1
    s.close()


def test_claimed_once_and_duplicate_ticks_are_idempotent(c, uid):
    mk_reminder(c, uid)
    s = db()
    first = RM.fire_due(s, user_id=uid); second = RM.fire_due(s, user_id=uid); third = RM.fire_due(s, user_id=uid)
    assert (first, second, third) == (1, 0, 0) and len(notifs(uid)) == 1
    s.close()


def test_idempotency_key_blocks_a_replayed_occurrence(c, uid):
    s = db()
    key = f"reminder_due:replay:{NOW.isoformat()}"
    assert RM._notify(s, uid, "reminder", "t", "b", "today.html", {}, None, key) is not None
    assert RM._notify(s, uid, "reminder", "t", "b", "today.html", {}, None, key) is None                     # worker retry / restart replay
    assert len([n for n in notifs(uid) if n.idempotency_key == key]) == 1
    s.close()


def test_two_users_are_isolated(c, uid):
    other = c.post("/v1/auth/guest").json()["user_id"]
    mk_reminder(c, uid, "mine"); mk_reminder(c, other, "theirs")
    s = db(); RM.fire_due(s, user_id=uid)
    assert len(notifs(uid)) == 1 and notifs(other) == []
    RM.fire_due(s, user_id=other)
    assert len(notifs(other)) == 1 and "theirs" in notifs(other)[0].body and "mine" in notifs(uid)[0].body
    assert c.get("/v1/notifications", params={"user_id": other}).json()[0]["body"].count("mine") == 0
    s.close()


def test_completed_reminder_is_not_sent_again_and_snooze_changes_due_time(c, uid):
    rid = mk_reminder(c, uid, due=datetime.utcnow() + timedelta(minutes=30))
    before = datetime.utcnow()
    sn = c.post(f"/v1/reminders/{rid}/snooze", json={"user_id": uid, "minutes": 10}).json()
    s = db(); row = s.query(D.Reminder).filter(D.Reminder.id == rid).one()
    assert row.remind_at < before + timedelta(minutes=11) and row.snoozed_until == row.remind_at and sn["snooze_count"] == 1
    assert c.post(f"/v1/reminders/{rid}/complete", json={"user_id": uid}).json()["completed_at"]
    RM.fire_due(s, datetime.utcnow() + timedelta(hours=1), user_id=uid)
    assert notifs(uid) == []
    s.close()


def test_recurring_reminder_creates_next_occurrence(c, uid):
    rid = mk_reminder(c, uid, "Water", repeat="daily")
    s = db(); before = s.query(D.Reminder).filter(D.Reminder.id == rid).one().remind_at
    RM.fire_due(s, user_id=uid)
    after = s.query(D.Reminder).filter(D.Reminder.id == rid).one()                                            # re-read AFTER the tick
    assert after.status == "pending" and after.remind_at > before and after.remind_at > datetime.utcnow()
    assert len(notifs(uid)) == 1
    s.close()


def test_failed_push_is_retried_then_succeeds_and_gone_endpoints_are_removed(c, uid, monkeypatch):
    monkeypatch.setattr(push, "enabled", lambda: True)
    calls = {"n": 0}

    def flaky(sub, data):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("push service unavailable")
    monkeypatch.setattr(push, "_send_webpush", flaky)
    c.post("/v1/push/subscribe", json={"user_id": uid, "endpoint": "https://push.example/ok", "keys": {"p256dh": "a", "auth": "b"}})
    mk_reminder(c, uid)
    s = db(); t0 = datetime.utcnow()
    RM.fire_due(s, t0, user_id=uid)
    d = s.query(D.NotificationDelivery).filter(D.NotificationDelivery.user_id == uid).one()
    assert d.status == "failed" and d.attempts == 1 and d.next_retry_at > t0 and "unavailable" in d.error
    RM.fire_due(s, t0 + timedelta(seconds=10), user_id=uid); s.refresh(d); assert d.attempts == 1               # not due yet
    RM.fire_due(s, t0 + timedelta(minutes=2), user_id=uid); s.refresh(d)
    assert d.status == "ok" and d.attempts == 2 and d.delivered_at
    # gone endpoint: unsubscribed
    monkeypatch.setattr(push, "_send_webpush", lambda sub, data: (_ for _ in ()).throw(push.PushGone("410")))
    mk_reminder(c, uid, "again")
    RM.fire_due(s, user_id=uid)
    assert s.query(D.PushSubscription).filter(D.PushSubscription.user_id == uid).count() == 0
    assert s.query(D.NotificationDelivery).filter(D.NotificationDelivery.status == "gone", D.NotificationDelivery.user_id == uid).count() == 1
    s.close()


def test_push_retries_stop_after_max_attempts_and_after_user_saw_it(c, uid, monkeypatch):
    monkeypatch.setattr(push, "enabled", lambda: True)
    monkeypatch.setattr(push, "_send_webpush", lambda sub, data: (_ for _ in ()).throw(RuntimeError("down")))
    c.post("/v1/push/subscribe", json={"user_id": uid, "endpoint": "https://push.example/down", "keys": {"p256dh": "a", "auth": "b"}})
    mk_reminder(c, uid)
    s = db(); t = datetime.utcnow()
    RM.fire_due(s, t, user_id=uid)
    for i in range(1, 6):
        RM.fire_due(s, t + timedelta(minutes=20 * i), user_id=uid)
    d = s.query(D.NotificationDelivery).filter(D.NotificationDelivery.user_id == uid).one()
    assert d.status == "failed" and d.attempts == push.MAX_ATTEMPTS and d.next_retry_at is None
    s.close()


def test_stale_morning_plan_never_sent_at_night_and_not_duplicated(c, uid):
    c.put("/v1/notifications/settings", json={"user_id": uid, "daily_brief": True, "daily_brief_time": "07:30"})
    s = db()
    row = s.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "daily_brief", D.Reminder.status == "pending").one()
    due = row.remind_at
    RM.fire_due(s, due + timedelta(hours=7), user_id=uid)
    assert notifs(uid, "daily_brief") == []
    nxt = s.query(D.Reminder).filter(D.Reminder.id == row.id).one().remind_at
    RM.fire_due(s, nxt + timedelta(hours=1), user_id=uid); RM.fire_due(s, nxt + timedelta(hours=1), user_id=uid)
    n = notifs(uid, "daily_brief")
    assert len(n) == 1 and n[0].idempotency_key.startswith(f"daily_plan:{uid}:")
    s.close()


# ================================================================= system endpoints
def test_tick_requires_a_secret_and_status_endpoints(c, uid, monkeypatch):
    monkeypatch.delenv("OPAI_TICK_SECRET", raising=False)
    assert c.post("/v1/system/tick").status_code == 503 and c.get("/v1/system/scheduler-status").status_code == 503
    monkeypatch.setenv("OPAI_TICK_SECRET", "s3cret")
    assert c.post("/v1/system/tick").status_code == 403 and c.post("/v1/system/tick", headers={"x-tick-secret": "nope"}).status_code == 403
    assert c.post("/v1/system/tick", headers={"x-tick-secret": "s3cret"}).json()["fired"] >= 0
    st = c.get("/v1/system/scheduler-status", headers={"x-tick-secret": "s3cret"}).json()
    assert st["ticks"] >= 1 and st["last_tick_at"] and "pending_due" in st and "oldest_due_lag_s" in st and "failed_deliveries" in st
    h = c.get("/v1/system/health").json()
    assert h["status"] == "ok" and h["tick_configured"] and "scheduler_tick" in h["events"]


def test_observability_events_are_counted(c, uid):
    c.post("/v1/chat", json={"user_id": uid, "text": "Remind me in 15 minutes to stretch"})
    ev = c.get("/v1/system/health").json()["events"]
    for name in ("intent_classified", "reminder_created", "brief_created", "action_proposed", "action_executed"):
        assert ev.get(name, 0) >= 1, name


def test_reminder_patch_and_validation(c, uid):
    rid = c.post("/v1/reminders", json={"user_id": uid, "title": "Lab", "at": "2030-01-01T09:00:00"}).json()["id"]
    p = c.patch(f"/v1/reminders/{rid}", json={"user_id": uid, "title": "Lab record", "at": "2030-01-01T10:30:00"}).json()
    assert p["title"] == "Lab record" and p["local_time"] == "10:30 AM"
    c.post(f"/v1/reminders/{rid}/complete", json={"user_id": uid})
    assert c.patch(f"/v1/reminders/{rid}", json={"user_id": uid, "title": "x"}).status_code == 409
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.patch(f"/v1/reminders/{rid}", json={"user_id": other, "title": "x"}).status_code == 404


def test_daily_plan_preference_endpoints(c, uid):
    on = c.post("/v1/preferences/daily-plan", json={"user_id": uid, "time": "06:45", "timezone": "Asia/Kolkata"}).json()
    assert on["daily_brief"] == {"enabled": True, "time": "06:45"}
    assert c.post("/v1/preferences/daily-plan", json={"user_id": uid, "time": "25:00"}).status_code == 422
    off = c.delete("/v1/preferences/daily-plan", params={"user_id": uid}).json()
    assert off["daily_brief"]["enabled"] is False
    s = db(); assert s.query(D.Reminder).filter(D.Reminder.user_id == uid, D.Reminder.kind == "daily_brief", D.Reminder.status == "pending").count() == 0; s.close()


# ================================================================= brief integrity + approval binding
def _daily_with_exam(c, uid):
    s = db()
    sem = D.Semester(user_id=uid, is_current=True, daily_study_minutes=180); s.add(sem); s.flush()
    co = D.Course(user_id=uid, semester_id=sem.id, name="OS"); s.add(co); s.flush()
    s.add(D.Exam(user_id=uid, course_id=co.id, exam_date=date.today() + timedelta(days=5), weightage=100, status="confirmed"))
    for i in range(3):
        s.add(D.Topic(course_id=co.id, name=f"T{i}", estimated_minutes=45, difficulty=4, exam_weightage=25, confidence=1))
    s.commit(); s.close()
    return c.post("/v1/briefs/daily", json={"user_id": uid}).json()


def test_tampered_action_payload_is_refused(c, uid):
    b = _daily_with_exam(c, uid)
    act = b["priorities"][0]["actions"][0]
    s = db(); row = s.query(D.BriefAction).filter(D.BriefAction.id == act["id"]).one()
    row.payload = dict(row.payload, ref_id="someone-elses-block"); s.commit(); s.close()
    r = c.post(f"/v1/actions/{act['id']}/execute", json={"user_id": uid})
    assert r.status_code == 409 and "changed" in r.json()["detail"]


def test_unknown_action_and_expired_brief(c, uid):
    assert c.post("/v1/actions/act_nope/execute", json={"user_id": uid}).status_code == 404
    b = _daily_with_exam(c, uid)
    s = db(); s.query(D.Brief).filter(D.Brief.id == b["brief_id"]).update({"expires_at": datetime.utcnow() - timedelta(minutes=1)}); s.commit(); s.close()
    ex = b["priorities"][0]["actions"][0]
    r = c.post(f"/v1/actions/{ex['id']}/execute", json={"user_id": uid})
    assert r.status_code == 409 and "expired" in r.json()["detail"]
    assert c.post(f"/v1/actions/{ex['id']}/confirm", json={"user_id": uid}).status_code == 409


def test_medium_risk_confirm_endpoint(c, uid):
    c.post("/v1/dsa/plan", json={"user_id": uid})
    b = c.post("/v1/briefs/dsa", json={"user_id": uid}).json()
    pause = [a for a in b["actions"] if a["type"] == "pause_dsa"][0]
    assert pause["requires_confirmation"] and pause["risk"] == "medium" and pause["requires_approval"] is False
    assert c.post(f"/v1/actions/{pause['id']}/execute", json={"user_id": uid}).json()["status"] == "needs_confirmation"
    assert c.post(f"/v1/actions/{pause['id']}/confirm", json={"user_id": uid}).json()["status"] == "executed"


def _propose_email(c, uid, to="prof@iit.ac.in"):
    return c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": {"to": to, "subject": "Hi", "body": "Hello professor."}}).json()


def test_high_risk_always_needs_approval_bound_to_the_exact_payload(c, uid):
    p = _propose_email(c, uid)
    assert p["status"] == "pending_approval" and p["requires_approval"] is True
    assert c.get("/v1/outbox", params={"user_id": uid}).json() == []
    h = A.payload_hash(p["payload"])
    assert c.post(f"/v1/actions/{p['action_id']}/approve", json={"user_id": uid}).status_code == 428           # "approve" must name the version reviewed
    s = db(); rec = s.query(D.ActionRecord).filter(D.ActionRecord.id == p["action_id"]).one()
    rec.payload_json = dict(rec.payload_json, to="attacker@evil.com"); s.commit(); s.close()                    # recipient silently changed
    r = c.post(f"/v1/actions/{p['action_id']}/approve", json={"user_id": uid, "payload_hash": h})
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    assert c.get("/v1/outbox", params={"user_id": uid}).json() == []


def test_approval_is_single_use(c, uid):
    p = _propose_email(c, uid)
    h = A.payload_hash(p["payload"])
    assert c.post(f"/v1/actions/{p['action_id']}/approve", json={"user_id": uid, "payload_hash": h}).json()["status"] == "executed"
    assert c.post(f"/v1/actions/{p['action_id']}/approve", json={"user_id": uid, "payload_hash": h}).status_code == 409
    assert len(c.get("/v1/outbox", params={"user_id": uid}).json()) == 1


def test_approval_brief_requires_the_hash_too(c, uid):
    p = _propose_email(c, uid)
    b = c.post("/v1/briefs/approval", json={"user_id": uid}).json()
    it = b["approval_items"][0]
    appr = [a for a in b["actions"] if a["type"] == "approve"][0]
    assert appr["requires_approval"] is True and it["payload_hash"] == A.payload_hash(p["payload"])
    assert c.post(f"/v1/actions/{appr['id']}/approve", json={"user_id": uid}).status_code == 428
    assert c.post(f"/v1/actions/{appr['id']}/approve", json={"user_id": uid, "payload_hash": it["payload_hash"]}).json()["status"] == "executed"


def test_all_brief_types_share_one_action_shape(c, uid):
    _daily_with_exam(c, uid)
    briefs = [c.post("/v1/briefs/exam", json={"user_id": uid}).json(), c.post("/v1/briefs/weekly", json={"user_id": uid}).json(),
              c.post("/v1/briefs/recovery", json={"user_id": uid}).json(), c.post("/v1/briefs/approval", json={"user_id": uid}).json(),
              c.post("/v1/briefs/decision", json={"user_id": uid, "question": "Should I join the club?"}).json(),
              c.post("/v1/briefs/dsa", json={"user_id": uid}).json()]
    for b in briefs:
        for a in b["actions"]:
            assert {"id", "action_id", "brief_id", "type", "label", "risk", "kind", "status", "requires_confirmation", "requires_approval"} <= set(a)
            assert a["id"] == a["action_id"] and a["brief_id"] == b["brief_id"]


# ================================================================= frontend safety
def test_frontend_never_injects_api_strings_as_html_in_briefs_page():
    src = open(os.path.join(FRONTEND, "briefs.html"), encoding="utf-8").read()
    assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write|eval\(|new Function", src)
    assert "function safeUrl" in src and "textContent" in src
    for state in ("Retry", "offline", "Loading", "out of date", "Nothing needs your attention", "Why this"):
        assert state.lower() in src.lower(), state


def test_popup_uses_chat_contract_and_safe_navigation():
    src = open(os.path.join(FRONTEND, "karna-popup.js"), encoding="utf-8").read()
    assert "/v1/chat" in src and "/v1/actions/" in src and "safeUrl" in src and "/execute" in src and "/confirm" in src


# ================================================================= simulated-clock integration (real tick, real endpoints)
def test_integration_reminder_to_notification_to_brief_to_done(c, uid, monkeypatch):
    monkeypatch.setenv("OPAI_TICK_SECRET", "tick")
    a = c.post("/v1/chat", json={"user_id": uid, "text": "Remind me in 30 minutes", "timezone": "Asia/Kolkata"}).json()
    b = c.post("/v1/chat", json={"user_id": uid, "text": "I have a work data structure record"}).json()
    rid = b["data"]["reminder"]["id"]
    s = db(); s.query(D.Reminder).filter(D.Reminder.id == rid).update({"remind_at": datetime.utcnow() - timedelta(seconds=3)}); s.commit(); s.close()   # clock reaches due time
    assert c.post("/v1/system/tick", headers={"x-tick-secret": "tick"}).json()["fired"] >= 1
    inbox = c.get("/v1/notifications", params={"user_id": uid, "undelivered": True}).json()
    n = inbox[0]
    assert n["title"] == "Reminder due" and "record" in n["body"].lower() and n["data"]["actions"] == ["done", "snooze"]
    brief_id = re.search(r"brief=(brf_\w+)", n["link"]).group(1)                                                    # open the brief URL
    brief = c.get(f"/v1/briefs/{brief_id}", params={"user_id": uid}).json()
    done = [x for x in brief["priorities"][0]["actions"] if x["type"] == "complete_reminder"][0]
    assert c.post(f"/v1/actions/{done['id']}/execute", json={"user_id": uid}).json()["status"] == "executed"        # click Done
    assert c.get("/v1/reminders", params={"user_id": uid, "status": "done"}).json()[0]["id"] == rid
    assert c.post(f"/v1/notifications/{n['id']}/read", json={"user_id": uid}).json()["read"]
    assert c.post("/v1/system/tick", headers={"x-tick-secret": "tick"}).json()["fired"] == 0                       # nothing more is sent


@pytest.mark.parametrize("text,hhmm", [("send me my plan every morning at 7:30", "07:30"), ("send me my plan every morning at 7:30am", "07:30"),
                                       ("send me my plan every evening at 7", "19:00"), ("send me my plan every day at 6:15 pm", "18:15"),
                                       ("send me my plan every morning at 19:30", "19:30")])
def test_daily_plan_time_uses_daypart_words(c, uid, text, hhmm):
    s = db()
    assert RC._hhmm(text.lower(), datetime(2026, 10, 7, 9, 4), RM.offset_fn(s, uid)) == hhmm
    s.close()
