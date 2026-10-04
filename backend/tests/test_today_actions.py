"""Phase 1: Today engine + typed actions. Run: cd backend && python -m pytest tests -q"""
import os, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import database as D
import today_engine as T

D1 = lambda n: date.today() + timedelta(days=n)


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    return c.post("/v1/auth/guest").json()["user_id"]


def db():
    return D.SessionLocal()


def seed_exam(uid, days=5, n_topics=4):
    s = db()
    sem = D.Semester(user_id=uid, is_current=True, daily_study_minutes=180); s.add(sem); s.flush()
    co = D.Course(user_id=uid, semester_id=sem.id, name="Operating Systems", code="CS301"); s.add(co); s.flush()
    ex = D.Exam(user_id=uid, course_id=co.id, exam_date=D1(days), weightage=100, status="confirmed"); s.add(ex)
    for i in range(n_topics):
        s.add(D.Topic(course_id=co.id, name=f"Topic {i}", estimated_minutes=45, difficulty=4, exam_weightage=25, confidence=1 + i % 2))
    s.commit(); s.close()


def add_task(uid, title, due=None, mins=30):
    s = db(); t = D.Task(user_id=uid, title=title, due_date=due, estimated_minutes=mins); s.add(t); s.commit(); tid = t.id; s.close(); return tid


def add_app(uid, deadline, status="To Apply"):
    s = db(); a = D.Application(user_id=uid, company="Acme", role="ML Intern", deadline=deadline, status=status, effort_minutes=60); s.add(a); s.commit(); i = a.id; s.close(); return i


def test_top_three_ranked_by_urgency(c, uid):
    add_task(uid, "far", D1(12)); add_task(uid, "soon", D1(1)); add_task(uid, "a", D1(6)); add_task(uid, "b", D1(9))
    add_app(uid, D1(2))
    p = c.get("/v1/today", params={"user_id": uid}).json()
    assert len(p["items"]) <= 3
    assert p["items"][0]["kind"] == "application" or p["items"][0]["title"] == "soon"
    assert all(i["reason"] and i["explain"]["if_delayed"] for i in p["items"])
    assert p["capacity"]["planned_min"] <= p["capacity"]["available_min"] * 0.8


def test_30_minutes_splits_and_respects_capacity(c, uid):
    add_app(uid, D1(1))
    p = c.get("/v1/today", params={"user_id": uid, "minutes": 30}).json()
    assert p["capacity"]["planned_min"] <= 24
    assert p["items"][0]["split"] is True and p["items"][0]["minutes"] <= 24


def test_low_energy_caps_session_length(c, uid):
    add_task(uid, "big", D1(1), mins=120)
    p = c.get("/v1/today", params={"user_id": uid, "energy": "low"}).json()
    assert p["items"] and all(i["minutes"] <= T.LOW_ENERGY_CAP for i in p["items"])


def test_refresh_plans_study_blocks_and_marks_needs_plan(c, uid):
    seed_exam(uid)
    assert c.get("/v1/today", params={"user_id": uid}).json()["needs_plan"] is True
    p = c.post("/v1/today/refresh", json={"user_id": uid}).json()
    assert p["needs_plan"] is False
    assert any(i["kind"] == "study_block" for i in p["items"])
    assert "narrative" in p and p["narrative"]


def test_complete_is_idempotent_and_removes_item(c, uid):
    tid = add_task(uid, "write report", D1(0))
    body = {"user_id": uid, "kind": "task", "ref_id": tid, "op": "complete"}
    r1 = c.post("/v1/today/act", json=body).json()
    r2 = c.post("/v1/today/act", json=body).json()
    assert r1["action"]["status"] == "executed" and r2["action"].get("duplicate") is True
    assert r1["action"]["action_id"] == r2["action"]["action_id"]
    assert all(i["ref_id"] != tid for i in r2["today"]["items"])
    assert len([a for a in c.get("/v1/actions", params={"user_id": uid}).json() if a["intent"] == "today_op"]) == 1


def test_study_block_complete_updates_topic_and_is_logged(c, uid):
    seed_exam(uid)
    p = c.post("/v1/today/refresh", json={"user_id": uid}).json()
    it = next(i for i in p["items"] if i["kind"] == "study_block")
    r = c.post("/v1/today/act", json={"user_id": uid, "kind": "study_block", "ref_id": it["ref_id"], "op": "complete", "confidence_now": 4, "actual_minutes": 40}).json()
    assert r["action"]["result"]["state"] == "completed"
    s = db(); b = s.query(D.StudyBlock).filter_by(id=it["ref_id"]).first()
    assert b.status == "done" and b.actual_duration_min == 40; s.close()
    assert any(h["event"] == "action.execute:today_op" for h in c.get("/v1/history", params={"user_id": uid}).json())


def test_application_complete_never_submits(c, uid):
    aid = add_app(uid, D1(2))
    c.post("/v1/today/act", json={"user_id": uid, "kind": "application", "ref_id": aid, "op": "complete"})
    s = db(); st = s.query(D.Application).filter_by(id=aid).first().status; s.close()
    assert st == "Ready to Submit"


