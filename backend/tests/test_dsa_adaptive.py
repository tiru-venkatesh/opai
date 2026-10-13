"""Adaptive roadmap length + resource preferences. Run: cd backend && python -m pytest tests/test_dsa_adaptive.py -q"""
from tests.test_dsa_api import c, uid, make   # noqa: F401  (shared fixtures)
import dsa_roadmap as R


def test_weeks_follow_daily_time_and_stay_contiguous():
    assert [R.weeks_for(m) for m in (20, 25, 30, 45, 60, 90)] == [18, 18, 16, 14, 12, 10]
    for w in (10, 12, 14, 16, 18):
        ts = R.build_topics("Python", weeks=w)
        weeks = [t["planned_week"] for t in ts]
        assert weeks == sorted(weeks) and weeks[0] == 1 and weeks[-1] == w
    assert [t["planned_week"] for t in R.build_topics("Python", weeks=12)] == [t["planned_week"] for t in R.build_topics("Python")]


def test_plan_length_and_rescale_on_settings_change(c, uid):
    s = make(c, uid, daily_minutes=30)
    assert s["progress"]["weeks"] == 16 and s["plan"]["weeks"] == 16 and s["phases"][-1]["weeks"][1] == 16
    r = c.patch("/v1/dsa/plan", json={"user_id": uid, "daily_minutes": 60}).json()
    assert r["progress"]["weeks"] == 12 and r["phases"][-1]["weeks"] == [12, 12]


def test_resources_inherited_and_custom_wins(c, uid):
    s = make(c, uid, daily_minutes=60)
    t0 = s["phases"][1]["topics"][1]                                  # Hash maps and sets (has a fixed LeetCode problem by default)
    assert t0["practice_url"] == "https://leetcode.com/problemset/" and t0["learn_url"] == "https://neetcode.io/roadmap"
    r = c.patch("/v1/dsa/plan", json={"user_id": uid, "resources": {"learn": {"source": "YouTube"}, "practice": {"source": "Codeforces"}}}).json()
    t1 = r["phases"][1]["topics"][1]
    assert "youtube.com/results" in t1["learn_url"] and t1["practice_url"] == "https://codeforces.com/problemset"
    # a link the learner edited stays; re-saving an inherited value does not pin it
    c.patch(f"/v1/dsa/topics/{t1['id']}", json={"user_id": uid, "practice_url": "https://leetcode.com/problems/3sum/"})
    c.patch(f"/v1/dsa/plan", json={"user_id": uid, "resources": {"practice": {"source": "LeetCode"}}})
    r = c.get("/v1/dsa", params={"user_id": uid}).json()
    assert r["phases"][1]["topics"][1]["practice_url"].endswith("3sum/") and r["phases"][1]["topics"][0]["practice_url"] == "https://leetcode.com/problemset/"
    c.patch(f"/v1/dsa/topics/{t0['id']}", json={"user_id": uid, "learn_url": r["phases"][1]["topics"][1]["learn_url"], "notes": "x"})


def test_resource_validation_and_notes_link(c, uid):
    make(c, uid)
    assert c.patch("/v1/dsa/plan", json={"user_id": uid, "resources": {"learn": {"source": "Udemy"}}}).status_code == 422
    assert c.patch("/v1/dsa/plan", json={"user_id": uid, "resources": {"practice": {"source": "Custom"}}}).status_code == 422
    assert c.patch("/v1/dsa/plan", json={"user_id": uid, "resources": {"notes": {"source": "Notion", "url": "javascript:alert(1)"}}}).status_code == 422
    r = c.patch("/v1/dsa/plan", json={"user_id": uid, "resources": {"notes": {"source": "Notion", "url": "https://notion.so/my-dsa"}}}).json()
    assert r["plan"]["resources"]["notes"]["source"] == "Notion"
    assert [b["url"] for b in r["today"]["blocks"] if b["kind"] == "notes"] == ["https://notion.so/my-dsa"]
