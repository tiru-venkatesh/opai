"""Guards for the orchestrator hardening: failures are logged + rolled back, dates follow IST, int-safe minutes."""
import logging
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from agent import orchestrator as O


def test_try_logs_and_rolls_back(caplog):
    db = MagicMock()
    def boom():
        raise RuntimeError("aborted transaction")
    with caplog.at_level(logging.ERROR, logger="opa.orchestrator"):
        assert O._try(db, "identity", boom) is None
    db.rollback.assert_called_once()
    assert "identity" in caplog.text and "aborted transaction" in caplog.text


def test_try_passes_value_through_without_rollback():
    db = MagicMock()
    assert O._try(db, "ok", lambda: {"reply": "x"}) == {"reply": "x"}
    db.rollback.assert_not_called()


def test_due_dates_follow_ist_not_server_clock():
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert O.extract_due_date("revise paging today") == ist_today.isoformat()
    assert O.extract_due_date("revise paging tmrw") == (ist_today + timedelta(days=1)).isoformat()
    assert O.extract_due_date("revise paging") is None


def test_task_title_still_extracts():
    assert O.extract_task_title("add a task to revise paging tomorrow") == "Revise paging"


def test_clarify_never_leaks_internal_reason_code():
    d = MagicMock(reason_code="low_confidence_intent")
    r = O._clarify(d, "???")
    assert "low_confidence" not in r.reply and "routing" not in (r.payload or {})
