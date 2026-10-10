"""Run: cd backend && python -m pytest tests/test_opportunities.py -q"""
import uuid as _uuid
import os, sys, tempfile
from datetime import date, timedelta
import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import opp_parse as P  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python, rag, sql", "highlight": "Built OPAI"})
    return u


POSTING = """Machine Learning Intern
Example AI · Hyderabad (Hybrid)
Apply by 20 Oct 2026
Requirements:
- Pursuing B.Tech, final year students only
- Minimum 8.0 CGPA
- Python and PyTorch experience
Responsibilities:
- Build RAG pipelines
"""


def preview(c, uid, text=POSTING, url="https://www.linkedin.com/jobs/view/3912345678/?trackingId=abc&refId=x"):
    return c.post("/v1/opp/intake/preview", json={"user_id": uid, "text": text, "url": url}).json()


def confirm(c, uid, **kw):
    pv = preview(c, uid)
    f = pv["fields"]
    body = dict(user_id=uid, title=f["title"]["value"], company="Example AI", source_url=pv["source_url"], source_type=pv["source_type"],
                location="Hyderabad", work_mode="hybrid", deadline="2026-10-20", requirements=f["requirements"]["value"],
                tags=f["tags"]["value"], confirmed_fields=["title", "company", "deadline"], allow_duplicate=True)
    body.update(kw)
    return c.post("/v1/opp/intake/confirm", json=body)


def test_parse_and_linkedin_normalisation():
    pv = P.parse_posting(POSTING, "https://www.linkedin.com/jobs/view/3912345678/?trackingId=abc")
    assert pv["fields"]["title"]["value"] == "Machine Learning Intern"
    assert pv["fields"]["deadline"]["value"].endswith("-10-20")
    assert pv["fields"]["work_mode"]["value"] == "hybrid"
    assert "pytorch" in pv["fields"]["tags"]["value"]
    assert pv["source_url"] == "https://www.linkedin.com/jobs/view/3912345678/" and pv["source_type"] == "linkedin_user_saved"
    assert P.normalize_url("javascript:alert(1)")["url"] != "javascript:alert(1)"


def test_preview_saves_nothing_and_link_only_asks_for_text(c, uid):
    before = c.get("/v1/opp/saved", params={"user_id": uid}).json()["count"]
    r = c.post("/v1/opp/intake/preview", json={"user_id": uid, "url": "https://www.linkedin.com/jobs/view/3999999999/"}).json()
    assert "paste the posting text" in r["message"]
    assert c.get("/v1/opp/saved", params={"user_id": uid}).json()["count"] == before


def test_email_alert_parse(c, uid):
    txt = "New jobs\nAI Intern\nAcme Labs · Pune\nView job: https://www.linkedin.com/comm/jobs/view/4000000001/?trk=x\nData Intern\nBeta · Remote\nhttps://www.linkedin.com/jobs/view/4000000002/\n"
    r = c.post("/v1/opp/intake/email-preview", json={"user_id": uid, "text": txt}).json()
    assert r["count"] == 2 and r["candidates"][0]["title"] == "AI Intern"


def test_brief_separates_signals_and_never_overclaims_eligibility(c, uid):
    out = confirm(c, uid).json()
    b = out["brief"]
    assert b["match"] in ("Partial", "Good") and "pytorch" in b["match_detail"]["gaps"]
    assert b["eligibility"]["summary"] != "Appears eligible"           # profile unconfirmed -> unknown
    assert any("not confirmed" in u for u in b["signals"]["unknown"])
    assert set(b["signals"]) == {"verified_facts", "profile_match", "unknown", "ai_suggestions"}
    # confirm a profile that fails the CGPA rule -> flagged unmet, not eligible
    c.put("/v1/opp/profile", json={"user_id": uid, "year": 2, "cgpa": 7.0, "confirm": True})
    b2 = c.get(f"/v1/opp/opportunities/{out['opportunity']['id']}/brief", params={"user_id": uid}).json()
    assert b2["eligibility"]["summary"] == "Does not appear eligible" and b2["match"] == "Poor"


