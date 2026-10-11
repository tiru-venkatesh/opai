"""Questions about the user's own profile are answered from their rows (no LLM), in Workspace AND General mode.
Run: cd backend && python -m pytest tests/test_identity.py -q"""
import os, sys, tempfile, uuid as _uuid
import pytest

os.environ["GROQ_API_KEY"] = ""          # no LLM at all: every answer here must come straight from the database
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
from agent import identity as I  # noqa: E402
from database import SessionLocal, Semester, User  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def make(c, email=None, **profile):
    email = email or "id-" + _uuid.uuid4().hex[:10] + "@test.local"
    u = c.post("/v1/auth/dev-login", params={"email": email}).json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json=profile)
    return u, email


def semester(uid, college="IIT Madras", n=3, year="2025-26", current=True):
    db = SessionLocal()
    try:
        db.add(Semester(user_id=uid, college=college, degree="B.Tech", branch="CSE", semester_number=n, academic_year=year, is_current=current))
        db.commit()
    finally:
        db.close()


def prefs(uid, **kw):
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.id == uid).first()
        p = dict(u.preferences or {}); p.update(kw); u.preferences = p; db.commit()
    finally:
        db.close()


def ws(c, uid, text):
    return c.post("/v1/jarvis/chat", json={"user_id": uid, "message": text}).json()["reply"]


def gen(c, uid, text):
    r = c.post("/v1/chat/general", json={"user_id": uid, "messages": [{"role": "user", "content": text}]})
    return r


@pytest.fixture()
def full(c):
    u, email = make(c, name="Tiru Venkatesh", degree="B.Tech", branch="Computer Science Engineering", cgpa=8.4,
                    github="https://github.com/tiru", skills="python, rag, sql")
    semester(u)
    prefs(u, timezone="Asia/Kolkata", opportunity_profile={"year": 2, "graduation_date": "2028-05", "linkedin_url": "https://linkedin.com/in/tiru",
                                                           "portfolio_url": "https://tiru.dev", "role_types": ["internship"]})
    return u, email


# ---------------------------------------------------------------- detection
@pytest.mark.parametrize("q,expect", [
    ("what is my name", ["name"]), ("waht is my college", ["college"]), ("where do i study", ["college"]), ("which year am i in", ["year"]),
    ("what is my email", ["email"]), ("my gmail id", ["email"]), ("what skills do i have", ["skills"]), ("what is my cgpa", ["cgpa"]),
    ("my name and college", ["name", "college"]), ("what is my name and college", ["name", "college"]), ("please what is my name", ["name"]),
    ("what do you know about me", ["about"]), ("who am i", ["about"]), ("my dob", ["private"]), ("how old am i", ["private"]),
    ("my phone number", ["phone"]), ("my fav hero", ["not_stored"]), ("mky weight", ["not_stored"]), ("my height", ["not_stored"]),
])
def test_detects_profile_questions(q, expect):
    assert I.detect(q) == expect


@pytest.mark.parametrize("q", [
    "this is tiru", "my next pproject", "add my skills", "update my college", "change my name", "draft an email to my professor",
    "show my emails", "my college timetable", "what is on my plan today", "where can i add my skills", "my projects", "hi",
    "email my professor about my skills", "my email draft", "set my goals", "summarise my documents", "my exams this week", "my courses",
])
def test_does_not_hijack_other_requests(q):
    assert I.detect(q) == []


# ---------------------------------------------------------------- answers come from the user's rows, in BOTH modes
def test_workspace_answers_from_rows(c, full):
    u, email = full
    assert "Tiru Venkatesh" in ws(c, u, "what is my name")
    assert "IIT Madras" in ws(c, u, "where do i study")
    assert "2nd year" in ws(c, u, "which year am i in")
    assert "semester 3" in ws(c, u, "which semester am i in")
    assert "python" in ws(c, u, "what skills do i have") and "rag" in ws(c, u, "what skills do i have")
    assert email in ws(c, u, "what is my email")
    assert "8.4" in ws(c, u, "what is my cgpa")
    assert "github.com/tiru" in ws(c, u, "my github")
    assert "linkedin.com/in/tiru" in ws(c, u, "my linkedin")
    assert "Asia/Kolkata" in ws(c, u, "my timezone")


