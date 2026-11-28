"""Original-file storage: off by default, local + R2 backends, quotas, ownership, cleanup, safe downloads."""
import io

import pytest

import database as D
import file_store as FS
from tests.test_auth_guard import c, tok, H, _keys, mail  # noqa: F401

PDF = b"%PDF-1.4 fake pdf bytes " + b"x" * 200
TXT = ("Operating systems syllabus. Unit 1: processes and threads. Unit 2: scheduling and memory management. " * 6).encode()


class FakeS3:
    """Just enough of the boto3 S3 client for R2Backend."""
    def __init__(self):
        self.objects, self.calls = {}, []

    def put_object(self, Bucket, Key, Body, ContentType):
        self.calls.append(("put", Bucket, Key, ContentType)); self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def delete_object(self, Bucket, Key):
        self.calls.append(("del", Bucket, Key)); self.objects.pop((Bucket, Key), None)


@pytest.fixture()
def fs(c, monkeypatch, tmp_path):
    monkeypatch.setenv("OPAI_FILE_STORE", "local")
    monkeypatch.setenv("OPAI_FILE_DIR", str(tmp_path / "store"))
    FS.reset_backend()
    e = mail()
    uid = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    yield c, uid, e
    FS.reset_backend()


def _up(c, uid, e, name="notes.txt", data=TXT):
    return c.post("/v1/rag/docs", data={"user_id": uid}, files=[("files", (name, data, "text/plain"))], headers=H(tok(e)))


def _list(c, uid, e):
    return c.get("/v1/files", params={"user_id": uid}, headers=H(tok(e))).json()


def test_off_by_default_keeps_nothing(c, monkeypatch):
    monkeypatch.delenv("OPAI_FILE_STORE", raising=False)
    e = mail(); uid = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
    assert _up(c, uid, e).status_code == 200
    j = _list(c, uid, e)
    assert j["enabled"] is False and j["files"] == []


def test_upload_is_kept_and_downloads_back_identical(fs):
    c, uid, e = fs
    r = _up(c, uid, e)
    assert r.status_code == 200 and r.json()["results"][0]["ok"]
    j = _list(c, uid, e)
    assert j["enabled"] and len(j["files"]) == 1
    f = j["files"][0]
    assert f["filename"] == "notes.txt" and f["kind"] == "doc" and f["size"] == len(TXT)
    d = c.get(f"/v1/files/{f['id']}/download", params={"user_id": uid}, headers=H(tok(e)))
    assert d.status_code == 200 and d.content == TXT
    assert "attachment" in d.headers["content-disposition"] and d.headers["x-content-type-options"] == "nosniff"


def test_reupload_same_bytes_does_not_duplicate_and_new_bytes_replace(fs):
    c, uid, e = fs
    _up(c, uid, e); _up(c, uid, e)
    assert len(_list(c, uid, e)["files"]) == 1
    _up(c, uid, e, data=TXT + b" more")
    fl = _list(c, uid, e)["files"]
    assert len(fl) == 1 and fl[0]["size"] == len(TXT) + 5


def test_deleting_the_document_removes_the_original(fs):
    c, uid, e = fs
    doc_id = _up(c, uid, e).json()["results"][0]["doc_id"]
    assert len(_list(c, uid, e)["files"]) == 1
    assert c.delete(f"/v1/rag/docs/{doc_id}", params={"user_id": uid}, headers=H(tok(e))).status_code == 200
    assert _list(c, uid, e)["files"] == []


def test_user_can_delete_own_file_and_gets_usage_back(fs):
    c, uid, e = fs
    _up(c, uid, e)
    fid = _list(c, uid, e)["files"][0]["id"]
    r = c.delete(f"/v1/files/{fid}", params={"user_id": uid}, headers=H(tok(e)))
    assert r.status_code == 200 and r.json()["usage"]["bytes"] == 0
    assert c.delete(f"/v1/files/{fid}", params={"user_id": uid}, headers=H(tok(e))).status_code == 404


def test_other_users_cannot_see_download_or_delete(fs, monkeypatch):
    c, uid, e = fs
    _up(c, uid, e)
    fid = _list(c, uid, e)["files"][0]["id"]
    e2 = mail(); uid2 = c.post("/v1/auth/dev-login", params={"email": e2}, headers=H(tok(e2))).json()["user_id"]
    assert _list(c, uid2, e2)["files"] == []
    assert c.get(f"/v1/files/{fid}/download", params={"user_id": uid2}, headers=H(tok(e2))).status_code == 404
    assert c.delete(f"/v1/files/{fid}", params={"user_id": uid2}, headers=H(tok(e2))).status_code == 404
    # asking for someone else's user_id with your own token is refused once the guard enforces
    monkeypatch.setenv("OPAI_AUTH_MODE", "enforce")
    assert c.get("/v1/files", params={"user_id": uid}, headers=H(tok(e2))).status_code in (401, 403)


