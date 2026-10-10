"""Pure-logic tests (no FastAPI / DB needed): cd backend && python -m pytest tests/test_resume_lab_core.py -q"""
import io
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import resume_lab_core as K  # noqa: E402

ML = """Asha Rao
asha@example.com | +91 98765 43210 | github.com/asha
Skills: Python, PyTorch, RAG, SQL
Education
B.Tech CSE, Example College, 2023-2027
Projects
RAG Assistant (2025)
- Built a RAG assistant in Python and FastAPI that answers questions over 500 documents with 92% retrieval accuracy
- Fine-tuned a PyTorch classifier on 20k samples, improving F1 by 8%
- Responsible for various tasks in the team
Experience
Intern, Acme (2025)
- Developed REST APIs with Docker and deployed them on AWS serving 1,000+ requests per day
"""
WEB = """Asha Rao
Skills: React, TypeScript, Node, CSS
Projects
- Designed a React dashboard with TypeScript that reduced report time by 40%
- Worked on the website frontend
- Built a Node API with 12 endpoints and automated tests
"""


def test_review_flags_real_problems_and_scores_lower():
    good = K.ats_review(ML)
    bad = K.ats_review(WEB)
    ids = {c["id"]: c["status"] for c in bad["checks"]}
    assert ids["email"] == "bad" and ids["edu"] == "warn" and ids["weak"] == "warn"
    assert good["score"] > bad["score"]
    assert {c["id"]: c["status"] for c in good["checks"]}["email"] == "ok"


def test_review_detects_columns_symbols_and_keywords():
    messy = ML + "\nPython | SQL | Git | Docker\n★ Great team player\n"
    r = K.ats_review(messy, terms=["python", "kubernetes", "rag"])
    st = {c["id"]: c["status"] for c in r["checks"]}
    assert st["columns"] == "warn" and st["symbols"] == "warn"
    assert r["keywords"]["missing"] == ["kubernetes"] and r["keywords"]["coverage"] == 0.67


def test_coach_diagnoses_and_never_invents_numbers():
    c = K.coach_bullet("- Responsible for various tasks in the team", terms=["python", "docker"])
    ids = {i["id"] for i in c["issues"]}
    assert {"weak_start", "no_metric"} <= ids and c["questions"] and not c["ok"]
    assert c["posting_terms_only_if_true"] == ["python", "docker"]
    strong = K.coach_bullet("Built a RAG assistant in Python that answers questions over 500 documents with 92% accuracy")
    assert strong["ok"] and strong["issues"] == []


def test_rewrite_grounding_blocks_invented_content():
    orig = "Worked on a chatbot using Python for the college fest"
    ok, _ = K.rewrite_is_grounded(orig, "Built a chatbot in Python for the college fest", known_terms=["python", "docker"])
    assert ok
    ok, p = K.rewrite_is_grounded(orig, "Built a chatbot in Python serving 5,000 users", known_terms=["python"])
    assert not ok and any("5000" in x for x in p)
    ok, p = K.rewrite_is_grounded(orig, "Built a chatbot in Python on Docker", known_terms=["python", "docker"])
    assert not ok and any("docker" in x for x in p)
    ok, p = K.rewrite_is_grounded(orig, "Built a chatbot in Python at Google", known_terms=[])
    assert not ok
    ok, _ = K.rewrite_is_grounded(orig, "Built a chatbot in Python serving 200 users", facts="200 students used it", known_terms=["python"])
    assert ok


def test_compare_finds_common_reworded_and_unique():
    a = ML
    b = ML.replace("- Responsible for various tasks in the team", "- Led a team of 3 on various tasks") \
          .replace("Fine-tuned a PyTorch classifier on 20k samples, improving F1 by 8%",
                   "Fine-tuned a PyTorch classifier on 20k samples and improved F1 by 8%")
    r = K.compare_versions(a, b, terms=["python", "kubernetes"])
    assert len(r["common_bullets"]) == 2
    assert len(r["reworded"]) == 1 and r["reworded"][0]["similarity"] >= 0.55
    assert r["posting"]["a"]["missing"] == ["kubernetes"]
    r2 = K.compare_versions(ML, WEB)
    assert "react" in r2["skills"]["only_in_b"] and "python" in r2["skills"]["only_in_a"]


def test_build_reorders_drops_and_adds_verbatim_only():
    doc = K.build_tailored(ML, exclude=["Responsible for various tasks in the team"],
                           extras=[{"text": "Designed a React dashboard with TypeScript that reduced report time by 40%", "section": "projects"}],
                           order_terms=["pytorch"])
    bl = K.doc_bullets(doc)
    assert "Responsible for various tasks in the team" not in bl and doc["dropped"] == ["Responsible for various tasks in the team"]
    assert bl.index(next(b for b in bl if "PyTorch" in b)) < bl.index(next(b for b in bl if "RAG assistant" in b))
    assert doc["added"] and doc["added"][0] in bl
    base_bullets = {b["text"] for b in K.parse_resume(ML)["bullets"]}
    assert all(b in base_bullets or b in doc["added"] for b in bl)            # nothing else appears
    txt = K.render_txt(doc)
    assert txt.startswith("Asha Rao") and "PROJECTS" in txt and "asha@example.com" in txt and "Education".upper() in txt


def test_docx_export_roundtrip():
    from docx import Document
    data = K.render_docx(K.build_tailored(ML))
    d = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in d.paragraphs)
    assert "Asha Rao" in text and "RAG assistant" in text and "PROJECTS" in text


def test_pdf_export_is_selectable_text():
    data = K.render_pdf(K.build_tailored(ML))
    assert data[:5] == b"%PDF-"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
    try:
        out = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
    finally:
        os.unlink(f.name)
    assert "Asha Rao" in out and "RAG assistant" in out and "PROJECTS" in out


def test_excluded_bullet_is_not_re_added_by_extras():
    b = "Designed a React dashboard with TypeScript that reduced report time by 40%"
    doc = K.build_tailored(ML, exclude=[b], extras=[{"text": b}])
    assert b not in K.doc_bullets(doc) and doc["added"] == []
