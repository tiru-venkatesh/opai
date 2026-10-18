"""Run: cd backend && python -m pytest tests/test_auto_outreach.py -q

The draft writer is replaced with a fake, so no LLM and no network. The real database, guard and Outbox are used."""
import os
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402

import auto_outreach as AO  # noqa: E402
import main  # noqa: E402
from database import AutoOutreachSetting, Contact, OutboxItem, OutreachHistory, SessionLocal  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def _cleanup(user_ids):
    """All test modules share one SQLite file when run together, and Contacts are global. Remove everything this
    module created so other modules (e.g. test_opportunities' faculty add) still see a clean dataset."""
    from database import AutoOutreachSetting, Notification, SuppressedContact
    db = SessionLocal()
    try:
        for u in user_ids:
            cids = {(i.ref or {}).get("id") for i in db.query(OutboxItem).filter(OutboxItem.user_id == u).all() if (i.ref or {}).get("kind") == "contact"}
            cids |= {h.contact_id for h in db.query(OutreachHistory).filter(OutreachHistory.user_id == u).all()}
            db.query(OutboxItem).filter(OutboxItem.user_id == u).delete()
            db.query(OutreachHistory).filter(OutreachHistory.user_id == u).delete()
            db.query(SuppressedContact).filter(SuppressedContact.user_id == u).delete()
            db.query(AutoOutreachSetting).filter(AutoOutreachSetting.user_id == u).delete()
            db.query(Notification).filter(Notification.user_id == u).delete()
            for cid in [x for x in cids if x]:
                db.query(Contact).filter(Contact.id == cid).delete()
        db.commit()
    finally:
        db.close()


_CREATED = []


@pytest.fixture(autouse=True, scope="module")
def _tidy():
    yield
    _cleanup(_CREATED)


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    _CREATED.append(u)
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "machine learning, computer vision, python", "highlight": "Built OPAI"})
    return u


def fake_draft(user_id, contact_id, db):
    ct = db.query(Contact).filter(Contact.id == str(contact_id)).first()
    return SimpleNamespace(subject_line=f"RA enquiry: {ct.name}", email_body="Hello Prof.\nI built X.\nThanks", repeat_warning=None)


def boom(user_id, contact_id, db):
    raise RuntimeError("llm down")


def enable(c, uid, inst="IIT Delhi"):
    return c.put("/v1/opp/faculty/auto", json={"user_id": uid, "enabled": True, "institute": inst})


def test_settings_validation(c, uid):
    assert c.put("/v1/opp/faculty/auto", json={"user_id": uid, "enabled": True}).status_code == 422          # no IIT picked
    assert c.put("/v1/opp/faculty/auto", json={"user_id": uid, "enabled": True, "institute": "IIT Mars"}).status_code == 422
    st = c.get("/v1/opp/faculty/auto", params={"user_id": uid}).json()
    assert st["enabled"] is False and "IIT Delhi" in st["institutes"]
    st = enable(c, uid).json()
    assert st["enabled"] and st["institute"] == "IIT Delhi" and st["next_run_at"]
    off = c.put("/v1/opp/faculty/auto", json={"user_id": uid, "enabled": False, "institute": "IIT Delhi"}).json()
    assert off["enabled"] is False


def test_drafts_once_per_24h_and_never_sends(c, uid):
    enable(c, uid)
    db = SessionLocal()
    try:
        r1 = AO.run_for_user(db, uid, draft_fn=fake_draft)
        assert r1["result"] == "drafted", r1
        item = db.query(OutboxItem).filter(OutboxItem.id == r1["outbox_id"]).first()
        assert item.status == "pending" and item.sent_at is None and item.send_state in (None, "not_sent")
        assert item.payload["to"] and item.payload_hash and item.note.startswith("Auto-draft")
        assert item.payload["to"].endswith(".ac.in") or "@" in item.payload["to"]
        # second run inside 24h: refused, nothing new created
        r2 = AO.run_for_user(db, uid, draft_fn=fake_draft, force=True)
        assert r2["result"] == "too_soon"
        assert db.query(OutboxItem).filter(OutboxItem.user_id == uid).count() == 1
        # tick() also respects the gap
        assert AO.tick(db) == 0 or db.query(OutboxItem).filter(OutboxItem.user_id == uid).count() == 1
        # the draft is reviewable through the normal approval path
        rv = c.get(f"/v1/opp/outbox/{item.id}/review", params={"user_id": uid}).json()
        assert rv["status"] == "pending" and rv["payload_hash"] == item.payload_hash
    finally:
        db.close()