def test_per_file_limit_and_quota_skip_storing_but_upload_still_works(fs, monkeypatch):
    c, uid, e = fs
    monkeypatch.setenv("OPAI_FILE_MAX_MB", "0.0001")           # ~100 bytes
    r = _up(c, uid, e)
    assert r.status_code == 200 and r.json()["results"][0]["ok"] and _list(c, uid, e)["files"] == []
    monkeypatch.setenv("OPAI_FILE_MAX_MB", "10")
    monkeypatch.setenv("OPAI_FILE_QUOTA_MB", '{"free": 0.0005}')   # ~500 bytes total
    _up(c, uid, e, name="a.txt", data=TXT[:400])
    _up(c, uid, e, name="b.txt", data=TXT[:400])               # would exceed the quota
    names = {f["filename"] for f in _list(c, uid, e)["files"]}
    assert names == {"a.txt"}


def test_storage_failure_never_breaks_the_upload(fs, monkeypatch):
    c, uid, e = fs
    class Boom:
        def put(self, *a, **k): raise OSError("disk full")
        def get(self, *a, **k): raise OSError("x")
        def delete(self, *a, **k): pass
    FS.reset_backend(Boom())
    r = _up(c, uid, e)
    assert r.status_code == 200 and r.json()["results"][0]["ok"]
    assert _list(c, uid, e)["files"] == []


def test_download_is_never_served_as_html(fs):
    c, uid, e = fs
    db = D.SessionLocal()
    try:
        row = FS.save(db, uid, "doc", "evil.html", b"<script>alert(1)</script>")
    finally:
        db.close()
    d = c.get(f"/v1/files/{row['id']}/download", params={"user_id": uid}, headers=H(tok(e)))
    assert d.headers["content-type"].startswith("application/octet-stream") and "attachment" in d.headers["content-disposition"]


def test_syllabus_and_resume_uploads_are_kept(fs):
    c, uid, e = fs
    r = c.post("/v1/academics/syllabus", data={"user_id": uid, "course_name": "OS"}, files=[("files", ("os.txt", TXT, "text/plain"))], headers=H(tok(e)))
    assert r.status_code == 200
    kinds = {f["kind"] for f in _list(c, uid, e)["files"]}
    res = r.json()["results"][0]
    assert res["ok"], res
    assert "syllabus" in kinds


def test_local_backend_blocks_path_traversal(tmp_path):
    b = FS.LocalBackend(str(tmp_path))
    with pytest.raises(ValueError):
        b.put("../escape.txt", b"x", "text/plain")
    b.put("u/1/a.txt", b"ok", "text/plain")
    assert b.get("u/1/a.txt") == b"ok"


def test_r2_backend_round_trip_with_fake_s3(c, monkeypatch):
    monkeypatch.setenv("OPAI_FILE_STORE", "r2")
    s3 = FakeS3()
    FS.reset_backend(FS.R2Backend(s3, "opai-files"))
    try:
        e = mail(); uid = c.post("/v1/auth/dev-login", params={"email": e}, headers=H(tok(e))).json()["user_id"]
        doc = _up(c, uid, e, name="r.md", data=TXT).json()["results"]
        assert doc[0]["ok"]
        fl = _list(c, uid, e)["files"]
        assert len(fl) == 1 and fl[0]["content_type"].startswith("text/plain")
        put = [x for x in s3.calls if x[0] == "put"][0]
        assert put[1] == "opai-files" and put[2].startswith(f"u/{uid.lower()}/") and "r.md" not in put[2]   # opaque key
        d = c.get(f"/v1/files/{fl[0]['id']}/download", params={"user_id": uid}, headers=H(tok(e)))
        assert d.content == TXT
        c.delete(f"/v1/files/{fl[0]['id']}", params={"user_id": uid}, headers=H(tok(e)))
        assert s3.objects == {}
    finally:
        FS.reset_backend()


def test_r2_without_config_reports_a_clear_error(monkeypatch):
    monkeypatch.setenv("OPAI_FILE_STORE", "r2")
    for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    FS.reset_backend()
    with pytest.raises(RuntimeError, match="R2 is not configured"):
        FS.backend()
    FS.reset_backend()


RESUME = ("Asha Rao. B.Tech CSE. Projects: built a FastAPI service handling 2k requests a day. Skills: Python, SQL, React. "
          "Experience: Intern at Acme building data pipelines in Python and Postgres. Education: B.Tech 2027.").encode()


def test_resume_upload_is_kept_and_deleting_the_resume_removes_it(fs):
    c, uid, e = fs
    r = c.post("/v1/resume-lab/import-files", data={"user_id": uid}, files=[("files", ("asha.txt", RESUME, "text/plain"))], headers=H(tok(e)))
    assert r.status_code == 200 and r.json()["created"], r.json()
    rid = r.json()["created"][0]["id"]
    fl = _list(c, uid, e)["files"]
    assert [(f["kind"], f["ref_id"]) for f in fl] == [("resume", rid)]
    assert c.delete(f"/v1/resumes/{rid}", headers=H(tok(e))).status_code == 200
    assert _list(c, uid, e)["files"] == []
