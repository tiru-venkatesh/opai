"""DSA Roadmap API + Today integration. Run: cd backend && python -m pytest tests/test_dsa_api.py -q"""
import os, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    return c.post("/v1/auth/guest").json()["user_id"]


def make(c, uid, **kw):
    body = {"user_id": uid, "goal": "Placement preparation", "language": "Python", "daily_minutes": 60, "days_per_week": 5}
    body.update(kw)
    r = c.post("/v1/dsa/plan", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_no_plan_then_create(c, uid):
    s = c.get("/v1/dsa", params={"user_id": uid}).json()
    assert s["plan"] is None and "Python" in s["options"]["languages"]
    s = make(c, uid)
    assert s["plan"]["target"] == "90-day roadmap" and len(s["phases"]) == 11 and s["today"]["topic"]["name"] == "Python basics"
    assert [b["kind"] for b in s["today"]["blocks"]] == ["learn", "practice", "notes"]


def test_validation(c, uid):
    assert c.post("/v1/dsa/plan", json={"user_id": uid, "language": "Rust"}).status_code == 422
    assert c.get("/v1/dsa", params={"user_id": "nope"}).status_code == 404
    s = make(c, uid)
    tid = s["phases"][0]["topics"][0]["id"]
    assert c.patch(f"/v1/dsa/topics/{tid}", json={"user_id": uid, "learn_url": "javascript:alert(1)"}).status_code == 422
    ok = c.patch(f"/v1/dsa/topics/{tid}", json={"user_id": uid, "practice_url": "https://leetcode.com/problems/two-sum/", "status": "learning"})
    assert ok.status_code == 200 and ok.json()["phases"][0]["topics"][0]["practice_url"].endswith("two-sum/")


def test_complete_adapts_and_is_isolated_per_user(c, uid):
    s = make(c, uid)
    sid = s["today"]["session_id"]
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": other}).status_code == 404
    done = c.post(f"/v1/dsa/sessions/{sid}/complete", json={"user_id": uid, "confidence": 4}).json()
    assert done["today"]["status"] == "done" and done["progress"]["advanced"] == 1


def test_today_shows_one_dsa_block_and_can_complete_it(c, uid):
    make(c, uid)
    t = c.get("/v1/today", params={"user_id": uid}).json()
    dsa = [i for i in t["items"] if i["kind"] == "dsa"]
    assert len(dsa) == 1 and dsa[0]["category"] == "DSA ROADMAP" and dsa[0]["link"] == "dsa.html"
    r = c.post("/v1/today/act", json={"user_id": uid, "kind": "dsa", "ref_id": dsa[0]["ref_id"], "op": "complete", "confidence_now": 5})
    assert r.status_code == 200, r.text
    assert c.get("/v1/dsa", params={"user_id": uid}).json()["today"]["status"] == "done"


def test_skip_from_today_keeps_roadmap_intact(c, uid):
    make(c, uid)
    t = c.get("/v1/today", params={"user_id": uid}).json()
    sid = next(i["ref_id"] for i in t["items"] if i["kind"] == "dsa")
    assert c.post("/v1/today/act", json={"user_id": uid, "kind": "dsa", "ref_id": sid, "op": "skip"}).status_code == 200
    s = c.get("/v1/dsa", params={"user_id": uid}).json()
    assert s["today"]["status"] == "skipped" and s["progress"]["advanced"] == 0
