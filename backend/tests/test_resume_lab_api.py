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
from database import SessionLocal  # noqa: E402

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


# ---------------------------------------------------------------- PDF text quirks, references, upload
SPACED = "A B I S H E K  K\nS K I L L S\nP R O J E C T S\nT e n s o r F l o w ,  P y T o r c h ,\n"


def test_clean_pdf_text_repairs_letter_spacing():
    t = L.clean_pdf_text(SPACED)
    assert "ABISHEK K" in t and "TensorFlow, PyTorch," in t and "SKILLS" in t


def test_parser_handles_pdf_glyphs_wraps_and_uppercase_headings():
    txt = ("Jane Doe\nPROJECTS\n•Built a search service with FastAPI that handled 10,000+ queries daily\n"
           "◦Improved latency by 35% through caching and\nbatching of requests\nINTERNSHIP EXPERIENCE\n"
           "Worked with a team of five engineers on dashboards used across the whole company every week\n")
    b = L.parse_resume(txt)["bullets"]
    assert len(b) == 3 and "batching of requests" in b[1]["text"] and b[0]["section"] == "projects"


def test_scrub_pii():
    t = L.scrub_pii("Mail jane@x.com or call +91-6281031843, see https://github.com/jane and linkedin.com/in/jane")
    assert "@" not in t and "6281031843" not in t and "github.com" not in t and "linkedin.com" not in t


def test_reference_resumes_never_leak_into_own_features(c, uid):
    two(c, uid)
    other = ML.replace("Asha Rao", "Someone Else").replace("RAG assistant", "UNIQUEREFPROJECT assistant") + "\njane@x.com +91 9876543210\n"
    r = imp(c, uid, [{"label": "ref1", "text": other, "kind": "reference"}]).json()
    assert r["created"][0]["kind"] == "reference" and r["total_versions"] == 2 and r["total_references"] == 1
    lib = c.get("/v1/resume-lab/library", params={"user_id": uid}).json()
    assert lib["count"] == 2 and all(v["label"] != "ref1" for v in lib["versions"])
    assert c.get("/v1/resumes", params={"user_id": uid}).json() and all(x["label"] != "ref1" for x in c.get("/v1/resumes", params={"user_id": uid}).json())
    hits = c.post("/v1/resume-lab/bullets/search", json={"user_id": uid, "query": "UNIQUEREFPROJECT assistant", "k": 10}).json()["results"]
    assert all("UNIQUEREFPROJECT" not in h["bullet"] for h in hits)
    tl = c.post("/v1/resume-lab/tailor", json={"user_id": uid, "job_text": "UNIQUEREFPROJECT Python RAG"}).json()
    assert all("UNIQUEREFPROJECT" not in x["bullet"] for x in tl["lead_with"] + tl["consider_from_other_versions"])
    refs = c.get("/v1/resume-lab/references", params={"user_id": uid}).json()
    assert refs["count"] == 1 and "text" not in refs["references"][0] and "jane" not in str(refs)
    with SessionLocal() as db:
        from database import Resume
        row = db.query(Resume).filter(Resume.label == "ref1", Resume.user_id == uid).first()
        assert "jane@x.com" not in row.raw_text and "9876543210" not in row.raw_text
    ins = c.get("/v1/resume-lab/insights", params={"user_id": uid}).json()
    assert ins["benchmark"]["references"] == 1