def test_duplicate_detection(c, uid):
    assert confirm(c, uid, allow_duplicate=True).status_code == 200
    assert confirm(c, uid, allow_duplicate=False).status_code == 409


def test_applied_requires_user_confirmation_and_history(c, uid):
    oid = confirm(c, uid).json()["opportunity"]["id"]
    a = c.post(f"/v1/opp/opportunities/{oid}/track", json={"user_id": uid}).json()
    assert a["stage"] == "Saved"
    assert c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "to": "Applied"}).status_code == 409
    assert c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "to": "Nonsense"}).status_code == 422
    r = c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "to": "Applied", "user_confirms_submitted": True}).json()
    assert r["stage"] == "Applied" and r["submitted_at"] and r["follow_up_date"]
    assert [h["to"] for h in r["history"]] == ["Saved", "Applied"]
    assert c.post(f"/v1/opp/opportunities/{oid}/track", json={"user_id": uid}).status_code == 409
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.get(f"/v1/opp/applications/{a['id']}", params={"user_id": other}).status_code == 404


def _professor(c, uid, email="prof@iitx.ac.in"):
    r = c.post("/v1/opp/professors", json={"user_id": uid, "name": "Dr Rao", "institute": "IIT X", "source_url": "https://iitx.ac.in/faculty/rao",
                                           "email": email, "email_shown_on_source": True, "research_areas": ["rag", "nlp"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_outbox_approval_bound_to_hash(c, uid):
    prof = _professor(c, uid, "bind@iitx.ac.in")
    assert prof["email_verification"] == "public_on_page"
    c.post(f"/v1/contacts/{prof['id']}/research-brief", json={"user_id": uid})
    d = c.post(f"/v1/contacts/{prof['id']}/draft-email", json={"user_id": uid}).json()
    oid = d["outbox_id"]
    rv = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()
    assert rv["recipient"]["to"] == "bind@iitx.ac.in" and rv["payload_hash"]
    # edit after review invalidates the approval
    c.patch(f"/v1/opp/outbox/{oid}", json={"user_id": uid, "subject": "Changed subject"})
    r = c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": rv["payload_hash"]})
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    rv2 = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()
    ok = c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": rv2["payload_hash"]})
    assert ok.status_code == 200 and "mail.google.com" in ok.json()["compose_url"]
    # approval does not mean sent: no follow-up until the user confirms
    assert c.get("/v1/opp/followups", params={"user_id": uid}).json()["items"] == []
    s = c.post(f"/v1/opp/outbox/{oid}/sent", json={"user_id": uid}).json()
    assert s["follow_up_date"]
    assert c.post(f"/v1/opp/outbox/{oid}/sent", json={"user_id": uid}).status_code == 409


def test_unverified_recipient_needs_confirmation(c, uid):
    r = c.post("/v1/opp/professors", json={"user_id": uid, "name": "Dr Seed", "institute": "IIT Y", "email": "seed@iity.ac.in", "research_areas": ["rag", "python"]}).json()
    assert r["email_verification"] == "unverified"
    c.post(f"/v1/contacts/{r['id']}/research-brief", json={"user_id": uid, "source_url": "https://iity.ac.in/seed", "source_title": "Faculty page"})
    d = c.post(f"/v1/contacts/{r['id']}/draft-email", json={"user_id": uid})
    assert d.status_code == 200, d.text
    oid = d.json()["outbox_id"]
    h = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()["payload_hash"]
    assert c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": h}).status_code == 409
    assert c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": h, "confirm_recipient": True}).status_code == 200


def test_followup_flow_never_reads_inbox(c, uid):
    oid = confirm(c, uid).json()["opportunity"]["id"]
    a = c.post(f"/v1/opp/opportunities/{oid}/track", json={"user_id": uid, "contact_ref": "hr@example.com"}).json()
    c.post(f"/v1/opp/applications/{a['id']}/stage", json={"user_id": uid, "to": "Applied", "user_confirms_submitted": True, "follow_up_days": 2})
    assert c.get("/v1/opp/followups", params={"user_id": uid}).json()["items"] == []
    from database import SessionLocal, Application
    db = SessionLocal(); row = db.query(Application).filter(Application.id == a["id"]).first()
    row.follow_up_date = date.today() - timedelta(days=1); db.commit(); db.close()
    items = c.get("/v1/opp/followups", params={"user_id": uid}).json()["items"]
    assert items[0]["question"] == "Have they replied?"
    r = c.post(f"/v1/opp/followups/application/{a['id']}/answer", json={"user_id": uid, "answer": "not_yet"}).json()
    assert r["result"] == "drafted"
    assert c.get("/v1/opp/outbox", params={"user_id": uid}).json()["items"][0]["status"] == "pending"


def test_summary_reports_documents(c, uid):
    confirm(c, uid)
    s = c.get("/v1/opp/summary", params={"user_id": uid}).json()
    assert {"strong_to_review", "deadlines_this_week", "drafts_awaiting_approval", "recommended_next_action"} <= set(s)
    assert c.get("/v1/opp/reports", params={"user_id": uid}).json()["applications_total"] >= 0
    assert "resumes" in c.get("/v1/opp/documents", params={"user_id": uid}).json()
    assert c.get("/v1/opp/pipeline", params={"user_id": uid}).json()["stages"][0] == "Saved"


def test_faculty_search_and_add(c, uid):
    r = c.get("/v1/opp/faculty/search", params={"user_id": uid, "q": "computer vision"}).json()
    assert r["items"] and r["items"][0]["data_status"].endswith("unverified") and r["items"][0]["matched_terms"]
    assert not r["auto"] and len(r["institutes"]) >= 4
    iit = c.get("/v1/opp/faculty/search", params={"user_id": uid, "q": "machine learning", "institute": "IIT Delhi"}).json()["items"]
    assert iit and all(i["institute"] == "IIT Delhi" for i in iit)
    auto = c.get("/v1/opp/faculty/search", params={"user_id": uid}).json()          # profile skills: python, rag, sql
    assert auto["auto"] and auto["query_used"]
    fid = r["items"][0]["id"]
    added = c.post("/v1/opp/faculty/add", json={"user_id": uid, "faculty_id": fid}).json()
    assert added["email_verification"] == "unverified" and added["outreach_status"] == "Not started"
    again = c.get("/v1/opp/faculty/search", params={"user_id": uid, "q": "computer vision"}).json()["items"]
    assert next(i for i in again if i["id"] == fid)["already_added"]
    assert c.post("/v1/opp/faculty/add", json={"user_id": uid, "faculty_id": "nope123456"}).status_code == 404


def test_faculty_browse_when_nothing_to_rank_by(c):
    fresh = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]          # no skills, no query
    r = c.get("/v1/opp/faculty/search", params={"user_id": fresh}).json()
    assert r["browse"] and r["items"] and r["total"] > 400
    ism = c.get("/v1/opp/faculty/search", params={"user_id": fresh, "institute": "IIT (ISM) Dhanbad", "limit": 5}).json()
    assert len(ism["items"]) == 5 and all(i["institute"] == "IIT (ISM) Dhanbad" for i in ism["items"])


# ---------------- direct Gmail send (send-only token, exact approved version) ----------------
def _approved(c, uid, email):
    prof = _professor(c, uid, email)
    c.post(f"/v1/contacts/{prof['id']}/research-brief", json={"user_id": uid})
    oid = c.post(f"/v1/contacts/{prof['id']}/draft-email", json={"user_id": uid}).json()["outbox_id"]
    h = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()["payload_hash"]
    assert c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": h}).status_code == 200
    return prof, oid


def test_gmail_send_exact_version_once(c, uid, monkeypatch):
    import gmail_send
    calls = []
    monkeypatch.setattr(gmail_send, "send", lambda tok, to, sub, body, frm=None: calls.append((tok, to, sub, body)) or "gm-123")
    prof, oid = _approved(c, uid, "gsend@iitx.ac.in")
    r = c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "tok-abc"})
    assert r.status_code == 200, r.text
    assert r.json()["provider_message_id"] == "gm-123" and r.json()["sent_via"] == "gmail_api" and r.json()["follow_up_date"]
    assert len(calls) == 1 and calls[0][1] == "gsend@iitx.ac.in"
    # the body that left is exactly the approved body
    rv = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()
    assert calls[0][2] == rv["subject"] and calls[0][3] == rv["body"]
    # a second click cannot send it again
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "tok-abc"}).status_code == 409
    assert len(calls) == 1
    # bookkeeping happened once, only after the send
    assert c.get("/v1/opp/outbox", params={"user_id": uid}).json()["items"][0]["sent_at"]
    # the token is never written to the audit trail
    from database import SessionLocal, AgentActivityLog
    db = SessionLocal()
    try:
        assert not [a for a in db.query(AgentActivityLog).all() if "tok-abc" in str(a.arguments) + str(a.result_summary)]
    finally:
        db.close()


