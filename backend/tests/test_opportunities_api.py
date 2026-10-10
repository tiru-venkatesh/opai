"""Run: cd backend && python -m pytest tests/test_opportunities_api.py -q   (Groq forced off; Gmail stubbed)"""
import uuid as _uuid
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import opportunities_api as OA  # noqa: E402

POSTING = """Machine Learning Intern at Example AI
Location: Bengaluru, India
Hybrid role. Python, PyTorch and RAG experience needed. Pre-final year students, 7.5 CGPA minimum.
Deadline: 20 Oct 2099
"""


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python, rag", "highlight": "Built OPAI, an agent with RAG."})
    return u


@pytest.fixture()
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(OA, "_gmail_send", lambda tok, raw: (calls.append(raw), "gm-123")[1])
    return calls


def track(c, uid, text=POSTING, url="https://www.linkedin.com/jobs/view/123456/?trackingId=abc"):
    r = c.post("/v1/opp/intake", json={"user_id": uid, "url": url, "text": text}).json()
    f = r["fields"]
    conf = c.post("/v1/opp/intake/confirm", json={
        "user_id": uid, "title": f["title"], "organization": f["organization"], "source_type": r["source_type"],
        "source_url": url, "location": f.get("location"), "work_mode": f.get("work_mode"), "role_type": f.get("role_type", "internship"),
        "deadline": f.get("deadline"), "description_text": text,
        "facts": {k: f[k] for k in ("min_gpa", "eligibility_text") if k in f}})
    return r, conf


def test_intake_parses_and_does_not_save(c, uid):
    r = c.post("/v1/opp/intake", json={"user_id": uid, "url": "https://www.linkedin.com/jobs/view/1/?trk=x", "text": POSTING}).json()
    assert r["saved"] is False and r["source_type"] == "linkedin_user_saved"
    f = r["fields"]
    assert f["title"] == "Machine Learning Intern" and f["organization"] == "Example AI"
    assert f["deadline"] == "2099-10-20" and f["work_mode"] == "hybrid" and f["min_gpa"] == 7.5
    assert f["source_url"] == "https://www.linkedin.com/jobs/view/1"        # tracking params stripped
    assert c.get("/v1/opp/opportunities", params={"user_id": uid}).json() == []   # nothing saved yet


def test_job_alert_lists_candidates_only(c, uid):
    body = "New jobs: https://www.linkedin.com/comm/jobs/view/111?x=1 and https://www.linkedin.com/jobs/view/222/"
    r = c.post("/v1/opp/intake", json={"user_id": uid, "text": body}).json()
    assert len(r["job_alert_candidates"]) == 2


def test_duplicate_blocked_and_bad_url(c, uid):
    track(c, uid)
    _, again = track(c, uid)
    assert again.status_code == 409
    assert c.post("/v1/opp/intake", json={"user_id": uid, "url": "javascript:alert(1)"}).status_code == 422


def test_brief_never_claims_eligibility_without_confirmed_profile(c, uid):
    _, o = track(c, uid)
    b = c.get(f"/v1/opp/opportunities/{o.json()['id']}/brief", params={"user_id": uid}).json()
    assert b["match"] == "Unknown" and b["eligibility"] == "Needs confirmation"
    assert any("not confirmed" in x for x in b["unknown"])
    assert b["ai_suggestion"]["label"].startswith("AI suggestion")


def test_brief_with_confirmed_profile_separates_signals(c, uid):
    c.put("/v1/opp/profile", json={"user_id": uid, "skills": ["python", "rag"], "year": "pre-final", "gpa": 8.1,
                                   "work_modes": ["hybrid"], "confirmed": True})
    _, o = track(c, uid)
    b = c.get(f"/v1/opp/opportunities/{o.json()['id']}/brief", params={"user_id": uid}).json()
    assert b["match"] in ("Strong", "Moderate")
    assert any("python" in x for x in b["profile_match"])
    assert any("pytorch" in x for x in b["gaps"])
    assert b["eligibility"].startswith("Appears eligible")
    assert any(x.startswith("Deadline:") for x in b["verified_facts"])


