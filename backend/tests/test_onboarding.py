"""Onboarding flow. Run: cd backend && python -m pytest tests/test_onboarding.py -q"""
import os, sys, tempfile, uuid as _uuid
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date

import pytest
from fastapi.testclient import TestClient

import main
import database as D


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def new_user(c):
    r = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()
    return r["user_id"], r


def post(c, uid, step, body):
    return c.post(f"/v1/onboarding/{step}", params={"user_id": uid}, json=body)


BASIC = {"full_name": "Tiru Venkatesh", "date_of_birth": "2004-08-15", "timezone": "Asia/Kolkata"}
EDU = {"course_type": "btech", "branch": "Computer Science and Engineering", "current_year": 3, "current_semester": 5, "college": "Example Institute"}
GOALS = {"goals": ["exams", "internships"], "daily_focus_minutes": 120, "preferred_study_time": "evening"}


def test_new_user_requires_onboarding(c):
    uid, login = new_user(c)
    assert login["onboarding_required"] is True
    s = c.get("/v1/onboarding/status", params={"user_id": uid}).json()
    assert s["required"] and s["step"] == 0


def test_existing_user_is_never_blocked(c):
    uid, _ = new_user(c)
    s = D.SessionLocal(); u = s.get(D.User, uid); email = u.email; u.profile_setup_completed = None; u.name = "Tiru V"; u.branch = "CSE"; s.commit(); s.close()   # a pre-onboarding account that already has name + course
    assert c.post("/v1/auth/dev-login", params={"email": email}).json()["onboarding_required"] is False
    assert c.get("/v1/onboarding/status", params={"user_id": uid}).json()["required"] is False


def test_full_flow_creates_starter_workspace_and_is_idempotent(c):
    uid, _ = new_user(c)
    assert post(c, uid, "basic", BASIC).json()["step"] == 1
    assert post(c, uid, "education", EDU).json()["step"] == 2
    assert post(c, uid, "goals", GOALS).json()["step"] == 3
    r = post(c, uid, "links", {"github": "github.com/tiru", "linkedin": "https://www.linkedin.com/in/tiru", "portfolio": "tiru.dev"}).json()
    assert r["step"] == 4 and r["profile"]["github"] == "https://github.com/tiru" and r["profile"]["portfolio"] == "https://tiru.dev"
    done = c.post("/v1/onboarding/complete", params={"user_id": uid}).json()
    assert done["completed"] and done["first_name"] == "Tiru" and done["semester_created"] and "Semester exam planning" in done["starts_with"]
    assert c.get("/v1/onboarding/status", params={"user_id": uid}).json()["required"] is False
    s = D.SessionLocal()
    sems = s.query(D.Semester).filter_by(user_id=uid).all()
    assert len(sems) == 1 and sems[0].semester_number == 5 and sems[0].daily_study_minutes == 120 and sems[0].peak_start == "19:00" and sems[0].is_current
    u = s.get(D.User, uid)
    assert u.preferences["today"]["goals"] == ["exams", "internships"] and u.degree == "B.Tech / B.E." and u.branch.startswith("Computer")
    s.close()
    again = c.post("/v1/onboarding/complete", params={"user_id": uid}).json()          # double click / retry
    assert again["completed"] and again["semester_created"] is False
    s = D.SessionLocal(); assert s.query(D.Semester).filter_by(user_id=uid).count() == 1; s.close()
    assert c.get("/v1/profile", params={"user_id": uid}).json().get("date_of_birth") is None   # DOB is never exposed by the profile API


def test_resume_from_saved_step(c):
    uid, _ = new_user(c)
    post(c, uid, "basic", BASIC); post(c, uid, "education", EDU)
    s = c.get("/v1/onboarding/status", params={"user_id": uid}).json()
    assert s["step"] == 2 and s["profile"]["full_name"] == "Tiru Venkatesh" and s["profile"]["current_year"] == 3


def test_complete_requires_the_required_steps(c):
    uid, _ = new_user(c)
    post(c, uid, "basic", BASIC)
    r = c.post("/v1/onboarding/complete", params={"user_id": uid})
    assert r.status_code == 409 and "education" in r.json()["detail"] and "goals" in r.json()["detail"]


