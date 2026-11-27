import pytest
from fastapi.testclient import TestClient
from opai_rag.api import create_app
from opai_rag.cli import main
from conftest import HANDBOOK


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("OPAI_RAG_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return TestClient(create_app(str(tmp_path / "api.db")))


def test_upload_list_ask_delete_flow(client):
    r = client.post("/documents", files=[("files", ("handbook.md", HANDBOOK, "text/markdown"))])
    assert r.status_code == 200 and r.json()["results"][0]["chunks"] >= 1
    doc_id = client.get("/documents").json()["documents"][0]["id"]
    a = client.post("/ask", json={"question": "support hours"}).json()
    assert "9am" in a["answer"] and a["sources"][0]["title"] == "handbook.md"
    assert client.delete(f"/documents/{doc_id}").status_code == 200
    assert client.delete(f"/documents/{doc_id}").status_code == 404


def test_bad_upload_reports_error_not_500(client):
    r = client.post("/documents", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 200 and "unsupported" in r.json()["results"][0]["error"]


def test_api_key_enforced_when_set(client, monkeypatch):
    monkeypatch.setenv("OPAI_RAG_API_KEY", "s3cret")
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/documents", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200  # health stays open


def test_question_validation(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "hi", "k": 999}).status_code == 422


def test_cli_roundtrip(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db, f = str(tmp_path / "c.db"), tmp_path / "h.md"
    f.write_bytes(HANDBOOK)
    assert main(["--db", db, "ingest", str(f)]) == 0
    assert main(["--db", db, "ask", "when is support available"]) == 0
    out = capsys.readouterr().out
    assert "Monday to Friday" in out and "Sources:" in out
    assert main(["--db", db, "ingest", str(tmp_path / "missing.pdf")]) == 1
