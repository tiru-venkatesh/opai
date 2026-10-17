"""DSA Coach: mastery rules, weakness diagnosis, tomorrow's plan, attempts API and the opt-in streak reminders."""
import os, sys, tempfile, uuid as _uuid
from datetime import date, datetime, timedelta
import pytest
os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["OPAI_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import dsa_coach as C  # noqa: E402
import reminders as RM  # noqa: E402
from database import Notification, SessionLocal  # noqa: E402

D = date(2026, 10, 1)


# ------------------------------------------------------------ pure rules
def test_result_honesty():
    assert C.effective_result("solved", 0, False) == "solved"
    assert C.effective_result("solved", 2, False) == "hinted"
    assert C.effective_result("solved", 0, True) == "hinted"
    assert C.effective_result("failed", 0, False) == "failed"


def test_mastery_ladder_and_resets():
    m = C.next_mastery(0, 0, 0, "solved", D)
    assert (m["stage"], m["next_review"], m["clean_resolves"]) == (1, D + timedelta(days=1), 0)      # first try is not a re-solve
    m = C.next_mastery(m["stage"], 0, 1, "solved", D)
    assert (m["stage"], m["next_review"], m["clean_resolves"]) == (2, D + timedelta(days=3), 1)
    h = C.next_mastery(2, 1, 2, "hinted", D)
    assert (h["stage"], h["next_review"]) == (1, D + timedelta(days=2))
    f = C.next_mastery(4, 3, 5, "failed", D)
    assert (f["stage"], f["next_review"]) == (0, D + timedelta(days=1))


def test_mastered_needs_two_clean_resolves():
    stage = clean = n = 0
    for _ in range(5):
        m = C.next_mastery(stage, clean, n, "solved", D)
        stage, clean, n = m["stage"], m["clean_resolves"], m["attempts"]
    assert stage == 5 and clean == 4 and m["state"] == "mastered"
    m = C.next_mastery(5, 1, 6, "solved", D)
    assert m["clean_resolves"] == 2 and m["state"] == "mastered"
    assert C.mastery_state(5, 1, 6, "solved") != "mastered"


def _att(p, r, ago, resolve=False, mistakes=()):
    return dict(pattern=p, result=r, on=D - timedelta(days=ago), is_resolve=resolve, mistakes=list(mistakes))


def test_weakness_needs_evidence_and_ignores_untested():
    st = C.pattern_stats([_att("dp", "failed", 0)], D)
    assert st["dp"]["label"] == "not enough data"            # one failure is not a diagnosis
    assert st["graphs"]["label"] == "untested" and st["graphs"]["weakness"] is None
    assert C.weakest_patterns(st) == []
    st = C.pattern_stats([_att("dp", "failed", 0, mistakes=["wrong_pattern"]), _att("dp", "failed", 1, mistakes=["wrong_pattern", "edge_case"]),
                          _att("dp", "hinted", 2), _att("trees", "solved", 0), _att("trees", "solved", 1), _att("trees", "solved", 2)], D)
    assert st["dp"]["label"] == "weak" and st["trees"]["label"] == "strong"
    assert [s["pattern"] for s in C.weakest_patterns(st)] == ["dp"]
    assert st["dp"]["top_mistakes"][0]["tag"] == "wrong_pattern" and st["dp"]["top_mistakes"][0]["count"] == 2


def test_recent_results_outweigh_old_ones():
    old_fail = [_att("dp", "failed", 60), _att("dp", "failed", 61), _att("dp", "failed", 62), _att("dp", "solved", 0), _att("dp", "solved", 1), _att("dp", "solved", 2)]
    assert C.pattern_stats(old_fail, D)["dp"]["label"] in ("steady", "strong")
    assert C.pattern_stats([_att("dp", "failed", 0, True), _att("dp", "failed", 1, True)], D)["dp"]["label"] == "weak"


def test_resolve_stats_counts_repeats_only():
    rows = [dict(is_resolve=False, result="solved"), dict(is_resolve=True, result="solved"), dict(is_resolve=True, result="hinted")]
    assert C.resolve_stats(rows) == dict(resolves=2, clean=1, rate=50)
    assert C.resolve_stats([dict(is_resolve=False, result="solved")])["rate"] is None


def test_pick_new_matches_strength_and_skips_seen():
    easy = C.pick_new("dp", 0.2, [])
    assert easy["difficulty"] == "Easy" and easy["key"] == "climbing-stairs"
    nxt = C.pick_new("dp", 0.2, ["climbing-stairs"])
    assert nxt["key"] != "climbing-stairs" and nxt["difficulty"] == "Medium"
    assert C.pick_new("dp", 0.2, [p[0] for p in C.PROBLEM_BANK if p[3] == "dp"]) is None


def _mrow(key, pattern, due_ago, stage=1, result="solved", state="learning"):
    return dict(key=key, title=key, url=f"https://leetcode.com/problems/{key}/", pattern=pattern, difficulty="Medium", stage=stage, state=state,
                last_result=result, last_attempt=D - timedelta(days=due_ago + 1), next_review=D - timedelta(days=due_ago))


def test_plan_has_new_revision_mixed_and_hides_mixed_pattern():
    atts = [_att("dp", "failed", 0), _att("dp", "failed", 1), _att("dp", "hinted", 2)]
    st = C.pattern_stats(atts, D)
    mastery = [_mrow("two-sum", "arrays-hashing", 2), _mrow("coin-change", "dp", 0, result="failed", state="shaky")]
    plan = C.plan_tomorrow(st, mastery, {"two-sum", "coin-change"}, D, roadmap_pattern="trees")
    by = {i["slot"]: i for i in plan["items"]}
    assert set(by) == {"new", "revision", "mixed"}
    assert by["revision"]["key"] == "two-sum"                          # most overdue first
    assert by["new"]["pattern"] == "dp" and "weakest" in by["new"]["reason"]
    assert by["mixed"]["pattern"] != by["new"]["pattern"] and by["mixed"]["reveal_pattern"] is False
    assert len({i["key"] for i in plan["items"]}) == 3                 # never the same problem twice


def test_plan_for_a_brand_new_learner_follows_the_roadmap():
    st = C.pattern_stats([], D)
    plan = C.plan_tomorrow(st, [], set(), D, roadmap_pattern="sliding-window")
    by = {i["slot"]: i for i in plan["items"]}
    assert by["revision"]["title"] is None and by["new"]["pattern"] == "sliding-window" and by["mixed"]["title"]


def test_quiet_hours_wrap_midnight():
    assert C.in_quiet_hours("23:30", "23:00", "07:00") and C.in_quiet_hours("03:00", "23:00", "07:00")
    assert not C.in_quiet_hours("07:00", "23:00", "07:00") and not C.in_quiet_hours("22:30", "23:00", "07:00")
    assert C.in_quiet_hours("00:30", "00:00", "07:00") and not C.in_quiet_hours("23:45", "00:00", "07:00")
    assert not C.in_quiet_hours("12:00", "08:00", "08:00")           # empty window


def test_practice_streak_today_stays_open():
    days = [D - timedelta(days=i) for i in (1, 2, 3)]
    s = C.practice_streak(days, D)
    assert s["current"] == 3 and s["at_risk"] and not s["done_today"]
    s = C.practice_streak(days + [D], D)
    assert s["current"] == 4 and not s["at_risk"]
    assert C.practice_streak([D - timedelta(days=3)], D)["current"] == 0


def test_nudge_rules():
    on = dict(streak=C.practice_streak([D - timedelta(days=1), D - timedelta(days=2)], D), sent_today=0)
    assert C.nudge(**on, slot=0, local_hhmm="20:00")["tone"] == "gentle"
    assert C.nudge(**on, slot=1, local_hhmm="22:30")["tone"] == "risk"
    assert C.nudge(**on, slot=2, local_hhmm="23:45")["tone"] == "last"
    assert C.nudge(**on, slot=2, local_hhmm="23:45", quiet=("23:00", "07:00")) is None            # quiet hours win
    assert C.nudge(streak=on["streak"], sent_today=3, slot=2, local_hhmm="23:45") is None          # daily cap
    done = C.practice_streak([D, D - timedelta(days=1)], D)
    assert C.nudge(streak=done, sent_today=0, slot=0, local_hhmm="20:00") is None                  # already practised
    none = C.practice_streak([], D)
    assert C.nudge(streak=none, sent_today=0, slot=0, local_hhmm="20:00")["tone"] == "gentle"
    assert C.nudge(streak=none, sent_today=1, slot=1, local_hhmm="22:30") is None                  # no streak, no warnings
    away = C.practice_streak([D - timedelta(days=5)], D)
    assert C.nudge(streak=away, sent_today=0, slot=0, local_hhmm="20:00")["tone"] == "comeback"
    assert C.nudge(streak=away, sent_today=1, slot=1, local_hhmm="22:30") is None                  # recovery: one gentle note only


# ------------------------------------------------------------ API
@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


def new_user(c):
    uid = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    c.put("/v1/notifications/settings", json={"user_id": uid, "timezone": "Asia/Kolkata"})
    return uid


def log(c, uid, **kw):
    body = {"user_id": uid, "result": "solved", **kw}
    r = c.post("/v1/dsa/attempts", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_log_attempt_fills_from_bank_and_schedules_revision(c):
    uid = new_user(c)
    out = log(c, uid, url="https://leetcode.com/problems/two-sum/")
    assert out["attempt"]["title"] == "Two Sum" and out["attempt"]["pattern"] == "arrays-hashing"
    assert out["mastery"]["stage"] == 1 and out["mastery"]["due_in_days"] == 1
    again = log(c, uid, url="https://leetcode.com/problems/two-sum/", result="hinted", hints_used=1)
    assert again["attempt"]["is_resolve"] is True and again["mastery"]["attempts"] == 2 and again["mastery"]["state"] == "shaky"


def test_solved_with_hints_is_downgraded_and_no_mistakes_on_clean_solve(c):
    uid = new_user(c)
    o = log(c, uid, title="Two Sum", hints_used=2, mistakes=["edge_case"])
    assert o["attempt"]["result"] == "hinted" and o["attempt"]["mistakes"] == ["edge_case"]
    o = log(c, uid, title="Valid Anagram", mistakes=["edge_case"])
    assert o["attempt"]["result"] == "solved" and o["attempt"]["mistakes"] == []


def test_validation(c):
    uid = new_user(c)
    assert c.post("/v1/dsa/attempts", json=dict(user_id=uid, result="solved")).status_code == 422
    assert c.post("/v1/dsa/attempts", json=dict(user_id=uid, result="maybe", title="x")).status_code == 422
    assert c.post("/v1/dsa/attempts", json=dict(user_id=uid, result="solved", title="x", pattern="magic")).status_code == 422
    assert c.post("/v1/dsa/attempts", json=dict(user_id=uid, result="solved", title="x", mistakes=["nope"])).status_code == 422
    assert c.post("/v1/dsa/attempts", json=dict(user_id=uid, result="solved", title="x", url="javascript:alert(1)")).status_code == 422
    assert c.post("/v1/dsa/attempts", json=dict(user_id="missing", result="solved", title="x")).status_code == 404


def test_active_recall_is_scored(c):
    uid = new_user(c)
    assert log(c, uid, title="Two Sum", predicted_pattern="arrays-hashing")["attempt"]["recall_correct"] is True
    assert log(c, uid, title="Valid Anagram", predicted_pattern="dp")["attempt"]["recall_correct"] is False
    k = c.get("/v1/dsa/coach", params={"user_id": uid}).json()
    assert k["recall"] == dict(tried=2, correct=1, rate=50)


def test_coach_diagnoses_weak_pattern_and_plans_around_it(c):
    uid = new_user(c)
    for t in ("Climbing Stairs", "House Robber", "Coin Change"):
        log(c, uid, title=t, result="failed", mistakes=["wrong_pattern"])
    for t in ("Maximum Depth of Binary Tree", "Invert Binary Tree", "Diameter of Binary Tree"):
        log(c, uid, title=t)
    k = c.get("/v1/dsa/coach", params={"user_id": uid}).json()
    assert k["weakest"][0]["pattern"] == "dp" and k["weakest"][0]["top_mistakes"][0]["tag"] == "wrong_pattern"
    by = {i["slot"]: i for i in k["plan"]["items"]}
    assert by["new"]["pattern"] == "dp" and by["new"]["key"] not in ("climbing-stairs", "house-robber", "coin-change")
    assert by["revision"]["key"] in ("climbing-stairs", "house-robber", "coin-change")
    assert by["mixed"]["reveal_pattern"] is False
    assert k["streak"]["current"] == 1 and k["streak"]["done_today"] is True
    assert k["mastery_counts"]["learning"] >= 3


def test_delete_attempt_rebuilds_mastery(c):
    uid = new_user(c)
    a = log(c, uid, title="Two Sum")
    b = log(c, uid, title="Two Sum", result="failed")
    k = c.delete(f"/v1/dsa/attempts/{b['attempt']['id']}", params={"user_id": uid}).json()
    due = c.get("/v1/dsa/attempts", params={"user_id": uid}).json()
    assert len(due) == 1 and due[0]["is_resolve"] is False
    assert k["recent"][0]["title"] == "Two Sum"
    c.delete(f"/v1/dsa/attempts/{a['attempt']['id']}", params={"user_id": uid})
    assert c.get("/v1/dsa/coach", params={"user_id": uid}).json()["mastery_counts"]["learning"] == 0
    assert c.delete(f"/v1/dsa/attempts/{a['attempt']['id']}", params={"user_id": uid}).status_code == 404


def test_cannot_touch_another_users_attempts(c):
    a, b = new_user(c), new_user(c)
    att = log(c, a, title="Two Sum")["attempt"]
    assert c.delete(f"/v1/dsa/attempts/{att['id']}", params={"user_id": b}).status_code == 404
    assert c.get("/v1/dsa/attempts", params={"user_id": b}).json() == []


# ------------------------------------------------------------ opt-in streak reminders through the real scheduler
def _tick(uid, now):
    db = SessionLocal()
    try:
        RM.fire_due(db, now=now, user_id=uid)
        return [(n.title, n.kind) for n in db.query(Notification).filter(Notification.user_id == uid, Notification.kind == "dsa_streak")
                .order_by(Notification.created_at).all()]
    finally:
        db.close()


def _ist(local_dt):
    return local_dt - timedelta(minutes=330)


def _reminders(uid):
    from database import Reminder
    db = SessionLocal()
    try:
        return sorted(db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "dsa_streak", Reminder.status == "pending").all(), key=lambda r: r.remind_at)
    finally:
        db.close()


def test_reminders_are_off_by_default_and_opt_in(c):
    uid = new_user(c)
    s = c.get("/v1/dsa/coach/reminders", params={"user_id": uid}).json()
    assert s["enabled"] is False and s["times"] == ["20:00", "22:30", "23:45"] and _reminders(uid) == []
    s = c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": True}).json()
    assert s["enabled"] and len(_reminders(uid)) == 3
    s = c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": False}).json()
    assert not s["enabled"] and _reminders(uid) == []
    assert c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "times": ["25:00"]}).status_code == 422
    assert c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "times": ["08:00", "09:00", "10:00", "11:00"]}).status_code in (422,)


