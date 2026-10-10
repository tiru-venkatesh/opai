"""Streak counts planned days only; rest days never break it; a missed planned day does."""
import os, sys, tempfile
from datetime import date, timedelta
import pytest
os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from database import DsaPlan, DsaSession, DsaTopic, SessionLocal  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def seed(uid, spec):
    """spec: {days_ago: status}. Real plan/topic rows because SQLite enforces the foreign keys here."""
    db = SessionLocal()
    plan = DsaPlan(user_id=uid)
    db.add(plan); db.flush()
    topic = DsaTopic(user_id=uid, plan_id=plan.id, name="Arrays")
    db.add(topic); db.flush()
    for ago, st in spec.items():
        db.add(DsaSession(user_id=uid, plan_id=plan.id, topic_id=topic.id, plan_date=date.today() - timedelta(days=ago), status=st))
    db.commit(); db.close()


def streak(c, uid):
    return c.get("/v1/dsa/streak", params={"user_id": uid}).json()


def test_rest_days_do_not_break_streak(c):
    uid = c.post("/v1/auth/guest").json()["user_id"]
    seed(uid, {1: "done", 2: "done", 5: "done", 6: "done"})   # days 3-4 are rest days (no sessions)
    k = streak(c, uid)
    assert k["current"] == 4 and k["lost_streak"] == 0 and k["today_status"] == "rest_day"


def test_lost_streak_reported(c):
    uid = c.post("/v1/auth/guest").json()["user_id"]
    seed(uid, {1: "skipped", 2: "done", 3: "done", 4: "done"})
    k = streak(c, uid)
    assert k["current"] == 0 and k["lost_streak"] == 3 and k["missed_days"] == 1 and k["longest"] == 3


def test_today_open_keeps_streak_and_flags_risk(c):
    uid = c.post("/v1/auth/guest").json()["user_id"]
    seed(uid, {0: "planned", 1: "done", 2: "done"})
    k = streak(c, uid)
    assert k["current"] == 2 and k["at_risk"] is True and k["lost_streak"] == 0
