"""Brief persistence, lifecycle and action execution.

Lifecycle: generated -> shown -> partially_acted -> completed | expired | superseded | dismissed.
Execution never bypasses action_service: typed contract -> risk policy -> audit.
  low    : runs immediately
  medium : runs after the user confirms ON the brief (that confirmation is recorded as the approval)
  high   : becomes a pending approval; only /approve executes it
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

import action_service as A
import obs
from audit.logger import record as audit
from database import Brief, BriefAction
from . import schema

ACTIVE = ("generated", "shown", "partially_acted")


class BriefError(Exception):
    def __init__(self, status: int, detail: Any):
        self.status, self.detail = status, detail
        super().__init__(str(detail))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def urgency_label(score: float) -> str:
    return "high" if score >= 65 else "medium" if score >= 40 else "low"


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ------------------------------------------------------------------ build context
class Ctx:
    """Passed to every builder. `act()` registers a button; the same dict object may be shown in a priority and in the
    top-level `actions` list, so ids/status stay consistent."""

    def __init__(self, db: Session, uid: str, btype: str, params: Dict[str, Any]):
        self.db, self.uid, self.type, self.params = db, uid, btype, params
        self.brief_id = new_id("brf")
        self.actions: List[Dict[str, Any]] = []
        self.internal: Dict[str, Dict[str, Any]] = {}

    def act(self, type: str, label: str, *, kind: str = "navigate", risk: str = "low", intent: Optional[str] = None,
            payload: Optional[Dict[str, Any]] = None, link: Optional[str] = None, entity_id: Optional[str] = None,
            confirm: bool = False, primary: bool = False) -> Dict[str, Any]:
        if kind == "execute" and not intent:
            raise ValueError("execute actions need an intent")
        aid = new_id("act")
        a = {"id": aid, "action_id": aid, "brief_id": self.brief_id, "type": type, "label": label[:120], "risk": risk, "kind": kind,
             "requires_confirmation": bool(confirm), "requires_approval": bool(kind == "decision" or risk == "high"), "primary": bool(primary),
             "link": link, "entity_id": str(entity_id) if entity_id is not None else None, "status": "available"}
        self.actions.append(a)
        self.internal[a["action_id"]] = {"intent": intent, "payload": payload or {}}
        return a


# ------------------------------------------------------------------ persistence
def _db_time(dt: Optional[datetime]) -> Optional[datetime]:
    return dt


def persist(ctx: Ctx, doc: Dict[str, Any], *, scope_key: str, expires_at: Optional[datetime]) -> Dict[str, Any]:
    """Validate -> supersede older briefs for the same scope -> save brief + actions -> audit."""
    db, uid = ctx.db, ctx.uid
    doc = dict(doc, brief_id=ctx.brief_id, type=ctx.type, status="ready", generated_at=now_iso(), actions=ctx.actions)
    try:
        clean = schema.validate(doc)
    except Exception as e:                       # a malformed brief must never reach the UI
        raise BriefError(500, f"Brief failed validation: {str(e)[:300]}")

    for old in (db.query(Brief).filter(Brief.user_id == uid, Brief.type == ctx.type, Brief.scope_key == scope_key,
                                       Brief.status.in_(ACTIVE)).all()):
        old.status, old.superseded_by = "superseded", ctx.brief_id
    row = Brief(id=ctx.brief_id, user_id=uid, type=ctx.type, scope_key=scope_key, title=clean["title"], summary=clean["summary"],
                status="generated", confidence=clean["confidence"], params=ctx.params, body=clean, actions_taken=[],
                expires_at=expires_at)
    db.add(row)
    db.flush()
    for a in ctx.actions:
        meta = ctx.internal[a["action_id"]]
        db.add(BriefAction(id=a["action_id"], brief_id=row.id, user_id=uid, type=a["type"], label=a["label"], kind=a["kind"],
                           risk=a["risk"], intent=meta["intent"], payload=meta["payload"], payload_hash=_action_hash(meta["intent"], meta["payload"]),
                           link=a["link"], entity_id=a["entity_id"],
                           requires_confirmation=a["requires_confirmation"], primary=a["primary"], status="available"))
    db.commit()
    obs.emit("brief_created", brief_id=row.id, type=ctx.type, priorities=len(clean["priorities"]), actions=len(ctx.actions))
    audit(db, uid, f"brief.generate:{ctx.type}", {"brief_id": row.id, "scope": scope_key},
          {"priorities": len(clean["priorities"]), "actions": len(ctx.actions), "confidence": clean["confidence"]}, "low")
    return serialize(db, row)


def _action_hash(intent: Optional[str], payload: Optional[Dict[str, Any]]) -> str:
    return A.payload_hash({"intent": intent, "payload": payload or {}})


def _overlay(obj: Any, statuses: Dict[str, str]) -> None:
    """Refresh each embedded action's live status (available / executed / pending_approval ...)."""
    if isinstance(obj, dict):
        if "action_id" in obj and obj["action_id"] in statuses:
            obj["status"] = statuses[obj["action_id"]]
        for v in obj.values():
            _overlay(v, statuses)
    elif isinstance(obj, list):
        for v in obj:
            _overlay(v, statuses)


