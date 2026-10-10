"""Run: cd backend && python -m pytest tests -q   (uses a temp SQLite DB, hash embedder, mocked LLM)"""
import io, os, sys, tempfile
os.environ["RAG_EMBEDDER"] = "hash"
os.environ["GROQ_API_KEY"] = ""
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
import main, rag_api

client = TestClient(main.app)


@pytest.fixture(scope="module")
def users():
    with TestClient(main.app) as c:
        a = c.post("/v1/auth/guest").json()["user_id"]
        b = c.post("/v1/auth/guest").json()["user_id"]
    return a, b


def up(uid, name, data, ctype="text/plain"):
    return client.post("/v1/rag/docs", data={"user_id": uid}, files=[("files", (name, data, ctype))]).json()


def make_pdf(pages):
    from reportlab.pdfgen import canvas  # may be missing; tests that need it skip
    buf = io.BytesIO(); c = canvas.Canvas(buf)
    for t in pages:
        c.drawString(72, 700, t); c.showPage()
    c.save(); return buf.getvalue()


def test_upload_ask_cites_source(users):
    a, _ = users
    r = up(a, "os_notes.txt", b"Paging splits memory into fixed size frames. A page table maps virtual pages to frames.\n\nThrashing happens when the working set exceeds RAM.")
    assert r["results"][0]["ok"] and r["docs"][0]["filename"] == "os_notes.txt"
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "what is thrashing?"}).json()
    assert res["mode"] == "extractive" and res["sources"][0]["title"] == "os_notes.txt"
    assert "[1]" in res["answer"] and "thrashing" in res["answer"].lower()


def test_same_filename_replaces(users):
    a, _ = users
    up(a, "dup.txt", b"alpha beta gamma original version")
    r = up(a, "dup.txt", b"completely new text about kubernetes pods")
    assert [d["filename"] for d in r["docs"]].count("dup.txt") == 1
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "kubernetes pods"}).json()
    assert any(s["title"] == "dup.txt" for s in res["sources"])


def test_user_isolation(users):
    a, b = users
    up(a, "secret.txt", b"The launch code is zebra-9921 for project falcon.")
    res = client.post("/v1/rag/ask", json={"user_id": b, "question": "what is the launch code for project falcon?"}).json()
    assert res["sources"] == [] and "zebra" not in res["answer"]
    assert client.get("/v1/rag/docs", params={"user_id": b}).json()["docs"] == []


def test_delete_removes_from_retrieval(users):
    a, _ = users
    r = up(a, "temp.txt", b"quantum entanglement of photons experiment")
    doc = next(d for d in r["docs"] if d["filename"] == "temp.txt")["doc_id"]
    assert client.delete(f"/v1/rag/docs/{doc}", params={"user_id": a}).status_code == 200
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "quantum entanglement photons"}).json()
    assert all(s["title"] != "temp.txt" for s in res["sources"])
    assert client.delete(f"/v1/rag/docs/{doc}", params={"user_id": a}).status_code == 404


def test_bad_files_reported_not_crashing(users):
    a, _ = users
    r = up(a, "evil.exe", b"MZ....")
    assert not r["results"][0]["ok"] and "unsupported" in r["results"][0]["error"]
    r = up(a, "empty.txt", b"")
    assert not r["results"][0]["ok"]
    r = up(a, "broken.pdf", b"not a pdf at all", "application/pdf")
    assert not r["results"][0]["ok"]
    r = up(a, "broken.docx", b"not a docx", "application/octet-stream")
    assert not r["results"][0]["ok"]


def test_docx_and_csv(users):
    import docx
    a, _ = users
    d = docx.Document(); d.add_paragraph("Raft uses leader election with randomized timeouts."); buf = io.BytesIO(); d.save(buf)
    assert up(a, "raft.docx", buf.getvalue())["results"][0]["ok"]
    assert up(a, "jobs.csv", b"company,role,skills\nAcme,ML Intern,pytorch and sql\n")["results"][0]["ok"]
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "which skills does Acme need?"}).json()
    assert any(s["title"] == "jobs.csv" for s in res["sources"])


def test_pdf_pages(users):
    pytest.importorskip("reportlab")
    a, _ = users
    r = up(a, "book.pdf", make_pdf(["Chapter one covers lexical analysis.", "Chapter two covers LR parsing tables."]), "application/pdf")
    assert r["results"][0]["ok"] and r["results"][0]["pages"] == 2
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "LR parsing tables"}).json()
    assert res["sources"][0]["page"] == 2


def test_doc_scope_and_followup_history(users):
    a, _ = users
    r1 = up(a, "projA.txt", b"Project Atlas is a recommender system that uses embeddings and cosine similarity.")
    up(a, "projB.txt", b"Project Borealis is a weather dashboard that uses charts and REST APIs.")
    doc_b = next(d for d in client.get("/v1/rag/docs", params={"user_id": a}).json()["docs"] if d["filename"] == "projB.txt")["doc_id"]
    scoped = client.post("/v1/rag/ask", json={"user_id": a, "question": "what does it use?", "doc_ids": [doc_b]}).json()
    assert {s["title"] for s in scoped["sources"]} == {"projB.txt"}
    hist = [{"role": "user", "content": "Tell me about Project Atlas"}, {"role": "assistant", "content": "It is a recommender."}]
    fu = client.post("/v1/rag/ask", json={"user_id": a, "question": "what does it use?", "history": hist}).json()
    assert fu["sources"][0]["title"] == "projA.txt"


