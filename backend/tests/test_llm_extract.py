"""LLM fact extraction: output is validated, grounded in the user's text, and falls back safely."""
import pytest
from agent import learn, groq_client


@pytest.fixture
def llm(monkeypatch):
    monkeypatch.setenv("KARNA_LLM_EXTRACT", "1")
    monkeypatch.setattr(groq_client, "groq_enabled", lambda: True)
    box = {}
    monkeypatch.setattr(groq_client, "generate_json", lambda *a, **k: box["r"])
    return box


def test_question_is_not_a_fact(llm):
    llm["r"] = {"college": None, "branch": None, "skills": None, "goal": None}
    assert learn.extract_llm("ucen jntuk telusa") == []


def test_telugu_slang_fact_and_skills(llm):
    llm["r"] = {"college": "narasaraopeta ucen jntuk", "skills": ["python", "sql"], "goal": None}
    got = dict(learn.extract_llm("nenu narasaraopeta ucen jntuk lo chaduvutunna, python sql telusu"))
    assert "college" in got and got["skills"] == "python, sql"


def test_ungrounded_value_is_dropped(llm):
    llm["r"] = {"college": "Harvard University", "branch": "cse"}
    assert learn.extract_llm("I study at Stanford") == []


def test_private_text_never_reaches_llm(llm):
    llm["r"] = {"college": "x"}
    assert learn.extract_llm("my phone number is 9876543210") is None


def test_llm_failure_returns_none_for_regex_fallback(monkeypatch):
    monkeypatch.setenv("KARNA_LLM_EXTRACT", "1")
    monkeypatch.setattr(groq_client, "groq_enabled", lambda: True)
    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(groq_client, "generate_json", boom)
    assert learn.extract_llm("I study at JNTU Kakinada") is None