def test_dob_is_optional_but_validated(c):
    uid, _ = new_user(c)
    assert post(c, uid, "basic", {"full_name": "Asha Rao"}).status_code == 200
    assert post(c, uid, "basic", {"full_name": "Asha Rao", "date_of_birth": "2999-01-01"}).status_code == 422
    assert post(c, uid, "basic", {"full_name": "Asha Rao", "date_of_birth": f"{date.today().year - 5}-01-01"}).status_code == 422   # under 13


@pytest.mark.parametrize("body", [
    {**BASIC, "full_name": "A"}, {**BASIC, "full_name": "x" * 81}, {**BASIC, "timezone": "../../etc"},
])
def test_basic_rejects_bad_input(c, body):
    uid, _ = new_user(c)
    assert post(c, uid, "basic", body).status_code == 422


@pytest.mark.parametrize("body", [
    {**EDU, "course_type": "wizard"}, {**EDU, "branch": ""}, {**EDU, "current_year": 5}, {**EDU, "current_year": 0},
    {**EDU, "current_semester": 9}, {"course_type": "mtech", "current_year": 3},
])
def test_education_rejects_bad_input(c, body):
    uid, _ = new_user(c)
    assert post(c, uid, "education", body).status_code == 422


def test_education_branch_optional_for_diploma(c):
    uid, _ = new_user(c)
    assert post(c, uid, "education", {"course_type": "diploma", "current_year": 2}).status_code == 200


@pytest.mark.parametrize("body", [
    {**GOALS, "goals": []}, {**GOALS, "goals": ["world_domination"]}, {**GOALS, "daily_focus_minutes": 5},
    {**GOALS, "daily_focus_minutes": 481}, {**GOALS, "preferred_study_time": "midnight"},
])
def test_goals_rejects_bad_input(c, body):
    uid, _ = new_user(c)
    assert post(c, uid, "goals", body).status_code == 422


@pytest.mark.parametrize("body", [
    {"github": "https://gitlab.com/x"}, {"github": "http://github.com/x"}, {"github": "javascript:alert(1)"},
    {"linkedin": "https://evil.com/in/x"}, {"portfolio": "not a url"}, {"github": "https://github.com/a b"},
])
def test_links_reject_bad_urls(c, body):
    uid, _ = new_user(c)
    assert post(c, uid, "links", body).status_code == 422


def test_links_are_optional_and_skippable(c):
    uid, _ = new_user(c)
    r = post(c, uid, "links", {}).json()
    assert r["step"] == 4 and r["profile"]["github"] is None


def test_unknown_user_404(c):
    assert c.get("/v1/onboarding/status", params={"user_id": str(_uuid.uuid4())}).status_code == 404


def _status(c, uid):
    return c.get("/v1/onboarding/status", params={"user_id": uid}).json()


def test_legacy_account_missing_the_minimum_is_asked_once(c):
    uid, login = new_user(c); email = login["email"]
    s = D.SessionLocal(); u = s.get(D.User, uid); u.profile_setup_completed = None; s.commit(); s.close()
    assert _status(c, uid)["required"] is True                  # no real name, no course
    s = D.SessionLocal(); u = s.get(D.User, uid); u.name = "Asha Rao"; s.commit(); s.close()
    assert _status(c, uid)["required"] is True                  # name only is still not enough
    s = D.SessionLocal(); u = s.get(D.User, uid); u.degree = "Btech 2nd year"; s.commit(); s.close()
    assert _status(c, uid)["required"] is False                 # name + course: never asked
    assert c.post("/v1/auth/dev-login", params={"email": email}).json()["onboarding_required"] is False


def test_explicitly_unfinished_account_stays_required_even_with_details(c):
    uid, _ = new_user(c)
    s = D.SessionLocal(); u = s.get(D.User, uid); u.name = "Asha Rao"; u.branch = "CSE"; u.profile_setup_completed = False; s.commit(); s.close()
    assert _status(c, uid)["required"] is True