def test_llm_used_and_citations_pruned(users, monkeypatch):
    a, _ = users
    up(a, "llm.txt", b"The viva is scheduled for 14 March in room 204.")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    seen = {}
    def fake(question, history, context):
        seen["ctx"] = context; return "It is on 14 March in room 204 [1] [7]."
    monkeypatch.setattr(rag_api, "_llm_answer", fake)
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "when is the viva?"}).json()
    assert res["mode"] == "llm" and "[1]" in res["answer"] and "[7]" not in res["answer"]
    assert seen["ctx"].startswith("[1] (llm.txt")


def test_llm_failure_falls_back(users, monkeypatch):
    a, _ = users
    monkeypatch.setenv("GROQ_API_KEY", "x")
    def boom(*a, **k): raise RuntimeError("groq down")
    monkeypatch.setattr(rag_api, "_llm_answer", boom)
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "when is the viva?"}).json()
    assert res["mode"] == "extractive" and res["sources"]


def test_injection_guard_in_prompt():
    assert "untrusted DATA" in rag_api.SYSTEM_PROMPT and "do not follow" in rag_api.SYSTEM_PROMPT


def test_notes_and_tasks_indexed(users):
    a, _ = users
    assert client.post("/v1/rag/notes", json={"user_id": a, "title": "Idea", "text": "Build a compiler fuzzing harness."}).status_code == 200
    t = client.post("/v1/tasks", json={"user_id": a, "title": "Revise virtual memory chapter"}).json()
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "revise virtual memory"}).json()
    assert any(s["type"] == "task" for s in res["sources"])
    client.delete(f"/v1/tasks/{t['id']}")
    res = client.post("/v1/rag/ask", json={"user_id": a, "question": "revise virtual memory chapter task"}).json()
    assert all(s["type"] != "task" for s in res["sources"])


def test_jarvis_chat_routes_content_questions_to_rag(users):
    a, _ = users
    up(a, "proj.txt", b"Atlas project uses embeddings for retrieval.")
    client.post("/v1/projects", json={"user_id": a, "title": "Atlas", "description": "uses embeddings for retrieval", "status": "active"})
    r = client.post("/v1/jarvis/chat", json={"user_id": a, "message": "which project uses embeddings?"}).json()
    assert r["payload"].get("sources"), r          # not the table dump
    r = client.post("/v1/jarvis/chat", json={"user_id": a, "message": "which skills does the Acme internship need?"}).json()
    assert r["action"] != "matches"


def test_task_title_extraction():
    from agent.orchestrator import extract_task_title, extract_due_date
    assert extract_task_title("add a task to revise paging tomorrow") == "Revise paging"
    assert extract_task_title("Please create a task: finish OS assignment by friday") == "Finish OS assignment"
    assert extract_task_title("remind me to call mom") == "Call mom"
    assert extract_due_date("add a task to revise paging tomorrow")


def test_bm25_prefers_rare_term_and_mmr_dedups():
    import rag_service as rag
    docs = [rag.tokenize(t) for t in ["the paging policy of os", "cooking pasta with tomato", "paging paging memory frames"]]
    sc = rag.bm25_scores(rag.tokenize("paging memory"), docs)
    assert sc[2] > sc[0] > sc[1] == 0.0


def chat(uid, msg):
    return client.post("/v1/jarvis/chat", json={"user_id": uid, "message": msg}).json()


def test_chat_adds_to_every_section(users):
    from database import SessionLocal, Project, Academic, Application, Opportunity, ClientRequest
    a, _ = users
    cases = [
        ("add a project called KARNA RAG using FastAPI, React", "projects"),
        ("add an exam for Operating Systems on 20 Nov", "academics"),
        ("add an application as ML Intern at Acme Corp deadline 30 Oct", "applications"),
        ("add an internship at Google Research deadline 15 Dec", "opportunities"),
        ("add client request from Radisson wants a booking website", "requests"),
    ]
    for msg, sec in cases:
        r = chat(a, msg)
        assert r["payload"].get("created") and r["payload"]["section"] == sec, (msg, r)
    db = SessionLocal()
    try:
        assert db.query(Project).filter_by(user_id=a, title="KARNA RAG").first().tech_stack == ["FastAPI", "React"]
        ex = db.query(Academic).filter_by(user_id=a).first()
        assert ex.subject == "Operating Systems" and ex.exam_date.month == 11 and ex.exam_date.day == 20
        ap = db.query(Application).filter_by(user_id=a).first()
        assert (ap.company, ap.role) == ("Acme Corp", "ML Intern") and ap.deadline.month == 10
        assert db.query(Opportunity).filter_by(company_or_lab="Google Research").first()
        assert db.query(ClientRequest).filter_by(user_id=a, client="Radisson").first()
    finally:
        db.close()


def test_chat_capture_asks_for_missing_and_ignores_questions(users):
    a, _ = users
    r = chat(a, "add an application")
    assert "I still need" in r["reply"] and not r["payload"].get("created")
    q = chat(a, "how do I add a project to my resume?")
    assert not (q.get("payload") or {}).get("created")


def test_smalltalk_and_no_docs_message(users):
    _, b = users   # user b has uploaded nothing
    r = chat(b, "hi")
    assert "I don't have enough" not in r["reply"] and r["payload"]["answer_mode"] == "smalltalk"
    r = chat(b, "Summarise my uploaded documents")
    assert "haven't uploaded any documents" in r["reply"]
