import os, tempfile
os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["KARNA_LLM_EXTRACT"] = "0"   # tests exercise the regex path; LLM extraction is covered in test_llm_extract.py
import pytest
from fastapi.testclient import TestClient
import main
from agent import learn, identity

@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as cl:
        yield cl

@pytest.fixture(autouse=True)
def _no_chat_rate_limit():
    main._GENERAL_HITS.clear()          # confirm-first flows send several chat turns per test
    yield

def mk(c, email):
    return c.post("/v1/auth/dev-login", params={"email": email}).json()["user_id"]

@pytest.mark.parametrize("t,kind", [("i am ucen jntuk","college"),("I study at JNTUK Kakinada","college"),("my college is Vignan Institute of Technology","college"),
    ("i know python, sql and react","skills"),("my goal is a research internship at IIT","goal"),("I am doing ECE","branch")])
def test_extract_positive(t, kind):
    assert kind in [k for k, _ in learn.extract(t)]

@pytest.mark.parametrize("t", ["what is my college?","how do I study at night","my dob is 15-08-2004","i am 2nd year","my phone number is 9876543210","i am happy",
    "write an email to professor","I want to know about RAG?","my password is abc123 i know python"])
def test_extract_negative(t):
    assert learn.extract(t) == []

def test_learn_dedupe_replace_and_identity(c):
    from database import SessionLocal
    uid = mk(c, "learn1@x.com")
    with SessionLocal() as db:
        assert learn.learn_from_message(db, uid, "i am ucen jntuk")
        assert learn.learn_from_message(db, uid, "i am ucen jntuk") == []             # no duplicate
        assert "UCEN" in (identity.facts(db, uid)["college"] or "").upper()
        learn.learn_from_message(db, uid, "I study at JNTUK Kakinada")                   # newest college replaces the old one
        assert "Kakinada" in identity.facts(db, uid)["college"]
        ctx = learn.personal_context(db, uid, "where do I study")
        assert "Kakinada" in ctx["text"] and not ctx["empty"]

def test_general_chat_statement_is_learned_and_typo_question_answered(c, monkeypatch):
    uid = mk(c, "learn2@x.com")
    body = lambda t: {"user_id": uid, "messages": [{"role": "user", "content": t}]}
    r = c.post("/v1/chat/general", json=body("i am ucen jntuk")).json()
    assert r["source"] == "memory" and "remember" in r["reply"].lower() and r["memory"]["pending"]
    r = c.post("/v1/chat/general", json=body("my stydy?")).json()
    assert r["source"] != "profile" or "UCEN" not in r["reply"].upper()          # nothing saved before confirmation
    c.post("/v1/chat/general", json=body("yes"))                                  # typed yes confirms the pending item
    r = c.post("/v1/chat/general", json=body("my stydy?")).json()
    assert r["source"] == "profile" and "UCEN" in r["reply"].upper()
    r = c.post("/v1/chat/general", json=body("about me")).json()
    assert r["source"] == "profile"
    r = c.post("/v1/chat/general", json=body("my dob")).json()
    assert "private" in r["reply"].lower()

def test_workspace_chat_learns(c):
    uid = mk(c, "learn3@x.com")
    r = c.post("/v1/jarvis/chat", json={"user_id": uid, "message": "i know python and sql"}).json()
    assert r["payload"]["intent"] == "memory_pending"
    assert c.get("/v1/rag/stats", params={"user_id": uid}).json()["chunks_by_source"].get("memory_item", 0) == 0   # pending is not indexed
    c.post(f"/v1/memory/items/{r['payload']['memory']['pending'][0]['id']}/confirm", params={"user_id": uid}, json={"status": "active"})
    st = c.get("/v1/rag/stats", params={"user_id": uid}).json()
    assert st["chunks_by_source"].get("memory_item", 0) >= 1


def _chat(c, uid, msgs):
    return c.post("/v1/chat/general", json={"user_id": uid, "messages": msgs}).json()


def test_transcript_thats_my_college(c):
    uid = mk(c, "learn4@x.com")
    u = lambda t: {"role": "user", "content": t}
    a = lambda t: {"role": "assistant", "content": t}
    hist = [u("jntu narasaraopeta"), a("JNTU - Narasaraopeta Campus ..."), u("thats my college")]
    r = _chat(c, uid, hist)
    assert r["source"] == "memory" and "narasaraopeta" in r["reply"].lower() and r["memory"]["pending"]
    _chat(c, uid, hist + [a(r["reply"]), u("yes")])
    r = _chat(c, uid, [u("my college?")])
    assert r["source"] == "profile" and "narasaraopeta" in r["reply"].lower()


def test_bare_answer_after_not_set_and_yes_confirmation(c):
    uid = mk(c, "learn5@x.com")
    u = lambda t: {"role": "user", "content": t}
    a = lambda t: {"role": "assistant", "content": t}
    r = _chat(c, uid, [u("my college"), a("I don't have your college yet. You can add it in Academics."), u("jntu narasaraopeta")])
    assert r["source"] == "memory"
    uid2 = mk(c, "learn6@x.com")
    r = _chat(c, uid2, [u("x"), a("If you'd like to add JNTU Narasaraopeta as your college, you can do so."), u("yeps")])
    assert r["source"] == "memory" and "Narasaraopeta" in r["reply"]


def test_telugu_and_false_claims():
    assert ("college", "Jntu Narasaraopeta") in [(k, v) for k, v in learn.extract("naa college jntu narasaraopeta")] or learn.extract("naa college jntu narasaraopeta")
    assert learn.extract("nenu jntu narasaraopeta lo chaduvutunna")
    assert "can't change" in learn.strip_false_claim("Got it! I've added JNTU as your college in the profile.", [])
    assert learn.strip_false_claim("Got it! I've added JNTU as your college.", [("college", "x")]).startswith("Got it")
    assert learn.extract("ucen jntuk telusa?") == []
