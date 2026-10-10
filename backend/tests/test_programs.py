"""Run: cd backend && python -m pytest tests/test_programs.py -q"""
import os, sys, tempfile
from datetime import date, timedelta
import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import programs_logic as L  # noqa: E402

B = "/v1/opp/programs"


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    u = c.post("/v1/auth/guest").json()["user_id"]
    c.patch("/v1/profile", params={"user_id": u}, json={"skills": "python, git, open source"})
    return u


def add(c, uid, cid):
    r = c.post(B, json={"user_id": uid, "catalog_id": cid})
    assert r.status_code == 200, r.text
    return r.json()


def confirm(c, uid, cycle_id, url, **kw):
    body = {"user_id": uid, "source_url": url, "checked_official_page": True, **kw}
    return c.put(f"{B}/cycles/{cycle_id}", json=body)


def test_catalog_has_no_dates_and_no_open_claims(c, uid):
    items = c.get(f"{B}/catalog", params={"user_id": uid}).json()["items"]
    assert {"gsoc", "hacktoberfest", "imagine_cup", "nvidia_student", "outreachy", "mlh_fellowship"} <= {i["id"] for i in items}
    assert all(i["status"] == "Verify current cycle" and "deadline" not in i for i in items)
    assert len({i["type"] for i in items}) >= 4        # not forced into one 'internship' category


def test_new_program_is_unverified_never_open(c, uid):
    p = add(c, uid, "hacktoberfest")
    cy = p["cycle"]
    assert cy["status"] == "Verify current cycle" and cy["confirmed"] is False
    assert cy["eligibility"] == "Check official rules" and cy["source"]["last_checked"] == "Not checked yet"
    assert "official page" in p["next_step"].lower() or "challenge" in p["next_step"].lower()
    assert add(c, uid, "hacktoberfest").get("duplicate")


def test_dates_on_third_party_page_are_not_trusted(c, uid):
    p = add(c, uid, "imagine_cup")
    today = date.today()
    r = confirm(c, uid, p["cycle"]["id"], "https://some-listing-site.com/imagine-cup", applications_open=str(today - timedelta(days=5)), deadline=str(today + timedelta(days=20)))
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "Verify current cycle" and j["source"]["verification"] == "third_party" and "NOT trusted" in j["note"]


def test_official_confirmation_gives_open_and_edit_drops_trust(c, uid):
    p = add(c, uid, "imagine_cup")
    cid, today = p["cycle"]["id"], date.today()
    j = confirm(c, uid, cid, "https://imaginecup.microsoft.com/en-us/rules", applications_open=str(today - timedelta(days=5)), deadline=str(today + timedelta(days=20))).json()
    assert j["status"] == "Open" and j["confirmed"] and j["source"]["last_checked"] == today.isoformat()
    # http (not https) and look-alike domains are not official
    q = add(c, uid, "gsoc")
    assert confirm(c, uid, q["cycle"]["id"], "http://developers.google.com/open-source/gsoc", deadline=str(today + timedelta(days=3))).json()["status"] == "Verify current cycle"
    assert confirm(c, uid, q["cycle"]["id"], "https://developers.google.com.evil.example/x", deadline=str(today + timedelta(days=3))).json()["status"] == "Verify current cycle"
    # editing a confirmed date without re-confirming drops the badge
    r = c.put(f"{B}/cycles/{cid}", json={"user_id": uid, "deadline": str(today + timedelta(days=40))}).json()
    assert r["status"] == "Verify current cycle" and "re-confirming" in r["note"]


def test_old_cycle_is_closed_and_paired_with_next_not_announced(c, uid):
    p = add(c, uid, "gsoc")
    cid = p["cycle"]["id"]
    confirm(c, uid, cid, "https://developers.google.com/open-source/gsoc/timeline", label="2026", applications_open="2026-03-01", deadline="2026-03-31")
    row = next(x for x in c.get(B, params={"user_id": uid}).json()["items"] if x["id"] == p["id"])
    if date.today() > date(2026, 3, 31):
        assert row["cycle"]["status"] == "Closed" and row["next_cycle"]["status"] == "Not announced"
        assert "Prepare your profile" in row["next_cycle"]["next_step"]
        assert c.post(f"{B}/cycles/{cid}/plan", params={"user_id": uid}).status_code == 409      # no tasks for a closed cycle
    nxt = c.post(f"{B}/{p['id']}/cycles", json={"user_id": uid, "label": "Next announced cycle", "year": 2027, "announced": False}).json()
    assert nxt["status"] == "Not announced"
    row = next(x for x in c.get(B, params={"user_id": uid}).json()["items"] if x["id"] == p["id"])
    assert row["cycle"]["id"] == nxt["id"]             # the newest edition is now the current one


