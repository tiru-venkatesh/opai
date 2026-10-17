"""/v1/jarvis/chat (the route super-chat.html uses): greetings and capability questions never reach memory extraction or the LLM."""
import time
from unittest.mock import patch
from test_learn import mk, c, _no_chat_rate_limit  # noqa: F401


def _jc(c, uid, text, **kw):
    return c.post("/v1/jarvis/chat", json={"user_id": uid, "message": text, **kw}).json()


def test_hi_and_capabilities_skip_memory_extraction(c):
    uid = mk(c, "jv1@x.com")
    c.post("/v1/onboarding/basic", params={"user_id": uid}, json={"full_name": "Tiru Venkatesh"})
    with patch("agent.learn.propose_from_message", side_effect=AssertionError("memory pass must not run for small talk")), \
         patch("agent.learn.extract_llm", side_effect=AssertionError("LLM must not run for small talk")):
        t0 = time.perf_counter()
        r = _jc(c, uid, "hi")
        assert r["reply"].startswith("Hi, Tiru.") and time.perf_counter() - t0 < 1.5
        r = _jc(c, uid, "what can you")
        assert "KARNA" in r["reply"] and "not confident" not in r["reply"].lower()
        assert _jc(c, uid, "nee features enti")["payload"]["answer_mode"] == "capabilities"


def test_real_requests_still_go_through_memory_pass(c):
    uid = mk(c, "jv2@x.com")
    with patch("agent.learn.propose_from_message", return_value={"pending": [], "saved": [], "dropped": []}) as m:
        _jc(c, uid, "help me plan my day")
        assert m.called


def test_doc_scope_is_never_hijacked(c):
    uid = mk(c, "jv3@x.com")
    with patch("agent.learn.propose_from_message", return_value={"pending": [], "saved": [], "dropped": []}) as m:
        _jc(c, uid, "help", doc_ids=["d1"])
        assert m.called