def serialize(db: Session, row: Brief) -> Dict[str, Any]:
    body = json.loads(json.dumps(row.body or {}))
    statuses = {a.id: a.status for a in db.query(BriefAction).filter(BriefAction.brief_id == row.id).all()}
    _overlay(body, statuses)
    body["lifecycle"] = row.status
    body["actions_taken"] = list(row.actions_taken or [])
    body["superseded_by"] = row.superseded_by
    body["expires_at"] = row.expires_at.isoformat() if row.expires_at else None
    return body


def _expire_if_due(db: Session, row: Brief) -> Brief:
    if row.status in ACTIVE and row.expires_at and row.expires_at < datetime.utcnow():
        row.status = "expired"
        db.commit()
    return row


def get_row(db: Session, uid: str, brief_id: str) -> Brief:
    row = db.query(Brief).filter(Brief.id == brief_id, Brief.user_id == uid).first()
    if not row:
        raise BriefError(404, "Brief not found")
    return _expire_if_due(db, row)


def fetch(db: Session, uid: str, brief_id: str) -> Dict[str, Any]:
    """GET: marks a generated brief as shown."""
    row = get_row(db, uid, brief_id)
    if row.status == "generated":
        row.status, row.shown_at = "shown", datetime.utcnow()
        db.commit()
        obs.emit("brief_shown", brief_id=row.id, type=row.type)
    return serialize(db, row)


def latest(db: Session, uid: str, btype: str, scope_key: str) -> Optional[Brief]:
    rows = (db.query(Brief).filter(Brief.user_id == uid, Brief.type == btype, Brief.scope_key == scope_key,
                                   Brief.status.in_(ACTIVE)).order_by(Brief.created_at.desc()).all())
    for r in rows:
        if _expire_if_due(db, r).status in ACTIVE:
            return r
    return None


def listing(db: Session, uid: str, btype: Optional[str], status: Optional[str], limit: int) -> List[Dict[str, Any]]:
    q = db.query(Brief).filter(Brief.user_id == uid)
    if btype:
        q = q.filter(Brief.type == btype)
    if status:
        q = q.filter(Brief.status == status)
    rows = q.order_by(Brief.created_at.desc()).limit(max(1, min(limit, 100))).all()
    return [{"brief_id": r.id, "type": r.type, "title": r.title, "summary": r.summary, "status": r.status,
             "confidence": float(r.confidence or 0), "created_at": r.created_at.isoformat() if r.created_at else None,
             "actions_taken": list(r.actions_taken or [])} for r in rows]


def dismiss(db: Session, uid: str, brief_id: str) -> Dict[str, Any]:
    row = get_row(db, uid, brief_id)
    if row.status in ("completed", "superseded"):
        raise BriefError(409, f"Brief is already {row.status}")
    row.status = "dismissed"
    db.commit()
    audit(db, uid, "brief.dismiss", {"brief_id": row.id}, {"type": row.type}, "low")
    return serialize(db, row)


# ------------------------------------------------------------------ actions
def public(ba: BriefAction) -> Dict[str, Any]:
    return {"id": ba.id, "action_id": ba.id, "brief_id": ba.brief_id, "type": ba.type, "label": ba.label, "risk": ba.risk, "kind": ba.kind,
            "requires_confirmation": bool(ba.requires_confirmation), "requires_approval": bool(ba.kind == "decision" or ba.risk == "high"),
            "primary": bool(ba.primary), "link": ba.link,
            "entity_id": ba.entity_id, "status": ba.status}