def test_general_mode_answers_too_and_needs_no_llm_key(c, full):
    u, _ = full
    r = gen(c, u, "what is my name")
    assert r.status_code == 200 and "Tiru Venkatesh" in r.json()["reply"] and r.json()["source"] == "profile"
    assert "IIT Madras" in gen(c, u, "waht is my college").json()["reply"]
    # a normal general question still needs the model; with no key that is the existing 503, not an invented answer
    assert gen(c, u, "explain photosynthesis").status_code == 503


def test_two_fields_in_one_question(c, full):
    u, _ = full
    reply = ws(c, u, "my name and college")
    assert "Tiru Venkatesh" in reply and "IIT Madras" in reply


def test_about_me_lists_what_is_saved(c, full):
    u, email = full
    reply = ws(c, u, "what do you know about me")
    for bit in ("Tiru Venkatesh", "IIT Madras", "2nd year", "python", email, "Asia/Kolkata"):
        assert bit in reply
    assert gen(c, u, "who am i").json()["reply"].count("-") >= 5


def test_missing_fields_are_reported_not_guessed(c):
    u, _ = make(c)                                   # nothing but the default placeholder name
    r = ws(c, u, "what is my name")
    assert "don't have your name" in r and "User" not in r
    assert "don't have your college" in ws(c, u, "where do i study") and "Academics" in ws(c, u, "where do i study")
    assert "don't have your year" in ws(c, u, "which year am i in")
    assert "don't have your skills" in ws(c, u, "what skills do i have")
    both = ws(c, u, "what is my name and college")
    assert both.count("don't have your") == 2


def test_college_falls_back_to_opportunity_profile(c):
    u, _ = make(c, name="Asha")
    prefs(u, opportunity_profile={"college": "NIT Warangal", "year": 3})
    assert "NIT Warangal" in ws(c, u, "what is my college")


# ---------------------------------------------------------------- privacy and honesty
def test_dob_is_private_never_looked_up(c, full):
    u, _ = full
    prefs(u, dob="2004-01-02")                       # even if something stored one, it is not read out
    for q in ("my dob", "what is my date of birth", "how old am i"):
        r = ws(c, u, q)
        assert "private" in r and "2004" not in r
        assert "private" in gen(c, u, q).json()["reply"]


def test_phone_and_unstored_details(c, full):
    u, _ = full
    assert "no phone number" in ws(c, u, "my phone number")
    for q in ("my fav hero", "my fav food", "mky weight", "my height"):
        assert "doesn't store" in ws(c, u, q)


def test_llm_context_has_profile_but_never_dob_or_email(c, full):
    from agent import karna_prompt as K
    u, email = full
    prefs(u, dob="2004-01-02")
    db = SessionLocal()
    try:
        text = K.render_context(K.collect_context(db, u))
    finally:
        db.close()
    for must in ("Tiru Venkatesh", "IIT Madras", "Year of study: 2", "Semester: 3", "python", "internship"):
        assert must in text
    assert email not in text and "2004" not in text and "dob" not in text.lower()


def test_only_your_own_data(c, full):
    a, _ = full
    b, _ = make(c, name="Someone Else")
    r = ws(c, b, "where do i study") + ws(c, b, "my skills") + ws(c, b, "what is my name")
    assert "IIT Madras" not in r and "Tiru" not in r and "python" not in r
    assert gen(c, "00000000-0000-0000-0000-000000000000", "what is my name").status_code in (404, 503)   # unknown user: no answer, no leak


# ---------------------------------------------------------------- the rest of the pipeline is untouched
def test_other_questions_still_reach_their_handlers(c, full):
    u, _ = full
    assert I.answer(SessionLocal(), u, "what is on my plan today") is None
    r = ws(c, u, "what are my pending tasks")
    assert "tasks" in r.lower() or "no " in r.lower()
    assert "Tiru" not in ws(c, u, "my projects")


def test_guide_no_longer_hijacks_where_do_i_study():
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "guide.js")).read()
    assert "study|studying|go to college" in js          # the exception exists; behaviour is covered in the browser run