def test_streak_reminders_fire_in_order_and_stop_once_you_practise(c):
    uid = new_user(c)
    # a 2-day streak ending yesterday, so tonight is "at risk"
    db = SessionLocal()
    from database import DsaAttempt
    today_local = (datetime.utcnow() + timedelta(minutes=330)).date()
    for ago in (1, 2):
        db.add(DsaAttempt(user_id=uid, problem_key=f"k{ago}", title=f"k{ago}", result="solved", attempted_on=today_local - timedelta(days=ago)))
    db.commit(); db.close()
    c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": True, "quiet_start": "00:00", "quiet_end": "07:00"})
    rs = _reminders(uid)
    assert len(rs) == 3
    base = rs[0].remind_at                                               # first upcoming slot (UTC)
    # Move all three due reminders to "today" local times so a single tick can see them
    db = SessionLocal()
    from database import Reminder
    day = today_local
    for r, hhmm in zip(db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "dsa_streak", Reminder.status == "pending").order_by(Reminder.title).all(), ("20:00", "22:30", "23:45")):
        h, m = map(int, hhmm.split(":"))
        r.remind_at = _ist(datetime(day.year, day.month, day.day, h, m))
    db.commit(); db.close()
    out = _tick(uid, _ist(datetime(day.year, day.month, day.day, 20, 1)))
    assert [t for t, _ in out] == ["Today's DSA practice"]
    out = _tick(uid, _ist(datetime(day.year, day.month, day.day, 22, 31)))
    assert [t for t, _ in out][-1] == "Your 2-day streak is open" and len(out) == 2
    # practise before the last call: it must not be sent
    log(c, uid, title="Two Sum")
    out = _tick(uid, _ist(datetime(day.year, day.month, day.day, 23, 46)))
    assert len(out) == 2
    # and a repeat tick never duplicates
    assert len(_tick(uid, _ist(datetime(day.year, day.month, day.day, 23, 47)))) == 2


