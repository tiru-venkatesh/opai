import pytest
from fastapi import HTTPException

from ai_admin_api import _admin


def test_admin_analytics_requires_a_configured_secret(monkeypatch):
    monkeypatch.setenv("OPAI_ADMIN_KEY", "")
    monkeypatch.setenv("FEEDBACK_ADMIN_KEY", "")
    with pytest.raises(HTTPException) as caught:
        _admin(None)
    assert caught.value.status_code == 403


def test_admin_analytics_accepts_only_matching_key(monkeypatch):
    monkeypatch.setenv("OPAI_ADMIN_KEY", "test-admin-secret")
    with pytest.raises(HTTPException):
        _admin("wrong")
    assert _admin("test-admin-secret") is None
