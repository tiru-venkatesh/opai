"""Run: cd backend && python -m pytest tests/test_resume_lab_api.py -q"""
import os
import sys
import tempfile

import pytest

os.environ["GROQ_API_KEY"] = ""
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import resume_lab_api as L  # noqa: E402

ML = """Asha Rao
Skills: Python, PyTorch, RAG, SQL
Projects
- Built a RAG assistant in Python and FastAPI that answers questions over 500 documents with 92% retrieval accuracy
- Fine-tuned a PyTorch classifier on 20k samples, improving F1 by 8%
- Responsible for various tasks in the team
Experience
- Developed REST APIs with Docker and deployed them on AWS serving 1,000+ requests per day
"""
WEB = """Asha Rao
Skills: React, TypeScript, Node, CSS
Projects
- Designed a React dashboard with TypeScript that reduced report time by 40%
- Worked on the website frontend
- Built a Node API with 12 endpoints and automated tests
"""


@pytest.fixture(scope="module")
def c():
    with TestClient(main.app) as client:
        yield client


@pytest.fixture()
def uid(c):
    return c.post("/v1/auth/guest").json()["user_id"]


def imp(c, uid, items):
    return c.post("/v1/resume-lab/import", json={"user_id": uid, "resumes": items})


def two(c, uid):
    r = imp(c, uid, [{"label": "ML", "target_role": "ML intern", "text": ML}, {"label": "Web", "target_role": "frontend", "text": WEB}])
    assert r.status_code == 200, r.text
    return r.json()


def test_parse_finds_bullets_and_skips_skills_line():
    p = L.parse_resume(ML)
    assert len(p["bullets"]) == 4 and all("Skills" not in b["text"] for b in p["bullets"])
    st = L.bullet_stats(p["bullets"])
    assert st["metric_ratio"] >= 0.75 and "responsible for" in st["weak"]


def test_import_dedupes_and_limits(c, uid):
    r = two(c, uid)
    assert len(r["created"]) == 2 and r["total_versions"] == 2
    r = imp(c, uid, [{"label": "ML copy", "text": ML}, {"label": "web", "text": WEB + " "}])
    j = r.json()
    assert j["created"] == [] and len(j["skipped"]) == 2
    lib = c.get("/v1/resume-lab/library", params={"user_id": uid}).json()
    assert lib["count"] == 2 and lib["versions"][0]["bullets"] >= 3


def test_library_cap_ten(c, uid):
    items = [{"label": f"v{i}", "text": WEB + f"\n- Built project number {i} with extra detail for uniqueness here"} for i in range(10)]
    assert len(imp(c, uid, items).json()["created"]) == 10
    r = imp(c, uid, [{"label": "eleventh", "text": ML}]).json()
    assert r["created"] == [] and "full" in r["skipped"][0]["reason"]


def test_match_picks_right_version_and_reports_gaps(c, uid):
    two(c, uid)
    job = "ML Intern. We need Python, PyTorch and RAG experience. Kubernetes a plus. RAG pipelines, PyTorch models."
    r = c.post("/v1/resume-lab/match", json={"user_id": uid, "job_text": job}).json()
    assert r["best"]["label"] == "ML"
    assert "kubernetes" in r["gaps_in_every_version"]
    assert "python" not in r["gaps_in_every_version"]
    web = c.post("/v1/resume-lab/match", json={"user_id": uid, "job_text": "Frontend intern: React, TypeScript, Node."}).json()
    assert web["best"]["label"] == "Web"


def test_bullet_search_and_scope(c, uid):
    two(c, uid)
    r = c.post("/v1/resume-lab/bullets/search", json={"user_id": uid, "query": "retrieval question answering documents", "k": 3}).json()
    assert r["results"] and "RAG" in r["results"][0]["bullet"]
    ids = {x["id"]: x["label"] for x in c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["versions"]}
    web_id = [k for k, v in ids.items() if v == "Web"][0]
    r = c.post("/v1/resume-lab/bullets/search", json={"user_id": uid, "query": "retrieval", "resume_id": web_id}).json()
    assert all(x["resume_id"] == web_id for x in r["results"])


def test_tailor_is_selection_only(c, uid):
    two(c, uid)
    r = c.post("/v1/resume-lab/tailor", json={"user_id": uid, "job_text": "Python PyTorch RAG internship, Kubernetes"}).json()
    assert r["base_resume"]["label"] == "ML"
    allb = [x["bullet"] for x in r["lead_with"] + r["consider_from_other_versions"]]
    assert allb and all(b in ML or b in WEB for b in allb)          # verbatim from the user's own text
    assert "kubernetes" in r["gaps"]


def test_bank_follows_edits_and_deletes(c, uid):
    two(c, uid)
    ml_id = [v["id"] for v in c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["versions"] if v["label"] == "ML"][0]
    c.post("/v1/resume-lab/bullets/search", json={"user_id": uid, "query": "docker aws"})
    c.delete(f"/v1/resumes/{ml_id}")
    r = c.post("/v1/resume-lab/bullets/search", json={"user_id": uid, "query": "docker aws deployed requests"}).json()
    assert all(x["resume_id"] != ml_id for x in r["results"])


def test_insights_needs_two_then_reports(c, uid):
    assert c.get("/v1/resume-lab/insights", params={"user_id": uid}).json()["ready"] is False
    two(c, uid)
    j = c.get("/v1/resume-lab/insights", params={"user_id": uid}).json()
    assert j["ready"] and j["best_versions"] and any("responsible for" in t or "worked on" in t for t in j["tips"])


def test_isolation(c, uid):
    two(c, uid)
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.get("/v1/resume-lab/library", params={"user_id": other}).json()["count"] == 0
    assert c.post("/v1/resume-lab/match", json={"user_id": other, "job_text": "python"}).status_code == 409
    r = c.post("/v1/resume-lab/bullets/search", json={"user_id": other, "query": "python rag"}).json()
    assert r["results"] == []
