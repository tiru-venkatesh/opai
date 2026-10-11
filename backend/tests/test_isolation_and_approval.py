"""Regression tests: per-user isolation on the legacy endpoints, approve != sent, cap counts approvals.
Run: cd backend && python -m pytest tests/test_isolation_and_approval.py -q"""
import uuid as _uuid
import os, sys, tempfile
import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import opportunities_api as O  # noqa: E402
from database import Contact, OutboxItem, OutreachHistory, SessionLocal  # noqa: E402

POSTING = "Machine Learning Intern\nExample AI · Hyderabad (Hybrid)\nApply by 20 Oct 2026\nRequirements:\n- Python and PyTorch experience\n"


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def new_user(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python"})
    return u


def save_job(c, uid):
    before = {x["id"] for x in c.get("/v1/opp/saved", params={"user_id": uid}).json()["items"]}
    pv = c.post("/v1/opp/intake/preview", json={"user_id": uid, "text": POSTING, "url": "https://www.linkedin.com/jobs/view/3912345678/"}).json()
    f = pv["fields"]
    r = c.post("/v1/opp/intake/confirm", json=dict(user_id=uid, title=f["title"]["value"], company="Example AI", source_url=pv["source_url"],
               source_type=pv["source_type"], requirements=f["requirements"]["value"], tags=f["tags"]["value"],
               confirmed_fields=["title", "company"], allow_duplicate=True))
    assert r.status_code == 200, r.text
    after = [x["id"] for x in c.get("/v1/opp/saved", params={"user_id": uid}).json()["items"] if x["id"] not in before]
    assert len(after) == 1   # exactly the posting this user just saved (other tests may leave shared rows in the same DB)
    return after[0]


def test_saved_posting_is_private_on_legacy_endpoints_too(c):
    a, b = new_user(c), new_user(c)
    oid = save_job(c, a)
    assert any(x["id"] == oid for x in c.get("/v1/opportunities", params={"user_id": a}).json())
    assert not any(x["id"] == oid for x in c.get("/v1/opportunities", params={"user_id": b}).json())
    assert not any(x["id"] == oid for x in c.get("/v1/opportunities").json())
    assert not any(x["id"] == oid for x in c.get("/v1/opportunities/intel", params={"user_id": b}).json())


def test_other_user_cannot_dismiss_or_convert(c):
    a, b = new_user(c), new_user(c)
    oid = save_job(c, a)
    assert c.post(f"/v1/opportunities/{oid}/dismiss", params={"user_id": b}).status_code == 404
    assert c.post(f"/v1/opportunities/{oid}/dismiss").status_code == 404
    assert c.post(f"/v1/opportunities/{oid}/convert", params={"user_id": b}).status_code == 404
    assert c.post(f"/v1/opportunities/{oid}/dismiss", params={"user_id": a}).status_code == 200


def draft_for(c, uid, email):
    ct = c.post("/v1/contacts", json={"name": "Dr Q", "institute": "IIT X", "email": email, "research_areas": ["rag"], "bio": "rag"}).json()["id"]
    ob = c.post("/v1/outbox", json={"user_id": uid, "channel": "email", "payload": {"to": email, "subject": "Hi", "body": "Hello there professor"},
                                   "ref": {"kind": "contact", "id": ct}}).json()["id"]
    s = SessionLocal(); h = O.payload_hash(s.query(OutboxItem).filter_by(id=ob).first()); s.close()
    return ct, ob, h


def test_legacy_approve_does_not_mark_sent_or_start_followup(c):
    a, b = new_user(c), new_user(c)
    ct, ob, h = draft_for(c, a, "legacy1@iitx.ac.in")
    assert c.post(f"/v1/outbox/{ob}/approve", params={"reviewed_hash": h}).status_code == 200
    s = SessionLocal()
    assert s.query(Contact).filter_by(id=ct).first().status != "Sent"
    assert s.query(OutreachHistory).filter_by(user_id=a).count() == 0
    row = s.query(OutboxItem).filter_by(id=ob).first(); assert row.status == "approved" and row.approved_at is not None
    s.close()
    # the real send is logged through the pipeline, once
    assert c.post(f"/v1/opp/outbox/{ob}/sent", json={"user_id": a}).status_code == 200
    assert c.post(f"/v1/opp/outbox/{ob}/sent", json={"user_id": a}).status_code == 409
    s = SessionLocal(); assert [x.status for x in s.query(OutreachHistory).filter_by(user_id=a).all()] == ["Sent"]; s.close()


def test_contact_status_is_per_user(c):
    a, b = new_user(c), new_user(c)
    ct, ob, h = draft_for(c, a, "shared@iitx.ac.in")
    c.post(f"/v1/outbox/{ob}/approve", params={"reviewed_hash": h})
    c.post(f"/v1/opp/outbox/{ob}/sent", json={"user_id": a})
    st = lambda u: next(x["status"] for x in c.get("/v1/contacts", params={"user_id": u}).json() if x["id"] == ct)
    assert st(a) == "Sent" and st(b) == "Not started"


def test_daily_cap_counts_approvals_not_only_logged_sends(c, monkeypatch):
    monkeypatch.setenv("OPAI_OUTREACH_DAILY_CAP", "2")
    a = new_user(c)
    codes = []
    for i in range(3):   # approve three drafts WITHOUT logging any send
        ct, ob, h = draft_for(c, a, f"cap{i}@iitx.ac.in")
        codes.append(c.post(f"/v1/outbox/{ob}/approve", params={"reviewed_hash": h}).status_code)
    assert codes == [200, 200, 429]