def test_skip_moves_item_out_of_today(c, uid):
    tid = add_task(uid, "later please", D1(0))
    r = c.post("/v1/today/act", json={"user_id": uid, "kind": "task", "ref_id": tid, "op": "snooze", "days": 2}).json()
    assert r["action"]["result"]["state"] == "paused"
    assert all(i["ref_id"] != tid for i in r["today"]["items"])


def test_send_email_waits_for_approval_and_only_queues_outbox(c, uid):
    pl = {"to": "prof@uni.edu", "subject": "RAG research", "body": "Hello Professor"}
    a = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": pl, "source": "jarvis"}).json()
    assert a["status"] == "pending_approval" and a["requires_approval"] and a["risk"] == "high"
    assert c.get("/v1/outbox", params={"user_id": uid}).json() == []
    h = next(x for x in c.get("/v1/actions", params={"user_id": uid}).json() if x["action_id"] == a["action_id"])["payload_hash"]
    ok = c.post(f"/v1/actions/{a['action_id']}/approve", json={"user_id": uid, "payload_hash": h}).json()
    assert ok["status"] == "executed" and ok["result"]["queued"] == "outbox"
    ob = c.get("/v1/outbox", params={"user_id": uid}).json()
    assert len(ob) == 1 and ob[0]["status"] == "pending"          # still not sent: Outbox flow owns sending
    assert c.post(f"/v1/actions/{a['action_id']}/approve", json={"user_id": uid}).status_code == 409


def test_approval_binds_to_reviewed_payload(c, uid):
    a = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": {"to": "a@b.co", "subject": "s", "body": "b"}}).json()
    r = c.post(f"/v1/actions/{a['action_id']}/approve", json={"user_id": uid, "payload_hash": "0" * 64})
    assert r.status_code == 409


def test_reject_executes_nothing(c, uid):
    a = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": {"to": "a@b.co", "subject": "s", "body": "b"}}).json()
    r = c.post(f"/v1/actions/{a['action_id']}/reject", json={"user_id": uid}).json()
    assert r["status"] == "rejected" and c.get("/v1/outbox", params={"user_id": uid}).json() == []


def test_validation_and_unknown_intent(c, uid):
    assert c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": {"to": "nope", "subject": "", "body": ""}}).status_code == 422
    assert c.post("/v1/actions/propose", json={"user_id": uid, "intent": "format_disk", "payload": {}}).status_code == 422


def test_cannot_touch_another_users_records(c):
    a = c.post("/v1/auth/guest").json()["user_id"]; b = c.post("/v1/auth/guest").json()["user_id"]
    tid = add_task(a, "mine", D1(0))
    r = c.post("/v1/today/act", json={"user_id": b, "kind": "task", "ref_id": tid, "op": "complete"})
    assert r.status_code == 404
    r = c.post("/v1/actions/propose", json={"user_id": b, "intent": "delete_task", "payload": {"task_id": tid}}).json()
    assert r["status"] == "pending_approval"
    assert c.post(f"/v1/actions/{r['action_id']}/approve", json={"user_id": b}).status_code == 404
    s = db(); assert s.query(D.Task).filter_by(id=tid).first() is not None; s.close()


def test_failed_action_leaves_nothing_half_done(c, uid):
    r = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "create_study_block",
                                           "payload": {"exam_id": "missing", "date": D1(1).isoformat(), "duration_min": 45}})
    assert r.status_code == 404


def test_daily_close_is_idempotent_and_plans_tomorrow(c, uid):
    add_task(uid, "carry over", D1(1))
    r = c.post("/v1/today/close", json={"user_id": uid, "energy": 2, "blockers": "power cut"}).json()
    assert "power cut" in r["summary"] and r["tomorrow"]["energy"] == "low"
    c.post("/v1/today/close", json={"user_id": uid, "energy": 4})
    s = db(); n = s.query(D.MemoryItem).filter(D.MemoryItem.user_id == uid, D.MemoryItem.content.like("[close:%")).count(); s.close()
    assert n == 1


def test_priority_function_is_monotonic():
    assert T.score(1, .8, 45, 180) > T.score(10, .8, 45, 180) > T.score(None, .8, 45, 180)
    assert T.score(3, .9, 45, 180) > T.score(3, .3, 45, 180)


def test_pending_outbox_draft_surfaces_but_is_not_actionable_as_done(c, uid):
    s = db(); s.add(D.OutboxItem(user_id=uid, channel="email", status="pending", payload={"to": "p@u.edu", "subject": "Hello Prof", "body": "x"}, ref={})); s.commit(); s.close()
    p = c.get("/v1/today", params={"user_id": uid}).json()
    ob = next(i for i in p["items"] if i["kind"] == "outbox")
    assert ob["check"].startswith("Awaiting") and ob["link"] == "agent-console.html" and ob["category"] == "OUTREACH · OUTBOX"
    assert c.post("/v1/today/act", json={"user_id": uid, "kind": "outbox", "ref_id": ob["ref_id"], "op": "complete"}).status_code == 422