def test_upload_txt_and_pdf(c, uid):
    r = c.post("/v1/resume-lab/import-file", data={"user_id": uid, "kind": "reference", "label": "sample"},
               files={"file": ("a.txt", ML.encode(), "text/plain")})
    assert r.status_code == 200 and r.json()["created"]["kind"] == "reference"
    assert c.post("/v1/resume-lab/import-file", data={"user_id": uid}, files={"file": ("a.exe", b"x" * 200, "x/y")}).status_code == 422
    try:
        from reportlab.pdfgen import canvas
    except ImportError:
        return
    import io
    buf = io.BytesIO()
    cv = canvas.Canvas(buf)
    y = 800
    for ln in ML.splitlines():
        cv.drawString(40, y, ln.replace("•", "-")[:100]); y -= 16
    cv.save()
    r = c.post("/v1/resume-lab/import-file", data={"user_id": uid, "label": "pdf one"}, files={"file": ("r.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- review / coach / compare / builds / export / attach
JOB = "ML Intern. We need Python, PyTorch and RAG experience. Kubernetes a plus. RAG pipelines, PyTorch models."


def rid(c, uid, label):
    return [v["id"] for v in c.get("/v1/resume-lab/library", params={"user_id": uid}).json()["versions"] if v["label"] == label][0]


def mk_app(c, uid, company="Acme", role="ML Intern"):
    r = c.post("/v1/applications", json={"user_id": uid, "company": company, "role": role})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_review_reports_checks_and_keywords(c, uid):
    two(c, uid)
    r = c.post("/v1/resume-lab/review", json={"user_id": uid, "resume_id": rid(c, uid, "ML")}).json()
    ids = {x["id"] for x in r["checks"]}
    assert {"core_sections", "contact", "metrics", "weak_phrases"} <= ids and "keyword_coverage" not in ids and r["top_fixes"]
    k = c.post("/v1/resume-lab/review", json={"user_id": uid, "resume_id": rid(c, uid, "Web"), "job_text": JOB}).json()
    cov = [x for x in k["checks"] if x["id"] == "keyword_coverage"][0]
    assert cov["status"] in ("warn", "fail") and "python" in cov["evidence"] and "kubernetes" in cov["evidence"]


def test_review_coach_compare_are_isolated_and_refuse_references(c, uid):
    two(c, uid)
    ml = rid(c, uid, "ML")
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.post("/v1/resume-lab/review", json={"user_id": other, "resume_id": ml}).status_code == 404
    assert c.post("/v1/resume-lab/coach", json={"user_id": other, "resume_id": ml}).status_code == 404
    imp(c, uid, [{"label": "ref", "text": ML.replace("Asha Rao", "Someone") + "\n- Built a unique reference thing with 99 parts", "kind": "reference"}])
    with SessionLocal() as db:
        from database import Resume
        ref = db.query(Resume).filter(Resume.user_id == uid, Resume.kind == "reference").first().id
    for path, body in (("review", {}), ("coach", {}), ("compare", {"resume_b": ml})):
        body = {"user_id": uid, "resume_id": ref, **body}
        if path == "compare":
            body = {"user_id": uid, "resume_a": ref, "resume_b": ml}
        assert c.post(f"/v1/resume-lab/{path}", json=body).status_code == 404, path
    assert c.get(f"/v1/resume-lab/resumes/{ref}/export", params={"user_id": uid, "format": "txt"}).status_code == 404


def test_coach_diagnoses_and_never_rewrites_without_model(c, uid):
    two(c, uid)
    r = c.post("/v1/resume-lab/coach", json={"user_id": uid, "resume_id": rid(c, uid, "ML"), "limit": 3}).json()
    assert r["rewrite_status"] == "off" and r["bullets"][0]["bullet"] == "Responsible for various tasks in the team"
    assert r["bullets"][0]["questions"] and "rewrites" not in r["bullets"][0]
    r = c.post("/v1/resume-lab/coach", json={"user_id": uid, "resume_id": rid(c, uid, "ML"), "rewrite": True}).json()
    assert r["rewrite_status"] == "unavailable" and all("rewrites" not in b for b in r["bullets"])      # no key in tests
    one = c.post("/v1/resume-lab/coach", json={"user_id": uid, "resume_id": rid(c, uid, "ML"), "bullet": "Worked on the app"}).json()
    assert len(one["bullets"]) == 1 and one["bullets"][0]["issues"]


def test_coach_drops_model_rewrites_that_invent_facts(c, uid, monkeypatch):
    import agent.groq_client as gc
    two(c, uid)
    bullet = "Worked on a RAG assistant in Python over 500 documents"
    monkeypatch.setattr(gc, "groq_enabled", lambda: True)
    monkeypatch.setattr(gc, "generate_json", lambda s, u, **k: {"rewrites": [
        "Built a Python RAG assistant over 500 documents, cutting latency by 40%",      # invented number -> dropped
        "Built a RAG assistant using LangChain over 500 documents",                     # invented tool -> dropped
        "Built a Python RAG assistant over 500 documents, improving accuracy by [add number]%"]})
    r = c.post("/v1/resume-lab/coach", json={"user_id": uid, "resume_id": rid(c, uid, "ML"), "bullet": bullet, "rewrite": True}).json()
    b = r["bullets"][0]
    assert r["rewrite_status"] == "ok" and len(b["rewrites"]) == 1 and b["rewrites"][0]["has_placeholder"] and b["rewrites_rejected"] == 2


def test_compare_two_versions(c, uid):
    two(c, uid)
    ml, web = rid(c, uid, "ML"), rid(c, uid, "Web")
    assert c.post("/v1/resume-lab/compare", json={"user_id": uid, "resume_a": ml, "resume_b": ml}).status_code == 422
    r = c.post("/v1/resume-lab/compare", json={"user_id": uid, "resume_a": ml, "resume_b": web, "job_text": JOB}).json()
    assert r["a"]["label"] == "ML" and r["b"]["label"] == "Web" and r["bullets"]["only_a"] and r["bullets"]["only_b"]
    assert "kubernetes" in r["keywords"]["missing_in_both"] and "python" in r["keywords"]["only_a"]


def draft_for(c, uid, job=JOB, base=None):
    body = {"user_id": uid, "job_text": job}
    if base:
        body["base_resume_id"] = base
    r = c.post("/v1/resume-lab/builds/suggest", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_builds_suggest_create_list_and_stay_out_of_own_features(c, uid):
    two(c, uid)
    assert c.post("/v1/resume-lab/builds/suggest", json={"user_id": uid}).status_code == 422          # needs a posting
    s = draft_for(c, uid)
    assert s["base_label"] == "ML" and s["draft"]["sections"] and "kubernetes" in s["terms_missing"]
    r = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "ML for Acme", "base_resume_id": s["base_resume_id"], "build": s["draft"]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["provenance"].get("own", 0) >= 1 and "user_added" not in b["provenance"]
    lib = c.get("/v1/resume-lab/library", params={"user_id": uid}).json()
    assert lib["count"] == 2 and all(v["label"] != "ML for Acme" for v in lib["versions"])           # not one of the 10 versions
    m = c.post("/v1/resume-lab/match", json={"user_id": uid, "job_text": JOB}).json()
    assert all(x["label"] != "ML for Acme" for x in m["ranking"])
    lst = c.get("/v1/resume-lab/builds", params={"user_id": uid}).json()
    assert lst["count"] == 1 and lst["builds"][0]["id"] == b["id"]
    full = c.get(f"/v1/resume-lab/builds/{b['id']}", params={"user_id": uid}).json()
    assert full["build"]["sections"] and full["build"]["sections"][0]["items"][0]["origin"] in ("own", "edited", "user_added")
    assert c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "ml for acme", "build": s["draft"]}).status_code == 409   # label reuse
    assert c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "ML", "build": s["draft"]}).status_code == 409              # clashes with a version


