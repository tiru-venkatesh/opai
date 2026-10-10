"""OPAI Opportunities: discovery -> evaluate -> prepare -> apply/reach out -> follow up -> learn.

Boundaries enforced in code, not prompts:
  * LinkedIn is a USER-CONTROLLED source: pasted links/text and job-alert emails the user shares. No scraping, no
    browser automation, no connection requests, no auto-messaging. Nothing here fetches a URL.
  * OPAI never submits an application. The user marks "Applied". Email leaves only after the user approves an exact
    hash of the recipient/subject/body/attachments they reviewed (any edit invalidates it), and only the user's own
    click sends it: either through Gmail with a send-only token (never stored) or from their Gmail compose window.
  * Replies are never detected by reading the inbox. The follow-up flow asks "Have they replied?".
  * Eligibility is never claimed unless the posting AND the confirmed profile both state the facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import opp_parse as P
import outreach_guard as G
from audit.logger import record as audit
from database import (Application, ApplicationEvent, Contact, Opportunity, OutboxItem, OutreachHistory, Project,
                      ResearchBrief, Resume, SuppressedContact, User, get_db)

router = APIRouter(prefix="/v1/opp", tags=["opportunities"])

STAGES = ["Saved", "Reviewing", "Preparing", "Ready to submit", "Applied", "Assessment", "Interview",
          "Offer", "Rejected", "Withdrawn"]
TERMINAL = {"Offer", "Rejected", "Withdrawn"}
LEGACY_STAGE = {"to apply": "Saved", "draft": "Saved", "not started": "Saved"}
FOLLOWUP_DAYS = 7
MAX_FOLLOWUPS_PER_CONTACT = 1


# ---------------------------------------------------------------- helpers
def _user(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == str(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _llm_json(system: str, prompt: str) -> Optional[Dict[str, Any]]:
    try:
        from agent.groq_client import generate_json, groq_enabled
        if not groq_enabled():
            return None
        out = generate_json(system, prompt)
        return out if isinstance(out, dict) else None
    except Exception:
        return None


def stage_of(a: Application) -> str:
    s = (a.status or "Saved").strip()
    if s in STAGES:
        return s
    return LEGACY_STAGE.get(s.lower(), s)


def _own_opp(db: Session, uid: str, opp_id: str) -> Opportunity:
    o = db.query(Opportunity).filter(Opportunity.id == opp_id).first()
    if not o or (o.user_id and o.user_id != uid):
        raise HTTPException(404, "Opportunity not found")
    return o


def _own_app(db: Session, uid: str, app_id: str) -> Application:
    a = db.query(Application).filter(Application.id == app_id, Application.user_id == uid).first()
    if not a:
        raise HTTPException(404, "Application not found")
    return a


def _event(db: Session, uid: str, app_id: str, kind: str, note: str = "", frm: str = None, to: str = None,
           at: datetime = None) -> ApplicationEvent:
    ev = ApplicationEvent(user_id=uid, application_id=app_id, kind=kind, from_status=frm, to_status=to, note=note or None, event_at=at)
    db.add(ev)
    return ev


# ================================================================ 1. PROFILE
class ProfileBody(BaseModel):
    user_id: str
    degree: Optional[str] = Field(default=None, max_length=80)
    year: Optional[int] = Field(default=None, ge=1, le=6)
    branch: Optional[str] = Field(default=None, max_length=80)
    college: Optional[str] = Field(default=None, max_length=120)
    graduation_date: Optional[str] = Field(default=None, max_length=20)
    skills: Optional[List[str]] = None
    role_types: Optional[List[str]] = None          # internship | research | part-time
    locations: Optional[List[str]] = None
    work_modes: Optional[List[str]] = None          # remote | hybrid | onsite
    available_from: Optional[str] = Field(default=None, max_length=20)
    available_to: Optional[str] = Field(default=None, max_length=20)
    cgpa: Optional[float] = Field(default=None, ge=0, le=10)
    eligibility_notes: Optional[str] = Field(default=None, max_length=500)
    communication_style: Optional[str] = Field(default=None, max_length=300)
    resume_url: Optional[str] = Field(default=None, max_length=300)
    portfolio_url: Optional[str] = Field(default=None, max_length=300)
    github_url: Optional[str] = Field(default=None, max_length=300)
    confirm: bool = False


_PROFILE_KEYS = ["degree", "year", "branch", "college", "graduation_date", "skills", "role_types", "locations", "work_modes",
                 "available_from", "available_to", "cgpa", "eligibility_notes", "communication_style", "resume_url",
                 "portfolio_url", "github_url"]


def _stored_profile(u: User) -> Dict[str, Any]:
    return dict((u.preferences or {}).get("opportunity_profile") or {})


def _profile_view(u: User) -> Dict[str, Any]:
    """Stored (user-confirmed) values win. Prefill only from fields the user explicitly entered elsewhere in OPAI."""
    stored = _stored_profile(u)
    prefill = {"degree": u.degree, "branch": u.branch, "cgpa": float(u.cgpa) if u.cgpa is not None else None,
               "skills": [s.strip() for s in (u.skills or "").split(",") if s.strip()],
               "github_url": u.github}
    merged = {k: stored.get(k) if k in stored else prefill.get(k) for k in _PROFILE_KEYS}
    missing = [k for k in ("degree", "year", "branch", "college", "graduation_date", "skills", "role_types") if not merged.get(k)]
    return {"profile": merged, "confirmed_at": stored.get("confirmed_at"), "is_confirmed": bool(stored.get("confirmed_at")),
            "prefilled_from_account": [k for k in prefill if k not in stored and prefill.get(k)],
            "missing": missing,
            "note": "Review and confirm. OPAI does not infer eligibility details (work authorization, category, etc.) from other data."}


@router.get("/profile")
def get_profile(user_id: str, db: Session = Depends(get_db)):
    return _profile_view(_user(db, user_id))


@router.put("/profile")
def put_profile(p: ProfileBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    stored = _stored_profile(u)
    for k, v in p.model_dump(exclude_unset=True).items():
        if k in _PROFILE_KEYS:
            stored[k] = v
    if p.confirm:
        stored["confirmed_at"] = datetime.utcnow().isoformat()
    elif any(k in p.model_dump(exclude_unset=True) for k in _PROFILE_KEYS):
        stored.pop("confirmed_at", None)        # edits after confirmation need re-confirmation
    prefs = dict(u.preferences or {})
    prefs["opportunity_profile"] = stored
    u.preferences = prefs
    db.commit()
    audit(db, u.id, "opp.profile_update", {"confirm": p.confirm}, {"ok": True}, "low")
    return _profile_view(u)


def _skill_pool(db: Session, u: User) -> Dict[str, str]:
    """skill -> where it is evidenced. Only from confirmed profile skills, resumes and projects."""
    pool: Dict[str, str] = {}
    prof = _profile_view(u)["profile"]
    for s in prof.get("skills") or []:
        pool[str(s).strip().lower()] = "profile"
    for r in db.query(Resume).filter(Resume.user_id == u.id).all():
        for s in (r.skills or []):
            pool.setdefault(str(s).strip().lower(), f"resume: {r.label}")
    for pr in db.query(Project).filter(Project.user_id == u.id).all():
        for s in (pr.tech_stack or []):
            pool.setdefault(str(s).strip().lower(), f"project: {pr.title}")
    return {k: v for k, v in pool.items() if k}


def _has(pool: Dict[str, str], tag: str) -> Optional[str]:
    for k, src in pool.items():
        if k == tag or (len(tag) > 3 and tag in k) or (len(k) > 3 and k in tag):
            return src
    return None


# ================================================================ 2. INTAKE (user-controlled)
class IntakeBody(BaseModel):
    user_id: str
    url: Optional[str] = Field(default=None, max_length=600)
    text: Optional[str] = Field(default=None, max_length=20000)


@router.post("/intake/preview")
def intake_preview(p: IntakeBody, db: Session = Depends(get_db)):
    """Extract fields from pasted posting text and/or a link. NOTHING is saved and no URL is fetched.
    If only a link was given, the link is kept as a reference and the user is asked to paste the posting text."""
    _user(db, p.user_id)
    if not (p.url or "").strip() and not (p.text or "").strip():
        raise HTTPException(422, "Paste a job link, the posting text, or both.")
    parsed = P.parse_posting(p.text or "", p.url)
    if p.url and not parsed["source_url"]:
        raise HTTPException(422, "That does not look like a valid link.")
    parsed["message"] = ("Only a link was given. OPAI does not open or scrape pages for you: open it yourself and paste the posting text "
                         "so details can be extracted, or fill the fields below by hand.") if not (p.text or "").strip() else \
                        "Check each field. Anything marked guess or missing needs your confirmation before it is saved."
    parsed["open_source_url"] = parsed["source_url"]
    dups = _find_dups(db, p.user_id, (parsed["fields"].get("company") or {}).get("value"), (parsed["fields"].get("title") or {}).get("value"),
                      parsed["source_url"])
    parsed["possible_duplicates"] = dups
    return parsed


class EmailBody(BaseModel):
    user_id: str
    text: str = Field(min_length=10, max_length=60000)


@router.post("/intake/email-preview")
def intake_email_preview(p: EmailBody, db: Session = Depends(get_db)):
    """Parse a job-alert email the user pasted or forwarded. Candidates only; the user picks which to track."""
    _user(db, p.user_id)
    cands = P.parse_alert_email(p.text)
    for c in cands:
        c["possible_duplicates"] = _find_dups(db, p.user_id, c.get("company"), c.get("title"), c["source_url"])
    return {"candidates": cands, "count": len(cands),
            "note": "Nothing is saved yet. Select the roles you want to track; details are confirmed on each card."}


class IntakeConfirm(BaseModel):
    user_id: str
    title: str = Field(min_length=2, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    source_url: Optional[str] = Field(default=None, max_length=600)
    source_type: str = "manual"
    location: Optional[str] = Field(default=None, max_length=160)
    work_mode: Optional[str] = None
    role_type: str = "internship"
    deadline: Optional[date] = None
    description_text: Optional[str] = Field(default=None, max_length=8000)
    requirements: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    confirmed_fields: List[str] = Field(default_factory=list)    # fields the user checked on the review card
    extracted_fields: List[str] = Field(default_factory=list)    # fields that came from the posting text
    allow_duplicate: bool = False


_SOURCES = {"linkedin_user_saved", "email_alert", "career_page", "faculty_page", "referral", "manual", "feed"}


def _find_dups(db: Session, uid: str, company: Optional[str], title: Optional[str], url: Optional[str]) -> List[Dict[str, Any]]:
    def n(s):
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    out = []
    for o in db.query(Opportunity).filter((Opportunity.user_id == uid) | (Opportunity.user_id.is_(None))).filter(Opportunity.status != "Dismissed").all():
        if (url and o.link and o.link == url) or (company and title and n(o.company_or_lab) == n(company) and n(o.title) == n(title)):
            out.append({"id": o.id, "title": o.title, "company": o.company_or_lab, "status": o.status})
    return out[:5]


@router.post("/intake/confirm")
def intake_confirm(p: IntakeConfirm, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    nu = P.normalize_url(p.source_url) if p.source_url else {"url": None, "source_type": None}
    stype = p.source_type if p.source_type in _SOURCES else "manual"
    if nu.get("source_type") == "linkedin_user_saved":
        stype = "linkedin_user_saved"
    if p.work_mode and p.work_mode not in ("remote", "hybrid", "onsite"):
        raise HTTPException(422, "work_mode must be remote, hybrid or onsite.")
    if not p.allow_duplicate:
        d = _find_dups(db, u.id, p.company, p.title, nu.get("url"))
        if d:
            raise HTTPException(409, f"This looks like something you already track ({d[0]['title']} at {d[0]['company']}). Pass allow_duplicate to add it anyway.")
    confirmed = set(p.confirmed_fields)
    extracted = set(p.extracted_fields)
    fsrc = {}
    for f in ("title", "company", "location", "work_mode", "deadline", "requirements"):
        fsrc[f] = "user_confirmed" if f in confirmed else ("posting_unconfirmed" if f in extracted else "user_entered")
    o = Opportunity(user_id=u.id, title=p.title.strip(), company_or_lab=p.company.strip(), type=p.role_type, description=p.description_text,
                    link=nu.get("url"), source=stype, source_type=stype, status="New", tags=sorted({t.strip().lower() for t in p.tags if t.strip()}),
                    deadline=p.deadline, location=p.location, work_mode=p.work_mode, requirements=p.requirements[:15],
                    field_sources=fsrc, last_verified_at=datetime.utcnow())
    db.add(o)
    db.commit()
    db.refresh(o)
    audit(db, u.id, "opp.intake_confirm", {"source_type": stype}, {"opportunity_id": o.id}, "low")
    return {"opportunity": _opp_out(o), "brief": build_brief(db, u, o)}


def _opp_out(o: Opportunity) -> Dict[str, Any]:
    return {"id": o.id, "title": o.title, "organization": o.company_or_lab, "role_type": o.type, "source_type": o.source_type or o.source,
            "source_url": o.link, "location": o.location, "work_mode": o.work_mode, "deadline": o.deadline.isoformat() if o.deadline else None,
            "status": o.status, "tags": o.tags or [], "requirements": o.requirements or [],
            "last_verified_at": o.last_verified_at.isoformat() if o.last_verified_at else None}


# ================================================================ 3. MATCH & DECIDE (Opportunity Brief)
_YEAR_WORDS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "pre-final": 3, "pre final": 3, "prefinal": 3,
               "fourth": 4, "4th": 4, "final": 4}


def _check_requirement(req: str, prof: Dict[str, Any]) -> Dict[str, str]:
    """met | unmet | unknown. Only compares against profile values the user entered; otherwise unknown."""
    r = req.lower()
    m = re.search(r"(?:cgpa|gpa)\D{0,15}(\d(?:\.\d+)?)", r) or re.search(r"(\d(?:\.\d+)?)\s*\+?\s*(?:cgpa|gpa)", r)
    if m:
        if prof.get("cgpa") is None:
            return {"requirement": req, "status": "unknown", "why": "Your CGPA is not in your confirmed profile."}
        ok = float(prof["cgpa"]) >= float(m.group(1))
        return {"requirement": req, "status": "met" if ok else "unmet", "why": f"Your profile CGPA is {prof['cgpa']}; posting states {m.group(1)}."}
    ym = re.search(r"\b(pre[\s-]?final|final|first|second|third|fourth|1st|2nd|3rd|4th)[\s-]*year\b", r)
    if ym:
        need = _YEAR_WORDS.get(ym.group(1).replace("  ", " ").replace("-", " ").strip(), _YEAR_WORDS.get(ym.group(1)))
        if not prof.get("year") or need is None:
            return {"requirement": req, "status": "unknown", "why": "Your year of study is not in your confirmed profile."}
        ok = int(prof["year"]) == need
        return {"requirement": req, "status": "met" if ok else "unmet", "why": f"Posting asks for year {need}; your profile says year {prof['year']}."}
    gm = re.search(r"\b(20\d{2})\s*(?:batch|graduat|pass[\s-]?out)|(?:graduat\w*|batch|pass[\s-]?out)\D{0,15}(20\d{2})", r)
    if gm:
        want = gm.group(1) or gm.group(2)
        have = (prof.get("graduation_date") or "")[:4]
        if not have:
            return {"requirement": req, "status": "unknown", "why": "Your graduation date is not in your confirmed profile."}
        return {"requirement": req, "status": "met" if have == want else "unmet", "why": f"Posting mentions {want}; your profile says {have}."}
    return {"requirement": req, "status": "unknown", "why": "Cannot be checked against your profile. Verify on the posting."}


def build_brief(db: Session, u: User, o: Opportunity) -> Dict[str, Any]:
    """Opportunity Brief with four kinds of signal kept apart: verified facts, profile match, unknown, AI suggestion."""
    view = _profile_view(u)
    prof, confirmed = view["profile"], view["is_confirmed"]
    pool = _skill_pool(db, u)
    tags = [t.lower() for t in (o.tags or [])]
    matched = [(t, _has(pool, t)) for t in tags if _has(pool, t)]
    gaps = [t for t in tags if not _has(pool, t)]
    fs = o.field_sources or {}

    verified = []
    for label, val, key in (("Title", o.title, "title"), ("Organization", o.company_or_lab, "company"), ("Location", o.location, "location"),
                            ("Work mode", o.work_mode, "work_mode"), ("Deadline", o.deadline.isoformat() if o.deadline else None, "deadline")):
        if val and fs.get(key) in ("user_confirmed", "user_entered", None):
            verified.append({"field": label, "value": val, "basis": "confirmed by you" if fs.get(key) == "user_confirmed" else "entered by you"})
    unknown = []
    for label, val, key in (("Location", o.location, "location"), ("Work mode", o.work_mode, "work_mode"), ("Deadline", o.deadline, "deadline")):
        if not val:
            unknown.append(f"{label} is not stated. Check the source page.")
        elif fs.get(key) == "posting_unconfirmed":
            unknown.append(f"{label} was read from pasted text and is not confirmed yet.")

    checks = [_check_requirement(r, prof) for r in (o.requirements or [])]
    unmet = [c for c in checks if c["status"] == "unmet"]
    unk = [c for c in checks if c["status"] == "unknown"]
    if unmet:
        elig = "Does not appear eligible"
    elif checks and not unk and confirmed:
        elig = "Appears eligible"
    elif not checks:
        elig = "No eligibility rules recorded. Confirm on the posting"
    else:
        elig = "Appears eligible so far; some requirements need confirmation"
    for c in unk:
        unknown.append(c["requirement"][:140] + " - needs your verification")
    if not confirmed:
        unknown.append("Your opportunity profile is not confirmed, so this match is provisional.")

    ratio = (len(matched) / len(tags)) if tags else None
    if unmet:
        label = "Poor"
    elif ratio is None:
        label = "Unclear"
    elif ratio >= 0.7:
        label = "Strong"
    elif ratio >= 0.4:
        label = "Good"
    else:
        label = "Partial"

    days_left = (o.deadline - date.today()).days if o.deadline else None
    urgency = ("none" if days_left is None else "overdue" if days_left < 0 else "critical" if days_left <= 3 else "soon" if days_left <= 7 else "ok")
    prep = 45 + 20 * min(len(gaps), 3) + (15 if (o.requirements or []) else 0)

    suggestions = []
    if gaps:
        suggestions.append(f"If you have worked with {', '.join(gaps[:3])}, add it to your profile or resume; otherwise treat it as a gap.")
    if matched:
        suggestions.append("Lead your resume with: " + ", ".join(t for t, _ in matched[:4]) + ".")
    if urgency in ("critical", "soon"):
        suggestions.append("Deadline is close. Decide today whether to pursue it.")
    gen = _llm_json("You help a student decide on an opportunity. Return JSON {\"suggestions\": [up to 3 short strings]}. "
                    "Use ONLY the facts given. Never state eligibility, deadlines or requirements that are not in the facts.",
                    json.dumps({"title": o.title, "org": o.company_or_lab, "requirements": (o.requirements or [])[:8], "matched": [t for t, _ in matched], "gaps": gaps}))
    if gen and isinstance(gen.get("suggestions"), list):
        suggestions += [str(s)[:200] for s in gen["suggestions"][:3] if isinstance(s, str)]

    if unmet:
        nxt = "Check the unmet requirement on the source page; if it is firm, mark Not interested."
    elif urgency == "overdue":
        nxt = "The deadline has passed. Verify on the source page before spending time."
    elif label in ("Strong", "Good"):
        nxt = "Review the posting, then prepare a role-specific resume."
    else:
        nxt = "Open the source and decide whether the gaps are worth closing."
    return {
        "opportunity_id": o.id, "title": o.title, "organization": o.company_or_lab, "match": label,
        "match_detail": {"matched": [{"skill": t, "evidence": s} for t, s in matched], "gaps": gaps,
                         "profile_confirmed": confirmed},
        "eligibility": {"summary": elig, "checks": checks},
        "deadline": o.deadline.isoformat() if o.deadline else None, "days_left": days_left, "urgency": urgency,
        "estimated_prep_minutes": prep,
        "signals": {"verified_facts": verified, "profile_match": [f"{t} (from {s})" for t, s in matched], "unknown": unknown,
                    "ai_suggestions": suggestions},
        "recommended_next_step": nxt,
        "source": {"type": o.source_type or o.source, "url": o.link, "last_verified_at": o.last_verified_at.isoformat() if o.last_verified_at else None,
                   "stale": bool(o.last_verified_at and (datetime.utcnow() - o.last_verified_at).days > 14)},
        "actions": ["open_source", "track", "not_interested"],
    }


def _visible_opps(db: Session, uid: str):
    return (db.query(Opportunity).filter(Opportunity.status == "New")
            .filter((Opportunity.user_id == uid) | (Opportunity.user_id.is_(None))).all())


@router.get("/opportunities/{opportunity_id}/brief")
def opportunity_brief(opportunity_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return build_brief(db, u, _own_opp(db, u.id, opportunity_id))


_RANK = {"Strong": 0, "Good": 1, "Partial": 2, "Unclear": 3, "Poor": 4}


@router.get("/saved")
def saved_opportunities(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    out = []
    for o in _visible_opps(db, u.id):
        b = build_brief(db, u, o)
        out.append({**_opp_out(o), "brief": {k: b[k] for k in ("match", "eligibility", "urgency", "days_left", "estimated_prep_minutes", "recommended_next_step")}})
    out.sort(key=lambda r: (_RANK.get(r["brief"]["match"], 5), r["deadline"] or "9999"))
    return {"items": out, "count": len(out)}


@router.get("/today-matches")
def todays_matches(user_id: str, limit: int = 5, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = []
    for o in _visible_opps(db, u.id):
        b = build_brief(db, u, o)
        if b["match"] in ("Strong", "Good") and b["urgency"] != "overdue" and b["eligibility"]["summary"] != "Does not appear eligible":
            rows.append((_RANK[b["match"]], o.deadline or date.max, b))
    rows.sort(key=lambda r: (r[0], r[1]))
    return {"items": [r[2] for r in rows[:max(1, min(limit, 20))]]}


@router.post("/opportunities/{opportunity_id}/dismiss")
def dismiss(opportunity_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    o = _own_opp(db, u.id, opportunity_id)
    o.status = "Dismissed"
    db.commit()
    return {"status": "dismissed"}


class RefreshBody(BaseModel):
    user_id: str
    deadline: Optional[date] = None
    note: Optional[str] = None


@router.post("/opportunities/{opportunity_id}/verified")
def mark_verified(opportunity_id: str, p: RefreshBody, db: Session = Depends(get_db)):
    """The user re-checked the source page: bump last_verified_at and optionally correct the deadline."""
    u = _user(db, p.user_id)
    o = _own_opp(db, u.id, opportunity_id)
    o.last_verified_at = datetime.utcnow()
    if p.deadline:
        o.deadline = p.deadline
        fs = dict(o.field_sources or {})
        fs["deadline"] = "user_confirmed"
        o.field_sources = fs
    db.commit()
    return _opp_out(o)


# ================================================================ 4. APPLICATION PIPELINE
def _checklist(a: Application) -> List[Dict[str, Any]]:
    return [
        {"item": "Verify requirements and deadline on the original posting", "done": stage_of(a) not in ("Saved",)},
        {"item": "Tailored resume version chosen", "done": bool(a.resume_id)},
        {"item": "Application answers / cover letter drafted", "done": bool(a.answers or a.cover_letter)},
        {"item": "You reviewed every document", "done": stage_of(a) in ("Ready to submit", "Applied", "Assessment", "Interview", "Offer", "Rejected", "Withdrawn")},
        {"item": "You submitted on the original site", "done": a.submitted_at is not None},
    ]


def _app_out(db: Session, a: Application, detail: bool = False) -> Dict[str, Any]:
    d = {"id": a.id, "company": a.company, "role": a.role, "type": a.type, "stage": stage_of(a), "deadline": a.deadline.isoformat() if a.deadline else None,
         "link": a.link, "source_type": a.source_type, "resume_id": a.resume_id, "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
         "follow_up_date": a.follow_up_date.isoformat() if a.follow_up_date else None, "contact_ref": a.contact_ref, "opportunity_id": a.opportunity_id}
    if detail:
        evs = (db.query(ApplicationEvent).filter(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.created_at.asc()).all())
        d.update({"notes": a.notes, "cover_letter": a.cover_letter, "answers": a.answers or [], "checklist": _checklist(a),
                  "history": [{"kind": e.kind, "from": e.from_status, "to": e.to_status, "note": e.note,
                               "event_at": e.event_at.isoformat() if e.event_at else None, "at": e.created_at.isoformat() if e.created_at else None} for e in evs]})
    return d


class TrackBody(BaseModel):
    user_id: str
    contact_ref: Optional[str] = Field(default=None, max_length=200)


@router.post("/opportunities/{opportunity_id}/track")
def track(opportunity_id: str, p: TrackBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    o = _own_opp(db, u.id, opportunity_id)
    existing = db.query(Application).filter(Application.user_id == u.id, Application.opportunity_id == o.id).first()
    if existing:
        raise HTTPException(409, "You are already tracking this opportunity.")
    a = Application(user_id=u.id, company=o.company_or_lab, role=o.title, type=o.type, status="Saved", deadline=o.deadline, link=o.link,
                    notes=None, opportunity_id=o.id, source_type=o.source_type or o.source, contact_ref=p.contact_ref,
                    effort_minutes=build_brief(db, u, o)["estimated_prep_minutes"])
    o.status = "Converted"
    db.add(a)
    db.flush()
    _event(db, u.id, a.id, "status", "Tracking started", None, "Saved")
    db.commit()
    db.refresh(a)
    audit(db, u.id, "opp.track", {"opportunity_id": o.id}, {"application_id": a.id}, "low")
    return _app_out(db, a, True)


@router.get("/pipeline")
def pipeline(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    cols = {s: [] for s in STAGES}
    for a in db.query(Application).filter(Application.user_id == u.id).all():
        cols.setdefault(stage_of(a), []).append(_app_out(db, a))
    return {"stages": STAGES, "columns": cols, "total": sum(len(v) for v in cols.values())}


@router.get("/applications/{application_id}")
def application_detail(application_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return _app_out(db, _own_app(db, u.id, application_id), True)


class StageBody(BaseModel):
    user_id: str
    to: str
    note: Optional[str] = Field(default=None, max_length=500)
    event_at: Optional[datetime] = None                 # interview / assessment time
    user_confirms_submitted: bool = False               # required for "Applied": the USER submitted on the original site
    follow_up_days: int = Field(default=FOLLOWUP_DAYS, ge=2, le=30)


@router.post("/applications/{application_id}/stage")
def set_stage(application_id: str, p: StageBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    a = _own_app(db, u.id, application_id)
    if p.to not in STAGES:
        raise HTTPException(422, f"Stage must be one of: {', '.join(STAGES)}.")
    cur = stage_of(a)
    if cur == p.to:
        return _app_out(db, a, True)
    if p.to == "Applied":
        if not p.user_confirms_submitted:
            raise HTTPException(409, "OPAI never submits applications. Submit on the original site yourself, then confirm you did (user_confirms_submitted=true).")
        a.submitted_at = datetime.utcnow()
        a.follow_up_date = date.today() + timedelta(days=p.follow_up_days)
    elif p.to in TERMINAL:
        a.follow_up_date = None
    a.status = p.to
    _event(db, u.id, a.id, "interview" if p.to in ("Interview", "Assessment") and p.event_at else "status", p.note or "", cur, p.to, p.event_at)
    db.commit()
    audit(db, u.id, "opp.stage", {"application_id": a.id, "from": cur, "to": p.to}, {"ok": True}, "medium")
    out = _app_out(db, a, True)
    if p.to == "Applied":
        out["next"] = f"Follow-up reminder set for {a.follow_up_date.isoformat()}."
    return out


class PrepBody(BaseModel):
    user_id: str
    resume_id: Optional[str] = None
    cover_letter: Optional[str] = Field(default=None, max_length=6000)
    answers: Optional[List[Dict[str, str]]] = None
    notes: Optional[str] = Field(default=None, max_length=3000)
    contact_ref: Optional[str] = Field(default=None, max_length=200)
    deadline: Optional[date] = None


@router.put("/applications/{application_id}/prep")
def update_prep(application_id: str, p: PrepBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    a = _own_app(db, u.id, application_id)
    data = p.model_dump(exclude_unset=True)
    if "resume_id" in data and data["resume_id"]:
        if not db.query(Resume).filter(Resume.id == data["resume_id"], Resume.user_id == u.id).first():
            raise HTTPException(404, "Resume version not found")
        a.resume_id = data["resume_id"]
    for k in ("cover_letter", "notes", "contact_ref", "deadline"):
        if k in data:
            setattr(a, k, data[k])
    if "answers" in data and data["answers"] is not None:
        a.answers = [{"question": str(x.get("question", ""))[:300], "answer": str(x.get("answer", ""))[:3000]} for x in data["answers"][:20]]
    db.commit()
    return _app_out(db, a, True)


@router.delete("/applications/{application_id}")
def delete_application(application_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    a = _own_app(db, u.id, application_id)
    db.query(ApplicationEvent).filter(ApplicationEvent.application_id == a.id).delete()
    db.delete(a)
    db.commit()
    return {"status": "deleted"}


# ================================================================ 5. PROFESSOR OUTREACH
class ProfessorBody(BaseModel):
    user_id: str
    name: str = Field(min_length=2, max_length=120)
    institute: str = Field(min_length=2, max_length=160)
    department: Optional[str] = Field(default=None, max_length=120)
    source_url: Optional[str] = Field(default=None, max_length=500)
    email: Optional[str] = Field(default=None, max_length=254)
    email_shown_on_source: bool = False
    research_areas: List[str] = Field(default_factory=list)
    relevant_work: Optional[str] = Field(default=None, max_length=500)
    source_checked_on: Optional[date] = None


_EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/professors")
def add_professor(p: ProfessorBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    email = (p.email or "").strip().lower()
    if email and not _EMAIL_RX.match(email):
        raise HTTPException(422, "That email address is not valid.")
    nu = P.normalize_url(p.source_url) if p.source_url else {"url": None}
    if email:
        dup = db.query(Contact).filter(Contact.email == email).first()
        if dup:
            raise HTTPException(409, f"{dup.name} is already in your contacts.")
    ver = "public_on_page" if (email and p.email_shown_on_source and nu.get("url")) else "unverified"
    c = Contact(name=p.name.strip(), institute=p.institute.strip() + (f" - {p.department.strip()}" if p.department else ""), email=email,
                research_areas=[s.strip() for s in p.research_areas if s.strip()][:12], bio=None, status="Not started",
                source_url=nu.get("url"), source_checked_on=p.source_checked_on or (date.today() if nu.get("url") else None),
                email_verification=ver, relevant_work=p.relevant_work)
    db.add(c)
    db.commit()
    db.refresh(c)
    audit(db, u.id, "opp.professor_add", {"has_source": bool(nu.get("url"))}, {"contact_id": c.id}, "low")
    return _contact_out(db, c, u.id)


class ConfirmContact(BaseModel):
    user_id: str
    email: Optional[str] = Field(default=None, max_length=254)
    relevant_work: Optional[str] = Field(default=None, max_length=500)


@router.post("/professors/{contact_id}/confirm")
def confirm_professor(contact_id: str, p: ConfirmContact, db: Session = Depends(get_db)):
    """The user confirms the research connection and the email address before any draft is made."""
    u = _user(db, p.user_id)
    c = db.query(Contact).filter(Contact.id == contact_id).first()
    if not c:
        raise HTTPException(404, "Contact not found")
    if p.email:
        e = p.email.strip().lower()
        if not _EMAIL_RX.match(e):
            raise HTTPException(422, "That email address is not valid.")
        c.email = e
    if p.relevant_work is not None:
        c.relevant_work = p.relevant_work
    if not c.email:
        raise HTTPException(409, "Add the professor's email address first.")
    if c.email_verification == "unverified":
        c.email_verification = "user_confirmed"
    db.commit()
    return _contact_out(db, c, u.id)


class ListingBody(BaseModel):
    user_id: str
    text: str = Field(min_length=10, max_length=40000)


@router.post("/professors/parse-listing")
def parse_listing(p: ListingBody, db: Session = Depends(get_db)):
    _user(db, p.user_id)
    return {"candidates": P.parse_faculty_listing(p.text), "note": "Candidates only. Add each professor individually after checking their official page."}


def _contact_out(db: Session, c: Contact, uid: str) -> Dict[str, Any]:
    brief = (db.query(ResearchBrief).filter(ResearchBrief.user_id == uid, ResearchBrief.contact_id == c.id)
             .order_by(ResearchBrief.created_at.desc()).first())
    hist = (db.query(OutreachHistory).filter(OutreachHistory.user_id == uid, OutreachHistory.contact_id == c.id)
            .order_by(OutreachHistory.sent_at.desc()).first())
    return {"id": c.id, "name": c.name, "institute": c.institute, "email": c.email, "email_verification": c.email_verification or "unverified",
            "research_areas": c.research_areas or [], "source_url": c.source_url,
            "source_checked_on": c.source_checked_on.isoformat() if c.source_checked_on else None, "relevant_work": c.relevant_work,
            "outreach_status": c.status, "suppressed": bool(G.is_suppressed(db, uid, c.email)),
            "brief": {"id": brief.id, "verification": brief.verification, "relevance": brief.relevance} if brief else None,
            "last_outreach": {"status": hist.status, "follow_up_date": hist.follow_up_date.isoformat() if hist and hist.follow_up_date else None} if hist else None}


@router.get("/professors")
def list_professors(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    brief_ids = {b.contact_id for b in db.query(ResearchBrief).filter(ResearchBrief.user_id == u.id).all()}
    hist_ids = {h.contact_id for h in db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id).all()}
    rows = [c for c in db.query(Contact).all() if c.source_url or c.id in brief_ids or c.id in hist_ids or (c.status or "Not started") != "Not started"]
    return {"items": [_contact_out(db, c, u.id) for c in rows][:100],
            "daily_cap_remaining": G.remaining_today(db, u.id)}


# ================================================================ 6. OUTBOX: approval bound to the exact payload
def payload_hash(item: OutboxItem) -> str:
    pl = item.payload or {}
    canon = {"channel": item.channel, "to": (pl.get("to") or "").strip().lower(), "subject": pl.get("subject") or "", "body": pl.get("body") or "",
             "attachments": sorted(str(x) for x in (pl.get("attachments") or [])), "from": pl.get("from_account") or "", "ref": item.ref or {}}
    return hashlib.sha256(json.dumps(canon, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _own_outbox(db: Session, uid: str, oid: str) -> OutboxItem:
    it = db.query(OutboxItem).filter(OutboxItem.id == oid, OutboxItem.user_id == uid).first()
    if not it:
        raise HTTPException(404, "Outbox item not found")
    if it.status == "pending" and it.expires_at and it.expires_at < datetime.utcnow():
        it.status = "expired"
        db.commit()
    return it


def _recipient_info(db: Session, uid: str, it: OutboxItem) -> Dict[str, Any]:
    ref = it.ref or {}
    c = db.query(Contact).filter(Contact.id == ref.get("id")).first() if ref.get("kind") == "contact" else None
    to = ((it.payload or {}).get("to") or "").strip()
    return {"to": to, "valid_address": bool(_EMAIL_RX.match(to)),
            "source": c.source_url if c else None, "source_checked_on": c.source_checked_on.isoformat() if c and c.source_checked_on else None,
            "verification": (c.email_verification if c else "not_a_contact") or "unverified",
            "suppressed": bool(G.is_suppressed(db, uid, to)) if to else False}


@router.get("/outbox")
def outbox_list(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = db.query(OutboxItem).filter(OutboxItem.user_id == u.id, OutboxItem.channel == "email").order_by(OutboxItem.created_at.desc()).limit(50).all()
    return {"items": [{"id": r.id, "status": r.status, "to": (r.payload or {}).get("to"), "subject": (r.payload or {}).get("subject"),
                       "kind": (r.ref or {}).get("kind"), "created_at": r.created_at.isoformat() if r.created_at else None,
                       "sent_at": r.sent_at.isoformat() if r.sent_at else None} for r in rows],
            "daily_cap_remaining": G.remaining_today(db, u.id)}


@router.get("/outbox/{outbox_id}/review")
def outbox_review(outbox_id: str, user_id: str, db: Session = Depends(get_db)):
    """Everything the user must see before approving. The returned hash is what approval is bound to."""
    u = _user(db, user_id)
    it = _own_outbox(db, u.id, outbox_id)
    pl = it.payload or {}
    h = payload_hash(it)
    if it.payload_hash != h:
        it.payload_hash = h
        db.commit()
    ri = _recipient_info(db, u.id, it)
    warnings = []
    if not ri["valid_address"]:
        warnings.append("The recipient address is missing or invalid.")
    if ri["suppressed"]:
        warnings.append("This address is on your do-not-contact list.")
    if ri["verification"] == "unverified":
        warnings.append("The email address is not verified against an official source. Confirm it before approving.")
    if pl.get("attachments"):
        warnings.append("Attachments are not sent for you. Attach them yourself in Gmail; OPAI only records what you intended to attach.")
    return {"id": it.id, "status": it.status, "payload_hash": h, "recipient": ri, "subject": pl.get("subject"), "body": pl.get("body"),
            "attachments": pl.get("attachments") or [], "sending_account": pl.get("from_account") or "your signed-in Gmail account",
            "follow_up_if_sent": f"{FOLLOWUP_DAYS} days after you confirm it was sent", "warnings": warnings,
            "action_being_approved": f"Send this exact message to {ri['to'] or '(no recipient)'}", "expires_at": it.expires_at.isoformat() if it.expires_at else None}


class OutboxEdit(BaseModel):
    user_id: str
    to: Optional[str] = Field(default=None, max_length=254)
    subject: Optional[str] = Field(default=None, max_length=300)
    body: Optional[str] = Field(default=None, max_length=8000)
    attachments: Optional[List[str]] = None


@router.patch("/outbox/{outbox_id}")
def outbox_edit(outbox_id: str, p: OutboxEdit, db: Session = Depends(get_db)):
    """Editing changes the hash, so any earlier review no longer authorizes this content."""
    u = _user(db, p.user_id)
    it = _own_outbox(db, u.id, outbox_id)
    if it.status != "pending":
        raise HTTPException(409, f"Item is already '{it.status}'.")
    pl = dict(it.payload or {})
    for k, v in p.model_dump(exclude_unset=True).items():
        if k in ("to", "subject", "body", "attachments") and v is not None:
            pl[k] = v.strip() if isinstance(v, str) and k == "to" else v
    it.payload = pl
    it.reviewed_hash = None
    it.payload_hash = payload_hash(it)
    db.commit()
    return {"id": it.id, "payload_hash": it.payload_hash, "message": "Saved. Review the updated message again before approving."}


class OutboxApprove(BaseModel):
    user_id: str
    reviewed_hash: str = Field(min_length=64, max_length=64)
    confirm_recipient: bool = False      # required when the address is not verified against a source


@router.post("/outbox/{outbox_id}/approve")
def outbox_approve(outbox_id: str, p: OutboxApprove, db: Session = Depends(get_db)):
    """Authorizes ONE exact message. Does not send it: the user sends from their own Gmail (compose link returned),
    then confirms with /sent. If the content changed since review, approval is refused."""
    u = _user(db, p.user_id)
    it = _own_outbox(db, u.id, outbox_id)
    if it.status == "expired":
        raise HTTPException(410, "This draft expired. Draft it again.")
    if it.status != "pending":
        raise HTTPException(409, f"Item is already '{it.status}'.")
    current = payload_hash(it)
    if p.reviewed_hash != current:
        raise HTTPException(409, "This message changed after you reviewed it. Review it again before approving.")
    ri = _recipient_info(db, u.id, it)
    if not ri["valid_address"]:
        raise HTTPException(422, "The recipient address is missing or invalid.")
    if ri["verification"] == "unverified" and not p.confirm_recipient:
        raise HTTPException(409, "Confirm you have checked this email address (confirm_recipient=true) before approving.")
    ref = it.ref or {}
    if ref.get("kind") == "contact":
        c = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if c:
            try:
                G.check_can_send(db, u.id, c)
            except G.Blocked as e:
                raise HTTPException(e.status, e.detail)
    elif G.is_suppressed(db, u.id, ri["to"]):
        raise HTTPException(409, "This address is on your do-not-contact list.")
    it.status = "approved"
    it.reviewed_hash = current
    it.payload_hash = current
    db.commit()
    audit(db, u.id, "opp.outbox_approve", {"outbox_id": it.id}, {"hash": current[:12]}, "high")
    pl = it.payload or {}
    compose = ("https://mail.google.com/mail/?view=cm&fs=1&to=" + quote(ri["to"]) + "&su=" + quote(pl.get("subject") or "") + "&body=" + quote(pl.get("body") or ""))
    return {"id": it.id, "status": "approved", "approved_hash": current, "compose_url": compose,
            "message": "Approved for this exact message. Send it from Gmail, then press 'I sent it' so OPAI can log it and schedule a follow-up."}


class OutboxSent(BaseModel):
    user_id: str
    provider_message_id: Optional[str] = Field(default=None, max_length=200)
    sent_via: str = "gmail_compose"


def _log_sent(db: Session, u: User, it: OutboxItem, via: str, message_id: Optional[str]) -> Dict[str, Any]:
    """Bookkeeping once a message has really left (Gmail API) or the user confirmed they sent it (compose link)."""
    now = datetime.utcnow()
    it.sent_at, it.sent_via, it.provider_message_id = now, via[:40], message_id
    pl, ref = it.payload or {}, it.ref or {}
    fu = date.today() + timedelta(days=FOLLOWUP_DAYS)
    if ref.get("kind") == "contact":
        c = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if c:
            c.status, c.sent_on = "Sent", date.today()
            h = (db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.contact_id == c.id, OutreachHistory.status == "Draft",
                                                  OutreachHistory.subject == (pl.get("subject") or "")).first())
            if h:
                h.status, h.sent_at, h.follow_up_date, h.email_text = "Sent", now, fu, pl.get("body") or h.email_text
            else:
                db.add(OutreachHistory(user_id=u.id, contact_id=c.id, subject=pl.get("subject") or "", email_text=pl.get("body") or "", status="Sent", sent_at=now, follow_up_date=fu))
    elif ref.get("kind") == "application":
        a = db.query(Application).filter(Application.id == ref.get("id"), Application.user_id == u.id).first()
        if a:
            a.follow_up_date = fu + timedelta(days=FOLLOWUP_DAYS)
            _event(db, u.id, a.id, "followup", f"Follow-up email sent to {pl.get('to')}")
    db.commit()
    audit(db, u.id, "opp.outbox_sent", {"outbox_id": it.id}, {"via": it.sent_via, "provider_message_id": message_id}, "high")
    return {"id": it.id, "status": "approved", "sent_at": now.isoformat(), "sent_via": it.sent_via, "provider_message_id": message_id,
            "follow_up_date": fu.isoformat()}


class OutboxSent(BaseModel):
    user_id: str
    provider_message_id: Optional[str] = Field(default=None, max_length=200)
    sent_via: str = "gmail_compose"


@router.post("/outbox/{outbox_id}/sent")
def outbox_sent(outbox_id: str, p: OutboxSent, db: Session = Depends(get_db)):
    """The user sent it themselves (e.g. from the Gmail compose window) and confirms it."""
    u = _user(db, p.user_id)
    it = _own_outbox(db, u.id, outbox_id)
    if it.status != "approved" or it.reviewed_hash != payload_hash(it):
        raise HTTPException(409, "Only an approved, unchanged message can be logged as sent.")
    if it.sent_at:
        raise HTTPException(409, "Already logged as sent.")
    return _log_sent(db, u, it, p.sent_via, p.provider_message_id)


# ---- direct Gmail send (optional): send-only scope, token supplied per request and never stored ----
@router.get("/config")
def opp_config():
    import gmail_send
    cid = gmail_send.client_id()
    return {"gmail_send_enabled": bool(cid), "google_client_id": cid, "gmail_scope": gmail_send.GMAIL_SEND_SCOPE,
            "note": "Gmail sending uses the send-only scope. OPAI cannot read your inbox. Without a client id, use the compose link."}


class OutboxSend(BaseModel):
    user_id: str


@router.post("/outbox/{outbox_id}/send")
def outbox_send(outbox_id: str, p: OutboxSend, x_gmail_token: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    """Sends EXACTLY the approved version through Gmail. Refuses if the content changed since approval,
    if it was already sent, or if a send is in flight. The token is used for this one call and discarded."""
    import gmail_send
    u = _user(db, p.user_id)
    it = _own_outbox(db, u.id, outbox_id)
    if it.sent_at:
        raise HTTPException(409, "Already sent. Nothing was sent again.")
    if (it.sent_via or "") == "gmail_api:sending":
        raise HTTPException(409, "A send is already in progress for this message.")
    if it.status != "approved" or not it.reviewed_hash:
        raise HTTPException(409, "Approve the exact message first.")
    if it.reviewed_hash != payload_hash(it):
        raise HTTPException(409, "The message changed after approval. Review and approve the new version.")
    ri = _recipient_info(db, u.id, it)
    if not ri["valid_address"]:
        raise HTTPException(422, "The recipient address is missing or invalid.")
    ref = it.ref or {}
    if ref.get("kind") == "contact":
        c = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if c:
            try:
                G.check_can_send(db, u.id, c)
            except G.Blocked as e:
                raise HTTPException(e.status, e.detail)
    elif G.is_suppressed(db, u.id, ri["to"]):
        raise HTTPException(409, "This address is on your do-not-contact list.")
    it.sent_via = "gmail_api:sending"          # claim the send BEFORE the network call so a double click cannot duplicate it
    db.commit()
    pl = it.payload or {}
    try:
        mid = gmail_send.send(x_gmail_token or "", ri["to"], pl.get("subject") or "", pl.get("body") or "", pl.get("from_account"))
    except gmail_send.GmailError as e:
        it.sent_via = None
        db.commit()
        audit(db, u.id, "opp.outbox_send_failed", {"outbox_id": it.id}, {"error": e.detail}, "high", status="error")
        raise HTTPException(e.status, e.detail)
    return _log_sent(db, u, it, "gmail_api", mid)


@router.post("/outbox/{outbox_id}/reject")
def outbox_reject(outbox_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    it = _own_outbox(db, u.id, outbox_id)
    if it.status != "pending":
        raise HTTPException(409, f"Item is already '{it.status}'.")
    it.status = "rejected"
    ref = it.ref or {}
    if ref.get("kind") == "contact":
        c = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if c and c.status == "Drafted":
            c.status = "Not started"
    db.commit()
    return {"id": it.id, "status": "rejected"}


# ================================================================ 7. FOLLOW-UPS (no inbox reading)
def _followup_items(db: Session, uid: str) -> List[Dict[str, Any]]:
    today, out = date.today(), []
    for a in db.query(Application).filter(Application.user_id == uid, Application.status == "Applied", Application.follow_up_date.isnot(None),
                                          Application.follow_up_date <= today).all():
        out.append({"kind": "application", "id": a.id, "title": f"{a.role} at {a.company}", "due": a.follow_up_date.isoformat(),
                    "days_since": (today - a.submitted_at.date()).days if a.submitted_at else None, "question": "Have they replied?"})
    for h in db.query(OutreachHistory).filter(OutreachHistory.user_id == uid, OutreachHistory.status == "Sent", OutreachHistory.follow_up_date.isnot(None),
                                              OutreachHistory.follow_up_date <= today).all():
        c = db.query(Contact).filter(Contact.id == h.contact_id).first()
        out.append({"kind": "outreach", "id": h.id, "title": f"{c.name if c else 'Contact'}: {h.subject}", "due": h.follow_up_date.isoformat(),
                    "days_since": (today - h.sent_at.date()).days if h.sent_at else None, "question": "Have they replied?"})
    return sorted(out, key=lambda r: r["due"])


@router.get("/followups")
def followups(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return {"items": _followup_items(db, u.id), "note": "OPAI does not read your inbox. Tell it what happened."}


class FollowAnswer(BaseModel):
    user_id: str
    answer: str = Field(pattern="^(yes|not_yet|later)$")
    later_days: int = Field(default=3, ge=1, le=30)


def _followup_text(name: str, subject: str, sender: str, role: bool) -> Dict[str, str]:
    if role:
        body = (f"Dear {name},\n\nI applied for the {subject} role and wanted to follow up politely. I remain very interested and am happy to share "
                f"anything that would help with your review.\n\nThank you for your time.\n\nBest regards,\n{sender}")
        return {"subject": f"Following up: {subject} application", "body": body}
    return {"subject": "Re: " + subject.removeprefix("Re: "), "body": (f"Dear {name},\n\nI wanted to follow up briefly on my earlier email in case it was buried. "
            f"I remain interested in your work and would be glad to share more about my background if useful.\n\nThank you for your time.\n\nBest regards,\n{sender}")}


@router.post("/followups/{kind}/{item_id}/answer")
def followup_answer(kind: str, item_id: str, p: FollowAnswer, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if kind not in ("application", "outreach"):
        raise HTTPException(404, "Unknown follow-up kind")
    today = date.today()
    if kind == "application":
        a = _own_app(db, u.id, item_id)
        if p.answer == "yes":
            a.follow_up_date = None
            _event(db, u.id, a.id, "note", "They replied. Update the stage when you know the outcome.")
            db.commit()
            return {"result": "logged", "next": "Move the application to Assessment, Interview, Offer or Rejected when you know."}
        if p.answer == "later":
            a.follow_up_date = today + timedelta(days=p.later_days)
            db.commit()
            return {"result": "snoozed", "follow_up_date": a.follow_up_date.isoformat()}
        to = (a.contact_ref or "").strip()
        a.follow_up_date = today + timedelta(days=FOLLOWUP_DAYS)
        db.commit()
        if not _EMAIL_RX.match(to):
            return {"result": "reminder_moved", "follow_up_date": a.follow_up_date.isoformat(),
                    "note": "No recruiter email on file, so there is nothing to draft. Add one in the application if you want a follow-up email."}
        if G.is_suppressed(db, u.id, to) or G.sent_last_24h(db, u.id) >= G.daily_cap():
            return {"result": "blocked", "note": "A follow-up cannot be drafted right now (do-not-contact list or daily limit)."}
        t = _followup_text("Hiring Team", f"{a.role} at {a.company}", u.name, True)
        it = OutboxItem(user_id=u.id, channel="email", status="pending", payload={"to": to, "subject": t["subject"], "body": t["body"]},
                        ref={"kind": "application", "id": a.id}, note="follow-up draft", risk_level="high", approval_scope="single_use",
                        expires_at=datetime.utcnow() + timedelta(hours=48))
        db.add(it)
        db.flush()
        it.payload_hash = payload_hash(it)
        db.commit()
        return {"result": "drafted", "outbox_id": it.id, "note": "Nothing was sent. Review it in Email & Follow-ups."}

    h = db.query(OutreachHistory).filter(OutreachHistory.id == item_id, OutreachHistory.user_id == u.id).first()
    if not h:
        raise HTTPException(404, "Outreach record not found")
    c = db.query(Contact).filter(Contact.id == h.contact_id).first()
    if p.answer == "yes":
        h.status, h.follow_up_date = "Replied", None
        db.commit()
        return {"result": "logged"}
    if p.answer == "later":
        h.follow_up_date = today + timedelta(days=p.later_days)
        db.commit()
        return {"result": "snoozed", "follow_up_date": h.follow_up_date.isoformat()}
    prior = db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.contact_id == h.contact_id,
                                             OutreachHistory.subject.like("Re:%")).count()
    if prior >= MAX_FOLLOWUPS_PER_CONTACT:
        h.status, h.follow_up_date = "No Response", None
        db.commit()
        return {"result": "closed", "note": "You already followed up once. Marked as no response; leave it for now."}
    if not c or G.is_suppressed(db, u.id, c.email) or G.sent_last_24h(db, u.id) >= G.daily_cap():
        return {"result": "blocked", "note": "A follow-up cannot be drafted right now (do-not-contact list or daily limit)."}
    t = _followup_text(c.name, h.subject, u.name, False)
    it = OutboxItem(user_id=u.id, channel="email", status="pending", payload={"to": c.email, "subject": t["subject"], "body": t["body"]},
                    ref={"kind": "contact", "id": c.id}, note="follow-up draft", risk_level="high", approval_scope="single_use",
                    expires_at=datetime.utcnow() + timedelta(hours=48))
    db.add(it)
    db.add(OutreachHistory(user_id=u.id, contact_id=c.id, subject=t["subject"], email_text=t["body"], status="Draft"))
    h.follow_up_date = None
    db.flush()
    it.payload_hash = payload_hash(it)
    db.commit()
    return {"result": "drafted", "outbox_id": it.id, "note": "Nothing was sent. Review it in Email & Follow-ups."}


# ================================================================ 8. DOCUMENTS, REPORTS, SUMMARY
@router.get("/documents")
def documents(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    used: Dict[str, List[str]] = {}
    for a in db.query(Application).filter(Application.user_id == u.id, Application.resume_id.isnot(None)).all():
        used.setdefault(a.resume_id, []).append(f"{a.role} at {a.company}")
    resumes = [{"id": r.id, "label": r.label, "target_role": r.target_role, "skills": r.skills or [], "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "used_for": used.get(r.id, [])} for r in db.query(Resume).filter(Resume.user_id == u.id).order_by(Resume.updated_at.desc()).all()]
    projects = [{"id": pr.id, "title": pr.title, "tech_stack": pr.tech_stack or []} for pr in db.query(Project).filter(Project.user_id == u.id).all()]
    profile = _profile_view(u)["profile"]
    return {"resumes": resumes, "project_evidence": projects[:20], "links": {k: profile.get(k) for k in ("resume_url", "portfolio_url", "github_url")}}


@router.get("/reports")
def reports(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    apps = db.query(Application).filter(Application.user_id == u.id).all()
    by_stage = {s: 0 for s in STAGES}
    by_source: Dict[str, Dict[str, int]] = {}
    for a in apps:
        st = stage_of(a)
        by_stage[st] = by_stage.get(st, 0) + 1
        src = a.source_type or "manual"
        row = by_source.setdefault(src, {"tracked": 0, "applied": 0, "responses": 0})
        row["tracked"] += 1
        if a.submitted_at:
            row["applied"] += 1
        if st in ("Assessment", "Interview", "Offer"):
            row["responses"] += 1
    applied = sum(1 for a in apps if a.submitted_at)
    resp = sum(by_stage.get(s, 0) for s in ("Assessment", "Interview", "Offer"))
    sent = db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.status.in_(("Sent", "Replied", "No Response"))).count()
    replied = db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.status == "Replied").count()
    bottlenecks = []
    cutoff = datetime.utcnow() - timedelta(days=10)
    for st in ("Saved", "Reviewing", "Preparing", "Ready to submit"):
        stuck = 0
        for a in apps:
            if stage_of(a) != st:
                continue
            last = (db.query(ApplicationEvent).filter(ApplicationEvent.application_id == a.id).order_by(ApplicationEvent.created_at.desc()).first())
            if last and last.created_at and last.created_at < cutoff:
                stuck += 1
        if stuck:
            bottlenecks.append(f"{stuck} application(s) have sat in '{st}' for over 10 days.")
    if applied >= 5 and resp == 0:
        bottlenecks.append("5+ applications sent with no assessment or interview yet. Consider reviewing resume targeting.")
    return {"applications_total": len(apps), "by_stage": by_stage, "applied": applied, "response_rate": round(resp / applied, 2) if applied else None,
            "by_source": by_source, "outreach": {"sent": sent, "replied": replied, "reply_rate": round(replied / sent, 2) if sent else None},
            "bottlenecks": bottlenecks, "note": "Rates are small-sample and based only on what you logged."}


@router.get("/summary")
def summary(user_id: str, db: Session = Depends(get_db)):
    """Powers the 'Your internship search' card and the Today integration."""
    u = _user(db, user_id)
    today = date.today()
    strong = [o for o in _visible_opps(db, u.id) if build_brief(db, u, o)["match"] == "Strong"]
    apps = db.query(Application).filter(Application.user_id == u.id).all()
    open_apps = [a for a in apps if stage_of(a) not in TERMINAL | {"Applied", "Assessment", "Interview"}]
    week = [a for a in open_apps if a.deadline and 0 <= (a.deadline - today).days <= 7]
    week_opps = [o for o in _visible_opps(db, u.id) if o.deadline and 0 <= (o.deadline - today).days <= 7]
    waiting = [a for a in open_apps if stage_of(a) in ("Preparing", "Ready to submit")]
    brief_ids = {b.contact_id: b for b in db.query(ResearchBrief).filter(ResearchBrief.user_id == u.id, ResearchBrief.verification.in_(("verified", "partial"))).all()}
    drafts = db.query(OutboxItem).filter(OutboxItem.user_id == u.id, OutboxItem.status == "pending", OutboxItem.channel == "email").count()
    fu = _followup_items(db, u.id)
    nxt = None
    if week or week_opps:
        t = sorted([(a.deadline, f"{a.role} at {a.company}", "Finish the application") for a in week] +
                   [(o.deadline, f"{o.title} at {o.company_or_lab}", "Review the brief and decide") for o in week_opps], key=lambda r: r[0])[0]
        nxt = {"text": f"{t[2]}: {t[1]} (closes {t[0].isoformat()}).", "link": "opportunities.html"}
    elif drafts:
        nxt = {"text": "Review the email draft waiting for your approval.", "link": "opportunities.html#email"}
    elif fu:
        nxt = {"text": f"Check in on: {fu[0]['title']}.", "link": "opportunities.html#email"}
    elif strong:
        nxt = {"text": f"Review the brief for {strong[0].title} at {strong[0].company_or_lab}.", "link": "opportunities.html#saved"}
    from programs_api import programs_summary
    pr = programs_summary(db, u)
    if nxt is None and pr["program_next_action"]:
        nxt = {"text": pr["program_next_action"]["text"], "link": pr["program_next_action"]["link"]}
    return {"strong_to_review": len(strong), "deadlines_this_week": len(week) + len(week_opps), "applications_waiting_for_you": len(waiting),
            "professors_with_research_match": len(brief_ids), "drafts_awaiting_approval": drafts, "followups_due": len(fu),
            "programs_live": pr["programs_live"], "programs_to_verify": pr["programs_to_verify"], "recommended_next_action": nxt}
