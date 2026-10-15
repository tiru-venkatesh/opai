"""Internship section (opportunities_api) regressions, written against the CURRENT API (dev-login, /intake/preview + /intake/confirm).
Run: cd backend && python -m pytest tests/test_internship_fixes.py -q"""
import os
import sys
import tempfile
import uuid

import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import opportunities_api as OA  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def new_user(c, skills=("python", "pytorch", "rag"), confirm=True):
    uid = c.post("/v1/auth/dev-login", params={"email": f"i-{uuid.uuid4().hex[:10]}@test.local", "name": "Asha Rao"}).json()["user_id"]
    c.put("/v1/opp/profile", json={"user_id": uid, "degree": "B.Tech", "year": 3, "branch": "CSE", "college": "JNTU", "graduation_date": "2027-05",
                                  "cgpa": 8.1, "skills": list(skills), "role_types": ["internship"], "confirm": confirm})
    return uid


def save(c, uid, title, company, tags, **extra):
    r = c.post("/v1/opp/intake/confirm", json={"user_id": uid, "title": title, "company": company, "tags": list(tags), "role_type": "internship", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_skill_match_is_whole_word():
    pool = {"javascript": "profile", "react native": "project: App", "c++": "profile", "node.js": "resume"}
    assert OA._has(pool, "java") is None                 # javascript is not java
    assert OA._has(pool, "javascript") == "profile"
    assert OA._has(pool, "react") == "project: App"      # react is part of react native
    assert OA._has(pool, "c++") == "profile"
    assert OA._has(pool, "node") == "resume"             # node matches node.js
    assert OA._has(pool, "") is None


def test_one_tag_never_claims_strong(c):
    uid = new_user(c)
    b = save(c, uid, "Python Intern", "Acme", ["python"])["brief"]
    assert b["match"] == "Unclear"


def test_strong_needs_three_tags_and_confirmed_profile(c):
    uid = new_user(c)
    assert save(c, uid, "ML Intern", "Alpha", ["python", "pytorch", "rag"])["brief"]["match"] == "Strong"
    assert save(c, uid, "ML Intern 2", "Beta", ["python", "pytorch"])["brief"]["match"] == "Good"     # only two tags: capped
    other = new_user(c, confirm=False)
    assert save(c, other, "ML Intern", "Alpha", ["python", "pytorch", "rag"])["brief"]["match"] == "Good"   # profile not confirmed


def test_javascript_does_not_make_java_a_match(c):
    uid = new_user(c, skills=("javascript", "react", "node"))
    b = save(c, uid, "Java Intern", "Gamma", ["java", "spring", "sql"])["brief"]
    assert b["match"] in ("Partial", "Poor") and "java" in b["match_detail"]["gaps"]


def test_deleting_an_application_gives_the_opportunity_back(c):
    uid = new_user(c)
    opp = save(c, uid, "ML Intern", "Alpha", ["python", "pytorch", "rag"])["opportunity"]
    a = c.post(f"/v1/opp/opportunities/{opp['id']}/track", json={"user_id": uid}).json()
    assert opp["id"] not in [o["id"] for o in c.get("/v1/opp/saved", params={"user_id": uid}).json()["items"]]
    assert c.delete(f"/v1/opp/applications/{a['id']}", params={"user_id": uid}).status_code == 200
    assert opp["id"] in [o["id"] for o in c.get("/v1/opp/saved", params={"user_id": uid}).json()["items"]]
    assert c.post(f"/v1/opp/opportunities/{opp['id']}/track", json={"user_id": uid}).status_code == 200      # can track again


def test_summary_and_lists_agree(c):
    uid = new_user(c)
    save(c, uid, "ML Intern", "Alpha", ["python", "pytorch", "rag"])
    s = c.get("/v1/opp/summary", params={"user_id": uid}).json()
    saved = c.get("/v1/opp/saved", params={"user_id": uid}).json()
    today = c.get("/v1/opp/today-matches", params={"user_id": uid}).json()
    strong = [o for o in saved["items"] if o["brief"]["match"] == "Strong"]
    assert strong and s["strong_to_review"] == len(strong)          # shared roles from other users may exist; compare, do not hard-code
    assert {i.get("opportunity_id") or i.get("id") for i in today["items"]} <= {o["id"] for o in saved["items"]}