def test_waits_for_approval_then_picks_a_different_professor(c, uid):
    enable(c, uid)
    db = SessionLocal()
    try:
        t0 = datetime.utcnow()
        a = AO.run_for_user(db, uid, now=t0, draft_fn=fake_draft)
        assert a["result"] == "drafted"
        # 25h later, previous draft still pending (and not expired yet): do not pile up
        s = AO.get_setting(db, uid)
        s.last_run_at = t0 - timedelta(hours=25)
        db.commit()
        b = AO.run_for_user(db, uid, now=t0 + timedelta(minutes=1), draft_fn=fake_draft, force=True)
        assert b["result"] == "waiting_for_approval", b
        # user rejects it -> next run drafts a DIFFERENT professor
        assert c.post(f"/v1/opp/outbox/{a['outbox_id']}/reject", params={"user_id": uid}).status_code == 200
        s = AO.get_setting(db, uid)
        s.last_run_at = t0 - timedelta(hours=25)
        db.commit()
        n = AO.run_for_user(db, uid, now=t0 + timedelta(minutes=2), draft_fn=fake_draft, force=True)
        assert n["result"] == "drafted", n
        first = db.query(OutboxItem).filter(OutboxItem.id == a["outbox_id"]).first().payload["to"]
        second = db.query(OutboxItem).filter(OutboxItem.id == n["outbox_id"]).first().payload["to"]
        assert first != second
    finally:
        db.close()


def test_respects_do_not_contact_and_institute(c, uid):
    enable(c, uid, "IIT Delhi")
    db = SessionLocal()
    try:
        r = AO.run_for_user(db, uid, draft_fn=fake_draft)
        item = db.query(OutboxItem).filter(OutboxItem.id == r["outbox_id"]).first()
        contact = db.query(Contact).filter(Contact.id == item.ref["id"]).first()
        assert contact.institute.startswith("IIT Delhi")
        to = item.payload["to"]
        c.post(f"/v1/opp/outbox/{item.id}/reject", params={"user_id": uid})
        # suppress the one that was picked, force another run: it must never come back
        from database import SuppressedContact
        db.add(SuppressedContact(user_id=uid, email=to, reason="do_not_contact"))
        s = AO.get_setting(db, uid)
        s.last_run_at = None
        db.commit()
        r2 = AO.run_for_user(db, uid, draft_fn=fake_draft, force=True)
        assert r2["result"] == "drafted"
        assert db.query(OutboxItem).filter(OutboxItem.id == r2["outbox_id"]).first().payload["to"] != to
    finally:
        db.close()


def test_llm_failure_retries_later_and_does_not_burn_the_day(c, uid):
    enable(c, uid)
    db = SessionLocal()
    try:
        t0 = datetime.utcnow()
        r = AO.run_for_user(db, uid, now=t0, draft_fn=boom)
        assert r["result"] == "error"
        s = AO.get_setting(db, uid)
        assert s.last_run_at is None                       # the 24h clock did not start
        assert db.query(OutboxItem).filter(OutboxItem.user_id == uid).count() == 0
        assert AO.run_for_user(db, uid, now=t0 + timedelta(minutes=5), draft_fn=fake_draft)["result"] == "backoff"
        ok = AO.run_for_user(db, uid, now=t0 + timedelta(minutes=61), draft_fn=fake_draft)
        assert ok["result"] == "drafted"
    finally:
        db.close()


def test_needs_profile_skills(c):
    fresh = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    _CREATED.append(fresh)
    enable(c, fresh)
    db = SessionLocal()
    try:
        r = AO.run_for_user(db, fresh, draft_fn=fake_draft)
        assert r["result"] == "needs_profile"
        assert db.query(OutboxItem).filter(OutboxItem.user_id == fresh).count() == 0
    finally:
        db.close()


def test_off_means_off(c, uid):
    db = SessionLocal()
    try:
        assert AO.run_for_user(db, uid, draft_fn=fake_draft)["result"] == "off"
    finally:
        db.close()


def test_run_endpoint_obeys_gap(c, uid, monkeypatch):
    enable(c, uid)
    import agent_service
    monkeypatch.setattr(agent_service, "workflow_draft_outreach", fake_draft)
    r1 = c.post("/v1/opp/faculty/auto/run", params={"user_id": uid}).json()
    assert r1["result"] == "drafted" and r1["status"]["pending_outbox_id"]
    r2 = c.post("/v1/opp/faculty/auto/run", params={"user_id": uid}).json()
    assert r2["result"] == "too_soon"
