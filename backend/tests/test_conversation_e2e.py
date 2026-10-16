"""Through the real /v1/chat route: greetings and capability questions never hit the router or the LLM."""
import time
from test_learn import mk, c, _no_chat_rate_limit  # noqa: F401


def _chat(c, uid, text):
    return c.post("/v1/chat", json={"user_id": uid, "text": text}).json()


def test_greeting_and_capabilities_end_to_end(c):
    uid = mk(c, "conv1@x.com")
    c.post("/v1/onboarding/basic", params={"user_id": uid}, json={"full_name": "Tiru Venkatesh"})
    u = lambda t: t

    t0 = time.perf_counter()
    r = _chat(c, uid, u("hi"))
    assert r["reply"].startswith("Hi, Tiru.") and time.perf_counter() - t0 < 1.5

    r = _chat(c, uid, u("what can you"))
    assert "KARNA" in r["reply"] and "low_confidence" not in r["reply"] and "not confident" not in r["reply"].lower()
    assert "Plan my next two hours" in r["reply"]

    r = _chat(c, uid, u("nee features enti"))
    assert "KARNA" in r["reply"]


def test_general_mode_gets_the_same_fast_path(c):
    uid = mk(c, "conv2@x.com")
    r = c.post("/v1/chat/general", json={"user_id": uid, "messages": [{"role": "user", "content": "what can you"}]}).json()
    assert r["source"] == "conversation" and "KARNA" in r["reply"]
    r = c.post("/v1/chat/general", json={"user_id": uid, "messages": [{"role": "user", "content": "hi"}]}).json()
    assert r["reply"].startswith("Hi")
