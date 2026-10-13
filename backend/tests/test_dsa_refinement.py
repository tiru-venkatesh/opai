"""DSA refinement: levels, spaced revision, outcomes, paused mode, SEMS capacity.
Run: cd backend && python -m pytest tests/test_dsa_refinement.py -q"""
import os, sys, tempfile, uuid as _uuid
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import dsa_roadmap as R
import main
from database import DsaTopic, SessionLocal


# ---------------------------------------------------------------- pure rules
def test_review_intervals_follow_confidence():
    d = date(2026, 3, 1)
    assert [R.next_review_date(c, d) - d for c in (1, 2, 3, 4, 5)] == [timedelta(days=n) for n in (1, 1, 3, 7, 14)]
    assert R.next_review_date(None, d) - d == timedelta(days=3)


def test_review_minutes_short_and_capped():
    assert R.review_minutes(60, 1) == 20 and R.review_minutes(60, 3) == 15 and R.review_minutes(60, 5) == 10 and R.review_minutes(12, 1) == 12


def test_week_plan_matches_spec_example():
    assert R.week_plan(6) == {"learning": 3, "revision": 2, "reflection": 1}
    for d in range(1, 8):
        assert sum(R.week_plan(d).values()) == d


def test_levels_set_the_starting_topic():
    today = date(2026, 3, 1)
    assert R.active_topic(R.build_topics("Python", "Starting from basics", today))["name"] == "Python basics"
    t = R.active_topic(R.build_topics("Python", "Know syntax, weak at DSA", today))
    assert t["name"] == "Big-O"
    t = R.active_topic(R.build_topics("Python", "Already know basic DSA", today))
    assert t["phase_no"] == 3                                  # phases 1-2 skipped, not deleted
    ts = R.build_topics("Python", "Revising for interviews", today)
    assert R.active_topic(ts) is None and all(x["next_review"] is not None for x in ts)


def test_due_reviews_ordered_overdue_then_weakest():
    today = date(2026, 3, 10)
    ts = R.build_topics()
    ts[0].update(next_review=today - timedelta(days=1), confidence=4)
    ts[1].update(next_review=today - timedelta(days=3), confidence=5)
    ts[2].update(next_review=today, confidence=1)
    ts[3].update(next_review=today + timedelta(days=1), confidence=1)
    assert [t["position"] for t in R.due_reviews(ts, today)] == [1, 0, 2]


def test_revision_slot_after_two_learn_sessions_and_maintenance_reviews_due_first():
    ts = R.build_topics()
    ts[0].update(status="practicing", confidence=3, next_review=date(2026, 1, 1))
    due = R.due_reviews(ts, date(2026, 1, 2))
    assert R.pick_topic(ts, "normal", due, 0)[1] == "learn"
    t, kind = R.pick_topic(ts, "normal", due, R.REVISION_EVERY)
    assert kind == "revise" and t["position"] == 0
    t, kind = R.pick_topic(ts, "maintenance", due, 0)
    assert kind == "review" and t["position"] == 0
    assert R.pick_topic(ts, "paused", due, 5)[0] is None
    b = R.day_blocks(t, "normal", "revise", 15)
    assert [x["kind"] for x in b] == ["recall", "revision"] and sum(x["minutes"] for x in b) == 15


def test_partial_never_advances():
    assert R.status_after_session("learning", 5, 5, "partial") == "learning"
    assert R.status_after_session("learning", 0, 4, "completed") == "practicing"


def test_difficulty_tags_validated():
    assert R.clean_tags(["concept", "concept", "time"]) == ["concept", "time"]
    with pytest.raises(ValueError):
        R.clean_tags(["leetcode-hard"])


# ---------------------------------------------------------------- API
@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    return c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]


def make(c, uid, **kw):
    body = {"user_id": uid, "goal": "Internship preparation", "language": "Python", "level": "Starting from basics", "daily_minutes": 30, "days_per_week": 6}
    body.update(kw)
    r = c.post("/v1/dsa/plan", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_onboarding_fields_and_validation(c, uid):
    tgt = (date.today() + timedelta(days=120)).isoformat()
    s = make(c, uid, level="Know syntax, weak at DSA", target_date=tgt)
    assert s["plan"]["level"] == "Know syntax, weak at DSA" and s["plan"]["target_date"] == tgt
    assert s["today"]["topic"]["name"] == "Big-O"
    assert s["progress"]["milestone"]["sessions_remaining"] >= 1
    assert s["week_plan"] == {"learning": 3, "revision": 2, "reflection": 1}
    assert {"levels", "modes", "outcomes", "difficulty"} <= set(s["options"])
    for bad in ({"level": "Genius"}, {"goal": "World domination"}, {"target_date": "2020-01-01"}):
        body = {"user_id": uid, "goal": "Placement preparation", "language": "Python", "daily_minutes": 30, "days_per_week": 5, **bad}
        assert c.post("/v1/dsa/plan", json=body).status_code == 422
    assert make(c, uid, goal="Internship interviews")["plan"]                 # legacy goal still accepted


def test_complete_logs_outcome_confidence_and_next_review(c, uid):
    s = make(c, uid)
    sid = s["today"]["session_id"]
    r = c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "confidence": 2, "actual_minutes": 25, "difficulty": ["concept", "time"]})
    assert r.status_code == 200, r.text
    h = r.json()["history"][0]
    assert h["status"] == "done" and h["confidence"] == 2 and h["difficulty"] == ["concept", "time"] and h["minutes"] == 25
    with SessionLocal() as db:
        t = db.query(DsaTopic).filter(DsaTopic.user_id == uid, DsaTopic.position == 0).first()
        assert t.next_review == date.today() + timedelta(days=1) and t.confidence == 2


