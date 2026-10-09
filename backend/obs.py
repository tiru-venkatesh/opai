"""Structured events + in-process counters (exposed by /v1/system/health). One JSON line per event on logger `opa.events`.
Names: intent_classified brief_created brief_shown action_proposed action_confirmed action_approved action_executed action_failed
       reminder_created reminder_delivered notification_clicked scheduler_tick scheduler_error"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from typing import Any, Dict

log = logging.getLogger("opa.events")
_lock = threading.Lock()
COUNTS: Counter = Counter()
STARTED = time.time()


def emit(event: str, **fields: Any) -> None:
    with _lock:
        COUNTS[event] += 1
    try:
        log.info(json.dumps({"event": event, **fields}, default=str))
    except Exception:
        pass


def snapshot() -> Dict[str, Any]:
    with _lock:
        return {"uptime_s": int(time.time() - STARTED), "events": dict(COUNTS)}