def test_gpa_below_requirement_flags_ineligible(c, uid):
    c.put("/v1/opp/profile", json={"user_id": uid, "skills": ["python"], "year": "pre-final", "gpa": 6.0, "confirmed": True})
    _, o = track(c, uid)
    b = c.get(f"/v1/opp/opportunities/{o.json()['id']}/brief", params={"user_id": uid}).json()
    assert b["eligibility"] == "May not meet a stated requirement"


def test_opportunities_are_user_scoped(c, uid):
    _, o = track(c, uid)
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.get(f"/v1/opp/opportunities/{o.json()['id']}/brief", params={"user_id": other}).status_code == 404
    assert c.post(f"/v1/opp/opportunities/{o.json()['id']}/track", params={"user_id": other}).status_code == 404


def test_application_pipeline_and_applied_sets_followup(c, uid):
    _, o = track(c, uid)
    a = c.post(f"/v1/opp/opportunities/{o.json()['id']}/track", params={"user_id": uid}).json()
    assert a["stage"] == "Saved" and len(a["checklist"]) == 7
    assert c.post(f"/v1/opp/opportunities/{o.json()['id']}/track", params={"user_id": uid}).status_code == 409
    assert c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "stage": "Bogus"}).status_code == 422
    r = c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "stage": "Applied"}).json()
    assert r["submitted_on"] == date.today().isoformat()
    assert r["follow_up_date"] == (date.today() + timedelta(days=7)).isoformat()
    assert [h["stage"] for h in r["stage_history"]] == ["Saved", "Applied"]


def add_prof(c, uid, email="prof@iit.ac.in", shown=True):
    return c.post("/v1/opp/professors", json={
        "user_id": uid, "name": "Dr Asha Rao", "institution": "IIT X", "source_url": "https://iitx.ac.in/faculty/asha?utm=1",
        "email": email, "email_shown_on_source": shown, "research_areas": ["RAG systems", "databases"],
        "recent_work": "Paper on retrieval for databases"}).json()


def test_professor_requires_source_and_verified_email(c, uid):
    assert c.post("/v1/opp/professors", json={"user_id": uid, "name": "Dr X", "institution": "IIT", "source_url": ""}).status_code == 422
    p = add_prof(c, uid, shown=False)
    assert p["email_verification"] == "unverified" and p["source_checked_at"]
    assert c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).status_code == 409
    c.post(f"/v1/opp/professors/{p['id']}/confirm-email", json={"user_id": uid})
    assert c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).status_code == 200


def test_full_professor_flow_hash_bound_send(c, uid, sent):
    p = add_prof(c, uid)
    d = c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).json()
    oid, h = d["outbox_id"], d["payload_hash"]
    assert d["brief"]["sources"] and "Nothing has been sent" in d["note"]
    # pipeline items cannot be approved without presenting the hash
    assert c.post(f"/v1/outbox/{oid}/approve").status_code == 422
    assert c.post(f"/v1/outbox/{oid}/approve", params={"payload_hash": "0" * 64}).status_code == 409
    # not approved -> cannot send
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid, "access_token": "x" * 20}).status_code == 409
    assert c.post(f"/v1/outbox/{oid}/approve", params={"payload_hash": h}).status_code == 200
    # editing after approval revokes it
    e = c.patch(f"/v1/opp/outbox/{oid}", json={"user_id": uid, "subject": "Changed subject"}).json()
    assert e["status"] == "pending" and e["approved_hash"] is None and e["payload_hash"] != h
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid, "access_token": "x" * 20}).status_code == 409
    assert sent == []
    assert c.post(f"/v1/outbox/{oid}/approve", params={"payload_hash": h}).status_code == 409   # stale hash
    assert c.post(f"/v1/outbox/{oid}/approve", params={"payload_hash": e["payload_hash"]}).status_code == 200
    r = c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid, "access_token": "x" * 20}).json()
    assert r["send_state"] == "sent" and r["provider_message_id"] == "gm-123" and len(sent) == 1
    # idempotent: second send does not email again
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid, "access_token": "x" * 20}).json()["already_sent"] is True
    assert len(sent) == 1
    prof = c.get("/v1/opp/professors", params={"user_id": uid}).json()[0]
    assert prof["outreach_status"] == "Sent" and prof["last_outreach"]["status"] == "Sent"
    assert prof["last_outreach"]["follow_up_date"] == (date.today() + timedelta(days=7)).isoformat()


