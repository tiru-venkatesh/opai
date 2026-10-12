"""OPAI Feedback & Ideas API. Drop next to main.py, then:
    from feedback_api import router as feedback_router
    app.include_router(feedback_router)
Env: DATABASE_URL (sqlite default; Postgres ok), FEEDBACK_ADMIN_KEY (required for admin routes).
Needs: sqlalchemy (pip install sqlalchemy; psycopg2-binary for Postgres)."""
import os, uuid, hmac
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

_url = os.getenv("DATABASE_URL", "sqlite:///./opa_feedback.db")
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql://", 1)
engine = create_engine(_url, future=True, pool_pre_ping=True)

TYPES = {"idea", "bug", "general"}
STATUSES = ["Submitted", "Reviewing", "Planned", "In progress", "Released", "Not planned"]
LEVELS = {"low", "medium", "high"}
DAILY_LIMIT = 20

with engine.begin() as c:
    c.execute(text("""CREATE TABLE IF NOT EXISTS feedback_items (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, type TEXT NOT NULL, title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', product_area TEXT NOT NULL DEFAULT 'General',
        importance TEXT NOT NULL DEFAULT 'medium', status TEXT NOT NULL DEFAULT 'Submitted',
        priority TEXT NOT NULL DEFAULT '', app_version TEXT NOT NULL DEFAULT '',
        page_path TEXT NOT NULL DEFAULT '', request_id TEXT NOT NULL DEFAULT '',
        allow_follow_up INTEGER NOT NULL DEFAULT 0, admin_notes TEXT NOT NULL DEFAULT '',
        duplicate_of TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"""))
    c.execute(text("""CREATE TABLE IF NOT EXISTS feedback_votes (
        feedback_id TEXT NOT NULL, user_id TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(feedback_id, user_id))"""))

router = APIRouter(tags=["feedback"])
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


class FeedbackIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    type: str
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(default="", max_length=4000)
    product_area: str = Field(default="General", max_length=60)
    importance: str = "medium"
    app_version: str = Field(default="", max_length=30)
    page_path: str = Field(default="", max_length=200)
    request_id: str = Field(default="", max_length=80)
    allow_follow_up: bool = False


class VoteIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)


class AdminPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = Field(default=None, max_length=10)
    admin_notes: Optional[str] = Field(default=None, max_length=4000)
    duplicate_of: Optional[str] = Field(default=None, max_length=60)


def _admin(key: Optional[str]):
    want = os.getenv("FEEDBACK_ADMIN_KEY", "")
    if not want or not key or not hmac.compare_digest(key, want):
        raise HTTPException(403, "Admin key required")


def _rows(r):
    return [dict(x._mapping) for x in r]


@router.post("/v1/feedback")
def submit(b: FeedbackIn):
    if b.type not in TYPES: raise HTTPException(422, "type must be idea, bug or general")
    if b.importance not in LEVELS: raise HTTPException(422, "importance must be low, medium or high")
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with engine.begin() as c:
        n = c.execute(text("SELECT COUNT(*) FROM feedback_items WHERE user_id=:u AND created_at>:s"),
                      {"u": b.user_id, "s": since}).scalar()
        if n >= DAILY_LIMIT: raise HTTPException(429, "Daily feedback limit reached. Try again tomorrow.")
        fid, t = uuid.uuid4().hex[:12], now()
        c.execute(text("""INSERT INTO feedback_items (id,user_id,type,title,description,product_area,importance,
            app_version,page_path,request_id,allow_follow_up,created_at,updated_at)
            VALUES (:id,:u,:ty,:ti,:d,:a,:im,:v,:p,:r,:f,:t,:t)"""),
            {"id": fid, "u": b.user_id, "ty": b.type, "ti": b.title.strip(), "d": b.description.strip(),
             "a": b.product_area.strip() or "General", "im": b.importance, "v": b.app_version,
             "p": b.page_path, "r": b.request_id, "f": int(b.allow_follow_up), "t": t})
    return {"id": fid, "status": "Submitted"}


