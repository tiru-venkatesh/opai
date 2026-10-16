import pytest
from agent import conversation as C


@pytest.mark.parametrize("m", ["what can you", "What can you do?", "help", "how can you help", "what is karna", "who are you",
                               "nee features enti", "nuvvu em cheyagalav", "your features", "menu"])
def test_capabilities(m):
    r = C.answer(m)
    assert r and r["payload"]["answer_mode"] == "capabilities"
    assert "KARNA" in r["reply"] and "low_confidence" not in r["reply"]
    assert all(c in r["reply"] for c in C.ENABLED_CAPABILITIES)


@pytest.mark.parametrize("m", ["hi", "Hello!", "hey karna", "good morning", "namaste"])
def test_greeting_short_and_uses_name_only_when_set(m):
    assert C.answer(m, "Tiru")["reply"].startswith("Hi, Tiru.")
    assert C.answer(m, None)["reply"].startswith("Hi.")
    assert C.answer(m, "User")["reply"].startswith("Hi.")      # placeholder names are not used


@pytest.mark.parametrize("m", ["help me with my resume", "hi add a task to revise paging", "what can you tell me about paging",
                               "what is paging", "add a task", "help me plan my day", "", "x" * 200])
def test_real_requests_fall_through(m):
    assert C.answer(m) is None


def test_thanks_and_bye():
    assert "welcome" in C.answer("thanks")["reply"].lower()
    assert "bye" in C.answer("bye")["reply"].lower()