def test_send_failure_is_not_recorded_as_sent(c, uid, monkeypatch):
    def boom(tok, raw):
        raise OSError("401")
    monkeypatch.setattr(OA, "_gmail_send", boom)
    p = add_prof(c, uid, email="fail@iit.ac.in")
    d = c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).json()
    c.post(f"/v1/outbox/{d['outbox_id']}/approve", params={"payload_hash": d["payload_hash"]})
    assert c.post(f"/v1/opp/outbox/{d['outbox_id']}/send", json={"user_id": uid, "access_token": "x" * 20}).status_code == 502
    assert c.get("/v1/opp/professors", params={"user_id": uid}).json()[0]["outreach_status"] != "Sent"


def test_direct_payload_edit_in_db_revokes_approval(c, uid):
    """The central listener covers ANY write path, not just the PATCH endpoint."""
    from database import OutboxItem, SessionLocal
    p = add_prof(c, uid, email="listener@iit.ac.in")
    d = c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).json()
    c.post(f"/v1/outbox/{d['outbox_id']}/approve", params={"payload_hash": d["payload_hash"]})
    db = SessionLocal()
    row = db.query(OutboxItem).filter(OutboxItem.id == d["outbox_id"]).first()
    row.payload = {**row.payload, "to": "someone.else@example.com"}
    db.commit()
    db.refresh(row)
    assert row.status == "pending" and row.approved_hash is None
    db.close()


def test_followups_user_reported_reply_and_draft_rules(c, uid, sent):
    from database import OutreachHistory, SessionLocal
    p = add_prof(c, uid, email="fu@iit.ac.in")
    d = c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).json()
    c.post(f"/v1/outbox/{d['outbox_id']}/approve", params={"payload_hash": d["payload_hash"]})
    c.post(f"/v1/opp/outbox/{d['outbox_id']}/send", json={"user_id": uid, "access_token": "x" * 20})
    assert c.get("/v1/opp/followups", params={"user_id": uid}).json() == []                   # not due yet
    assert c.post(f"/v1/opp/professors/{p['id']}/followup-draft", params={"user_id": uid}).status_code == 409  # too early
    db = SessionLocal()
    h = db.query(OutreachHistory).filter(OutreachHistory.user_id == uid).first()
    h.sent_at = datetime.utcnow() - timedelta(days=8)
    h.follow_up_date = date.today() - timedelta(days=1)
    db.commit()
    hid = h.id
    db.close()
    due = c.get("/v1/opp/followups", params={"user_id": uid}).json()
    assert due and due[0]["question"] == "Have they replied?"
    r = c.post(f"/v1/opp/followups/professor/{hid}/answer", json={"user_id": uid, "answer": "not_yet"}).json()
    assert r["can_draft_followup"] is True
    fd = c.post(f"/v1/opp/professors/{p['id']}/followup-draft", params={"user_id": uid})
    assert fd.status_code == 200 and fd.json()["status"] == "pending_approval"
    c.post(f"/v1/opp/followups/professor/{hid}/answer", json={"user_id": uid, "answer": "yes"})
    assert c.get("/v1/opp/followups", params={"user_id": uid}).json() == []
    assert c.post(f"/v1/opp/professors/{p['id']}/followup-draft", params={"user_id": uid}).status_code == 409  # replied