def test_build_rejects_invented_content_but_accepts_marked_additions(c, uid):
    two(c, uid)
    sec = [{"name": "Projects", "items": [{"type": "bullet", "text": "Led a team of 30 engineers at Google"}]}]
    r = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "bad", "build": {"sections": sec, "skills": ["Kubernetes"]}})
    assert r.status_code == 422
    errs = r.json()["detail"]["errors"]
    assert any("not found in any of your resumes" in e for e in errs) and any("Kubernetes" in e for e in errs)
    sec[0]["items"][0].update(user_added=True)
    ok = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "good", "build": {"sections": sec, "skills": ["Kubernetes"], "user_added_skills": ["kubernetes"]}})
    assert ok.status_code == 200 and ok.json()["provenance"] == {"user_added": 1, "skill_user_added": 1}


def test_build_update_and_delete_detaches_applications(c, uid):
    two(c, uid)
    s = draft_for(c, uid)
    b = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "v1", "build": s["draft"]}).json()
    app_id = mk_app(c, uid)
    assert c.post("/v1/resume-lab/attach", json={"user_id": uid, "application_id": app_id, "resume_id": b["id"]}).status_code == 200
    items = s["draft"]["sections"][0]["items"]
    trimmed = {**s["draft"], "sections": [{**s["draft"]["sections"][0], "items": items[:2]}] + s["draft"]["sections"][1:]}
    u = c.put(f"/v1/resume-lab/builds/{b['id']}", json={"user_id": uid, "label": "v1b", "build": trimmed})
    assert u.status_code == 200 and u.json()["label"] == "v1b"
    d = c.delete(f"/v1/resume-lab/builds/{b['id']}", params={"user_id": uid}).json()
    assert d["detached_applications"] == 1
    att = [a for a in c.get("/v1/resume-lab/attachments", params={"user_id": uid}).json()["applications"] if a["application_id"] == app_id][0]
    assert att["resume_id"] is None
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.get(f"/v1/resume-lab/builds/{b['id']}", params={"user_id": other}).status_code == 404


