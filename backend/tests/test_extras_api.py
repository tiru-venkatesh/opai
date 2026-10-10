"""Run: cd backend && python -m pytest tests/test_extras_api.py -q
Groq is forced off so every deterministic fallback path is exercised."""
import os
import sys
import tempfile
from datetime import date, timedelta

import pytest

os.environ["GROQ_API_KEY"] = ""   # empty (not missing) so load_dotenv will not re-add a real key
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python, rag, sql", "highlight": "Built OPAI, an agent with RAG."})
    return u


def mk_contact(c, name="Dr Asha Rao", email="asha@iit.ac.in", areas=("RAG systems", "databases")):
    r = c.post("/v1/contacts", json={"name": name, "institute": "IIT X", "email": email, "research_areas": list(areas), "bio": "Works on RAG."})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_draft_requires_brief(c, uid):
    cid = mk_contact(c, email="a1@iit.ac.in")
    r = c.post(f"/v1/contacts/{cid}/draft-email", json={"user_id": uid})
    assert r.status_code == 409


def test_brief_then_draft_goes_to_outbox_pending(c, uid):
    cid = mk_contact(c, email="a2@iit.ac.in")
    b = c.post(f"/v1/contacts/{cid}/research-brief", json={"user_id": uid}).json()
    assert b["verification"] == "partial" and b["relevance"] > 0 and b["sources"]
    d = c.post(f"/v1/contacts/{cid}/draft-email", json={"user_id": uid}).json()
    assert d["status"] == "pending_approval" and "Nothing has been sent" in d["note"]
    ob = [o for o in c.get("/v1/outbox", params={"user_id": uid}).json() if o["id"] == d["outbox_id"]][0]
    assert ob["status"] == "pending"
    # second draft for the same contact is blocked
    assert c.post(f"/v1/contacts/{cid}/draft-email", json={"user_id": uid}).status_code == 409


def test_suppression_blocks_draft_and_approval(c, uid):
    cid = mk_contact(c, email="blocked@iit.ac.in")
    c.post(f"/v1/contacts/{cid}/research-brief", json={"user_id": uid})
    d = c.post(f"/v1/contacts/{cid}/draft-email", json={"user_id": uid}).json()
    c.post("/v1/outreach/suppression", json={"user_id": uid, "email": "Blocked@IIT.ac.in"})
    ob = [o for o in c.get("/v1/outbox", params={"user_id": uid}).json() if o["id"] == d["outbox_id"]][0]
    assert ob["status"] == "rejected"                    # auto-withdrawn
    cid2 = mk_contact(c, name="Dr B", email="blocked@iit.ac.in")
    c.post(f"/v1/contacts/{cid2}/research-brief", json={"user_id": uid})
    assert c.post(f"/v1/contacts/{cid2}/draft-email", json={"user_id": uid}).status_code == 409


def test_daily_cap_enforced_at_approval(c, uid, monkeypatch):
    monkeypatch.setenv("OPAI_OUTREACH_DAILY_CAP", "1")
    ids = []
    for i in range(2):
        cid = mk_contact(c, name=f"Dr C{i}", email=f"cap{i}@iit.ac.in")
        c.post(f"/v1/contacts/{cid}/research-brief", json={"user_id": uid})
        ids.append(c.post(f"/v1/contacts/{cid}/draft-email", json={"user_id": uid}).json()["outbox_id"])
    assert c.post(f"/v1/outbox/{ids[0]}/approve").status_code == 200
    assert c.post(f"/v1/outbox/{ids[1]}/approve").status_code == 429


def test_evaluate_opportunity_and_duplicates(c, uid):
    o = c.post("/v1/opportunities", json={"title": "ML Intern", "company_or_lab": "Acme", "tags": ["python", "pytorch"],
                                          "deadline": str(date.today() + timedelta(days=2))}).json()
    r = c.post(f"/v1/opportunities/{o['id']}/evaluate", params={"user_id": uid}).json()
    assert r["match_percent"] == 50 and r["gaps"] == ["pytorch"] and r["urgency"] == "critical"
    assert r["recommended_action"] == "save"