def test_gmail_send_requires_approval_and_unchanged_content(c, uid, monkeypatch):
    import gmail_send
    calls = []
    monkeypatch.setattr(gmail_send, "send", lambda *a, **k: calls.append(a) or "x")
    prof = _professor(c, uid, "gnoapp@iitx.ac.in")
    c.post(f"/v1/contacts/{prof['id']}/research-brief", json={"user_id": uid})
    oid = c.post(f"/v1/contacts/{prof['id']}/draft-email", json={"user_id": uid}).json()["outbox_id"]
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "t"}).status_code == 409   # not approved
    h = c.get(f"/v1/opp/outbox/{oid}/review", params={"user_id": uid}).json()["payload_hash"]
    c.post(f"/v1/opp/outbox/{oid}/approve", json={"user_id": uid, "reviewed_hash": h})
    from database import SessionLocal, OutboxItem
    db = SessionLocal(); row = db.query(OutboxItem).filter(OutboxItem.id == oid).first()
    row.payload = {**row.payload, "body": row.payload["body"] + "\nP.S. sneaked in after approval"}   # any path that edits behind the user's back
    db.commit(); db.close()
    r = c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "t"})
    assert r.status_code == 409 and "changed" in r.json()["detail"] and not calls


def test_gmail_failure_is_not_logged_as_sent_and_can_retry(c, uid, monkeypatch):
    import gmail_send
    state = {"fail": True}
    def fake(tok, to, sub, body, frm=None):
        if state["fail"]:
            raise gmail_send.GmailError(401, "Gmail rejected the token (expired or wrong scope). Reconnect Gmail.")
        return "gm-ok"
    monkeypatch.setattr(gmail_send, "send", fake)
    prof, oid = _approved(c, uid, "gfail@iitx.ac.in")
    r = c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "bad"})
    assert r.status_code == 401
    assert not c.get("/v1/opp/outbox", params={"user_id": uid}).json()["items"][0]["sent_at"]
    assert c.get("/v1/opp/followups", params={"user_id": uid}).json()["items"] == []
    state["fail"] = False
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": uid}, headers={"X-Gmail-Token": "good"}).json()["provider_message_id"] == "gm-ok"


def test_gmail_other_users_cannot_send(c, uid, monkeypatch):
    import gmail_send
    monkeypatch.setattr(gmail_send, "send", lambda *a, **k: "x")
    prof, oid = _approved(c, uid, "gowner@iitx.ac.in")
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.post(f"/v1/opp/outbox/{oid}/send", json={"user_id": other}, headers={"X-Gmail-Token": "t"}).status_code == 404


def test_config_reports_gmail_state(c, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert c.get("/v1/opp/config").json()["gmail_send_enabled"] is False
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    j = c.get("/v1/opp/config").json()
    assert j["gmail_send_enabled"] and j["gmail_scope"].endswith("gmail.send")
