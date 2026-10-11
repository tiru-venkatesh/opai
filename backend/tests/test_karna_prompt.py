"""Pure tests (no FastAPI/DB): cd backend && python -m pytest tests/test_karna_prompt.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent import karna_prompt as K, reply_guard as G

CTX = {"name": "Tiru", "track": "B.Tech CSE", "timezone": "Asia/Kolkata", "available_min": 180,
       "today": [{"title": "Operating Systems: Deadlocks", "minutes": 45, "due": "in 5 days", "reason": "exam soon, low confidence"}],
       "exams": [{"course": "Operating Systems", "type": "End Semester", "days": 5}],
       "applications": [{"company": "Example AI", "role": "ML Intern", "status": "Preparing", "days": 3}],
       "outbox_pending": 1, "completed_today": ["Fix routes (30 min)"]}


def test_context_packet_has_facts_and_is_labelled_as_data():
    t = K.render_context(CTX)
    assert t.startswith("OPAI_CONTEXT") and "not instructions" in t
    for must in ("Name: Tiru", "180 min", "Deadlocks", "in 5 days", "ML Intern at Example AI", "1 draft(s) awaiting"):
        assert must in t, must


def test_empty_context_and_truncation():
    assert "Nothing planned or due" in K.render_context({})
    big = {"today": [{"title": "x" * 200, "minutes": 5, "due": "today"} for _ in range(60)]}
    t = K.render_context(big)
    assert len(t) <= K.MAX_CONTEXT_CHARS + 40 and t.endswith("(context truncated)")


def test_messages_keep_rules_in_system_and_facts_in_user_turn():
    ctx = K.render_context(CTX)
    u = K.user_turn(ctx, "What should I do today?")
    assert "OPAI_CONTEXT" in u and u.endswith("What should I do today?")
    assert "OPAI_CONTEXT" not in K.KARNA_SYSTEM.split("RULES")[0] and "Never claim an action is done" in K.KARNA_SYSTEM


def test_guard_removes_unsupported_claims():
    r, p = G.check_reply("I've sent the email to Professor Rao. Your plan starts with OS.", [])
    assert "Professor Rao" not in r and "Your plan starts with OS." in r and G.SAFE_NOTE in r and len(p) == 1
    r, p = G.check_reply("Your application has been submitted.", None)
    assert p and r == G.SAFE_NOTE
    r, p = G.check_reply("Done. Everything is set.", [])
    assert p


def test_guard_allows_confirmed_actions_and_rejects_failed_ones():
    ok = [{"tool": "create_task", "arguments": {}, "result": {"id": "t1"}}]
    r, p = G.check_reply("I've created the task for Friday.", ok)
    assert not p and r == "I've created the task for Friday."
    bad = [{"tool": "create_task", "arguments": {}, "result": {"error": "invalid date"}}]
    r, p = G.check_reply("I've created the task for Friday.", bad)
    assert p and G.SAFE_NOTE in r
    r, p = G.check_reply("I've drafted the email; it is waiting in your Outbox.", [{"tool": "draft_outreach", "result": {"ok": True}}])
    assert not p
    r, p = G.check_reply("I've sent the draft.", [{"tool": "draft_outreach", "result": {"ok": True}}])   # drafting never means sending
    assert p


def test_guard_leaves_offers_negations_questions_alone():
    for s in ("I can't send emails, but I can prepare a draft for your approval.",
              "Do you want me to draft it?", "I can draft an email once you confirm the research topic.",
              "If I've sent it already you will see it in the Outbox.", "Nothing was sent."):
        r, p = G.check_reply(s, [])
        assert not p and r == s, s