def test_application_followup_needs_applied_and_goes_through_outbox(c, uid, sent):
    _, o = track(c, uid)
    a = c.post(f"/v1/opp/opportunities/{o.json()['id']}/track", params={"user_id": uid}).json()
    body = {"user_id": uid, "to": "hr@example.com", "recipient_source": "Careers page contact"}
    assert c.post(f"/v1/opp/applications/{a['id']}/followup-draft", json=body).status_code == 409
    c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "stage": "Applied"})
    d = c.post(f"/v1/opp/applications/{a['id']}/followup-draft", json=body).json()
    assert sent == []
    c.post(f"/v1/outbox/{d['outbox_id']}/approve", params={"payload_hash": d["payload_hash"]})
    assert c.post(f"/v1/opp/outbox/{d['outbox_id']}/send", json={"user_id": uid, "access_token": "x" * 20}).status_code == 200
    assert len(sent) == 1


def test_attachments_rejected_not_silently_dropped(c, uid, sent):
    p = add_prof(c, uid, email="att@iit.ac.in")
    d = c.post(f"/v1/opp/professors/{p['id']}/draft", params={"user_id": uid}).json()
    c.patch(f"/v1/opp/outbox/{d['outbox_id']}", json={"user_id": uid, "body": "x" * 100})
    from database import OutboxItem, SessionLocal
    db = SessionLocal()
    row = db.query(OutboxItem).filter(OutboxItem.id == d["outbox_id"]).first()
    row.payload = {**row.payload, "attachments": ["resume.pdf"]}
    db.commit()
    h = row.payload_hash
    db.close()
    c.post(f"/v1/outbox/{d['outbox_id']}/approve", params={"payload_hash": h})
    assert c.post(f"/v1/opp/outbox/{d['outbox_id']}/send", json={"user_id": uid, "access_token": "x" * 20}).status_code == 422
    assert sent == []


def test_summary_and_reports(c, uid):
    c.put("/v1/opp/profile", json={"user_id": uid, "skills": ["python", "rag", "pytorch"], "year": "pre-final", "gpa": 8, "confirmed": True})
    _, o = track(c, uid)
    s = c.get("/v1/opp/summary", params={"user_id": uid}).json()
    assert s["strong_matches"] == 1 and "Example AI" in s["recommended_next_action"]
    a = c.post(f"/v1/opp/opportunities/{o.json()['id']}/track", params={"user_id": uid}).json()
    c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "stage": "Applied"})
    r = c.get("/v1/opp/reports", params={"user_id": uid}).json()
    assert r["funnel"]["Saved"] == 1 and r["funnel"]["Applied"] == 1
    assert r["by_source"]["linkedin_user_saved"]["applied"] == 1
    assert r["bottleneck"].startswith("Applications are going out")


def test_today_matches_shape_for_the_page(c, uid):
    # empty workspace: 200 with an empty list, not a 404
    r = c.get("/v1/opp/today-matches", params={"user_id": uid})
    assert r.status_code == 200 and r.json() == {"items": []}
    track(c, uid)
    items = c.get("/v1/opp/today-matches", params={"user_id": uid}).json()["items"]
    assert len(items) == 1
    b = items[0]
    # exactly what the Today tab reads
    assert b["title"] == "Machine Learning Intern" and b["organization"] == "Example AI"
    assert b["source"]["url"] == "https://www.linkedin.com/jobs/view/123456"
    assert isinstance(b["eligibility"]["summary"], str) and b["eligibility"]["summary"]
    assert isinstance(b["estimated_prep_minutes"], int) and b["recommended_next_step"]
    assert b["match"] in ("Strong", "Moderate", "Unknown", "Weak") and b["days_left"] > 0
    # the original list endpoint is unchanged
    old = c.get("/v1/opp/matches", params={"user_id": uid}).json()
    assert isinstance(old, list) and old[0]["opportunity_id"] == b["opportunity_id"]
    # another user's workspace stays separate
    other = c.post("/v1/auth/dev-login", params={"email": "o-" + _uuid.uuid4().hex[:8] + "@test.local"}).json()["user_id"]
    assert c.get("/v1/opp/today-matches", params={"user_id": other}).json() == {"items": []}
    assert c.get("/v1/opp/today-matches", params={"user_id": "nope"}).status_code == 404
