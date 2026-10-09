"""POST /v1/chat: the ONE contract every channel consumes (web chat, KARNA popup, WhatsApp adapter, API).

request  : {user_id, text, channel, timezone, conversation_id, history, doc_ids}
pipeline : normalise tz/channel -> typed intent (registry) -> validate/missing fields -> workflow handler -> brief + actions -> audit
response : {request_id, conversation_id, intent, confidence, status: needs_input|completed|refused, reply, brief, brief_id,
            actions[], next_input, data}
Actions are the same objects briefs.html renders and /v1/actions/{id}/execute runs."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import obs
import reminders as RM
from agent import intents as I
from database import User, get_db

router = APIRouter()


class ChatIn(BaseModel):
    user_id: str
    text: str = Field(min_length=1, max_length=2000)
    channel: Literal["web_chat", "popup", "whatsapp", "api"] = "web_chat"
    timezone: Optional[str] = Field(default=None, max_length=64)       # IANA, e.g. Asia/Kolkata
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    history: Optional[List[Dict[str, str]]] = None
    doc_ids: Optional[List[str]] = None


@router.post("/v1/chat")
def chat(p: ChatIn, db: Session = Depends(get_db)):
    from agent_service import process_jarvis_message
    uid = str(p.user_id)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    request_id = "req_" + uuid.uuid4().hex[:16]
    conv = p.conversation_id or "conv_" + uuid.uuid4().hex[:16]
    if p.timezone and RM.valid_zone(p.timezone) and RM.tz_name(db, uid) != p.timezone:
        RM.set_tz(db, uid, name=p.timezone)

    try:
        intent = I.resolve(db, uid, p.text, p.channel)
    except Exception:
        db.rollback()
        intent = I.build("general_chat", 0.3, {}, p.channel)
    obs.emit("intent_classified", request_id=request_id, intent=intent.name, confidence=intent.confidence, channel=p.channel,
             clarification=bool(intent.missing_fields))
    base = {"request_id": request_id, "conversation_id": conv, **intent.as_dict(), "brief": None, "brief_id": None, "actions": [], "next_input": None, "data": None, "tool_calls": None}
    if not intent.channel_allowed:
        return {**base, "status": "refused", "reply": "That is not available on this channel. Open OPAI in the app to do it."}

    from schemas import ChatTurn
    hist = [ChatTurn(role=h.get("role", "user"), content=h.get("content", "")) for h in (p.history or [])][-8:] or None
    resp = process_jarvis_message(uid, p.text, db, history=hist, doc_ids=p.doc_ids)
    pl = resp.payload if isinstance(resp.payload, dict) else {}
    out = {**base, "reply": resp.reply, "status": pl.get("status") or "completed", "tool_calls": resp.tool_calls, "action": resp.action}
    if pl.get("intent") in I.REGISTRY:                       # the handler knows best (e.g. answered the pending title question)
        out["intent"] = pl["intent"]
    if resp.action == "brief":
        from briefs import jarvis
        out.update(brief=jarvis.preview(pl["brief"]), brief_id=pl["brief_id"], actions=pl.get("actions") or [])
    elif resp.action == "reminder":
        out.update(brief=pl.get("brief"), brief_id=pl.get("brief_id"), actions=pl.get("actions") or [], next_input=pl.get("next_input"), data={k: pl[k] for k in ("reminder", "reminders", "daily_brief") if k in pl} or None)
    else:
        out["data"] = {"action": resp.action, "payload": pl or resp.payload} if resp.payload else {"action": resp.action}
    return out
