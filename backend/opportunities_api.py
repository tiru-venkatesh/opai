"""OPAI Opportunities pipeline: discover -> evaluate -> prepare -> apply/reach out -> follow up -> learn.

Boundaries (enforced here, not in prompts):
  * No LinkedIn scraping / fetching / automation. LinkedIn is a user-controlled source: the user pastes a
    link or the posting text, or a job-alert email body; OPAI only parses what the user supplied.
  * Nothing is submitted or sent without the user: applications are marked Applied BY the user; emails
    go Outbox -> approval bound to a content hash -> Gmail send of exactly that content.
  * The brief never claims eligibility the posting/profile leaves unclear.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import outreach_guard as G
from audit.logger import record as audit
from database import (Application, Contact, Opportunity, OutboxItem, OutreachHistory, User,
                      get_db, outbox_content_hash)

router = APIRouter()

STAGES = ["Saved", "Reviewing", "Preparing", "Ready to submit", "Applied", "Assessment",
          "Interview", "Offer", "Rejected", "Withdrawn"]
SOURCE_TYPES = {"linkedin_user_saved", "career_page", "university_page", "email_alert", "referral", "pasted", "manual", "feed"}
FOLLOWUP_DAYS = 7
TECH_TERMS = ["python", "pytorch", "tensorflow", "rag", "llm", "nlp", "machine learning", "deep learning", "react",
              "node", "sql", "docker", "kubernetes", "aws", "java", "c++", "typescript", "javascript", "fastapi",
              "django", "flask", "computer vision", "data analysis", "git", "linux", "figma", "agents"]
CHECKLIST = ["Verify requirements and deadline on the original posting", "Compare posting with confirmed profile",
             "Pick or tailor a resume version", "Draft application answers / cover letter",
             "Review documents yourself", "Open the original application page and submit it yourself",
             "Mark as Applied here"]


# ---------------------------------------------------------------- helpers
def _user(db: Session, uid: str) -> User:
    u = db.query(User).filter(User.id == str(uid)).first()
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


def _terms(text: Optional[str]) -> List[str]:
    return [t.strip().lower() for t in re.split(r"[,;\n]", text or "") if t.strip()]


def _has(text: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])", text) is not None


def _clean_url(url: Optional[str]) -> Optional[str]:
    """Keep scheme/host/path only (drops tracking params). Never fetched."""
    if not url:
        return None
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise HTTPException(422, "Link must start with http:// or https://")
    return urlunparse((u.scheme, u.netloc, u.path.rstrip("/") or "/", "", "", ""))


def _is_linkedin(url: Optional[str]) -> bool:
    return bool(url) and urlparse(url).netloc.lower().endswith("linkedin.com")


# ---------------------------------------------------------------- 1. profile
class ProfileBody(BaseModel):
    user_id: str
    degree: Optional[str] = None
    year: Optional[str] = None            # e.g. "pre-final", "3rd year"
    branch: Optional[str] = None
    college: Optional[str] = None
    graduation_year: Optional[int] = None
    skills: Optional[List[str]] = None
    projects: Optional[List[str]] = None
    resume_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    github_url: Optional[str] = None
    role_types: Optional[List[str]] = None      # internship, research, part-time
    locations: Optional[List[str]] = None
    work_modes: Optional[List[str]] = None      # remote, hybrid, onsite
    availability: Optional[str] = None
    gpa: Optional[float] = None
    eligibility_notes: Optional[str] = None
    comm_style: Optional[str] = None
    confirmed: bool = False


@router.get("/v1/opp/profile")
def get_opp_profile(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    p = dict((u.preferences or {}).get("opportunity_profile") or {})
    # Prefill ONLY from fields the user already entered on their profile; never inferred.
    p.setdefault("degree", u.degree)
    p.setdefault("branch", u.branch)
    p.setdefault("skills", _terms(u.skills))
    p.setdefault("github_url", u.github)
    p.setdefault("confirmed", False)
    return p


@router.put("/v1/opp/profile")
def put_opp_profile(p: ProfileBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    data = p.model_dump(exclude={"user_id"}, exclude_none=True)
    for k in ("resume_url", "portfolio_url", "github_url"):
        if data.get(k):
            data[k] = _clean_url(data[k])
    prefs = dict(u.preferences or {})
    prefs["opportunity_profile"] = {**(prefs.get("opportunity_profile") or {}), **data,
                                    "confirmed_at": datetime.utcnow().isoformat() if p.confirmed else None}
    u.preferences = prefs
    db.commit()
    return get_opp_profile(u.id, db)


def _profile(db: Session, u: User) -> Dict[str, Any]:
    return get_opp_profile(u.id, db)


# ---------------------------------------------------------------- 2. intake (no fetching)
class IntakeBody(BaseModel):
    user_id: str
    url: Optional[str] = None
    text: Optional[str] = Field(default=None, max_length=30000)
    source_type: Optional[str] = None


_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _parse_date(s: str) -> Optional[date]:
    s = s.strip().replace(",", " ")
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[a-z]*\s+(\d{4})$", s)
    if m and m[2].lower() in _MONTHS:
        try:
            return date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))
        except ValueError:
            return None
    m = re.match(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})$", s)
    if m and m[1].lower() in _MONTHS:
        try:
            return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
        except ValueError:
            return None
    return None


def parse_posting(text: str) -> Dict[str, Any]:
    """Deterministic extraction from text the USER supplied. Returns fields + which were found vs unknown."""
    t = text or ""
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    low = t.lower()
    f: Dict[str, Any] = {}
    if lines:
        f["title"] = re.sub(r"\s+", " ", lines[0])[:160]
        m = re.search(r"\bat\s+([A-Z][\w&.\- ]{1,60})$", lines[0])
        if m:
            f["organization"] = m[1].strip()
            f["title"] = lines[0][: m.start()].strip()
        elif len(lines) > 1 and len(lines[1]) <= 80:
            f["organization"] = lines[1]
    m = re.search(r"(?:company|organization|employer|lab)\s*[:\-]\s*(.+)", t, re.I)
    if m:
        f["organization"] = m[1].strip()[:120]
    m = re.search(r"(?:location)\s*[:\-]\s*(.+)", t, re.I)
    if m:
        f["location"] = m[1].strip()[:120]
    for mode, pat in (("remote", r"\bremote\b"), ("hybrid", r"\bhybrid\b"), ("onsite", r"\bon[- ]?site\b|\bin[- ]office\b")):
        if re.search(pat, low):
            f["work_mode"] = mode
            break
    if re.search(r"\bresearch\b", low) and re.search(r"\b(intern|internship|fellow|assistant)\b", low):
        f["role_type"] = "research"
    elif re.search(r"\bintern(ship)?\b", low):
        f["role_type"] = "internship"
    elif re.search(r"part[- ]time", low):
        f["role_type"] = "part-time"
    dm = re.search(r"(?:deadline|apply (?:by|before)|last date(?: to apply)?|closes?(?: on)?)\s*[:\-]?\s*([0-9A-Za-z ,\-]{6,30})", t, re.I)
    if dm:
        d = _parse_date(dm[1].strip().rstrip(".,"))
        if not d:  # the capture may run on into following words; try the leading tokens
            toks = dm[1].split()
            for n in (3, 2):
                d = _parse_date(" ".join(toks[:n]))
                if d:
                    break
        if d:
            f["deadline"] = d.isoformat()
    f["tech_terms"] = [x for x in TECH_TERMS if _has(low, x)]
    gm = re.search(r"(\d(?:\.\d+)?)\s*\+?\s*(?:cgpa|gpa)", low)
    if gm:
        f["min_gpa"] = float(gm[1])
    em = re.search(r"(pre[- ]final|final[- ]year|third[- ]year|second[- ]year|(?:20\d\d)\s+(?:graduat|batch|pass))", low)
    if em:
        f["eligibility_text"] = em[1]
    return f


class ConfirmBody(BaseModel):
    user_id: str
    title: str = Field(min_length=2, max_length=200)
    organization: str = Field(min_length=1, max_length=200)
    source_type: str = "pasted"
    source_url: Optional[str] = None
    location: Optional[str] = None
    work_mode: Optional[str] = None
    role_type: str = "internship"
    deadline: Optional[date] = None
    description_text: Optional[str] = Field(default=None, max_length=30000)
    eligibility_note: Optional[str] = None
    facts: Dict[str, Any] = {}


@router.post("/v1/opp/intake")
def intake(p: IntakeBody, db: Session = Depends(get_db)):
    """Parse what the user pasted. NOTHING is fetched from the URL and NOTHING is saved until /intake/confirm."""
    _user(db, p.user_id)
    if not (p.url or p.text):
        raise HTTPException(422, "Paste a link, the posting text, or a job-alert email body")
    url = _clean_url(p.url)
    st = p.source_type or ("linkedin_user_saved" if _is_linkedin(url) else "pasted")
    if st not in SOURCE_TYPES:
        raise HTTPException(422, f"source_type must be one of {sorted(SOURCE_TYPES)}")
    candidates: List[Dict[str, Any]] = []
    if p.text:  # job-alert email body: list individual postings so the user picks which to track
        seen = set()
        for m in re.finditer(r"https?://[^\s<>\"')]+linkedin\.com/(?:comm/)?jobs/view/[^\s<>\"')]*", p.text):
            cu = _clean_url(m[0])
            if cu not in seen:
                seen.add(cu)
                candidates.append({"source_url": cu, "source_type": "linkedin_user_saved"})
    fields = parse_posting(p.text) if p.text else {}
    if url:
        fields["source_url"] = url
    found = [k for k in ("title", "organization", "location", "work_mode", "deadline", "role_type") if fields.get(k)]
    unknown = [k for k in ("title", "organization", "location", "work_mode", "deadline", "role_type") if not fields.get(k)]
    # Optional LLM assist only fills blanks and is labelled; the user confirms everything.
    ai_filled: List[str] = []
    if p.text and unknown:
        gen = _llm_json("Extract job posting fields from the text. Use ONLY text present. Return JSON with keys "
                        "title, organization, location, work_mode(remote|hybrid|onsite), role_type, deadline(YYYY-MM-DD). "
                        "Use null when absent.", p.text[:6000])
        for k in unknown:
            v = (gen or {}).get(k)
            if isinstance(v, str) and v.strip() and k != "deadline":
                fields[k] = v.strip()[:160]
                ai_filled.append(k)
    return {"source_type": st, "fields": fields, "found_in_text": found,
            "ai_suggested_fields": ai_filled, "unknown": [k for k in unknown if k not in ai_filled],
            "job_alert_candidates": candidates, "saved": False,
            "note": ("OPAI does not open or scrape LinkedIn. Review these details against the original posting, "
                     "then confirm to track it.")}


@router.post("/v1/opp/intake/confirm")
def intake_confirm(p: ConfirmBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if p.source_type not in SOURCE_TYPES:
        raise HTTPException(422, f"source_type must be one of {sorted(SOURCE_TYPES)}")
    url = _clean_url(p.source_url)
    if url:
        dup = db.query(Opportunity).filter(Opportunity.user_id == u.id, Opportunity.link == url).first()
        if dup:
            raise HTTPException(409, f"Already tracked ({dup.id})")
    norm_t, norm_o = p.title.strip().lower(), p.organization.strip().lower()
    dup = (db.query(Opportunity).filter(Opportunity.user_id == u.id, func.lower(func.trim(Opportunity.title)) == norm_t,
                                        func.lower(func.trim(Opportunity.company_or_lab)) == norm_o).first())
    if dup:
        raise HTTPException(409, f"Looks like a duplicate of an existing opportunity ({dup.id})")
    o = Opportunity(user_id=u.id, title=p.title.strip(), company_or_lab=p.organization.strip(), type=p.role_type,
                    description=(p.description_text or "")[:2000], description_text=p.description_text, link=url,
                    source=p.source_type, source_type=p.source_type, location=p.location, work_mode=p.work_mode,
                    deadline=p.deadline, eligibility_note=p.eligibility_note, status="New",
                    facts=p.facts or {}, last_verified_at=datetime.utcnow(),
                    tags=[x for x in TECH_TERMS if _has((p.description_text or "").lower(), x)])
    db.add(o)
    db.commit()
    db.refresh(o)
    audit(db, u.id, "opportunity.intake", {"source_type": p.source_type}, {"id": o.id}, "low")
    return _opp_out(o)


def _opp_out(o: Opportunity) -> Dict[str, Any]:
    return {"id": o.id, "title": o.title, "organization": o.company_or_lab, "role_type": o.type,
            "source_type": o.source_type or o.source, "source_url": o.link, "location": o.location,
            "work_mode": o.work_mode, "deadline": o.deadline.isoformat() if o.deadline else None,
            "status": o.status, "tags": o.tags or [],
            "last_verified_at": o.last_verified_at.isoformat() if o.last_verified_at else None}


@router.get("/v1/opp/opportunities")
def list_opps(user_id: str, status: Optional[str] = None, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    q = db.query(Opportunity).filter(Opportunity.user_id == u.id)
    if status:
        q = q.filter(Opportunity.status == status)
    return [_opp_out(o) for o in q.order_by(Opportunity.deadline.is_(None), Opportunity.deadline).all()]


@router.post("/v1/opp/opportunities/{oid}/reverify")
def reverify(oid: str, user_id: str, db: Session = Depends(get_db)):
    """User re-checked the original posting; stamps last_verified_at."""
    o = _own_opp(db, oid, user_id)
    o.last_verified_at = datetime.utcnow()
    db.commit()
    return _opp_out(o)


def _own_opp(db: Session, oid: str, user_id: str) -> Opportunity:
    o = db.query(Opportunity).filter(Opportunity.id == oid, Opportunity.user_id == str(user_id)).first()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    return o


# ---------------------------------------------------------------- 3. brief (separated signals)
def build_brief(o: Opportunity, prof: Dict[str, Any]) -> Dict[str, Any]:
    text = ((o.description_text or "") + " " + (o.title or "") + " " + " ".join(o.tags or [])).lower()
    confirmed = bool(prof.get("confirmed"))
    skills = {s.lower() for s in (prof.get("skills") or [])}
    for pr in prof.get("projects") or []:
        skills |= {w for w in TECH_TERMS if _has(str(pr).lower(), w)}
    posting_terms = [x for x in TECH_TERMS if _has(text, x)]
    have = [t for t in posting_terms if t in skills]
    gaps = [t for t in posting_terms if t not in skills]

    facts = [f"Title: {o.title}", f"Organization: {o.company_or_lab}"]
    if o.deadline:
        facts.append(f"Deadline: {o.deadline.isoformat()}")
    for label, val in (("Location", o.location), ("Work mode", o.work_mode), ("Role type", o.type)):
        if val:
            facts.append(f"{label}: {val}")
    if o.link:
        facts.append(f"Source: {o.link}")
    if o.last_verified_at:
        facts.append(f"Last checked: {o.last_verified_at.date().isoformat()}")

    unknown: List[str] = []
    eligibility = "Needs confirmation"
    reasons: List[str] = []
    f = o.facts or {}
    if not confirmed:
        unknown.append("Your profile is not confirmed yet, so match and eligibility are provisional")
    if not o.deadline:
        unknown.append("Deadline not stated - check the original posting")
    mg = f.get("min_gpa")
    if mg:
        gpa = prof.get("gpa")
        if gpa is None:
            unknown.append(f"Posting mentions {mg} CGPA; your GPA is not in your confirmed profile")
        elif float(gpa) < float(mg):
            reasons.append(f"Posting mentions {mg} CGPA; yours is {gpa}")
        else:
            reasons.append("CGPA requirement appears met")
    et = f.get("eligibility_text")
    if et:
        yr = (prof.get("year") or "").lower()
        if not yr and not prof.get("graduation_year"):
            unknown.append(f"Posting says \"{et}\"; your year/graduation date is not in your profile")
        elif yr and ((et.startswith("pre") and "pre" in yr) or (et.startswith("final") and "final" in yr and "pre" not in yr)):
            reasons.append("Year requirement appears to match")
        else:
            unknown.append(f"Posting says \"{et}\"; confirm it fits your year ({prof.get('year') or prof.get('graduation_year')})")
    if o.work_mode and prof.get("work_modes") and o.work_mode not in [w.lower() for w in prof["work_modes"]]:
        reasons.append(f"Work mode {o.work_mode} is outside your preferred modes")
    if any("not" in r or "outside" in r or "yours is" in r for r in reasons):
        eligibility = "May not meet a stated requirement"
    elif confirmed and not unknown and (reasons or not et and not mg):
        eligibility = "Appears eligible (based on what is stated)"

    if not confirmed or not posting_terms:
        match = "Unknown"
    else:
        ratio = len(have) / len(posting_terms)
        match = "Strong" if ratio >= 0.6 else "Moderate" if ratio >= 0.3 else "Weak"
    days = (o.deadline - date.today()).days if o.deadline else None
    deadline_note = None if days is None else ("Deadline passed" if days < 0 else f"{days} day(s) left")
    prep = 60 + 15 * min(len(gaps), 4) if posting_terms else 60
    nxt = ("Deadline has passed - verify on the original posting before spending time." if days is not None and days < 0
           else "Confirm your profile first." if not confirmed
           else "Review the posting, then prepare a role-specific resume." if match in ("Strong", "Moderate")
           else "Decide whether the gaps are worth closing before applying.")
    return {"opportunity_id": o.id, "title": o.title, "organization": o.company_or_lab, "match": match,
            "eligibility": eligibility, "deadline": o.deadline.isoformat() if o.deadline else None,
            "deadline_note": deadline_note,
            "verified_facts": facts,                               # stated in the posting
            "profile_match": [f"Your confirmed profile covers: {t}" for t in have] if confirmed else [],
            "unknown": unknown + reasons,                          # needs the user's verification
            "gaps": [f"{t} is mentioned in the posting but not shown in your profile" for t in gaps],
            "ai_suggestion": {"label": "AI suggestion, not a fact", "next_step": nxt, "estimated_prep_minutes": prep},
            "actions": ["open_source", "track", "not_interested"]}


@router.get("/v1/opp/opportunities/{oid}/brief")
def brief(oid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return build_brief(_own_opp(db, oid, u.id), _profile(db, u))


@router.get("/v1/opp/matches")
def todays_matches(user_id: str, limit: int = 5, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    prof = _profile(db, u)
    rank = {"Strong": 0, "Moderate": 1, "Unknown": 2, "Weak": 3}
    out = [build_brief(o, prof) for o in db.query(Opportunity).filter(Opportunity.user_id == u.id, Opportunity.status == "New").all()]
    out = [b for b in out if b["deadline_note"] != "Deadline passed"]
    out.sort(key=lambda b: (rank[b["match"]], b["deadline"] or "9999"))
    return out[:limit]


@router.post("/v1/opp/opportunities/{oid}/dismiss")
def dismiss(oid: str, user_id: str, db: Session = Depends(get_db)):
    o = _own_opp(db, oid, user_id)
    o.status = "Dismissed"
    db.commit()
    return _opp_out(o)


# ---------------------------------------------------------------- 4. applications
def _hist(a: Application, stage: str, note: Optional[str] = None) -> None:
    a.stage_history = list(a.stage_history or []) + [{"stage": stage, "at": datetime.utcnow().isoformat(), "note": note}]


@router.post("/v1/opp/opportunities/{oid}/track")
def track(oid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    o = _own_opp(db, oid, u.id)
    if db.query(Application).filter(Application.user_id == u.id, Application.opportunity_id == o.id).first():
        raise HTTPException(409, "Already tracked as an application")
    a = Application(user_id=u.id, company=o.company_or_lab, role=o.title, type=o.type or "internship", status="Saved",
                    deadline=o.deadline, link=o.link, opportunity_id=o.id,
                    checklist=[{"text": t, "done": False} for t in CHECKLIST])
    _hist(a, "Saved", f"from {o.source_type or o.source}")
    o.status = "Converted"
    db.add(a)
    db.commit()
    db.refresh(a)
    return _app_out(a)


def _app_out(a: Application) -> Dict[str, Any]:
    return {"id": a.id, "company": a.company, "role": a.role, "stage": a.status, "deadline": a.deadline.isoformat() if a.deadline else None,
            "source_url": a.link, "resume_id": a.resume_id, "submitted_on": a.submitted_on.isoformat() if a.submitted_on else None,
            "follow_up_date": a.follow_up_date.isoformat() if a.follow_up_date else None, "follow_up_state": a.follow_up_state,
            "referral_contact": a.referral_contact, "notes": a.notes, "checklist": a.checklist or [],
            "stage_history": a.stage_history or [], "opportunity_id": a.opportunity_id}


@router.get("/v1/opp/applications")
def list_apps(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return {"stages": STAGES, "items": [_app_out(a) for a in db.query(Application).filter(Application.user_id == u.id).all()]}


class StageBody(BaseModel):
    user_id: str
    stage: str
    note: Optional[str] = None


@router.post("/v1/opp/applications/{aid}/stage")
def set_stage(aid: str, p: StageBody, db: Session = Depends(get_db)):
    """Stage changes are made by the user. 'Applied' means THEY submitted it on the original page."""
    if p.stage not in STAGES:
        raise HTTPException(422, f"stage must be one of {STAGES}")
    a = db.query(Application).filter(Application.id == aid, Application.user_id == str(p.user_id)).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if p.stage == "Applied":
        a.submitted_on = date.today()
        a.follow_up_date = date.today() + timedelta(days=FOLLOWUP_DAYS)
        a.follow_up_state = "pending"
    a.status = p.stage
    _hist(a, p.stage, p.note)
    db.commit()
    return _app_out(a)


class AppPatch(BaseModel):
    user_id: str
    resume_id: Optional[str] = None
    referral_contact: Optional[str] = None
    notes: Optional[str] = None
    checklist_done: Optional[List[int]] = None


@router.patch("/v1/opp/applications/{aid}")
def patch_app(aid: str, p: AppPatch, db: Session = Depends(get_db)):
    a = db.query(Application).filter(Application.id == aid, Application.user_id == str(p.user_id)).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if p.resume_id:   # only your own versions or tailored builds; never another user's row or a reference resume
        from database import Resume
        rr = db.query(Resume).filter(Resume.id == p.resume_id, Resume.user_id == str(p.user_id)).first()
        if not rr or (rr.kind or "own") not in ("own", "tailored"):
            raise HTTPException(404, "Resume not found")
    for k in ("resume_id", "referral_contact", "notes"):
        v = getattr(p, k)
        if v is not None:
            setattr(a, k, v)
    if p.checklist_done is not None:
        a.checklist = [{**c, "done": i in p.checklist_done} for i, c in enumerate(a.checklist or [])]
    db.commit()
    return _app_out(a)


# ---------------------------------------------------------------- 5. professors
class ProfBody(BaseModel):
    user_id: str
    name: str = Field(min_length=2, max_length=120)
    institution: str = Field(min_length=2, max_length=200)
    department: Optional[str] = None
    source_url: str = Field(min_length=8, max_length=500)  # official faculty page (required: no source, no contact)
    email: Optional[str] = Field(default=None, max_length=254)
    email_shown_on_source: bool = False
    research_areas: List[str] = []
    recent_work: Optional[str] = Field(default=None, max_length=500)


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _prof_out(c: Contact, db: Session, uid: str) -> Dict[str, Any]:
    last = (db.query(OutreachHistory).filter(OutreachHistory.user_id == uid, OutreachHistory.contact_id == c.id)
            .order_by(OutreachHistory.sent_at.desc().nullslast()).first())
    return {"id": c.id, "name": c.name, "institution": c.institute, "department": c.lab, "email": c.email or None,
            "email_verification": c.email_verification or "unverified", "source_url": c.source_url,
            "source_checked_at": c.source_checked_at.isoformat() if c.source_checked_at else None,
            "research_areas": c.research_areas or [], "recent_work": c.recent_work, "outreach_status": c.status,
            "last_outreach": ({"status": last.status, "sent_at": last.sent_at.isoformat() if last.sent_at else None,
                               "follow_up_date": last.follow_up_date.isoformat() if last.follow_up_date else None} if last else None)}


@router.post("/v1/opp/professors")
def add_professor(p: ProfBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    src = _clean_url(p.source_url)
    email = (p.email or "").strip().lower()
    if email and not _EMAIL.match(email):
        raise HTTPException(422, "Email address is not valid")
    c = Contact(name=p.name.strip(), institute=p.institution.strip(), lab=p.department, email=email,
                research_areas=[a.strip() for a in p.research_areas if a.strip()], bio=p.recent_work,
                source_url=src, source_checked_at=datetime.utcnow(), recent_work=p.recent_work,
                email_verification=("public_page" if email and p.email_shown_on_source else "unverified"),
                owner_user_id=u.id, status="Not started")
    db.add(c)
    db.commit()
    db.refresh(c)
    return _prof_out(c, db, u.id)


@router.get("/v1/opp/professors")
def list_professors(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = db.query(Contact).filter(Contact.owner_user_id == u.id).all()
    return [_prof_out(c, db, u.id) for c in rows]


class ConfirmEmailBody(BaseModel):
    user_id: str
    email: Optional[str] = None


@router.post("/v1/opp/professors/{cid}/confirm-email")
def confirm_email(cid: str, p: ConfirmEmailBody, db: Session = Depends(get_db)):
    """User states they verified this address themselves (e.g. on the official page)."""
    u = _user(db, p.user_id)
    c = _own_contact(db, cid, u.id)
    if p.email:
        if not _EMAIL.match(p.email.strip()):
            raise HTTPException(422, "Email address is not valid")
        c.email = p.email.strip().lower()
    if not c.email:
        raise HTTPException(422, "No email on this contact")
    c.email_verification = "user_confirmed"
    db.commit()
    return _prof_out(c, db, u.id)


def _own_contact(db: Session, cid: str, uid: str) -> Contact:
    c = db.query(Contact).filter(Contact.id == cid, Contact.owner_user_id == str(uid)).first()
    if not c:
        raise HTTPException(404, "Professor not found in your list")
    return c


@router.post("/v1/opp/professors/{cid}/draft")
def professor_draft(cid: str, user_id: str, db: Session = Depends(get_db)):
    """Brief (source-backed) -> draft -> Outbox (pending). Never sends."""
    import extras_api as X
    u = _user(db, user_id)
    c = _own_contact(db, cid, u.id)
    if not c.email:
        raise HTTPException(409, "No email address on file. Add one from the official page and confirm it.")
    if c.email_verification not in ("public_page", "user_confirmed"):
        raise HTTPException(409, "Confirm the recipient's email address first (where did you see it?).")
    brief = X.research_brief(c.id, X.BriefBody(user_id=u.id, source_url=c.source_url, source_title=f"{c.institute} faculty page"), db)
    if brief["verification"] == "unverified":
        raise HTTPException(409, "No reliable research source. Add research areas or a recent project/paper first.")
    d = X.draft_email(c.id, X.DraftBody(user_id=u.id, brief_id=brief["id"]), db)
    item = db.query(OutboxItem).filter(OutboxItem.id == d["outbox_id"]).first()
    item.ref = {**(item.ref or {}), "pipeline": "opportunities"}
    db.commit()
    return {**d, "payload_hash": outbox_content_hash(item.channel, item.payload), "brief": brief,
            "recipient_source": {"email_verification": c.email_verification, "source_url": c.source_url}}


@router.post("/v1/opp/professors/{cid}/followup-draft")
def professor_followup(cid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    c = _own_contact(db, cid, u.id)
    last = (db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.contact_id == c.id,
                                             OutreachHistory.status.in_(("Sent", "No Response"))).order_by(OutreachHistory.sent_at.desc()).first())
    if not last or not last.sent_at:
        raise HTTPException(409, "Nothing sent to this professor yet")
    if last.status == "Replied":
        raise HTTPException(409, "They already replied")
    if datetime.utcnow() - last.sent_at < timedelta(days=FOLLOWUP_DAYS):
        raise HTTPException(409, f"Give them at least {FOLLOWUP_DAYS} days before following up")
    if G.is_suppressed(db, u.id, c.email):
        raise HTTPException(409, "On your do-not-contact list")
    open_items = db.query(OutboxItem).filter(OutboxItem.user_id == u.id, OutboxItem.status.in_(("pending", "approved"))).all()
    if any((i.ref or {}).get("id") == c.id and i.send_state != "sent" for i in open_items):
        raise HTTPException(409, "A draft for this contact is already waiting in your Outbox")
    last_name = (c.name.split() or [""])[-1]
    body = (f"Dear Professor {last_name},\n\nI wanted to follow up on my earlier email from {last.sent_at.date().isoformat()} about "
            f"your group's work. I understand you are busy; if there is a suitable opportunity or a better person to ask, "
            f"I would be grateful for a pointer.\n\nThank you for your time.\n\nBest regards,\n{u.name}")
    item = OutboxItem(user_id=u.id, channel="email", status="pending",
                      payload={"to": c.email, "subject": "Re: " + last.subject, "body": body},
                      ref={"kind": "contact", "id": c.id, "pipeline": "opportunities", "followup": True},
                      note="follow-up draft", risk_level="high", approval_scope="single_use",
                      expires_at=datetime.utcnow() + timedelta(hours=48))
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"outbox_id": item.id, "status": "pending_approval", "payload_hash": item.payload_hash, "note": "Nothing has been sent."}


# ---------------------------------------------------------------- 6. application follow-up draft
class AppFollowBody(BaseModel):
    user_id: str
    to: str = Field(max_length=254)     # recruiter/referral address the USER supplies
    recipient_source: str = Field(min_length=3, max_length=200)


@router.post("/v1/opp/applications/{aid}/followup-draft")
def app_followup(aid: str, p: AppFollowBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    a = db.query(Application).filter(Application.id == aid, Application.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    if a.status != "Applied":
        raise HTTPException(409, "Follow-ups apply to applications marked Applied")
    if not _EMAIL.match(p.to.strip()):
        raise HTTPException(422, "Recipient email is not valid")
    if G.is_suppressed(db, u.id, p.to):
        raise HTTPException(409, "On your do-not-contact list")
    body = (f"Hello,\n\nI applied for the {a.role} position at {a.company} on {a.submitted_on.isoformat() if a.submitted_on else 'recently'} "
            f"and wanted to confirm my application was received. I remain very interested and am happy to share anything further.\n\n"
            f"Thank you,\n{u.name}")
    item = OutboxItem(user_id=u.id, channel="email", status="pending",
                      payload={"to": p.to.strip().lower(), "subject": f"Following up: {a.role} application", "body": body},
                      ref={"kind": "application", "id": a.id, "pipeline": "opportunities", "recipient_source": p.recipient_source},
                      note="application follow-up", risk_level="high", approval_scope="single_use",
                      expires_at=datetime.utcnow() + timedelta(hours=48))
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"outbox_id": item.id, "status": "pending_approval", "payload_hash": item.payload_hash, "note": "Nothing has been sent."}


# ---------------------------------------------------------------- 7. Outbox review + send
def _review(item: OutboxItem, db: Session) -> Dict[str, Any]:
    ref = item.ref or {}
    src: Dict[str, Any] = {}
    if ref.get("kind") == "contact":
        c = db.query(Contact).filter(Contact.id == ref.get("id")).first()
        if c:
            src = {"email_verification": c.email_verification, "source_url": c.source_url, "name": c.name}
    elif ref.get("recipient_source"):
        src = {"recipient_source": ref["recipient_source"]}
    pl = item.payload or {}
    return {"id": item.id, "status": item.status, "send_state": item.send_state, "to": pl.get("to"), "subject": pl.get("subject"),
            "body": pl.get("body"), "attachments": pl.get("attachments") or [], "recipient": src,
            "payload_hash": outbox_content_hash(item.channel, item.payload), "approved_hash": item.approved_hash,
            "sent_at": item.sent_at.isoformat() if item.sent_at else None, "provider_message_id": item.provider_message_id,
            "action": "Send this exact email via Gmail (you will be asked for send-only access)",
            "expires_at": item.expires_at.isoformat() if item.expires_at else None}


@router.get("/v1/opp/outbox")
def pipeline_outbox(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = db.query(OutboxItem).filter(OutboxItem.user_id == u.id).order_by(OutboxItem.created_at.desc()).limit(50).all()
    return [_review(r, db) for r in rows if (r.ref or {}).get("pipeline") == "opportunities"]


class EditBody(BaseModel):
    user_id: str
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


@router.patch("/v1/opp/outbox/{oid}")
def edit_outbox(oid: str, p: EditBody, db: Session = Depends(get_db)):
    """Editing recipient/subject/body after approval revokes the approval (central hash listener)."""
    item = db.query(OutboxItem).filter(OutboxItem.id == oid, OutboxItem.user_id == str(p.user_id)).first()
    if not item:
        raise HTTPException(404, "Outbox item not found")
    if item.send_state == "sent":
        raise HTTPException(409, "Already sent")
    pl = dict(item.payload or {})
    for k in ("to", "subject", "body"):
        v = getattr(p, k)
        if v is not None:
            pl[k] = v.strip().lower() if k == "to" else v
    item.payload = pl            # reassign so SQLAlchemy sees the change
    db.commit()
    db.refresh(item)
    return _review(item, db)


class SendBody(BaseModel):
    user_id: str
    access_token: str = Field(min_length=10)   # short-lived Google token (gmail.send scope) from the user's browser; never stored


def _gmail_send(access_token: str, raw_b64: str) -> str:
    req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                                 data=json.dumps({"raw": raw_b64}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:   # noqa: S310 (fixed https host)
        return json.loads(r.read())["id"]


@router.post("/v1/opp/outbox/{oid}/send")
def send_outbox(oid: str, p: SendBody, db: Session = Depends(get_db)):
    item = db.query(OutboxItem).filter(OutboxItem.id == oid, OutboxItem.user_id == str(p.user_id)).first()
    if not item or (item.ref or {}).get("pipeline") != "opportunities":
        raise HTTPException(404, "Outbox item not found")
    if item.send_state == "sent":
        return {"already_sent": True, **_review(item, db)}          # idempotent: never double-send
    cur = outbox_content_hash(item.channel, item.payload)
    if item.status != "approved" or not item.approved_hash or item.approved_hash != cur:
        raise HTTPException(409, "Not approved for this exact content. Review and approve the current version.")
    if item.expires_at and item.expires_at < datetime.utcnow():
        raise HTTPException(410, "Approval expired - re-draft it")
    pl = item.payload or {}
    to = (pl.get("to") or "").strip()
    if not _EMAIL.match(to):
        raise HTTPException(422, "Recipient address is not valid")
    if pl.get("attachments"):
        raise HTTPException(422, "Attachments are not sent yet. Remove them and attach the file in Gmail yourself.")
    ref = item.ref or {}
    contact = db.query(Contact).filter(Contact.id == ref.get("id")).first() if ref.get("kind") == "contact" else None
    if contact:
        if contact.email_verification not in ("public_page", "user_confirmed"):
            raise HTTPException(409, "Recipient email is not verified")
        try:
            G.check_can_send(db, item.user_id, contact)
        except G.Blocked as e:
            raise HTTPException(e.status, e.detail)
    elif G.is_suppressed(db, item.user_id, to):
        raise HTTPException(409, "Recipient is on your do-not-contact list")
    msg = EmailMessage()
    msg["To"], msg["Subject"] = to, pl.get("subject") or ""
    msg.set_content(pl.get("body") or "")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        mid = _gmail_send(p.access_token, raw)
    except Exception as e:  # network / 401 / 403
        item.send_state = "failed"
        db.commit()
        raise HTTPException(502, f"Gmail did not accept the message ({type(e).__name__}). Nothing was recorded as sent.")
    now = datetime.utcnow()
    item.send_state, item.sent_at, item.provider_message_id = "sent", now, mid
    fu = date.today() + timedelta(days=FOLLOWUP_DAYS)
    if contact:
        contact.status, contact.sent_on = "Sent", date.today()
        h = (db.query(OutreachHistory).filter(OutreachHistory.user_id == item.user_id, OutreachHistory.contact_id == contact.id,
                                              OutreachHistory.status == "Draft").order_by(OutreachHistory.sent_at).first())
        if h and not ref.get("followup"):
            h.status, h.sent_at, h.subject, h.email_text, h.follow_up_date = "Sent", now, pl.get("subject") or "", pl.get("body") or "", fu
        else:
            db.add(OutreachHistory(user_id=item.user_id, contact_id=contact.id, subject=pl.get("subject") or "",
                                   email_text=pl.get("body") or "", status="Sent", sent_at=now, follow_up_date=fu))
    elif ref.get("kind") == "application":
        a = db.query(Application).filter(Application.id == ref.get("id")).first()
        if a:
            a.follow_up_date, a.follow_up_state = fu, "pending"
            _hist(a, a.status, "follow-up email sent")
    db.commit()
    audit(db, item.user_id, "opportunities.send", {"outbox_id": item.id, "to": to}, {"gmail_id": mid}, "high")
    return _review(item, db)


# ---------------------------------------------------------------- 8. follow-ups (user-reported replies; no inbox reading)
@router.get("/v1/opp/followups")
def followups(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    today = date.today()
    items: List[Dict[str, Any]] = []
    for h in (db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id, OutreachHistory.status == "Sent",
                                               OutreachHistory.follow_up_date <= today).all()):
        c = db.query(Contact).filter(Contact.id == h.contact_id).first()
        items.append({"kind": "professor", "id": h.id, "contact_id": h.contact_id, "title": f"{c.name if c else 'Professor'}: {h.subject}",
                      "due": h.follow_up_date.isoformat(), "question": "Have they replied?"})
    for a in (db.query(Application).filter(Application.user_id == u.id, Application.status == "Applied",
                                           Application.follow_up_state == "pending", Application.follow_up_date <= today).all()):
        items.append({"kind": "application", "id": a.id, "title": f"{a.role} at {a.company}", "due": a.follow_up_date.isoformat(),
                      "question": "Any response yet?"})
    return sorted(items, key=lambda x: x["due"])


class AnswerBody(BaseModel):
    user_id: str
    answer: str   # yes | not_yet | later


@router.post("/v1/opp/followups/{kind}/{fid}/answer")
def follow_answer(kind: str, fid: str, p: AnswerBody, db: Session = Depends(get_db)):
    if p.answer not in ("yes", "not_yet", "later"):
        raise HTTPException(422, "answer must be yes, not_yet or later")
    u = _user(db, p.user_id)
    if kind == "professor":
        h = db.query(OutreachHistory).filter(OutreachHistory.id == fid, OutreachHistory.user_id == u.id).first()
        if not h:
            raise HTTPException(404, "Not found")
        if p.answer == "yes":
            h.status = "Replied"
        elif p.answer == "later":
            h.follow_up_date = date.today() + timedelta(days=3)
        db.commit()
        return {"status": h.status, "follow_up_date": h.follow_up_date.isoformat() if h.follow_up_date else None,
                "can_draft_followup": p.answer == "not_yet"}
    if kind == "application":
        a = db.query(Application).filter(Application.id == fid, Application.user_id == u.id).first()
        if not a:
            raise HTTPException(404, "Not found")
        if p.answer == "yes":
            a.follow_up_state = "replied"
        elif p.answer == "later":
            a.follow_up_date = date.today() + timedelta(days=3)
        else:
            a.follow_up_state = "not_yet"
        _hist(a, a.status, f"follow-up answer: {p.answer}")
        db.commit()
        return {"follow_up_state": a.follow_up_state, "can_draft_followup": p.answer == "not_yet"}
    raise HTTPException(404, "kind must be professor or application")


# ---------------------------------------------------------------- 9. summary (Today) + reports
@router.get("/v1/opp/summary")
def summary(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    today = date.today()
    matches = todays_matches(u.id, 50, db)
    strong = [m for m in matches if m["match"] == "Strong"]
    week = [a for a in db.query(Application).filter(Application.user_id == u.id, Application.deadline.isnot(None),
                                                    Application.deadline >= today, Application.deadline <= today + timedelta(days=7))
            .all() if a.status in ("Saved", "Reviewing", "Preparing", "Ready to submit")]
    waiting = db.query(Application).filter(Application.user_id == u.id, Application.status == "Ready to submit").count()
    drafts = db.query(OutboxItem).filter(OutboxItem.user_id == u.id, OutboxItem.status == "pending").count()
    due = followups(u.id, db)
    rec = (f"Review {strong[0]['title']} at {strong[0]['organization']} and tailor your resume." if strong
           else "Add an opportunity from a link or posting text." if not matches else f"Review {matches[0]['title']}.")
    return {"strong_matches": len(strong), "deadlines_this_week": len(week), "applications_waiting": waiting,
            "drafts_awaiting_approval": drafts, "followups_due": len(due), "recommended_next_action": rec,
            "top_opportunity_id": (strong or matches or [{}])[0].get("opportunity_id")}


@router.get("/v1/opp/reports")
def reports(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    apps = db.query(Application).filter(Application.user_id == u.id).all()
    reached = lambda a, s: any(h.get("stage") == s for h in (a.stage_history or []))   # noqa: E731
    funnel = {s: sum(1 for a in apps if reached(a, s) or a.status == s) for s in ("Saved", "Applied", "Assessment", "Interview", "Offer")}
    by_source: Dict[str, Dict[str, int]] = {}
    for a in apps:
        o = db.query(Opportunity).filter(Opportunity.id == a.opportunity_id).first() if a.opportunity_id else None
        k = (o.source_type if o else None) or "manual"
        d = by_source.setdefault(k, {"tracked": 0, "applied": 0, "interviews": 0})
        d["tracked"] += 1
        d["applied"] += int(reached(a, "Applied") or a.status == "Applied")
        d["interviews"] += int(reached(a, "Interview") or a.status == "Interview")
    oh = db.query(OutreachHistory).filter(OutreachHistory.user_id == u.id).all()
    sent = [h for h in oh if h.status in ("Sent", "Replied", "No Response")]
    replied = [h for h in sent if h.status == "Replied"]
    bottleneck = None
    if funnel["Saved"] and funnel["Applied"] / funnel["Saved"] < 0.5:
        bottleneck = "Less than half of tracked roles reach Applied - preparation is the bottleneck."
    elif funnel["Applied"] and not funnel["Interview"]:
        bottleneck = "Applications are going out but none have reached interview yet."
    return {"funnel": funnel, "by_source": by_source,
            "professor_outreach": {"sent": len(sent), "replied": len(replied),
                                   "reply_rate": round(100 * len(replied) / len(sent)) if sent else None},
            "bottleneck": bottleneck}