def test_event_window_active_then_ended():
    class C:  # status rules directly, with controlled dates
        pass
    from datetime import datetime
    k = C(); k.verification, k.source_checked_at, k.announced = "official", datetime.utcnow(), None
    k.applications_open = k.deadline = None; k.event_start, k.event_end = date(2026, 10, 1), date(2026, 10, 31)
    assert L.cycle_status(k, date(2026, 10, 10))["status"] == "Active"
    assert L.cycle_status(k, date(2026, 11, 2))["status"] == "Ended"
    assert L.cycle_status(k, date(2026, 9, 20))["status"] == "Opens soon"
    k.source_checked_at = datetime.utcnow() - __import__("datetime").timedelta(days=30)
    assert L.cycle_status(k, date(2026, 10, 10))["needs_reverify"] is True


def test_plan_creates_few_real_tasks_idempotently(c, uid):
    p = add(c, uid, "hacktoberfest")
    cid = p["cycle"]["id"]
    r = c.post(f"{B}/cycles/{cid}/plan", params={"user_id": uid}).json()
    titles = [t["title"] for t in r["created"]]
    assert 1 <= len(titles) <= 3 and any("official page" in t for t in titles)       # unverified -> first task is to verify
    again = c.post(f"{B}/cycles/{cid}/plan", params={"user_id": uid}).json()
    assert again["created"] == [] and len(again["already_planned"]) == len(titles)
    today = c.get("/v1/today", params={"user_id": uid}).json()["items"]
    mine = [i for i in today if i["title"] == titles[0]]
    assert mine and mine[0]["link"] == "opportunities.html#programs" and mine[0]["minutes"] == 15
    row = c.get(f"{B}", params={"user_id": uid}).json()["items"][0]
    assert row["cycle"]["participation"] == "Planned" and row["cycle"]["open_prep_tasks"] == len(titles)


def test_submitted_needs_user_confirmation_and_history(c, uid):
    p = add(c, uid, "mlh_fellowship")
    cid = p["cycle"]["id"]
    assert c.post(f"{B}/cycles/{cid}/participation", json={"user_id": uid, "status": "Submitted"}).status_code == 409
    ok = c.post(f"{B}/cycles/{cid}/participation", json={"user_id": uid, "status": "Submitted", "user_confirms_submitted": True, "note": "applied on their site"}).json()
    assert ok["participation"] == "Submitted" and ok["history"][-1]["to"] == "Submitted"
    assert c.post(f"{B}/cycles/{cid}/participation", json={"user_id": uid, "status": "Nonsense"}).status_code == 422


def test_custom_program_needs_official_https_url_and_owner_isolation(c, uid):
    assert c.post(B, json={"user_id": uid, "name": "Campus Hack", "program_type": "hackathon"}).status_code == 422
    assert c.post(B, json={"user_id": uid, "name": "Campus Hack", "program_type": "hackathon", "official_url": "http://x.com"}).status_code == 422
    ok = c.post(B, json={"user_id": uid, "name": "Campus Hack", "program_type": "hackathon", "official_url": "https://campushack.edu/"})
    assert ok.status_code == 200 and ok.json()["type_label"] == "Hackathon"
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.put(f"{B}/cycles/{ok.json()['cycle']['id']}", json={"user_id": other, "eligibility": "x"}).status_code == 404
    assert c.get(B, params={"user_id": other}).json()["items"] == []


def test_parser_flags_yearless_dates_as_unconfirmed():
    r = L.parse_program_text("Applications open 1 March 2026\nApplication deadline: 31 March\nTeams of 2-4 students\nPrize: $10,000 for the winners", date(2026, 10, 10))["fields"]
    assert r["applications_open"]["state"] == "found" and r["deadline"]["state"] == "inferred"      # no year: never trusted
    assert r["team_min"]["value"] == 2 and r["team_max"]["value"] == 4 and "$10,000" in r["reward"]["value"]


def test_parse_endpoint_and_summary(c, uid):
    r = c.post(f"{B}/parse", json={"user_id": uid, "text": "Round 1: online submission\nDeadline: 5 Nov 2026\nMust be a currently enrolled student."}).json()
    assert r["fields"]["deadline"]["value"] == "2026-11-05" and "never trusted" not in r["note"] and "official" in r["note"]
    p = add(c, uid, "nvidia_student")
    s = c.get("/v1/opp/summary", params={"user_id": uid}).json()
    assert s["programs_to_verify"] >= 1 and "programs_live" in s
    assert c.delete(f"{B}/{p['id']}", params={"user_id": uid}).json()["status"] == "deleted"
