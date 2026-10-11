"""Confirm-first memory + onboarding profile as source of truth."""
from test_learn import mk, _chat, c, _no_chat_rate_limit  # noqa: F401  (reuse helpers + the module-scoped client fixture)


def test_profile_wins_and_chat_change_needs_save(c):
    uid = mk(c, "cp1@x.com")
    c.post("/v1/onboarding/basic", params={"user_id": uid}, json={"full_name": "Tiru V"})
    c.post("/v1/onboarding/education", params={"user_id": uid}, json={"course_type": "btech", "branch": "CSE", "current_year": 2, "current_semester": 3, "college": "JNTUK UCEN Narasaraopet"})
    u = lambda t: {"role": "user", "content": t}
    assert "narasaraopet" in _chat(c, uid, [u("my college?")])["reply"].lower()
    r = _chat(c, uid, [u("i study at JNTU Kakinada")])                       # differs from profile -> proposal, profile unchanged
    assert r["memory"]["pending"][0]["current"] == "JNTUK UCEN Narasaraopet" and "profile says" in r["reply"].lower()
    assert "narasaraopet" in _chat(c, uid, [u("my college?")])["reply"].lower()
    _chat(c, uid, [u("i study at JNTU Kakinada"), {"role": "assistant", "content": r["reply"]}, u("yes")])
    assert "kakinada" in _chat(c, uid, [u("my college?")])["reply"].lower()    # confirmed -> profile follows


def test_same_as_profile_is_not_reproposed(c):
    uid = mk(c, "cp2@x.com")
    c.post("/v1/onboarding/basic", params={"user_id": uid}, json={"full_name": "Tiru V"})
    c.post("/v1/onboarding/education", params={"user_id": uid}, json={"course_type": "btech", "branch": "CSE", "current_year": 2, "current_semester": 3, "college": "JNTU Kakinada"})
    r = _chat(c, uid, [{"role": "user", "content": "i study at jntu kakinada"}])
    assert not (r.get("memory") or {}).get("pending")
