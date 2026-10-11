"""Guest mode is gone: no endpoint, and old guest addresses cannot be logged into.
Run: cd backend && python -m pytest tests/test_no_guest.py -q"""
import os, sys, tempfile
os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402


def test_guest_endpoint_missing_and_old_guest_address_refused():
    with TestClient(main.app) as c:
        assert c.post("/v1/auth/guest").status_code in (404, 405)
        r = c.post("/v1/auth/dev-login", params={"email": "guest-0123456789ab@opa.local"})
        assert r.status_code == 403
        ok = c.post("/v1/auth/dev-login", params={"email": "real.person@example.com"})
        assert ok.status_code == 200 and ok.json()["user_id"]
