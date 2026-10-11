"""Brief System. Run: cd backend && python -m pytest tests/test_briefs.py -q
Groq is forced off, so every deterministic path is exercised."""
import uuid as _uuid
import os, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import database as D
from briefs import jarvis, schema
from briefs.core import BriefError

D1 = lambda n: date.today() + timedelta(days=n)


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python, rag, sql", "highlight": "Built OPAI."})
    return u


def db():
    return D.SessionLocal()


def seed_exam(uid, days=5, n_topics=4, name="Operating Systems"):
    s = db()
    sem = D.Semester(user_id=uid, is_current=True, daily_study_minutes=180); s.add(sem); s.flush()
    co = D.Course(user_id=uid, semester_id=sem.id, name=name, code="CS301"); s.add(co); s.flush()
    ex = D.Exam(user_id=uid, course_id=co.id, exam_date=D1(days), weightage=100, status="confirmed"); s.add(ex); s.flush()
    for i in range(n_topics):
        s.add(D.Topic(course_id=co.id, name=f"Topic {i}", estimated_minutes=45, difficulty=4, exam_weightage=25, confidence=1 + i % 2))
    s.commit(); eid = ex.id; s.close()
    return eid


def post_daily(c, uid, **kw):
    r = c.post("/v1/briefs/daily", json={"user_id": uid, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def all_action_ids(b):
    return {a["action_id"]: a for a in b["actions"]}


# ---------------------------------------------------------------- schema
def test_every_brief_has_the_universal_shape(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    for k in ("brief_id", "type", "title", "summary", "generated_at", "confidence", "status", "context", "priorities", "alerts",
              "actions", "approval_items", "sources", "explanation"):
        assert k in b, k
    assert b["brief_id"].startswith("brf_") and b["type"] == "daily_plan" and b["status"] == "ready" and 0 <= b["confidence"] <= 1
    assert b["explanation"]["details_available"] is True and b["sources"]


def test_schema_rejects_malformed_briefs():
    base = {"brief_id": "brf_x", "type": "daily_plan", "title": "t", "summary": "s", "generated_at": "now", "confidence": 0.5,
            "explanation": {"short": "x"}}
    schema.validate(base)
    with pytest.raises(Exception):
        schema.validate({**base, "type": "chatbot"})
    with pytest.raises(Exception):
        schema.validate({**base, "confidence": 1.5})
    pr = {"entity_type": "task", "title": "a"}
    with pytest.raises(Exception):
        schema.validate({**base, "priorities": [{**pr, "rank": 1}, {**pr, "rank": 1}]})


# ---------------------------------------------------------------- daily
def test_daily_brief_matches_spec_example(c, uid):
    seed_exam(uid, days=5)
    b = post_daily(c, uid)
    assert 1 <= len(b["priorities"]) <= 3
    p1 = b["priorities"][0]
    assert p1["rank"] == 1 and p1["entity_type"] == "study_block" and p1["urgency"] in ("high", "medium")
    assert "exam_in_5_days" in p1["reason_codes"] and "confidence_low" in p1["reason_codes"] and "high_weight_topic" in p1["reason_codes"]
    assert p1["reason_text"] and p1["next_action"] == "start_focus"
    assert {a["type"] for a in p1["actions"]} >= {"start_focus", "reschedule"}
    assert "exam" in b["summary"].lower() and "180 minutes" in b["summary"]
    cap = b["capacity"]
    assert cap["planned_min"] <= cap["available_min"] * 0.8 and cap["buffer_min"] >= 0
    assert p1["window"]["start"] < p1["window"]["end"]
    ids = all_action_ids(b)
    assert all(a["action_id"] in ids for p in b["priorities"] for a in p["actions"])      # priority buttons are real, shared actions


def test_capacity_override_gives_shorter_brief(c, uid):
    seed_exam(uid, days=5, n_topics=6)
    full = post_daily(c, uid)
    short = c.post("/v1/briefs/daily", params={"user_id": uid, "capacity_override": 60}).json()
    assert short["context"]["capacity_min"] == 60 and short["capacity"]["planned_min"] <= 48
    assert short["context"]["replanned"] is True
    assert sum(p["duration_min"] for p in short["priorities"]) < sum(p["duration_min"] for p in full["priorities"])
    assert short["capacity"]["buffer_min"] >= 12


def test_low_energy_caps_sessions(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid, energy="low")
    assert all(p["duration_min"] <= 25 for p in b["priorities"]) and any(a["title"] == "Low-energy mode" for a in b["alerts"])


def test_get_daily_is_get_or_create_and_post_supersedes(c, uid):
    seed_exam(uid)
    g1 = c.get("/v1/briefs/daily", params={"user_id": uid}).json()
    g2 = c.get("/v1/briefs/daily", params={"user_id": uid}).json()
    assert g1["brief_id"] == g2["brief_id"]
    new = post_daily(c, uid)
    assert new["brief_id"] != g1["brief_id"]
    old = c.get(f"/v1/briefs/{g1['brief_id']}", params={"user_id": uid}).json()
    assert old["lifecycle"] == "superseded" and old["superseded_by"] == new["brief_id"]


def test_daily_alerts_for_pending_outbox_and_empty_state(c, uid):
    empty = post_daily(c, uid)
    assert empty["priorities"] == [] and empty["summary"]
    s = db(); s.add(D.OutboxItem(user_id=uid, channel="email", status="pending", payload={"to": "x@y.edu", "subject": "Hello", "body": "b"},
                                 ref={"kind": "contact", "id": "zzz"}, risk_level="high")); s.commit(); s.close()
    seed_exam(uid)
    b = post_daily(c, uid)
    assert any("outreach draft" in a["title"] for a in b["alerts"]) or any(p["entity_type"] == "outbox" for p in b["priorities"])


# ---------------------------------------------------------------- lifecycle + actions
def test_lifecycle_and_action_execution(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    bid = b["brief_id"]
    assert c.get(f"/v1/briefs/{bid}", params={"user_id": uid}).json()["lifecycle"] == "shown"
    start = b["priorities"][0]["actions"][0]
    r = c.post(f"/v1/actions/{start['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed"
    again = c.post(f"/v1/actions/{start['action_id']}/execute", json={"user_id": uid}).json()
    assert again["duplicate"] is True
    got = c.get(f"/v1/briefs/{bid}", params={"user_id": uid}).json()
    assert got["lifecycle"] in ("partially_acted", "completed")
    assert any(t.startswith("start_focus:") for t in got["actions_taken"])
    assert [a for a in got["actions"] if a["action_id"] == start["action_id"]][0]["status"] == "executed"
    assert got["priorities"][0]["actions"][0]["status"] == "executed"
    # today reflects it
    assert c.get("/v1/today", params={"user_id": uid}).json()["items"][0]["state"] == "in_progress"
    # audit trail exists
    assert any(h["event"].startswith("brief.generate") for h in c.get("/v1/history", params={"user_id": uid}).json())


def test_brief_completes_when_every_primary_action_is_taken(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    for p in b["priorities"]:
        prim = [a for a in p["actions"] if a["primary"]][0]
        r = c.post(f"/v1/actions/{prim['action_id']}/execute", json={"user_id": uid})
        assert r.status_code == 200, r.text
    assert c.get(f"/v1/briefs/{b['brief_id']}", params={"user_id": uid}).json()["lifecycle"] == "completed"


def test_reschedule_moves_the_item(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    first = b["priorities"][0]
    mv = [a for a in first["actions"] if a["type"] == "reschedule"][0]
    assert c.post(f"/v1/actions/{mv['action_id']}/execute", json={"user_id": uid}).json()["result"]["state"] == "paused"
    assert first["entity_id"] not in [i["ref_id"] for i in c.get("/v1/today", params={"user_id": uid}).json()["items"]]


def test_stale_brief_cannot_execute_but_refresh_works(c, uid):
    seed_exam(uid)
    old = post_daily(c, uid)
    act = old["priorities"][0]["actions"][0]
    new = c.post(f"/v1/briefs/{old['brief_id']}/refresh", json={"user_id": uid}).json()
    assert new["brief_id"] != old["brief_id"] and new["type"] == "daily_plan"
    r = c.post(f"/v1/actions/{act['action_id']}/execute", json={"user_id": uid})
    assert r.status_code == 409 and "Refresh" in r.json()["detail"]


def test_dismiss_and_expiry(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    assert c.post(f"/v1/briefs/{b['brief_id']}/dismiss", json={"user_id": uid}).json()["lifecycle"] == "dismissed"
    b2 = post_daily(c, uid)
    s = db(); row = s.query(D.Brief).filter(D.Brief.id == b2["brief_id"]).first(); row.expires_at = datetime.utcnow() - timedelta(hours=1); s.commit(); s.close()
    assert c.get(f"/v1/briefs/{b2['brief_id']}", params={"user_id": uid}).json()["lifecycle"] == "expired"
    assert c.get("/v1/briefs/daily", params={"user_id": uid}).json()["brief_id"] != b2["brief_id"]      # expired briefs are regenerated


def test_briefs_are_private_to_their_owner(c, uid):
    seed_exam(uid)
    b = post_daily(c, uid)
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.get(f"/v1/briefs/{b['brief_id']}", params={"user_id": other}).status_code == 404
    act = b["priorities"][0]["actions"][0]["action_id"]
    assert c.post(f"/v1/actions/{act}/execute", json={"user_id": other}).status_code == 404
    assert c.get("/v1/briefs", params={"user_id": other}).json() == []


def test_list_briefs_filters(c, uid):
    seed_exam(uid)
    post_daily(c, uid); c.post("/v1/briefs/exam", json={"user_id": uid})
    assert {x["type"] for x in c.get("/v1/briefs", params={"user_id": uid}).json()} == {"daily_plan", "exam_readiness"}
    assert len(c.get("/v1/briefs", params={"user_id": uid, "type": "exam_readiness"}).json()) == 1


# ---------------------------------------------------------------- exam
def test_exam_brief(c, uid):
    eid = seed_exam(uid, days=5)
    b = c.post("/v1/briefs/exam", json={"user_id": uid, "exam_id": eid}).json()
    assert b["type"] == "exam_readiness" and b["exam"]["days_remaining"] == 5 and b["exam"]["course"] == "Operating Systems"
    assert b["exam"]["risk_level"] in ("medium", "high", "critical") and 0 <= b["exam"]["preparation_estimate"] <= 100
    assert "5 days" in b["summary"] and "estimated" in b["summary"]
    t = b["priority_topics"][0]
    assert t["weightage"] == "high" and t["next_session"] == "Learn + active recall" and 20 <= t["duration_min"] <= 60
    assert b["plan"]["remaining_estimated_min"] > 0 and "review_sessions_due" in b["plan"]
    assert {a["type"] for a in b["actions"]} >= {"generate_study_plan", "add_study_block"}
    g = c.get(f"/v1/briefs/exam/{eid}", params={"user_id": uid}).json()
    assert g["brief_id"] == b["brief_id"]


def test_exam_brief_picks_riskiest_and_handles_none(c, uid):
    assert c.post("/v1/briefs/exam", json={"user_id": uid}).status_code == 404
    seed_exam(uid, days=30, name="Far Course"); seed_exam(uid, days=3, name="Near Course")
    assert c.post("/v1/briefs/exam", json={"user_id": uid}).json()["exam"]["course"] == "Near Course"


def test_exam_actions_execute(c, uid):
    seed_exam(uid)
    b = c.post("/v1/briefs/exam", json={"user_id": uid}).json()
    add = [a for a in b["actions"] if a["type"] == "add_study_block"][0]
    assert c.post(f"/v1/actions/{add['action_id']}/execute", json={"user_id": uid}).json()["status"] == "executed"
    plan = [a for a in b["actions"] if a["type"] == "generate_study_plan"][0]
    assert c.post(f"/v1/actions/{plan['action_id']}/execute", json={"user_id": uid}).json()["result"]["replanned"] == "today"


# ---------------------------------------------------------------- DSA
def test_dsa_brief_without_and_with_plan(c, uid):
    b = c.post("/v1/briefs/dsa", json={"user_id": uid}).json()
    assert b["roadmap"] is None and b["actions"][0]["type"] == "create_dsa_roadmap"
    c.post("/v1/dsa/plan", json={"user_id": uid, "language": "Python"})
    b = c.post("/v1/briefs/dsa", json={"user_id": uid}).json()
    assert b["roadmap"]["language"] == "Python" and b["today"]["external_resources"][0]["url"].startswith("http")
    assert b["today"]["duration_min"] > 0 and b["roadmap"]["mode"] == "normal"
    # no practice platform: only external links
    assert all(r["type"] in ("learning", "external_practice") for r in b["today"]["external_resources"])


def test_dsa_brief_exam_season_is_maintenance_and_pause_needs_confirmation(c, uid):
    seed_exam(uid, days=5)
    c.post("/v1/dsa/plan", json={"user_id": uid})
    b = c.post("/v1/briefs/dsa", json={"user_id": uid}).json()
    assert b["roadmap"]["mode"] == "maintenance" and "exam" in b["reason"].lower()
    pause = [a for a in b["actions"] if a["type"] == "pause_dsa"][0]
    assert pause["risk"] == "medium" and pause["requires_confirmation"] is True
    r = c.post(f"/v1/actions/{pause['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "needs_confirmation"
    assert c.get("/v1/dsa", params={"user_id": uid}).json()["mode"]["override"] == "auto"      # nothing changed yet
    ok = c.post(f"/v1/actions/{pause['action_id']}/execute", json={"user_id": uid, "confirm": True}).json()
    assert ok["status"] == "executed"
    assert c.get("/v1/dsa", params={"user_id": uid}).json()["mode"]["override"] == "maintenance"
    acts = c.get("/v1/actions", params={"user_id": uid}).json()
    assert any(a["intent"] == "set_dsa_mode" and a["status"] == "executed" for a in acts)          # approval recorded + audited


# ---------------------------------------------------------------- application
def mk_opp(c, title="ML Intern", tags=("python", "rag", "pytorch"), days=3):
    r = c.post("/v1/opportunities", json={"title": title, "company_or_lab": "Example AI", "tags": list(tags), "deadline": D1(days).isoformat(), "link": "https://example.com/jobs"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_application_brief_and_tracking(c, uid):
    oid = mk_opp(c)
    b = c.post(f"/v1/briefs/application/{oid}", json={"user_id": uid}).json()
    assert b["opportunity"]["match_score"] == 67 and b["opportunity"]["tracked"] is False and b["gaps"] == ["pytorch"]
    assert "moderate" in b["summary"] and "3 days" in b["summary"]
    assert any(a["severity"] == "critical" for a in b["alerts"])
    assert b["next_best_action"]["duration_min"] > 0
    track = [a for a in b["actions"] if a["type"] == "create_application"][0]
    r = c.post(f"/v1/actions/{track['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed" and r["result"]["created"] == "application"
    assert c.post(f"/v1/actions/{track['action_id']}/execute", json={"user_id": uid}).json()["duplicate"]     # no double-tracking
    apps = c.get("/v1/applications", params={"user_id": uid}).json()
    assert len(apps) == 1 and apps[0]["status"] == "To Apply"                                               # tracked, never submitted
    b2 = c.post(f"/v1/briefs/application/{oid}", json={"user_id": uid}).json()
    assert b2["opportunity"]["tracked"] is True and b2["next_best_action"]["title"] == "Tailor your resume"
    assert {a["type"] for a in b2["actions"]} >= {"draft_resume_changes"}


def test_application_brief_for_an_existing_application(c, uid):
    r = c.post("/v1/applications", json={"user_id": uid, "company": "Acme", "role": "SDE Intern", "deadline": D1(2).isoformat()})
    aid = r.json()["id"]
    b = c.post(f"/v1/briefs/application/{aid}", json={"user_id": uid}).json()
    assert b["opportunity"]["tracked"] and b["opportunity"]["company"] == "Acme" and b["alerts"]
    assert c.post("/v1/briefs/application/nope", json={"user_id": uid}).status_code == 404


def test_overdue_opportunity_says_so(c, uid):
    oid = mk_opp(c, title="Old Role", days=-2)
    b = c.post(f"/v1/briefs/application/{oid}", json={"user_id": uid}).json()
    assert "passed" in b["summary"] and b["priorities"][0]["urgency"] == "high"


# ---------------------------------------------------------------- outreach
def mk_contact(c, email="prof@iit.ac.in", areas=("RAG systems", "databases")):
    r = c.post("/v1/contacts", json={"name": "Dr Asha Rao", "institute": "IIT X", "email": email, "research_areas": list(areas), "bio": "Works on RAG."})
    return r.json()["id"]


def test_outreach_brief_comes_before_the_draft(c, uid):
    cid = mk_contact(c)
    b = c.post(f"/v1/briefs/outreach/{cid}", json={"user_id": uid}).json()
    assert b["contact"]["email_status"] == "needs_verification" and b["research_match"]["score"] > 0 and b["research_match"]["why_relevant"]
    assert b["recommended_ask"] and b["sources"] and b["draft"] is None
    assert {a["type"] for a in b["actions"]} >= {"verify_contact", "draft_outreach"}
    assert not any(a["type"] == "send_email" for a in b["actions"])
    draft = [a for a in b["actions"] if a["type"] == "draft_outreach"][0]
    r = c.post(f"/v1/actions/{draft['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed" and r["result"]["queued"] == "outbox"
    ob = [o for o in c.get("/v1/outbox", params={"user_id": uid}).json() if o["id"] == r["result"]["outbox_id"]][0]
    assert ob["status"] == "pending"                                                                          # nothing was sent
    b2 = c.post(f"/v1/briefs/outreach/{cid}", json={"user_id": uid}).json()
    assert b2["draft"]["steps"] == ["Review", "Edit", "Approve", "Send"] and b2["draft"]["current_step"] == "Review"
    assert b2["approval_items"][0]["source"] == "outbox" and not any(a["type"] == "draft_outreach" for a in b2["actions"])


def test_outreach_brief_blocks_suppressed_contacts(c, uid):
    cid = mk_contact(c, email="dnc@iit.ac.in")
    c.post("/v1/outreach/suppression", json={"user_id": uid, "email": "dnc@iit.ac.in"})
    b = c.post(f"/v1/briefs/outreach/{cid}", json={"user_id": uid}).json()
    assert b["contact"]["email_status"] == "suppressed" and any(a["severity"] == "critical" for a in b["alerts"])
    assert not any(a["type"] == "draft_outreach" for a in b["actions"])


# ---------------------------------------------------------------- project
def test_project_brief(c, uid):
    pid = c.post("/v1/projects", json={"user_id": uid, "title": "OPAI"}).json()["id"]
    ms = c.post(f"/v1/projects/{pid}/milestones", json={"user_id": uid, "title": "Beta", "due_date": D1(5).isoformat()}).json()
    empty = c.post(f"/v1/briefs/project/{pid}", json={"user_id": uid}).json()
    assert empty["priorities"][0]["entity_type"] == "milestone" and empty["priorities"][0]["actions"][0]["type"] == "break_down_milestone"
    c.post(f"/v1/projects/{pid}/milestones/{ms['id']}/breakdown", json={"user_id": uid})
    b = c.post(f"/v1/briefs/project/{pid}", json={"user_id": uid}).json()
    assert b["project"]["title"] == "OPAI" and b["next_task"]["id"] and b["milestone"]["title"] == "Beta"
    assert b["priorities"][0]["actions"][0]["type"] == "start_focus" and any("due in" in a["title"] for a in b["alerts"])
    start = b["priorities"][0]["actions"][0]
    assert c.post(f"/v1/actions/{start['action_id']}/execute", json={"user_id": uid}).json()["status"] == "executed"
    c.post(f"/v1/projects/{pid}/blocker", json={"user_id": uid, "text": "Need API keys"})
    b = c.post(f"/v1/briefs/project/{pid}", json={"user_id": uid}).json()
    assert b["priorities"][0]["entity_type"] == "blocker" and any("blocked" in a["title"].lower() for a in b["alerts"])
    assert c.post("/v1/briefs/project/none", json={"user_id": uid}).status_code == 404


# ---------------------------------------------------------------- weekly / recovery
def seed_blocks(uid, eid, done=1, missed=4):
    s = db(); ex = s.query(D.Exam).filter(D.Exam.id == eid).first(); tp = s.query(D.Topic).filter(D.Topic.course_id == ex.course_id).first()
    for i in range(done):
        s.add(D.StudyBlock(user_id=uid, exam_id=eid, topic_id=tp.id, plan_date=D1(-1 - i), duration_min=45, mode="learn", status="done", actual_duration_min=40))
    for i in range(missed):
        s.add(D.StudyBlock(user_id=uid, exam_id=eid, topic_id=tp.id, plan_date=D1(-1 - i), duration_min=45, mode="learn", status="missed"))
    s.commit(); s.close()


def test_weekly_review_suggests_lighter_load_with_confirmation(c, uid):
    eid = seed_exam(uid, days=4); seed_blocks(uid, eid, done=1, missed=4)
    b = c.post("/v1/briefs/weekly", json={"user_id": uid}).json()
    assert b["review"]["study"]["done"] == 1 and b["review"]["study"]["missed"] == 4 and b["review"]["study"]["completion_rate"] == 0.2
    codes = [p["reason_codes"][0] for p in b["priorities"]]
    assert "completion_below_50" in codes and "exam_within_7_days" in codes and b["next_week"]["exams"]
    adj = [a for a in b["actions"] if a["type"] == "adjust_capacity"][0]
    assert adj["risk"] == "medium" and adj["requires_confirmation"]
    assert c.post(f"/v1/actions/{adj['action_id']}/execute", json={"user_id": uid}).json()["status"] == "needs_confirmation"
    r = c.post(f"/v1/actions/{adj['action_id']}/execute", json={"user_id": uid, "confirm": True}).json()
    assert r["status"] == "executed" and r["result"]["to"] < r["result"]["from"]


def test_weekly_review_with_no_data_is_honest(c, uid):
    b = c.post("/v1/briefs/weekly", json={"user_id": uid}).json()
    assert b["confidence"] <= 0.5 and b["priorities"][0]["reason_codes"] == ["insufficient_data"]


def test_recovery_brief(c, uid):
    eid = seed_exam(uid, days=6); seed_blocks(uid, eid, done=0, missed=2)
    s = db(); s.add(D.Task(user_id=uid, title="Old task", due_date=D1(-3), estimated_minutes=30)); s.commit(); s.close()
    b = c.post("/v1/briefs/recovery", json={"user_id": uid}).json()
    assert len(b["changes"]["missed_blocks"]) == 2 and b["changes"]["overdue_tasks"][0]["days_overdue"] == 3
    assert b["priorities"][0]["actions"][0]["type"] == "replan_today"
    r = c.post(f"/v1/actions/{b['priorities'][0]['actions'][0]['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed"
    mv = [a for a in b["actions"] if a["type"] == "reschedule"][0]
    assert c.post(f"/v1/actions/{mv['action_id']}/execute", json={"user_id": uid}).json()["result"]["state"] == "paused"


def test_recovery_when_nothing_is_wrong(c, uid):
    b = c.post("/v1/briefs/recovery", json={"user_id": uid}).json()
    assert "on track" in b["summary"].lower() and b["priorities"] == []


# ---------------------------------------------------------------- decision
def test_decision_brief_recommends_and_creates_task(c, uid):
    seed_exam(uid)
    b = c.post("/v1/briefs/decision", json={"user_id": uid, "question": "Should I take on the freelance logo request?", "estimated_minutes": 60, "deadline_days": 5}).json()
    assert b["type"] == "decision" and len(b["options"]) == 3 and b["priorities"][0]["rank"] == 1 and b["priorities"][0]["score"] >= b["priorities"][1]["score"]
    assert b["context"]["subject"] == "Take on the freelance logo request" and b["assumptions"] == []
    urgent = c.post("/v1/briefs/decision", json={"user_id": uid, "question": "Should I finish the report today?", "estimated_minutes": 20}).json()
    assert urgent["priorities"][0]["title"] == "Do it today" and urgent["context"]["deadline_days"] == 0
    act = urgent["priorities"][0]["actions"][0]
    r = c.post(f"/v1/actions/{act['action_id']}/execute", json={"user_id": uid}).json()
    assert r["status"] == "executed"
    assert any(t["title"] == "Finish the report today" for t in c.get("/v1/tasks", params={"user_id": uid}).json())
    assert c.post("/v1/briefs/decision", json={"user_id": uid, "question": "no"}).status_code == 422


def test_decision_states_its_assumptions(c, uid):
    b = c.post("/v1/briefs/decision", json={"user_id": uid, "question": "Should I learn Rust this month?"}).json()
    assert b["context"]["estimate_assumed"] is True and len(b["assumptions"]) == 2 and b["confidence"] <= 0.6


# ---------------------------------------------------------------- approval
def test_approval_brief_executes_nothing_until_approved(c, uid):
    prop = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "send_email", "payload": {"to": "prof@iit.ac.in", "subject": "Hi", "body": "Hello professor, a note."}, "source": "jarvis"}).json()
    assert prop["status"] == "pending_approval"
    b = c.post("/v1/briefs/approval", json={"user_id": uid}).json()
    item = [i for i in b["approval_items"] if i["approval_id"] == prop["action_id"]][0]
    assert item["risk"] == "high" and item["preview"]["to"] == "prof@iit.ac.in" and "Nothing is sent" in item["preview"]["effect"] and item["payload_hash"]
    assert c.get("/v1/outbox", params={"user_id": uid}).json() == []                                           # nothing queued yet
    # decision buttons cannot be 'executed' directly
    assert c.post(f"/v1/actions/{item['approve_action_id']}/execute", json={"user_id": uid}).status_code == 422
    # stale hash is refused
    assert c.post(f"/v1/actions/{item['approve_action_id']}/approve", json={"user_id": uid, "payload_hash": "bad"}).status_code == 409
    r = c.post(f"/v1/actions/{item['approve_action_id']}/approve", json={"user_id": uid, "payload_hash": item["payload_hash"]}).json()
    assert r["status"] == "executed" and r["result"]["queued"] == "outbox"
    ob = c.get("/v1/outbox", params={"user_id": uid}).json()
    assert len(ob) == 1 and ob[0]["status"] == "pending"                                                       # queued, still not sent
    assert c.get(f"/v1/briefs/{b['brief_id']}", params={"user_id": uid}).json()["lifecycle"] in ("partially_acted", "completed")


def test_approval_brief_reject_and_single_item(c, uid):
    prop = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "delete_task", "payload": {"task_id": "x"}}).json()
    b = c.post("/v1/briefs/approval", json={"user_id": uid, "action_id": prop["action_id"]}).json()
    assert len(b["approval_items"]) == 1 and "Delete task" in b["approval_items"][0]["title"]
    rej = b["approval_items"][0]["reject_action_id"]
    assert c.post(f"/v1/actions/{rej}/reject", json={"user_id": uid}).json()["status"] == "rejected"
    assert c.post("/v1/briefs/approval", json={"user_id": uid}).json()["approval_items"] == []
    assert "Nothing is waiting" in c.post("/v1/briefs/approval", json={"user_id": uid}).json()["summary"]


def test_generic_approve_still_works_and_syncs_brief_buttons(c, uid):
    aid = c.post("/v1/applications", json={"user_id": uid, "company": "A", "role": "R"}).json()["id"]
    prop = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "update_application_status", "payload": {"application_id": aid, "status": "Applied"}}).json()
    b = c.post("/v1/briefs/approval", json={"user_id": uid}).json()
    h = b["approval_items"][0]["payload_hash"]
    assert c.post(f"/v1/actions/{prop['action_id']}/approve", json={"user_id": uid}).status_code == 428                  # no hash, no approval
    assert c.post(f"/v1/actions/{prop['action_id']}/approve", json={"user_id": uid, "payload_hash": h}).json()["status"] == "executed"   # raw id
    got = c.get(f"/v1/briefs/{b['brief_id']}", params={"user_id": uid}).json()
    statuses = {a["type"]: a["status"] for a in got["actions"]}
    assert statuses == {"approve": "executed", "reject": "closed"} and got["lifecycle"] == "completed"
    assert c.get("/v1/applications", params={"user_id": uid}).json()[0]["status"] == "Applied"


def test_reject_from_the_brief_closes_the_approve_button(c, uid):
    prop = c.post("/v1/actions/propose", json={"user_id": uid, "intent": "delete_task", "payload": {"task_id": "x"}}).json()
    b = c.post("/v1/briefs/approval", json={"user_id": uid}).json()
    rej = [a for a in b["actions"] if a["type"] == "reject"][0]
    assert c.post(f"/v1/actions/{rej['action_id']}/reject", json={"user_id": uid}).json()["status"] == "rejected"
    got = c.get(f"/v1/briefs/{b['brief_id']}", params={"user_id": uid}).json()
    assert {a["type"]: a["status"] for a in got["actions"]} == {"approve": "closed", "reject": "executed"} and got["lifecycle"] == "completed"
    assert c.post(f"/v1/actions/{prop['action_id']}/approve", json={"user_id": uid}).status_code == 409           # cannot approve a rejected action


# ---------------------------------------------------------------- JARVIS
def test_detect_routes_only_planning_requests():
    assert jarvis.detect("What should I do today?")[0] == "daily_plan"
    assert jarvis.detect("I only have one hour")[1]["capacity_override"] == 60
    assert jarvis.detect("I have 90 minutes")[1]["capacity_override"] == 90
    assert jarvis.detect("I only have half an hour, and I'm tired")[1] == {"capacity_override": 30, "energy": "low"}
    assert jarvis.detect("plan my day")[0] == "daily_plan"
    assert jarvis.detect("weekly review please")[0] == "weekly_review"
    assert jarvis.detect("I missed yesterday's session")[0] == "recovery"
    assert jarvis.detect("anything waiting for my approval?")[0] == "approval"
    assert jarvis.detect("Should I apply to Acme this week?")[0] == "decision"
    assert jarvis.detect("how ready am I for my exam")[0] == "exam_readiness"
    for neg in ("hello", "how many applications do I have", "add a task to revise paging tomorrow", "write me an email to my professor", "what is deadlock"):
        assert jarvis.detect(neg) is None, neg


def test_jarvis_creates_daily_brief_and_adjusts_for_one_hour(c, uid):
    seed_exam(uid, n_topics=6)
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "What should I do today?"}).json()
    assert r["action"] == "brief" and r["payload"]["brief"]["type"] == "daily_plan"
    assert r["reply"].count(".") <= 4 and "Start with" in r["reply"]
    acts = r["payload"]["actions"]
    assert acts[0]["action_id"].startswith("act_") and acts[0]["id"] == acts[0]["action_id"]
    assert any(x["type"] == "open_brief" and x["client_only"] for x in acts) and any(x.get("prompt") for x in acts)
    one = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "I only have one hour."}).json()
    assert one["action"] == "brief" and one["payload"]["brief"]["context"]["capacity_min"] == 60
    assert "60 minutes" in one["reply"]
    stored = c.get(f"/v1/briefs/{one['payload']['brief_id']}", params={"user_id": uid}).json()
    assert stored["brief_id"] == one["payload"]["brief_id"]


def test_jarvis_missing_exam_is_a_plain_answer_not_an_error(c, uid):
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "how ready am I for my exam?"}).json()
    assert r["action"] == "chat" and "exam" in r["reply"].lower()


def test_jarvis_decision_question(c, uid):
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "Should I take the freelance request today?"}).json()
    assert r["action"] == "brief" and r["payload"]["brief"]["type"] == "decision"


def test_narrative_is_optional_and_never_replaces_facts(c, uid, monkeypatch):
    seed_exam(uid)
    import briefs.core as bc
    monkeypatch.setenv("GROQ_API_KEY", "test")
    monkeypatch.setattr(bc, "narrate", lambda doc: "A friendly restatement.")
    b = post_daily(c, uid, narrative=True)
    assert b["explanation"]["narrative"] == "A friendly restatement." and "minutes available" in b["summary"]
    assert post_daily(c, uid)["explanation"]["narrative"] is None
