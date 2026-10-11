"""Every API route the Opportunities and Resume Lab pages call must exist in the backend.
This is the check that would have caught the live 404s (today-matches, saved, pipeline, config, ...).
Run: cd backend && python -m pytest tests/test_frontend_contract.py -q"""
import os, re, sys, tempfile
os.environ["GROQ_API_KEY"] = ""
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

PAGES = ["opportunities.html", "resume-lab.html"]
FRONT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")


def _paths():
    with TestClient(main.app) as c:
        return list(c.get("/openapi.json").json()["paths"].keys())


def _literals(page):
    src = open(os.path.join(FRONT, page), errors="ignore").read()
    return sorted({m.group(1).split("?")[0] for m in re.finditer(r"""['"`](/v1/[A-Za-z0-9_\-/{}.]*)""", src)})


def test_every_route_the_pages_call_exists():
    paths = _paths()
    rx = [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$") for p in paths]
    missing = []
    for page in PAGES:
        for lit in _literals(page):
            if lit.endswith("/"):      # a prefix the page completes at runtime, e.g. '/v1/opp/outbox/' + id + '/approve'
                ok = any(p.startswith(lit) for p in paths)
            else:                      # a complete route: must match a registered path EXACTLY (no prefix leniency)
                ok = any(r.match(lit) for r in rx)
            if not ok:
                missing.append(f"{page}: {lit}")
    assert not missing, "Pages call routes the backend does not have:\n  " + "\n  ".join(missing)


def test_guest_endpoint_is_gone():
    paths = _paths()
    assert "/v1/auth/guest" not in paths
