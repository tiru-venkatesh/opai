"""Professor discovery from the bundled faculty CSV: /v1/opp/faculty/*"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auto_outreach as AO
import faculty_search as F
import outreach_guard as G
from audit.logger import record as audit
from database import Contact, Project, SuppressedContact, User, get_db
from opportunities_api import _contact_out, _profile_view, _skill_pool, _user

router = APIRouter(prefix="/v1/opp/faculty", tags=["opportunities"])


def _auto_query(db: Session, u: User) -> str:
    """Query built from what the user has actually entered: confirmed profile skills, resume skills, project tech."""
    pool = _skill_pool(db, u)
    prof = _profile_view(u)["profile"]
    terms = list(pool.keys())[:25] + [r for r in (prof.get("role_types") or []) if r == "research"]
    return " ".join(dict.fromkeys(terms))


@router.get("/search")
def faculty_search(user_id: str, q: Optional[str] = None, institute: Optional[str] = None, limit: int = 20,
                   include_on_leave: bool = False, db: Session = Depends(get_db)):
    """With q: search. Without q: rank professors against the user's own skills and projects ('recommended for you')."""
    u = _user(db, user_id)
    auto = not (q or "").strip()
    query = _auto_query(db, u) if auto else q.strip()
    have = {c.email for c in db.query(Contact).all() if c.email}
    suppressed = {x.email for x in db.query(SuppressedContact).filter(SuppressedContact.user_id == u.id).all()}
    if not query:   # nothing to rank by (new profile, no text): show the dataset itself instead of an empty box
        b = F.browse(institute, limit, include_on_leave, exclude_emails=suppressed)
        for it in b["items"]:
            it["already_added"] = it["email"] in have
        return {"auto": False, "browse": True, "query_used": "", "items": b["items"], "total": b["total"], "institutes": F.institutes(),
                "total_in_dataset": len(F.load_rows()),
                "note": "Showing the dataset A-Z. Type a research area, or add skills to your profile, to rank by fit. Data is scraped and unverified."}
    items = F.search(query, institute, limit, include_on_leave, exclude_emails=suppressed)
    for it in items:
        it["already_added"] = it["email"] in have
    return {"auto": auto, "query_used": query, "items": items, "institutes": F.institutes(), "total_in_dataset": len(F.load_rows()),
            "note": "Results come from a scraped dataset and may be outdated. Check each professor's official page before reaching out."}


class AddBody(BaseModel):
    user_id: str
    faculty_id: str = Field(min_length=6, max_length=20)


@router.post("/add")
def add_faculty(p: AddBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    r = F.get(p.faculty_id)
    if not r:
        raise HTTPException(404, "Professor not found in the dataset")
    if G.is_suppressed(db, u.id, r["email"]):
        raise HTTPException(409, "This address is on your do-not-contact list.")
    c = db.query(Contact).filter(Contact.email == r["email"]).first()
    if not c:
        c = Contact(name=r["name"], institute=f"{r['institute']} - {r['department']}" if r["department"] else r["institute"], email=r["email"],
                    research_areas=r["research_areas"], status="Not started", source_url=r["website"], source_checked_on=None,
                    email_verification="unverified")
        db.add(c)
        db.commit()
        db.refresh(c)
        audit(db, u.id, "opp.faculty_add", {"faculty_id": r["id"]}, {"contact_id": c.id}, "low")
    out = _contact_out(db, c, u.id)
    out["next"] = "Open their official page, confirm the research connection and email, then build a research brief."
    return out


# ---------------- daily auto-draft (one draft per 24h at the IIT the user picked; the user still approves) ----------------
class AutoBody(BaseModel):
    user_id: str
    enabled: bool
    institute: Optional[str] = Field(default=None, max_length=80)


@router.get("/auto")
def auto_status(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return AO.status(db, u.id)


@router.put("/auto")
def auto_set(p: AutoBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    inst = (p.institute or "").strip() or None
    if inst and inst.lower() not in {i.lower() for i in F.institutes()}:
        raise HTTPException(422, "Unknown institute. Pick one from the list.")
    if p.enabled and not inst:
        raise HTTPException(422, "Pick the IIT to write to first.")
    if inst:
        inst = next(i for i in F.institutes() if i.lower() == inst.lower())
    s = AO.get_setting(db, u.id, create=True)
    s.enabled, s.institute = bool(p.enabled), inst
    if p.enabled:
        s.last_attempt_at = None          # a fresh opt-in tries on the next tick, not after an old back-off
    db.commit()
    audit(db, u.id, "opp.auto_outreach_set", {"enabled": s.enabled, "institute": inst}, {}, "medium")
    return AO.status(db, u.id)


@router.post("/auto/run")
def auto_run(p: Optional[dict] = None, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Draft now instead of waiting for the scheduler. Still obeys the 24h gap, so it cannot be used to mass-draft."""
    uid = user_id or (p or {}).get("user_id")
    if not uid:
        raise HTTPException(422, "user_id is required")
    u = _user(db, uid)
    r = AO.run_for_user(db, u.id, force=True)
    return {**r, "status": AO.status(db, u.id)}
