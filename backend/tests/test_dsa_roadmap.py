"""DSA Roadmap pure logic. Run: cd backend && python -m pytest tests/test_dsa_roadmap.py -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import date, timedelta

import pytest
import dsa_roadmap as R


def topics(**over):
    ts = R.build_topics("Python")
    for k, v in over.items():
        for t in ts:
            if t["name"] == k.replace("_", " "):
                t["status"] = v
    return ts


def test_eleven_phases_and_spec_order():
    ts = R.build_topics("Java")
    names = [p[1] for p in R.PHASES]
    assert len(names) == 11
    assert names[0] == "Foundation" and names[1] == "Arrays and Hashing" and names[-1] == "Revision and Interview Preparation"
    assert ts[0]["name"] == "Java basics"                       # language is used
    assert [t["position"] for t in ts] == list(range(len(ts)))
    assert {t["status"] for t in ts} == {"not_started"}


def test_no_practice_product_fields():
    t = R.build_topics()[0]
    assert not ({"problem_statement", "solution", "code", "testcases"} & set(t))   # links only


def test_weeks_cover_twelve_and_are_monotonic():
    ts = R.build_topics()
    weeks = [t["planned_week"] for t in ts]
    assert weeks == sorted(weeks) and min(weeks) == 1 and max(weeks) == R.WEEKS
    assert {t["planned_week"] for t in ts if t["phase_no"] == 2} == {2, 3}   # Arrays & Hashing spans weeks 2-3


def test_split_minutes_matches_spec_example():
    assert R.split_minutes(65) == (25, 30, 10)
    for d in (20, 30, 45, 60, 90, 120):
        l, p, n = R.split_minutes(d)
        assert l + p + n == d and min(l, p, n) >= 5


def test_week_number_and_overrun():
    s = date(2026, 1, 1)
    assert R.week_number(s, s) == (1, False)
    assert R.week_number(s, s + timedelta(days=7)) == (2, False)
    assert R.week_number(s, s - timedelta(days=3)) == (1, False)
    assert R.week_number(s, s + timedelta(days=7 * 12)) == (12, True)


def test_active_topic_slides_with_learner():
    ts = R.build_topics()
    assert R.active_topic(ts)["position"] == 0
    ts[0]["status"] = "practicing"
    ts[1]["status"] = "learning"                              # learning is NOT advanced
    assert R.active_topic(ts)["position"] == 1
    for t in ts:
        t["status"] = "comfortable"
    assert R.active_topic(ts) is None


def test_status_after_session_rules():
    f = R.status_after_session
    assert f("not_started", 0, None) == "learning"
    assert f("learning", 1, None) == "practicing"             # second day moves on
    assert f("not_started", 0, 4) == "practicing"             # confident after one day
    assert f("learning", 1, 2) == "learning"                  # shaky: one more day
    assert f("practicing", 2, 4) == "revised"
    assert f("practicing", 2, 5) == "comfortable"
    assert f("revised", 3, 5) == "comfortable" and f("comfortable", 4, 1) == "comfortable"


def test_pace():
    ts = R.build_topics()
    assert R.pace(ts, 1)["state"] == "on_track"
    assert R.pace(ts, 5)["state"] == "behind"                 # nothing done by week 5
    for t in ts[:8]:
        t["status"] = "practicing"
    assert R.pace(ts, 2)["state"] == "ahead"


def test_exam_season_maintenance():
    assert R.mode_for(None) == ("normal", "")
    assert R.mode_for(30)[0] == "normal" and R.mode_for(15)[0] == "normal"
    m, why = R.mode_for(10)
    assert m == "maintenance" and "10 days" in why
    assert R.mode_for(0)[0] == "maintenance" and R.mode_for(-3)[0] == "normal"
    assert R.mode_for(100, "maintenance")[0] == "maintenance" and R.mode_for(2, "normal")[0] == "normal"
    assert R.day_minutes(60, "maintenance") == 20 and R.day_minutes(60, "normal") == 60 and R.day_minutes(15, "maintenance") == 15


def test_maintenance_never_starts_new_topic_and_is_review_only():
    ts = R.build_topics()
    ts[0]["status"] = "revised"; ts[0]["confidence"] = 5
    ts[1]["status"] = "practicing"; ts[1]["confidence"] = 2
    topic, kind = R.pick_topic(ts, "maintenance")
    assert kind == "review" and topic["position"] == 1        # weakest finished topic, not the next new one
    blocks = R.day_blocks(topic, "maintenance", kind, 60)
    assert len(blocks) == 1 and blocks[0]["kind"] == "review" and blocks[0]["minutes"] == 20


def test_normal_day_has_learn_practice_notes_with_external_links():
    t = R.active_topic(R.build_topics())
    b = R.day_blocks(t, "normal", "learn", 65)
    assert [x["kind"] for x in b] == ["learn", "practice", "notes"] and [x["minutes"] for x in b] == [25, 30, 10]
    assert b[1]["url"].startswith("https://leetcode.com/problems/") and b[2]["url"] is None


def test_revision_phase_without_link_has_no_url():
    ts = R.build_topics()
    for t in ts[:-2]:
        t["status"] = "practicing"
    t = R.active_topic(ts)
    assert t["name"] == "Revise weakest topics"
    assert R.day_blocks(t, "normal", "learn", 60)[1]["url"] is None


def test_all_done_revises_weakest():
    ts = R.build_topics()
    for i, t in enumerate(ts):
        t["status"] = "revised"; t["confidence"] = 5
    ts[3]["confidence"] = 1
    t, kind = R.pick_topic(ts, "normal")
    assert kind == "revise" and t["position"] == 3


def test_week_bullets():
    ts = R.build_topics()
    b = R.week_bullets(ts, 2)
    assert b[0]["text"] == "Learn Arrays and strings" and any("Practice selected external problems" == x["text"] for x in b)
    assert b[-1]["text"].startswith("Revise ")


def test_week_days_states():
    s = date(2026, 3, 2)
    cells = R.week_days(s, 1, {s: "done", s + timedelta(days=1): "skipped"}, s + timedelta(days=3))
    assert [c["state"] for c in cells] == ["done", "skipped", "missed", "planned", "upcoming", "upcoming", "upcoming"]


def test_clean_url():
    assert R.clean_url(None) is None and R.clean_url("  ") is None
    assert R.clean_url(" https://leetcode.com/problems/two-sum/ ") == "https://leetcode.com/problems/two-sum/"
    for bad in ("javascript:alert(1)", "data:text/html,x", "ftp://x.y", "https://a b.com", "https://" + "a" * 600):
        with pytest.raises(ValueError):
            R.clean_url(bad)
