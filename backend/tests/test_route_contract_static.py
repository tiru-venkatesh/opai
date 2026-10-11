"""Standard-library route contract: needs neither FastAPI nor a database, so it runs anywhere.
    cd backend && python -m pytest tests/test_route_contract_static.py -q      (or: python scripts/route_contract.py)
The OpenAPI-based tests/test_frontend_contract.py is the stricter check where FastAPI is installed."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
import route_contract as RC  # noqa: E402


def test_every_frontend_path_is_served_by_the_backend():
    missing = RC.check()
    assert not missing, "Frontend calls routes the backend does not have:\n  " + "\n  ".join(missing)


def test_every_page_that_calls_the_api_is_covered():
    pages = set(RC.frontend_paths())
    assert {"opportunities.html", "resume-lab.html", "today.html", "briefs.html"} <= pages, pages


def test_checker_really_detects_a_missing_route():
    real = RC.frontend_paths
    RC.frontend_paths = lambda: {"x.html": {"/v1/opp/this-route-does-not-exist"}}
    try:
        assert RC.check() == ["x.html: /v1/opp/this-route-does-not-exist"]
    finally:
        RC.frontend_paths = real


def test_version_and_health_routes_exist():
    paths = {p for _, p, _ in RC.backend_routes()}
    assert {"/v1/health", "/v1/version", "/v1/system/health", "/v1/system/scheduler-status", "/v1/opp/profile"} <= paths


def test_outbox_send_release_route_exists():
    assert any(p == "/v1/opp/outbox/{outbox_id}/send/release" for _, p, _ in RC.backend_routes())