def find_action(db: Session, uid: str, action_id: str) -> Optional[BriefAction]:
    return db.query(BriefAction).filter(BriefAction.id == str(action_id), BriefAction.user_id == uid).first()


def is_brief_action(db: Session, action_id: str) -> bool:
    return db.query(BriefAction.id).filter(BriefAction.id == str(action_id)).first() is not None


def _mark_acted(db: Session, ba: BriefAction) -> None:
    brief = db.query(Brief).filter(Brief.id == ba.brief_id).first()
    if not brief:
        return
    taken = list(brief.actions_taken or [])
    tag = f"{ba.type}:{ba.entity_id}" if ba.entity_id else ba.type
    if tag not in taken:
        taken.append(tag)
    brief.actions_taken = taken
    if brief.status in ACTIVE:
        brief.status = "partially_acted"
        primaries = db.query(BriefAction).filter(BriefAction.brief_id == brief.id, BriefAction.primary == True).all()  # noqa: E712
        if primaries and all(p.status in ("executed", "closed") for p in primaries):
            brief.status = "completed"
    db.commit()


def _finish(db: Session, ba: BriefAction, rec: Dict[str, Any]) -> Dict[str, Any]:
    ba.action_record_id = rec.get("action_id")
    if rec["status"] == "executed":
        ba.status, ba.result, ba.executed_at = "executed", rec.get("result") or {}, datetime.utcnow()
        db.commit()
        _mark_acted(db, ba)
    elif rec["status"] == "rejected":
        ba.status = "rejected"
        db.commit()
    elif rec["status"] == "pending_approval":
        ba.status = "pending_approval"
        db.commit()
    else:
        ba.status = "failed"
        db.commit()
    out = {"status": ba.status, "action": public(ba), "result": rec.get("result") or {}, "action_record_id": rec.get("action_id")}
    if ba.status == "pending_approval":
        out["payload_hash"] = A.payload_hash(rec.get("payload") or {})
        out["preview"] = rec.get("payload") or {}
        out["message"] = "Waiting for your approval. Nothing has run yet."
    return out


def _resolve_decisions(db: Session, uid: str, rec_id: str, outcome: str, chosen_id: Optional[str] = None) -> None:
    """Both Approve and Reject buttons point at one action record. When it is decided (from either button OR the generic
    /v1/actions/{id}/approve), the matching button is 'executed' and its sibling is 'closed'."""
    chosen = []
    for ba in db.query(BriefAction).filter(BriefAction.user_id == uid, BriefAction.kind == "decision", BriefAction.status == "available").all():
        if (ba.payload or {}).get("action_record_id") != rec_id:
            continue
        if ba.id == chosen_id or (chosen_id is None and ba.type == outcome):
            ba.status, ba.executed_at = "executed", datetime.utcnow()
            chosen.append(ba)
        else:
            ba.status = "closed"
    db.commit()
    for ba in chosen:                      # after siblings are closed, so the brief can complete
        _mark_acted(db, ba)


def execute_action(db: Session, uid: str, action_id: str, confirm: bool = False) -> Dict[str, Any]:
    ba = find_action(db, uid, action_id)
    if not ba:
        raise BriefError(404, "Action not found")
    brief = get_row(db, uid, ba.brief_id)
    if ba.status == "executed":
        return {"status": "executed", "action": public(ba), "result": ba.result or {}, "duplicate": True, "navigate": ba.link}
    if ba.kind == "decision":
        raise BriefError(422, "Decisions use /v1/actions/{id}/approve or /reject")
    if ba.kind == "navigate":
        ba.status, ba.executed_at = "executed", datetime.utcnow()
        db.commit()
        _mark_acted(db, ba)
        return {"status": "executed", "action": public(ba), "navigate": ba.link, "result": {}}
    if brief.status in ("superseded", "dismissed", "expired"):
        raise BriefError(409, f"This brief is {brief.status}. Refresh it before acting on it.")
    if ba.payload_hash and ba.payload_hash != _action_hash(ba.intent, ba.payload):
        obs.emit("action_failed", reason="payload_hash_mismatch", action_id=ba.id)
        raise BriefError(409, "This action changed after it was shown. Refresh the brief and review it again.")
    if ba.status == "pending_approval" and not confirm:
        return {"status": "pending_approval", "action": public(ba), "action_record_id": ba.action_record_id,
                "message": "Waiting for your approval. Nothing has run yet."}
    if ba.requires_confirmation and not confirm:
        return {"status": "needs_confirmation", "action": public(ba),
                "preview": {"intent": ba.intent, "payload": ba.payload or {}, "risk": ba.risk},
                "message": "Confirm to proceed. Nothing has changed yet."}
    if confirm and ba.requires_confirmation:
        obs.emit("action_confirmed", action_id=ba.id, type=ba.type, risk=ba.risk)
    try:
        rec = A.propose(db, uid, ba.intent, ba.payload or {}, source="brief", reason=f"From {brief.type} brief", scope=brief.id)
        if rec["status"] == "pending_approval" and ba.risk == "medium" and confirm:
            # Medium risk: the user's explicit confirmation on the brief IS the approval; recorded with the payload hash.
            rec = A.decide(db, uid, rec["action_id"], True, A.payload_hash(rec["payload"]))
    except A.ActionError as e:
        raise BriefError(e.status, e.detail)
    return _finish(db, ba, rec)


