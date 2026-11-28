"""KARNA chat experience endpoints.

  GET  /v1/karna/briefing?user_id=     personalised empty-state: greeting, "needs attention" cards, starter prompts
  POST /v1/jarvis/chat/stream          same pipeline and same body as /v1/jarvis/chat, delivered as Server-Sent Events:
                                         data: {"status": "reading", "label": "Reading your workspace"}      (progress phases)
                                         data: {"done": true, "result": <JarvisChatResponse>, "followups": [...]}
                                         data: {"error": "...", "status": 502, "done": true}                (failure)
The phases are honest progress markers (time-based), not claims about internal steps. The answer itself is the unchanged
/v1/jarvis/chat result, so grounding, citations, the approval gate and memory confirmation behave exactly as before.
"""
from __future__ import annotations

import contextvars
import json
import logging
import queue
import threading
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from agent import karna_prompt, karna_ux
from database import MemoryItem, SessionLocal, User, get_db
from schemas import JarvisChatRequest

router = APIRouter()
log = logging.getLogger("opai.karna")

PHASES = [(0.0, "reading", "Reading your workspace"), (1.4, "searching", "Checking your documents and data"), (4.0, "writing", "Writing the answer")]


@router.get("/v1/karna/briefing")
def briefing(user_id: str, db: Session = Depends(get_db)):
    uid = str(user_id)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    ctx: Dict[str, Any] = {}
    try:
        ctx = karna_prompt.collect_context(db, uid)
    except Exception:
        db.rollback()
    docs = 0
    try:
        import rag_service as rag
        docs = len(rag.list_docs(db, uid))
    except Exception:
        db.rollback()
    pend = 0
    try:
        pend = db.query(MemoryItem).filter(MemoryItem.user_id == uid, MemoryItem.status == "unconfirmed").count()
    except Exception:
        db.rollback()
    return karna_ux.briefing(ctx, docs=docs, pending_memory=pend)


def _sse(obj: Dict[str, Any]) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False, default=str) + "\n\n"


@router.post("/v1/jarvis/chat/stream")
def jarvis_chat_stream(request: JarvisChatRequest):
    from main import jarvis_chat          # late import: main includes this router
    results: "queue.Queue[tuple]" = queue.Queue()
    ctx = contextvars.copy_context()

    def work():
        db = SessionLocal()
        try:
            res = ctx.run(jarvis_chat, request, db)
            results.put(("ok", res))
        except HTTPException as e:
            results.put(("http", e))
        except Exception as e:             # noqa: BLE001
            log.exception("jarvis stream failed")
            results.put(("err", e))
        finally:
            db.close()

    threading.Thread(target=work, daemon=True).start()

    def gen():
        import time
        t0, sent = time.monotonic(), set()
        while True:
            el = time.monotonic() - t0
            for at, key, label in PHASES:
                if el >= at and key not in sent:
                    sent.add(key)
                    yield _sse({"status": key, "label": label})
            try:
                kind, val = results.get(timeout=0.25)
            except queue.Empty:
                if el > 120:
                    yield _sse({"error": "This is taking too long. Try again.", "status": 504, "done": True})
                    return
                continue
            if kind == "ok":
                body = json.loads(val.model_dump_json()) if hasattr(val, "model_dump_json") else val
                fu = []
                try:
                    pl = body.get("payload") if isinstance(body, dict) else None
                    srcs = pl.get("sources") if isinstance(pl, dict) else None
                    fu = karna_ux.followups(body.get("action"), body.get("reply", ""), pl, srcs, "ws", request.message)
                except Exception:
                    fu = []
                yield _sse({"done": True, "result": body, "followups": fu})
            elif kind == "http":
                yield _sse({"error": str(val.detail), "status": val.status_code, "done": True})
            else:
                yield _sse({"error": "AI chat failed. Try again.", "status": 502, "done": True})
            return

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
