"""Data-integrity checks for the hackathon list in frontend/projects.html.
Run: cd backend && python -m pytest tests/test_hackathon_data.py -q"""
import json, os, re, shutil, subprocess
import pytest

PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "projects.html")
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is needed to read the JS arrays")


def _arrays():
    src = open(PAGE, encoding="utf-8").read()
    h = re.search(r"var H=\[\n(.*?)\n\];", src, re.S).group(0)
    r = re.search(r"var R=\[\n(.*?)\n\];", src, re.S).group(0)
    code = "var DEVSEARCH='https://devpost.com/hackathons?search=';" + h + r + ";console.log(JSON.stringify({H:H,R:R}))"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_counts_and_unique_ids():
    d = _arrays()
    assert len(d["H"]) == 29 and len(d["R"]) == 25
    ids = [h["id"] for h in d["H"]]
    assert len(ids) == len(set(ids))
    names = [x["n"] for x in d["H"]] + [x["n"] for x in d["R"]]
    assert len(names) == len(set(names))


def test_every_entry_has_https_link_and_valid_deadline():
    d = _arrays()
    for h in d["H"]:
        assert h["u"].startswith("https://"), h["id"]
        assert re.fullmatch(r"2026-\d\d-\d\dT\d\d:\d\d:00[+-]\d\d:\d\d", h["d"]), h["id"]
        assert h["note"] and h["cat"] and h["ev"], h["id"]
    for r in d["R"]:
        assert r["u"].startswith("https://") and r["g"] and r["f"], r["n"]


def test_us_time_deadlines_name_the_organizer_zone():
    d = {h["id"]: h for h in _arrays()["H"]}
    assert d["paypal-ai"]["d"] == "2026-11-12T12:00:00-08:00" and "PST" in d["paypal-ai"]["tz"]
    assert d["build-ai"]["d"] == "2026-10-26T17:00:00-04:00" and "EDT" in d["build-ai"]["tz"]


def test_five_top_picks():
    d = _arrays()
    picks = [h["n"] for h in d["H"] if h.get("fit")] + [r["n"] for r in d["R"] if r.get("fit")]
    assert len(picks) == 5