def test_tailor_resume_is_grounded(c, uid):
    text = "Built a RAG pipeline in Python for question answering over PDFs\nWon a college chess tournament in second year\nDesigned SQL schemas for a student planner app"
    from database import Resume, SessionLocal   # POST /v1/resumes itself needs Groq, so insert the row directly
    db = SessionLocal()
    row = Resume(user_id=uid, label="v1", raw_text=text, skills=["python", "sql"])
    db.add(row); db.commit(); rid = row.id; db.close()
    app_ = c.post("/v1/applications", json={"user_id": uid, "company": "Acme", "role": "Python RAG Intern"}).json()
    r = c.post(f"/v1/applications/{app_['id']}/tailor-resume", json={"user_id": uid, "resume_id": rid}).json()
    assert r["resume_id"] == rid and r["bullets"][0].startswith("Built a RAG")
    assert all(b in text for b in r["bullets"])           # nothing invented
    blk = c.get(f"/v1/applications/{app_['id']}/blockers", params={"user_id": uid}).json()
    assert "resume_not_tailored" not in [b["code"] for b in blk["blockers"]]


def _topic(c, uid):
    sem = c.post("/v1/semesters", json={"user_id": uid, "name": "S1", "start_date": str(date.today()), "end_date": str(date.today() + timedelta(days=100))}).json()
    course = c.post("/v1/courses", json={"user_id": uid, "semester_id": sem["id"], "name": "OS"}).json()
    return c.post(f"/v1/courses/{course['id']}/topics", json={"course_id": course["id"], "name": "Deadlocks"}).json()["id"]


def test_quiz_recall_fallback_updates_mastery(c, uid):
    tid = _topic(c, uid)
    q = c.post("/v1/quizzes/generate", json={"user_id": uid, "topic_id": tid, "count": 3}).json()
    assert q["kind"] == "recall" and q["source"] == "template" and "answer" not in q["questions"][0]
    res = c.post("/v1/quiz-attempts", json={"user_id": uid, "quiz_id": q["quiz_id"], "answers": {x["id"]: 5 for x in q["questions"]}}).json()
    assert res["fraction"] == 1.0 and res["topic_confidence"] == 5
    assert c.post("/v1/quiz-attempts", json={"user_id": uid, "quiz_id": q["quiz_id"], "answers": {}}).status_code == 409
    assert c.get("/v1/mastery", params={"user_id": uid}).json()[0]["topic"] == "Deadlocks"


def test_quiz_mcq_scored_by_backend(c, uid):
    tid = _topic(c, uid)
    from database import Quiz, SessionLocal
    db = SessionLocal()
    quiz = Quiz(user_id=uid, topic_id=tid, kind="mcq", source="groq", questions=[
        {"id": "q1", "type": "mcq", "q": "x?", "options": list("abcd"), "answer": 2, "explanation": "because"},
        {"id": "q2", "type": "mcq", "q": "y?", "options": list("abcd"), "answer": 0, "explanation": ""}])
    db.add(quiz); db.commit(); qid = quiz.id; db.close()
    res = c.post("/v1/quiz-attempts", json={"user_id": uid, "quiz_id": qid, "answers": {"q1": 2, "q2": 3}}).json()
    assert res["score"] == 1 and res["total"] == 2 and res["review"][1]["correct_answer"] == 0


def test_builder_milestones_dashboard_and_scope(c, uid):
    pid = c.post("/v1/projects", json={"user_id": uid, "title": "Operating Agent"}).json()["id"]
    m = c.post(f"/v1/projects/{pid}/milestones", json={"user_id": uid, "title": "Typed tool router"}).json()
    bd = c.post(f"/v1/projects/{pid}/milestones/{m['id']}/breakdown", json={"user_id": uid}).json()
    assert len(bd["tasks"]) == 3
    c.post(f"/v1/projects/{pid}/blocker", json={"user_id": uid, "text": "Need final DB schema"})
    d = c.get(f"/v1/projects/{pid}/dashboard", params={"user_id": uid}).json()
    assert d["progress"] == {"done": 0, "total": 3} and d["blocker"] == "Need final DB schema" and d["next_task"]
    assert c.get("/v1/projects", params={"user_id": uid}).status_code == 200   # legacy list unaffected

    req = c.post("/v1/requests", json={"user_id": uid, "client": "Z", "ask": "Build a landing page. Add a contact form. Deploy it."}).json()
    p = c.post(f"/v1/requests/{req['id']}/scope", json={"user_id": uid}).json()
    assert p["saved"] is False and len(p["proposed_requirements"]) >= 2
    s = c.post(f"/v1/requests/{req['id']}/scope", json={"user_id": uid, "confirm": True, "requirements": p["proposed_requirements"]}).json()
    assert s["saved"] and s["status"] == "Scoped"


def test_memory_last_verified_set_on_confirm(c, uid):
    it = c.post("/v1/memory/items", json={"user_id": uid, "type": "profile", "content": "Prefers mornings", "source": "jarvis", "confidence": 0.8, "status": "unconfirmed"}).json()
    ok = c.post(f"/v1/memory/items/{it['id']}/confirm", json={"status": "active"}).json()
    assert ok["last_verified_at"]
