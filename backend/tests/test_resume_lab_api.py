"""Run: cd backend && python -m pytest tests/test_resume_lab_api.py -q"""
import uuid as _uuid
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
    return c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]


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
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.get("/v1/resume-lab/library", params={"user_id": other}).json()["count"] == 0
    assert c.post("/v1/resume-lab/match", json={"user_id": other, "job_text": "python"}).status_code == 409
    r = c.post("/v1/resume-lab/bullets/search", json={"user_id": other, "query": "python rag"}).json()
    assert r["results"] == []


# ---------------------------------------------------------------- review / coach / compare / build / export / attach
def _ids(c, uid):
    return {v["label"]: v["id"] for v in c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["versions"]}


def test_review_endpoint_scores_and_checks_keywords(c, uid):
    two(c, uid)
    ids = _ids(c, uid)
    r = c.post("/v1/resume-lab/review", json={"user_id": uid, "resume_id": ids["ML"], "job_text": "Python PyTorch Kubernetes Kubernetes Python"}).json()
    assert 0 <= r["score"] <= 100 and r["checks"] and "kubernetes" in r["keywords"]["missing"]
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.post("/v1/resume-lab/review", json={"user_id": other, "resume_id": ids["ML"]}).status_code == 404


def test_coach_returns_questions_and_never_a_ungrounded_rewrite(c, uid):
    r = c.post("/v1/resume-lab/coach", json={"user_id": uid, "bullet": "- Responsible for various tasks in the team", "use_ai": False}).json()
    assert not r["ok"] and r["questions"] and r["rewrite"] is None
    # even if an AI were enabled, a rewrite that invents content is rejected (unit-tested in test_resume_lab_core)


def test_compare_endpoint(c, uid):
    two(c, uid)
    ids = _ids(c, uid)
    r = c.post("/v1/resume-lab/compare", json={"user_id": uid, "a_id": ids["ML"], "b_id": ids["Web"]}).json()
    assert r["a"]["label"] == "ML" and r["only_in_a"] and r["only_in_b"]
    assert c.post("/v1/resume-lab/compare", json={"user_id": uid, "a_id": ids["ML"], "b_id": ids["ML"]}).status_code == 422


def test_build_only_accepts_own_bullets_as_extras(c, uid):
    two(c, uid)
    ids = _ids(c, uid)
    ok = c.post("/v1/resume-lab/build", json={"user_id": uid, "resume_id": ids["ML"], "job_text": "Python PyTorch RAG internship",
                "exclude": ["Responsible for various tasks in the team"],
                "extras": [{"text": "Designed a React dashboard with TypeScript that reduced report time by 40%"}]})
    assert ok.status_code == 200, ok.text
    j = ok.json()
    assert "Responsible for various tasks in the team" in j["dropped"] and j["added"] and "React dashboard" in j["text"]
    bad = c.post("/v1/resume-lab/build", json={"user_id": uid, "resume_id": ids["ML"], "extras": [{"text": "Led a team of 50 engineers at Google"}]})
    assert bad.status_code == 422


@pytest.mark.parametrize("fmt,magic", [("txt", b"Asha"), ("docx", b"PK"), ("pdf", b"%PDF")])
def test_export_formats(c, uid, fmt, magic):
    two(c, uid)
    ids = _ids(c, uid)
    r = c.post("/v1/resume-lab/export", json={"user_id": uid, "resume_id": ids["ML"], "format": fmt})
    assert r.status_code == 200 and r.content.startswith(magic) and "attachment" in r.headers["content-disposition"]


def test_attach_links_application_and_replaces_on_repeat(c, uid):
    two(c, uid)
    ids = _ids(c, uid)
    app = c.post("/v1/applications", json={"user_id": uid, "company": "Example AI", "role": "ML Intern"}).json()
    body = {"user_id": uid, "resume_id": ids["ML"], "application_id": app["id"], "job_text": "Python PyTorch RAG"}
    r1 = c.post("/v1/resume-lab/attach", json=body).json()
    assert r1["replaced_previous"] is False and r1["label"].startswith("Tailored: Example AI")
    n1 = c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["count"]
    r2 = c.post("/v1/resume-lab/attach", json={**body, "exclude": ["Responsible for various tasks in the team"]}).json()
    assert r2["replaced_previous"] is True and r2["resume_id"] == r1["resume_id"]
    assert c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["count"] == n1       # no duplicate versions
    other = c.post("/v1/auth/dev-login", params={"email": "u-" + _uuid.uuid4().hex[:10] + "@test.local"}).json()["user_id"]
    assert c.post("/v1/resume-lab/attach", json={**body, "user_id": other}).status_code in (404, 409)


def test_attach_respects_library_limit(c, uid):
    items = [{"label": f"v{i}", "text": WEB + f"\n- Built project number {i} with extra detail for uniqueness here"} for i in range(10)]
    imp(c, uid, items)
    ids = _ids(c, uid)
    app = c.post("/v1/applications", json={"user_id": uid, "company": "X", "role": "Y"}).json()
    r = c.post("/v1/resume-lab/attach", json={"user_id": uid, "resume_id": ids["v0"], "application_id": app["id"]})
    assert r.status_code == 409


def test_import_files_uploads_indexes_and_skips_duplicates(c, uid):
    import io
    body = ("Asha Rao\nSkills: Python, FastAPI, RAG\nExperience\n- Built a RAG assistant in Python that cut support lookup time by 40%\n"
            "- Developed REST APIs with FastAPI serving 2000 requests per day\nProjects\n- Created a resume parser using spaCy for 500 documents\n")
    if True:
        files = [("files", ("ML_v1.txt", io.BytesIO(body.encode()), "text/plain")),
                 ("files", ("copy.txt", io.BytesIO(body.encode()), "text/plain")),
                 ("files", ("bad.exe", io.BytesIO(b"x" * 200), "application/octet-stream"))]
        r = c.post("/v1/resume-lab/import-files", data={"user_id": uid, "target_role": "ML intern"}, files=files).json()
        assert [x["label"] for x in r["created"]] == ["ML_v1"]
        reasons = " ".join(x["reason"] for x in r["skipped"])
        assert "identical text" in reasons and "unsupported" in reasons
        hits = c.post("/v1/resume-lab/bullets/search", params={"user_id": uid}, json={"query": "FastAPI REST APIs", "k": 3}).json()
        assert "FastAPI" in str(hits)