def test_export_formats(c, uid):
    two(c, uid)
    ml = rid(c, uid, "ML")
    t = c.get(f"/v1/resume-lab/resumes/{ml}/export", params={"user_id": uid, "format": "txt"})
    assert t.status_code == 200 and "text/plain" in t.headers["content-type"] and "PROJECTS" in t.text
    assert 'filename="ML.txt"' in t.headers["content-disposition"]
    d = c.get(f"/v1/resume-lab/resumes/{ml}/export", params={"user_id": uid, "format": "docx"})
    assert d.status_code == 200 and d.content[:2] == b"PK"
    p = c.get(f"/v1/resume-lab/resumes/{ml}/export", params={"user_id": uid, "format": "pdf"})
    assert p.status_code == 200 and p.content[:5] == b"%PDF-"
    assert c.get(f"/v1/resume-lab/resumes/{ml}/export", params={"user_id": uid, "format": "exe"}).status_code == 422
    other = c.post("/v1/auth/guest").json()["user_id"]
    assert c.get(f"/v1/resume-lab/resumes/{ml}/export", params={"user_id": other, "format": "txt"}).status_code == 404
    s = draft_for(c, uid)
    b = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "Tailored", "build": s["draft"]}).json()
    t2 = c.get(f"/v1/resume-lab/resumes/{b['id']}/export", params={"user_id": uid, "format": "txt"})
    assert t2.status_code == 200 and "Built a RAG assistant" in t2.text


def test_attach_checks_ownership_and_kind(c, uid):
    two(c, uid)
    ml, web = rid(c, uid, "ML"), rid(c, uid, "Web")
    app_id = mk_app(c, uid)
    r = c.post("/v1/resume-lab/attach", json={"user_id": uid, "application_id": app_id, "resume_id": ml})
    assert r.status_code == 200 and r.json()["resume_label"] == "ML" and r.json()["resume_kind"] == "own"
    s = draft_for(c, uid)
    b = c.post("/v1/resume-lab/builds", json={"user_id": uid, "label": "T1", "build": s["draft"]}).json()
    r = c.post("/v1/resume-lab/attach", json={"user_id": uid, "application_id": app_id, "resume_id": b["id"]}).json()
    assert r["resume_kind"] == "tailored" and r["tailored_at"]
    assert c.get("/v1/resume-lab/builds", params={"user_id": uid}).json()["builds"][0]["attached_to"] == 1
    other = c.post("/v1/auth/guest").json()["user_id"]
    other_app = mk_app(c, other)
    assert c.post("/v1/resume-lab/attach", json={"user_id": uid, "application_id": other_app, "resume_id": ml}).status_code == 404
    assert c.post("/v1/resume-lab/attach", json={"user_id": other, "application_id": other_app, "resume_id": ml}).status_code == 404
    assert c.delete(f"/v1/resume-lab/attach/{app_id}", params={"user_id": uid}).json()["resume_id"] is None


def test_application_patch_cannot_attach_someone_elses_or_reference_resume(c, uid):
    two(c, uid)
    app_id = mk_app(c, uid)
    other = c.post("/v1/auth/guest").json()["user_id"]
    imp(c, other, [{"label": "theirs", "text": ML}])
    theirs = rid(c, other, "theirs")
    assert c.patch(f"/v1/opp/applications/{app_id}", json={"user_id": uid, "resume_id": theirs}).status_code == 404
    mine = rid(c, uid, "ML")
    assert c.patch(f"/v1/opp/applications/{app_id}", json={"user_id": uid, "resume_id": mine}).status_code == 200