@router.get("/v1/feedback/mine")
def mine(user_id: str = Query(min_length=1)):
    with engine.begin() as c:
        rows = _rows(c.execute(text("""SELECT i.id,i.type,i.title,i.description,i.product_area,i.status,i.created_at,
            (SELECT COUNT(*) FROM feedback_votes v WHERE v.feedback_id=i.id) AS votes
            FROM feedback_items i WHERE i.user_id=:u ORDER BY i.created_at DESC LIMIT 200"""), {"u": user_id}))
    return {"items": rows, "statuses": STATUSES}


@router.post("/v1/feedback/{fid}/vote")
def vote(fid: str, b: VoteIn):
    """'I want this too' toggle. Ideas only. UI for this ships later."""
    with engine.begin() as c:
        it = c.execute(text("SELECT type,duplicate_of FROM feedback_items WHERE id=:i"), {"i": fid}).first()
        if not it or it.type != "idea": raise HTTPException(404, "Idea not found")
        target = it.duplicate_of or fid
        had = c.execute(text("SELECT 1 FROM feedback_votes WHERE feedback_id=:f AND user_id=:u"),
                        {"f": target, "u": b.user_id}).first()
        if had:
            c.execute(text("DELETE FROM feedback_votes WHERE feedback_id=:f AND user_id=:u"), {"f": target, "u": b.user_id})
        else:
            c.execute(text("INSERT INTO feedback_votes (feedback_id,user_id,created_at) VALUES (:f,:u,:t)"),
                      {"f": target, "u": b.user_id, "t": now()})
        n = c.execute(text("SELECT COUNT(*) FROM feedback_votes WHERE feedback_id=:f"), {"f": target}).scalar()
    return {"voted": not had, "votes": n}


@router.get("/v1/admin/feedback")
def admin_list(type: str = "", product_area: str = "", status: str = "", x_admin_key: Optional[str] = Header(None)):
    _admin(x_admin_key)
    q, p = "SELECT i.*, (SELECT COUNT(*) FROM feedback_votes v WHERE v.feedback_id=i.id) AS votes FROM feedback_items i WHERE 1=1", {}
    for col, val in (("type", type), ("product_area", product_area), ("status", status)):
        if val: q += f" AND i.{col}=:{col}"; p[col] = val
    q += " ORDER BY i.created_at DESC LIMIT 500"
    with engine.begin() as c:
        items = _rows(c.execute(text(q), p))
    return {"items": items, "statuses": STATUSES}


@router.patch("/v1/admin/feedback/{fid}")
def admin_update(fid: str, b: AdminPatch, x_admin_key: Optional[str] = Header(None)):
    _admin(x_admin_key)
    sets, p = [], {"i": fid, "t": now()}
    if b.status is not None:
        if b.status not in STATUSES: raise HTTPException(422, "Unknown status")
        sets.append("status=:status"); p["status"] = b.status
    for f in ("priority", "admin_notes", "duplicate_of"):
        v = getattr(b, f)
        if v is not None: sets.append(f"{f}=:{f}"); p[f] = v.strip()
    if not sets: return {"ok": True}
    with engine.begin() as c:
        if not c.execute(text("SELECT 1 FROM feedback_items WHERE id=:i"), {"i": fid}).first():
            raise HTTPException(404, "Not found")
        if p.get("duplicate_of"):
            if p["duplicate_of"] == fid or not c.execute(text("SELECT 1 FROM feedback_items WHERE id=:i"), {"i": p["duplicate_of"]}).first():
                raise HTTPException(422, "Invalid duplicate target")
            # merge: the original's submitter counts as a vote on the target
            c.execute(text("""INSERT INTO feedback_votes (feedback_id,user_id,created_at)
                SELECT :tg, user_id, :t FROM feedback_items WHERE id=:i
                ON CONFLICT (feedback_id,user_id) DO NOTHING"""), {"tg": p["duplicate_of"], "i": fid, "t": p["t"]})
        c.execute(text(f"UPDATE feedback_items SET {','.join(sets)}, updated_at=:t WHERE id=:i"), p)
    return {"ok": True}
