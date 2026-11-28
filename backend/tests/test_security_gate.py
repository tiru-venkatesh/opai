import pytest

import auth_guard
import security_gate as G

ENV = ("RENDER", "OPAI_ENV", "OPAI_AUTH_MODE", "OPAI_LOCAL_AUTH_BYPASS", "ENABLE_DEV_SEED", "OPAI_ALLOW_INSECURE_START",
       "CORS_ORIGINS", "DATABASE_URL", "OPAI_REQUIRE_VERIFIED")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)


def test_local_defaults_to_log_and_boots():
    assert not G.is_production() and auth_guard.mode() == "log"
    G.enforce_startup()


@pytest.mark.parametrize("flag", [{"RENDER": "1"}, {"OPAI_ENV": "production"}])
def test_production_defaults_to_enforce(monkeypatch, flag):
    for k, v in flag.items():
        monkeypatch.setenv(k, v)
    assert G.is_production() and auth_guard.mode() == "enforce"


def test_explicit_mode_wins_so_rollout_and_rollback_still_work(monkeypatch):
    monkeypatch.setenv("RENDER", "1")
    monkeypatch.setenv("OPAI_AUTH_MODE", "log")
    assert auth_guard.mode() == "log"
    monkeypatch.setenv("OPAI_AUTH_MODE", "nonsense")
    assert auth_guard.mode() == "enforce"


@pytest.mark.parametrize("env", [{"OPAI_AUTH_MODE": "off"}, {"OPAI_LOCAL_AUTH_BYPASS": "1"}, {"ENABLE_DEV_SEED": "true"}])
def test_production_refuses_unsafe_config(monkeypatch, env):
    monkeypatch.setenv("RENDER", "1")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(RuntimeError, match="Refusing to start"):
        G.enforce_startup()
    monkeypatch.setenv("OPAI_ALLOW_INSECURE_START", "1")
    G.enforce_startup()                      # emergency override boots (and logs loudly)


def test_unsafe_flags_are_fine_outside_production(monkeypatch):
    monkeypatch.setenv("OPAI_AUTH_MODE", "off")
    monkeypatch.setenv("ENABLE_DEV_SEED", "1")
    G.enforce_startup()


def test_production_warns_on_weak_but_legal_settings(monkeypatch):
    monkeypatch.setenv("OPAI_ENV", "production")
    monkeypatch.setenv("OPAI_AUTH_MODE", "log")
    errs, warns = G.problems()
    assert not errs
    text = " ".join(warns)
    assert "log" in text and "CORS" in text and "SQLite" in text
