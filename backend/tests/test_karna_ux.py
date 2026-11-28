"""KARNA UX: briefing + follow-ups (pure) and the streaming workspace route."""
import json
from unittest.mock import patch
from agent import karna_ux as U
from test_learn import mk, c, _no_chat_rate_limit  # noqa: F401

CTX = {"name": "Tiru Venkatesh", "today": [{"title": "OS: Deadlocks", "minutes": 45}],
       "exams": [{"course": "Operating Systems", "type": "End Sem", "days": 2}],
       "applications": [{"company": "Acme", "role": "ML Intern", "status": "Preparing", "days": 1}], "outbox_pending": 2}


def test_briefing_uses_real_data_and_orders_urgent_first():
    b = U.briefing(CTX, docs=3, pending_memory=1, hour=9)
    assert b["greeting"] == "Good morning, Tiru"
    kinds = [x["kind"] for x in b["cards"]]
    assert kinds[0] == "approval" and "deadline" in kinds and len(b["cards"]) <= 4
    assert b["stats"] == {"today": 1, "exams": 1, "applications": 1, "drafts": 2, "docs": 3}
    assert any("Operating Systems" in s for s in b["starters"]) and len(set(b["starters"])) == len(b["starters"])


def test_briefing_empty_user_is_still_useful():
    b = U.briefing({}, hour=20)
    assert b["greeting"] == "Good evening" and b["cards"] == [] and b["starters"]


def test_followups_are_bounded_and_never_for_memory_prompts():
    assert U.followups("chat", "", {"intent": "memory_pending"}, None, "ws", "i study at x") == []
    f = U.followups("plan", "x", {}, None, "ws", "plan my day")
    assert 1 <= len(f) <= 3 and len(set(f)) == len(f)
    assert len(U.followups("chat", "x", {}, [{"n": 1}], "ws", "what is rag")) == 3


def test_briefing_route(c):
    uid = mk(c, "kux1@x.com")
    r = c.get("/v1/karna/briefing", params={"user_id": uid})
    assert r.status_code == 200 and r.json()["starters"] and "greeting" in r.json()
    assert c.get("/v1/karna/briefing", params={"user_id": "nope"}).status_code == 404


def _events(resp):
    return [json.loads(l[5:]) for l in resp.text.split("\n\n") if l.startswith("data:")]


def test_stream_returns_same_result_as_plain_route(c):
    uid = mk(c, "kux2@x.com")
    with c.stream("POST", "/v1/jarvis/chat/stream", json={"user_id": uid, "message": "hi"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        r.read()
    ev = _events(r)
    assert ev[0]["status"] == "reading" and ev[-1]["done"] and "error" not in ev[-1]
    assert ev[-1]["result"]["action"] == "chat" and ev[-1]["result"]["reply"]
    assert isinstance(ev[-1]["followups"], list)


def test_stream_surfaces_errors_with_status(c):
    uid = mk(c, "kux3@x.com")
    with patch("main.jarvis_chat", side_effect=RuntimeError("boom")):
        with c.stream("POST", "/v1/jarvis/chat/stream", json={"user_id": uid, "message": "plan"}) as r:
            r.read()
    last = _events(r)[-1]
    assert last["done"] and last["status"] == 502 and "boom" not in last["error"]