def test_turning_reminders_off_beats_an_already_due_row(c):
    uid = new_user(c)
    c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": True})
    db = SessionLocal()
    from database import Reminder
    rows = db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "dsa_streak", Reminder.status == "pending").all()
    for r in rows:
        r.remind_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit(); db.close()
    c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": False})
    assert _tick(uid, datetime.utcnow()) == []


def test_comeback_note_after_three_missed_days(c):
    uid = new_user(c)
    from database import DsaAttempt, Reminder
    db = SessionLocal()
    day = (datetime.utcnow() + timedelta(minutes=330)).date()
    db.add(DsaAttempt(user_id=uid, problem_key="old", title="old", result="solved", attempted_on=day - timedelta(days=6)))
    db.commit(); db.close()
    c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": True})
    db = SessionLocal()
    for r, hhmm in zip(db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "dsa_streak", Reminder.status == "pending").order_by(Reminder.title).all(), ("20:00", "22:30", "23:45")):
        h, m = map(int, hhmm.split(":"))
        r.remind_at = _ist(datetime(day.year, day.month, day.day, h, m))
    db.commit(); db.close()
    out = _tick(uid, _ist(datetime(day.year, day.month, day.day, 20, 5)))
    assert out == [("Ready for a light restart?", "dsa_streak")]          # away 6 days: one gentle comeback note, no streak talk
    out = _tick(uid, _ist(datetime(day.year, day.month, day.day, 23, 50)))
    assert len(out) == 1                      # 10:30 PM is >45 min stale and the 11:45 PM slot is a warning slot: neither adds pressure


def test_late_scheduler_drops_stale_nudges(c):
    uid = new_user(c)
    from database import DsaAttempt, Reminder
    day = (datetime.utcnow() + timedelta(minutes=330)).date()
    db = SessionLocal()
    db.add(DsaAttempt(user_id=uid, problem_key="y", title="y", result="solved", attempted_on=day - timedelta(days=1)))
    db.commit(); db.close()
    c.put("/v1/dsa/coach/reminders", json={"user_id": uid, "enabled": True})
    db = SessionLocal()
    for r, hhmm in zip(db.query(Reminder).filter(Reminder.user_id == uid, Reminder.kind == "dsa_streak", Reminder.status == "pending").order_by(Reminder.title).all(), ("20:00", "22:30", "23:45")):
        h, m = map(int, hhmm.split(":"))
        r.remind_at = _ist(datetime(day.year, day.month, day.day, h, m))
    db.commit(); db.close()
    assert _tick(uid, _ist(datetime(day.year, day.month, day.day, 23, 50)))[-1][0] == "Last call for today"   # 5 min late: still sent
    assert len(_tick(uid, _ist(datetime(day.year, day.month, day.day, 23, 55)))) == 1                         # 8 PM / 10:30 PM were hours late: dropped, not replayed