def test_partial_and_could_not_start(c, uid):
    s = make(c, uid)
    sid = s["today"]["session_id"]
    r = c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "confidence": 5, "outcome": "partial"}).json()
    assert r["progress"]["advanced"] == 0 and r["today"]["status"] == "done"
    s = make(c, uid)
    sid = s["today"]["session_id"]
    r = c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "outcome": "could_not_start"}).json()
    assert r["today"]["status"] == "skipped" and r["progress"]["advanced"] == 0
    assert c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "outcome": "bogus"}).status_code == 422
    assert c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "difficulty": ["x"]}).status_code == 422


def test_revision_queue_and_review_endpoint(c, uid):
    s = make(c, uid)
    assert s["revision_queue"] == []
    tid = s["phases"][0]["topics"][0]["id"]
    with SessionLocal() as db:
        t = db.query(DsaTopic).filter(DsaTopic.id == tid).first()
        t.status, t.confidence, t.next_review = "practicing", 2, date.today() - timedelta(days=2)
        db.commit()
    q = c.get("/v1/dsa", params={"user_id": uid}).json()["revision_queue"]
    assert len(q) == 1 and q[0]["topic_id"] == tid and q[0]["overdue_days"] == 2 and q[0]["minutes"] == 20
    r = c.post(f"/v1/dsa/topics/{tid}/review", json={"user_id": uid, "confidence": 5})
    assert r.status_code == 200 and r.json()["revision_queue"] == []
    with SessionLocal() as db:
        assert db.query(DsaTopic).filter(DsaTopic.id == tid).first().next_review == date.today() + timedelta(days=14)
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.post(f"/v1/dsa/topics/{tid}/review", json={"user_id": other, "confidence": 3}).status_code == 404
    assert c.post(f"/v1/dsa/topics/{tid}/review", json={"user_id": uid, "confidence": 9}).status_code == 422


def test_paused_mode_generates_no_blocks_and_resume_restores(c, uid):
    make(c, uid)
    s = c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "paused"}).json()
    assert s["mode"]["mode"] == "paused" and s["today"] is None
    t = c.get("/v1/today", params={"user_id": uid}).json()
    assert [i for i in t["items"] if i["kind"] == "dsa"] == []
    s = c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "auto"}).json()
    assert s["mode"]["mode"] == "normal" and s["today"]["topic"]["name"] == "Python basics"
    assert c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "sprint"}).status_code == 422
    assert c.patch("/v1/dsa/plan", json={"user_id": uid, "target_date": "2020-01-01"}).status_code == 422


def test_sems_capacity_rules(c, uid):
    from database import Exam
    make(c, uid, daily_minutes=60)
    with SessionLocal() as db:
        e = Exam(user_id=uid, exam_date=date.today() + timedelta(days=10), status="confirmed")
        db.add(e); db.commit(); eid = e.id
    s = c.get("/v1/dsa", params={"user_id": uid}).json()          # 8-14 days: still normal, but with a heads-up
    assert s["mode"]["mode"] == "normal" and "maintenance" in s["mode"]["heads_up"] and s["today"]["minutes"] == 60
    def set_days(n):
        with SessionLocal() as db:
            db.query(Exam).filter(Exam.id == eid).first().exam_date = date.today() + timedelta(days=n); db.commit()
    set_days(6)                                                   # within a week: maintenance, 15-20 min, review only
    s = c.get("/v1/dsa", params={"user_id": uid}).json()
    assert s["mode"]["mode"] == "maintenance" and s["today"]["minutes"] == 20 and [b["kind"] for b in s["today"]["blocks"]] == ["review"]
    set_days(2)                                                   # within 3 days: lighter still
    assert c.get("/v1/dsa", params={"user_id": uid}).json()["today"]["minutes"] == 15
    s = c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "normal"}).json()   # the learner stays in control
    assert s["mode"]["mode"] == "normal" and s["today"]["minutes"] == 60
    s = c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "paused"}).json()
    assert s["today"] is None
    set_days(-1)                                                  # after the exam: back to normal automatically
    s = c.patch("/v1/dsa/plan", json={"user_id": uid, "mode_override": "auto"}).json()
    assert s["mode"]["mode"] == "normal" and s["today"] is not None
