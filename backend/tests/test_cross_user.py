"""Cross-user isolation under OPAI_AUTH_MODE=enforce: user B holds a valid token and must not reach user A's rows.
Run: cd backend && python -m pytest tests/test_cross_user.py -q"""
import datetime as dt
import uuid as _uuid

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, JSON

import auth_guard
import database as D
from tests.test_auth_guard import c, tok, H, _keys, mail  # noqa: F401  (shared fixtures / token minting)


def _fill(model, **given):
    """Build a row with dummy values for every NOT NULL column that has no default."""
    vals = dict(given)
    for col in model.__table__.columns:
        if col.name in vals or col.primary_key or col.nullable or col.default is not None or col.server_default is not None:
            continue
        if col.foreign_keys and col.name not in vals:
            continue
        t = col.type
        vals[col.name] = (0 if isinstance(t, Integer) else 0.0 if isinstance(t, Float) else False if isinstance(t, Boolean)
                          else dt.datetime.utcnow() if isinstance(t, DateTime) else dt.date.today() if isinstance(t, Date)
                          else {} if isinstance(t, JSON) else "x")
    return model(**vals)


@pytest.fixture()
def world(c, monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    a, b = mail(), mail()
    ua = c.post("/v1/auth/dev-login", params={"email": a}, headers=H(tok(a))).json()["user_id"]
    ub = c.post("/v1/auth/dev-login", params={"email": b}, headers=H(tok(b))).json()["user_id"]
    db = D.SessionLocal()
    ids = {}
    try:
        for key, model in [("task", D.Task), ("project", D.Project), ("application", D.Application), ("academic", D.Academic),
                           ("request", D.ClientRequest), ("outbox", D.OutboxItem), ("resume", D.Resume), ("memory", D.MemoryItem),
                           ("course", D.Course), ("exam", D.Exam), ("studyblock", D.StudyBlock), ("outreach", D.OutreachHistory)]:
            try:
                row = _fill(model, user_id=ua)
                db.add(row); db.commit(); ids[key] = str(row.id)
            except Exception:
                db.rollback()
        if "course" in ids:
            t = _fill(D.Topic, course_id=ids["course"]); db.add(t); db.commit(); ids["topic"] = str(t.id)
    finally:
        db.close()
    return dict(a=a, b=b, ua=ua, ub=ub, ids=ids)


# (id key, method, path template, body)
ROUTES = [
    ("task", "PATCH", "/v1/tasks/{}", {"title": "hacked"}), ("task", "DELETE", "/v1/tasks/{}", None),
    ("project", "PATCH", "/v1/projects/{}", {"name": "hacked"}), ("project", "DELETE", "/v1/projects/{}", None),
    ("application", "PATCH", "/v1/applications/{}", {"status": "Applied"}), ("application", "DELETE", "/v1/applications/{}", None),
    ("application", "POST", "/v1/applications/{}/mark-applied", {}),
    ("academic", "PATCH", "/v1/academics/{}", {}), ("academic", "DELETE", "/v1/academics/{}", None),
    ("request", "PATCH", "/v1/requests/{}", {}), ("request", "DELETE", "/v1/requests/{}", None),
    ("outbox", "POST", "/v1/outbox/{}/approve", None), ("outbox", "POST", "/v1/outbox/{}/reject", None),
    ("resume", "GET", "/v1/resumes/{}", None), ("resume", "PATCH", "/v1/resumes/{}", {"label": "hacked"}),
    ("resume", "DELETE", "/v1/resumes/{}", None), ("resume", "POST", "/v1/resumes/{}/reanalyze", {}),
    ("memory", "DELETE", "/v1/memory/items/{}", None), ("memory", "PATCH", "/v1/memory/items/{}", {"content": "hacked"}),
    ("course", "GET", "/v1/courses/{}/topics", None), ("course", "POST", "/v1/courses/{}/topics", {"name": "x", "unit": "1"}),
    ("topic", "PATCH", "/v1/topics/{}", {"name": "hacked"}),
    ("exam", "GET", "/v1/exams/{}/risk", None),
    ("studyblock", "POST", "/v1/study-blocks/{}/complete", {"completed": True}),
    ("studyblock", "POST", "/v1/study-blocks/{}/reschedule?new_date=2030-01-01", None),
    ("outreach", "POST", "/v1/outreach/{}/mark-sent", None), ("outreach", "POST", "/v1/outreach/{}/reject", None),
]


def test_world_built(world):
    assert {"task", "project", "application", "resume", "memory", "course", "topic"} <= set(world["ids"])


def test_other_users_rows_are_not_reachable(c, world):
    hb = H(tok(world["b"]))
    tested = 0
    for key, method, tpl, body in ROUTES:
        if key not in world["ids"]:
            continue
        r = c.request(method, tpl.format(world["ids"][key]), json=body, headers=hb)
        assert r.status_code == 404, f"{method} {tpl} leaked to another user: {r.status_code} {r.text[:120]}"
        tested += 1
    assert tested >= 20
    db = D.SessionLocal()
    try:        # nothing of A's changed or disappeared
        for key, model in [("task", D.Task), ("project", D.Project), ("application", D.Application), ("resume", D.Resume), ("memory", D.MemoryItem)]:
            assert db.query(model).filter(model.id == world["ids"][key]).first() is not None, key
    finally:
        db.close()


def test_owner_still_reaches_own_rows(c, world):
    ha = H(tok(world["a"]))
    for key, method, tpl, body in [("exam", "GET", "/v1/exams/{}/risk", None), ("course", "GET", "/v1/courses/{}/topics", None)]:
        if key in world["ids"]:
            assert c.request(method, tpl.format(world["ids"][key]), json=body, headers=ha).status_code != 404, tpl


def test_user_id_of_someone_else_is_403(c, world):
    hb = H(tok(world["b"]))
    assert c.get("/v1/tasks", params={"user_id": world["ua"]}, headers=hb).status_code == 403
    assert c.get("/v1/dsa", params={"user_id": world["ua"]}, headers=hb).status_code == 403
    assert c.post("/v1/dsa/plan", json={"user_id": world["ua"], "daily_minutes": 30}, headers=hb).status_code == 403


def test_multipart_uploads_cannot_name_another_user(c, world):
    hb = H(tok(world["b"]))
    for path, files in [("/v1/rag/docs", {"files": ("n.txt", b"hello", "text/plain")}),
                        ("/v1/academics/syllabus", {"files": ("s.txt", b"Unit 1", "text/plain")}),
                        ("/v1/resume-lab/import-files", {"files": ("r.txt", b"My resume", "text/plain")})]:
        r = c.post(path, data={"user_id": world["ua"]}, files=files, headers=hb)
        assert r.status_code == 403, f"{path} accepted another user's id: {r.status_code}"
    ok = c.post("/v1/rag/docs", data={"user_id": world["ub"]}, files={"files": ("n.txt", b"hello world notes", "text/plain")}, headers=hb)
    assert ok.status_code != 403


def test_no_token_is_401(c, world):
    assert c.get("/v1/dsa", params={"user_id": world["ua"]}).status_code == 401
    assert c.delete(f"/v1/tasks/{world['ids']['task']}").status_code == 401