def decide_action(db: Session, uid: str, action_id: str, approve: bool, payload_hash: Optional[str] = None) -> Dict[str, Any]:
    """approve/reject for a brief action (an execute action waiting for approval, or a decision button on an Approval brief)."""
    ba = find_action(db, uid, action_id)
    if not ba:
        raise BriefError(404, "Action not found")
    rec_id = ba.action_record_id or (ba.payload or {}).get("action_record_id")
    if not rec_id:
        raise BriefError(409, "Nothing is waiting for approval on this action")
    try:
        rec = A.decide(db, uid, rec_id, approve, payload_hash)
    except A.ActionError as e:
        raise BriefError(e.status, e.detail)
    if ba.kind == "decision":
        ba.result, ba.action_record_id = rec.get("result") or {}, rec_id
        db.commit()
        _resolve_decisions(db, uid, rec_id, "approve" if approve else "reject", chosen_id=ba.id)
        return {"status": rec["status"], "action": public(ba), "result": rec.get("result") or {}, "action_record_id": rec_id}
    return _finish(db, ba, rec)


def sync_from_record(db: Session, uid: str, rec: Dict[str, Any]) -> None:
    """Keep brief actions in step when an action is approved/rejected through the generic /v1/actions/{id}/approve."""
    rid = rec.get("action_id")
    for ba in db.query(BriefAction).filter(BriefAction.action_record_id == rid).all():
        if rec["status"] == "executed" and ba.status != "executed":
            ba.status, ba.result, ba.executed_at = "executed", rec.get("result") or {}, datetime.utcnow()
            db.commit(); _mark_acted(db, ba)
        elif rec["status"] == "rejected":
            ba.status = "rejected"; db.commit()
    if rec["status"] in ("executed", "rejected"):
        _resolve_decisions(db, uid, rid, "approve" if rec["status"] == "executed" else "reject")


# ------------------------------------------------------------------ language layer (Groq may only reword finished facts)
def narrate(doc: Dict[str, Any]) -> Optional[str]:
    if not os.getenv("GROQ_API_KEY"):
        return None
    try:
        from agent_service import call_groq_json
        facts = {"title": doc["title"], "summary": doc["summary"],
                 "priorities": [{"title": p["title"], "minutes": p.get("duration_min"), "why": p.get("reason_text")} for p in doc["priorities"][:4]],
                 "alerts": [a["title"] for a in doc["alerts"][:4]]}
        out = call_groq_json("Return JSON {\"narrative\": string}. In at most 2 short friendly sentences, restate this brief for the student. "
                             "Use ONLY the facts in the JSON. Do not add dates, numbers, names or advice that are not present.", json.dumps(facts, default=str))
        text = (json.loads(out).get("narrative") or "").strip()
        return text[:500] or None
    except Exception:
        return None


def add_narrative(db: Session, row_dict: Dict[str, Any]) -> Dict[str, Any]:
    text = narrate(row_dict)
    if text:
        row = db.query(Brief).filter(Brief.id == row_dict["brief_id"]).first()
        body = dict(row.body or {})
        body["explanation"] = dict(body.get("explanation") or {}, narrative=text)
        row.body = body
        db.commit()
        row_dict["explanation"]["narrative"] = text
    return row_dict
