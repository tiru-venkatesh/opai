"""OPAI extras: the plan's endpoints that the first repo version did not have.

Outreach OS   POST /v1/contacts/{id}/research-brief, /draft-email, suppression list, bounce/reply marks
Opportunity   POST /v1/opportunities/{id}/evaluate, POST /v1/applications/{id}/tailor-resume, GET .../blockers
SEMS          POST /v1/quizzes/generate, POST /v1/quiz-attempts, GET /v1/mastery
Builder OS    milestones, task breakdown, project dashboard, blocker, POST /v1/requests/{id}/scope

Principle kept throughout: models propose, the backend verifies. Groq is optional everywhere;
every endpoint has a deterministic fallback, and nothing here sends anything externally.
"""
from __future__ import annotations

import difflib
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import outreach_guard as G
from audit.logger import record as audit
from database import (Application, ClientRequest, Contact, Course, Milestone, Opportunity, OutboxItem,
                      OutreachHistory, Project, Quiz, QuizAttempt, ResearchBrief, Resume, SuppressedContact,
                      Task, Topic, TopicMastery, User, get_db)

router = APIRouter()


# ---------------------------------------------------------------- helpers
def _user(db: Session, user_id: str) -> User:
    u = db.query(User).filter(User.id == str(user_id)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _llm_json(system: str, prompt: str) -> Optional[Dict[str, Any]]:
    """Groq JSON call that never raises: returns None when Groq is off, down or returns junk."""
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


def _words(text: Optional[str]) -> set:
    return {w for w in re.findall(r"[a-z0-9\+\#\.]{3,}", (text or "").lower())}


def _user_skill_set(db: Session, u: User) -> set:
    skills = set(_terms(u.skills))
    for r in db.query(Resume).filter(Resume.user_id == u.id).all():
        for s in (r.skills or []):
            skills.add(str(s).strip().lower())
    for p in db.query(Project).filter(Project.user_id == u.id).all():
        for s in (p.tech_stack or []):
            skills.add(str(s).strip().lower())
    return {s for s in skills if s}


def _overlap(a: str, b: str) -> bool:
    return a == b or (len(a) > 3 and a in b) or (len(b) > 3 and b in a)


# ================================================================ OUTREACH OS
class BriefBody(BaseModel):
    user_id: str
    source_url: Optional[str] = Field(default=None, max_length=500)
    source_title: Optional[str] = Field(default=None, max_length=300)
    source_checked_on: Optional[date] = None


def _brief_out(b: ResearchBrief) -> Dict[str, Any]:
    return {"id": b.id, "contact_id": b.contact_id, "relevance": b.relevance, "verification": b.verification,
            "created_at": b.created_at.isoformat() if b.created_at else None, **(b.content or {})}


@router.post("/v1/contacts/{contact_id}/research-brief")
def research_brief(contact_id: str, p: BriefBody, db: Session = Depends(get_db)):
    """Grounded brief built BEFORE any draft. Only facts already stored on the contact (or supplied with a source) are used."""
    u = _user(db, p.user_id)
    c = db.query(Contact).filter(Contact.id == contact_id).first()
    if not c:
        raise HTTPException(404, "Contact not found")
    areas = [str(a).strip() for a in (c.research_areas or []) if str(a).strip()]
    skills = _user_skill_set(db, u)
    projects = db.query(Project).filter(Project.user_id == u.id).all()

    why: List[str] = []
    matched: List[str] = []
    for area in areas:
        al = area.lower()
        hit_skill = next((s for s in skills if _overlap(al, s) or any(_overlap(w, s) for w in _words(al))), None)
        hit_proj = next((pr for pr in projects
                         if _words(al) & (_words(pr.title) | _words(pr.description) | {str(t).lower() for t in (pr.tech_stack or [])})), None)
        if hit_skill or hit_proj:
            matched.append(area)
            if hit_proj:
                why.append(f"Your project \"{hit_proj.title}\" relates to their work on {area}.")
            else:
                why.append(f"Your skill in {hit_skill} relates to their work on {area}.")
    if areas:
        relevance = round(100 * len(matched) / len(areas))
    else:
        bio_hits = _words(c.bio) & {w for s in skills for w in _words(s)}
        relevance = min(60, 15 * len(bio_hits))
        if bio_hits:
            why.append("Your profile shares terms with their bio: " + ", ".join(sorted(bio_hits)[:5]) + ".")

    sources: List[Dict[str, Any]] = []
    if c.bio or areas:
        sources.append({"title": f"OPAI contact record for {c.name}", "type": "contact_record", "url": None, "checked_on": None})
    if p.source_url:
        sources.append({"title": p.source_title or p.source_url, "type": "web", "url": p.source_url,
                        "checked_on": (p.source_checked_on or date.today()).isoformat()})
    verification = "verified" if p.source_url and (c.bio or areas) else ("partial" if (c.bio or areas) else "unverified")
    warnings = []
    if verification != "verified":
        warnings.append("No external source attached. Add a paper or lab-page link before relying on any claim about their work.")
    if not matched:
        warnings.append("No overlap found between your profile and their listed research. Consider a different contact or add projects to your profile.")

    ask = ("Ask for a short conversation or guidance on a relevant problem"
           if relevance >= 40 else "Ask which of their ongoing areas a beginner could contribute to")
    content = {
        "professor": c.name, "institute": c.institute, "lab": c.lab,
        "research_focus": areas, "bio": (c.bio or "")[:600] or None,
        "sources": sources, "why_you_fit": why, "matched_areas": matched,
        "suggested_ask": ask, "warnings": warnings, "verification": verification,
    }
    b = ResearchBrief(user_id=u.id, contact_id=c.id, content=content, relevance=relevance, verification=verification,
                      verified_at=datetime.utcnow() if verification == "verified" else None)
    db.add(b)
    db.commit()
    db.refresh(b)
    audit(db, u.id, "outreach.research_brief", {"contact_id": c.id}, {"verification": verification, "relevance": relevance}, "low")
    return _brief_out(b)


class DraftBody(BaseModel):
    user_id: str
    brief_id: Optional[str] = None


_EMAIL_SYSTEM = (
    "You write short, honest cold emails from a student to a professor. Use ONLY facts in the BRIEF and PROFILE. "
    "Never invent papers, results, or compliments about specific work. 90-160 words, polite, one clear ask, no flattery. "
    "Return JSON: {\"subject\": str, \"body\": str}. The body must not include a signature line."
)


def _template_email(u: User, c: Contact, brief: Dict[str, Any]) -> Dict[str, str]:
    areas = brief.get("matched_areas") or brief.get("research_focus") or []
    topic = areas[0] if areas else "your research"
    fit = (brief.get("why_you_fit") or [""])[0]
    highlight = (u.highlight or "").strip()
    lines = [f"Dear Professor {c.name.split()[-1] if c.name else ''},".replace("Professor  ", "Professor "),
             "",
             f"I am {u.name}, a student" + (f" in {u.branch}" if u.branch else "") + f", writing because of your group's work on {topic}."]
    if fit:
        lines.append(fit)
    if highlight:
        lines.append(highlight if highlight.endswith(".") else highlight + ".")
    lines += ["", "Would you be open to a short conversation, or could you point me to a problem in this area where a student could contribute?",
              "I would be glad to share details of my work.", "", "Thank you for your time."]
    return {"subject": f"Student interested in your work on {topic}", "body": "\n".join(lines)}


def _similar_draft_warning(db: Session, uid: str, contact: Contact, body: str) -> Optional[str]:
    def strip(t: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"dear [^,\n]+,", "", (t or "").lower())).strip()
    mine = strip(body)
    rows = (db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.channel == "email")
            .order_by(OutboxItem.created_at.desc()).limit(25).all())
    for r in rows:
        if (r.ref or {}).get("id") == contact.id:
            continue
        other = strip((r.payload or {}).get("body", ""))
        if other and difflib.SequenceMatcher(None, mine, other).ratio() > 0.85:
            return "This draft is nearly identical to another one you wrote. Personalise it before approving."
    return None


@router.post("/v1/contacts/{contact_id}/draft-email")
def draft_email(contact_id: str, p: DraftBody, db: Session = Depends(get_db)):
    """Creates ONE draft in the Outbox. Requires a research brief with at least a partial source. Never sends."""
    u = _user(db, p.user_id)
    c = db.query(Contact).filter(Contact.id == contact_id).first()
    if not c:
        raise HTTPException(404, "Contact not found")
    q = db.query(ResearchBrief).filter(ResearchBrief.user_id == u.id, ResearchBrief.contact_id == c.id)
    brief = q.filter(ResearchBrief.id == p.brief_id).first() if p.brief_id else q.order_by(ResearchBrief.created_at.desc()).first()
    if not brief:
        raise HTTPException(409, "Create a research brief for this contact first (POST /v1/contacts/{id}/research-brief).")
    if brief.verification == "unverified":
        raise HTTPException(409, "The research brief has no supporting source. Add the contact's bio or research areas, or attach a source link.")
    try:
        G.check_can_draft(db, u.id, c)
    except G.Blocked as e:
        raise HTTPException(e.status, e.detail)

    b = brief.content or {}
    gen = _llm_json(_EMAIL_SYSTEM, f"PROFILE: name={u.name}; branch={u.branch}; skills={u.skills}; highlight={u.highlight}\nBRIEF: {b}")
    subject = (gen or {}).get("subject") if isinstance((gen or {}).get("subject"), str) else None
    body = (gen or {}).get("body") if isinstance((gen or {}).get("body"), str) else None
    source = "groq"
    if not subject or not body or len(body) < 60:
        t = _template_email(u, c, b)
        subject, body, source = t["subject"], t["body"], "template"
    body = body.rstrip() + f"\n\nBest regards,\n{u.name}"

    warnings = list(b.get("warnings") or [])
    sim = _similar_draft_warning(db, u.id, c, body)
    if sim:
        warnings.append(sim)

    item = OutboxItem(user_id=u.id, channel="email", status="pending", payload={"to": c.email, "subject": subject, "body": body},
                      ref={"kind": "contact", "id": c.id}, note=f"brief:{brief.id}; drafted by {source}", risk_level="high",
                      approval_scope="single_use", expires_at=datetime.utcnow() + timedelta(hours=48))
    db.add(item)
    hist = OutreachHistory(user_id=u.id, contact_id=c.id, subject=subject, email_text=body, status="Draft")
    db.add(hist)
    if c.status == "Not started":
        c.status = "Drafted"
    db.commit()
    db.refresh(item)
    audit(db, u.id, "outreach.draft_email", {"contact_id": c.id, "brief_id": brief.id}, {"outbox_id": item.id, "source": source}, "high")
    return {"outbox_id": item.id, "status": "pending_approval", "to": c.email, "subject": subject, "body": body,
            "drafted_by": source, "brief_id": brief.id, "warnings": warnings,
            "approvals_remaining_today": G.remaining_today(db, u.id),
            "note": "Nothing has been sent. Review, edit and approve this in the Outbox."}


class SuppressBody(BaseModel):
    user_id: str
    email: str = Field(min_length=3, max_length=254)
    reason: str = "do_not_contact"


@router.get("/v1/outreach/suppression")
def list_suppression(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = db.query(SuppressedContact).filter(SuppressedContact.user_id == u.id).order_by(SuppressedContact.created_at.desc()).all()
    return [{"id": r.id, "email": r.email, "reason": r.reason, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


@router.post("/v1/outreach/suppression")
def add_suppression(p: SuppressBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if p.reason not in {"do_not_contact", "bounced", "unsubscribed", "replied_no"}:
        raise HTTPException(400, "reason must be do_not_contact, bounced, unsubscribed or replied_no")
    e = G.norm_email(p.email)
    row = G.is_suppressed(db, u.id, e)
    if not row:
        row = SuppressedContact(user_id=u.id, email=e, reason=p.reason)
        db.add(row)
        db.commit()
        db.refresh(row)
    # withdraw any pending drafts to this address
    for it in db.query(OutboxItem).filter(OutboxItem.user_id == u.id, OutboxItem.status == "pending").all():
        if G.norm_email((it.payload or {}).get("to")) == e:
            it.status = "rejected"
            it.note = "Auto-rejected: recipient added to do-not-contact list"
    db.commit()
    audit(db, u.id, "outreach.suppress", {"reason": p.reason}, {"ok": True}, "low")
    return {"id": row.id, "email": row.email, "reason": row.reason}


@router.delete("/v1/outreach/suppression/{item_id}")
def remove_suppression(item_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    row = db.query(SuppressedContact).filter(SuppressedContact.id == item_id, SuppressedContact.user_id == u.id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    return {"status": "removed"}


@router.post("/v1/outreach/{outreach_id}/bounced")
def mark_bounced(outreach_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    row = db.query(OutreachHistory).filter(OutreachHistory.id == outreach_id, OutreachHistory.user_id == u.id).first()
    if not row:
        raise HTTPException(404, "Outreach record not found")
    c = db.query(Contact).filter(Contact.id == row.contact_id).first()
    row.status = "No Response"
    if c and not G.is_suppressed(db, u.id, c.email):
        db.add(SuppressedContact(user_id=u.id, email=G.norm_email(c.email), reason="bounced"))
    db.commit()
    audit(db, u.id, "outreach.bounced", {"outreach_id": outreach_id}, {"suppressed": bool(c)}, "low")
    return {"status": "bounced", "suppressed": bool(c)}


@router.post("/v1/outreach/{outreach_id}/replied")
def mark_replied(outreach_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    row = db.query(OutreachHistory).filter(OutreachHistory.id == outreach_id, OutreachHistory.user_id == u.id).first()
    if not row:
        raise HTTPException(404, "Outreach record not found")
    row.status = "Replied"
    row.follow_up_date = None
    db.commit()
    return {"status": "replied"}


# ================================================================ OPPORTUNITY OS
def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


@router.post("/v1/opportunities/{opportunity_id}/evaluate")
def evaluate_opportunity(opportunity_id: str, user_id: str, db: Session = Depends(get_db)):
    """Deterministic fit check: match %, gaps, eligibility, deadline urgency, duplicates, source freshness."""
    u = _user(db, user_id)
    o = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    skills = _user_skill_set(db, u)
    required = [str(t).strip().lower() for t in (o.tags or []) if str(t).strip()]
    matched = [t for t in required if any(_overlap(t, s) for s in skills)]
    gaps = [t for t in required if t not in matched]
    if required:
        match, match_conf = round(100 * len(matched) / len(required)), "normal"
    else:
        match, match_conf = 50, "low"

    projects = db.query(Project).filter(Project.user_id == u.id).all()
    relevant_projects = [pr.title for pr in projects
                         if any(t in (_words(pr.title) | _words(pr.description) | {str(x).lower() for x in (pr.tech_stack or [])}) for t in matched)]

    days_left = (o.deadline - date.today()).days if o.deadline else None
    urgency = ("none" if days_left is None else "overdue" if days_left < 0 else "critical" if days_left <= 3
               else "soon" if days_left <= 7 else "ok")

    checklist: List[Dict[str, str]] = []
    note = (o.eligibility_note or "").strip()
    if note:
        status = "check"
        m = re.search(r"(?:cgpa|gpa)\D{0,15}(\d(?:\.\d+)?)", note, re.I) or re.search(r"(\d(?:\.\d+)?)\s*\+?\s*(?:cgpa|gpa)", note, re.I)
        if m and u.cgpa is not None:
            status = "met" if float(u.cgpa) >= float(m.group(1)) else "unmet"
        checklist.append({"item": note, "status": status})
    else:
        checklist.append({"item": "No eligibility criteria recorded. Check the source page.", "status": "check"})

    norm_key = (_norm(o.company_or_lab), _norm(o.title))
    dup_opps = [x.id for x in db.query(Opportunity).filter(Opportunity.id != o.id).all()
                if (_norm(x.company_or_lab), _norm(x.title)) == norm_key]
    dup_apps = [a.id for a in db.query(Application).filter(Application.user_id == u.id).all()
                if _norm(a.company) == norm_key[0] and _norm(a.role) == norm_key[1]]

    stale = bool(o.last_verified_at and (datetime.utcnow() - o.last_verified_at).days > 14)
    unmet = any(i["status"] == "unmet" for i in checklist)
    if urgency == "overdue" or unmet or dup_apps:
        action = "dismiss" if not dup_apps else "already_tracked"
    elif match >= 60:
        action = "apply"
    else:
        action = "save"
    effort = 60 + 15 * min(len(gaps), 3)

    why = []
    if matched:
        why.append("Skills overlap: " + ", ".join(matched))
    if relevant_projects:
        why.append("Relevant projects: " + ", ".join(relevant_projects[:3]))
    audit(db, u.id, "opportunity.evaluate", {"opportunity_id": o.id}, {"match": match, "action": action}, "low")
    return {
        "opportunity_id": o.id, "title": o.title, "company_or_lab": o.company_or_lab,
        "match_percent": match, "match_confidence": match_conf, "why_it_matches": why, "gaps": gaps,
        "eligibility_checklist": checklist, "deadline": o.deadline.isoformat() if o.deadline else None,
        "days_left": days_left, "urgency": urgency, "effort_minutes": effort,
        "duplicates": {"opportunities": dup_opps, "your_applications": dup_apps},
        "source": {"link": o.link, "source": o.source, "last_verified_at": o.last_verified_at.isoformat() if o.last_verified_at else None, "stale": stale},
        "recommended_action": action,
    }


class TailorBody(BaseModel):
    user_id: str
    resume_id: Optional[str] = None
    job_description: Optional[str] = Field(default=None, max_length=8000)


def _resume_lines(text: str) -> List[str]:
    out = []
    for ln in (text or "").splitlines():
        ln = ln.strip().lstrip("-*•· \t")
        if len(ln) >= 25:
            out.append(ln)
    return out


@router.post("/v1/applications/{application_id}/tailor-resume")
def tailor_resume(application_id: str, p: TailorBody, db: Session = Depends(get_db)):
    """Picks the best resume version and the lines that best fit this role. Grounded: bullets must come from the resume."""
    u = _user(db, p.user_id)
    a = db.query(Application).filter(Application.id == application_id, Application.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    target = " ".join([a.role or "", a.company or "", a.notes or "", p.job_description or ""])
    kw = _words(target) - {"the", "and", "for", "with", "intern", "internship", "company", "role", "will", "you", "our"}
    resumes = db.query(Resume).filter(Resume.user_id == u.id).all()
    if p.resume_id:
        resumes = [r for r in resumes if r.id == p.resume_id]
    if not resumes:
        raise HTTPException(409, "Add a resume first (POST /v1/resumes).")
    best = max(resumes, key=lambda r: len(_words(r.raw_text) & kw))
    lines = _resume_lines(best.raw_text)
    ranked = sorted(lines, key=lambda ln: len(_words(ln) & kw), reverse=True)
    picked = [ln for ln in ranked if _words(ln) & kw][:5] or ranked[:5]

    rewritten: List[str] = []
    gen = _llm_json("You tighten resume bullets for a specific role. Use ONLY facts present in each source line; never add numbers, tools or results. "
                    "Return JSON {\"bullets\": [{\"text\": str, \"source_line\": str}]} where source_line is copied exactly from the input.",
                    f"ROLE: {a.role} at {a.company}\nKEYWORDS: {sorted(kw)[:30]}\nLINES: {picked}")
    for b in ((gen or {}).get("bullets") or []):
        if isinstance(b, dict) and isinstance(b.get("text"), str) and b.get("source_line") in picked:
            rewritten.append(b["text"].strip())
    bullets = rewritten if len(rewritten) >= min(3, len(picked)) else picked
    method = "groq_grounded" if bullets is rewritten else "selected_from_resume"

    resume_words = _words(best.raw_text)
    missing = sorted(k for k in kw if k not in resume_words)[:10]
    a.resume_bullets = bullets
    a.resume_id = best.id
    a.tailored_at = datetime.utcnow()
    db.commit()
    audit(db, u.id, "application.tailor_resume", {"application_id": a.id, "resume_id": best.id}, {"bullets": len(bullets), "method": method}, "low")
    return {"application_id": a.id, "resume_id": best.id, "resume_label": best.label, "bullets": bullets, "method": method,
            "keywords_not_in_resume": missing,
            "note": "Review before use. Nothing has been submitted."}


@router.get("/v1/applications/{application_id}/blockers")
def application_blockers(application_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    a = db.query(Application).filter(Application.id == application_id, Application.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    out: List[Dict[str, str]] = []
    today = date.today()
    open_status = (a.status or "") in ("To Apply", "Draft", "Not started", "")
    if a.deadline and a.deadline < today and open_status:
        out.append({"code": "deadline_passed", "text": "The deadline has passed."})
    if not a.link:
        out.append({"code": "no_link", "text": "No application link saved."})
    if open_status and not a.tailored_at and not a.resume_bullets:
        out.append({"code": "resume_not_tailored", "text": "Resume has not been tailored for this role."})
    if open_status and a.deadline and 0 <= (a.deadline - today).days <= 3:
        out.append({"code": "deadline_close", "text": f"Deadline in {(a.deadline - today).days} day(s)."})
    if a.follow_up_date and a.follow_up_date <= today and not open_status:
        out.append({"code": "follow_up_due", "text": "A follow-up is due."})
    return {"application_id": a.id, "blocked": bool(out), "blockers": out}


# ================================================================ SEMS QUIZZES + MASTERY
class QuizGen(BaseModel):
    user_id: str
    topic_id: str
    count: int = Field(default=5, ge=1, le=10)


def _own_topic(db: Session, uid: str, topic_id: str):
    t = (db.query(Topic).join(Course, Course.id == Topic.course_id)
         .filter(Topic.id == topic_id, Course.user_id == uid).first())
    if not t:
        raise HTTPException(404, "Topic not found")
    course = db.query(Course).filter(Course.id == t.course_id).first()
    return t, course


def _valid_mcq(q: Any) -> bool:
    return (isinstance(q, dict) and isinstance(q.get("q"), str) and isinstance(q.get("options"), list)
            and len(q["options"]) == 4 and all(isinstance(o, str) and o.strip() for o in q["options"])
            and isinstance(q.get("answer"), int) and 0 <= q["answer"] <= 3)


@router.post("/v1/quizzes/generate")
def generate_quiz(p: QuizGen, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    t, course = _own_topic(db, u.id, p.topic_id)
    gen = _llm_json("You write exam-style multiple choice questions for a university course topic. Exactly 4 options each, one correct. "
                    "Return JSON {\"questions\": [{\"q\": str, \"options\": [str,str,str,str], \"answer\": 0-3, \"explanation\": str}]}.",
                    f"COURSE: {course.name if course else ''}\nTOPIC: {t.name}\nUNIT: {t.unit}\nNOTES: {(t.notes or '')[:1200]}\nCOUNT: {p.count}")
    qs = [q for q in ((gen or {}).get("questions") or []) if _valid_mcq(q)][:p.count]
    if qs:
        kind, source = "mcq", "groq"
        stored = [{"id": f"q{i+1}", "type": "mcq", "q": q["q"], "options": q["options"], "answer": q["answer"],
                   "explanation": str(q.get("explanation") or "")} for i, q in enumerate(qs)]
    else:
        kind, source = "recall", "template"
        prompts = [f"Explain \"{t.name}\" in your own words without looking at notes.",
                   f"List the key terms, steps or conditions of \"{t.name}\".",
                   f"Give one worked example or application of \"{t.name}\".",
                   f"What is the most common mistake students make on \"{t.name}\", and how do you avoid it?"]
        stored = [{"id": f"q{i+1}", "type": "recall", "q": s} for i, s in enumerate(prompts[:p.count])]
    quiz = Quiz(user_id=u.id, topic_id=t.id, kind=kind, source=source, questions=stored)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    public = [{k: v for k, v in q.items() if k not in ("answer", "explanation")} for q in stored]
    return {"quiz_id": quiz.id, "topic": t.name, "kind": kind, "source": source, "questions": public,
            "how_to_answer": ("answers: {question_id: option_index 0-3}" if kind == "mcq"
                              else "answers: {question_id: self_rating 1-5}. Groq is not configured, so these are self-assessed recall prompts.")}


class AttemptBody(BaseModel):
    user_id: str
    quiz_id: str
    answers: Dict[str, int]


def _next_review(frac: float) -> int:
    return 1 if frac < 0.5 else 3 if frac < 0.75 else 7 if frac < 0.9 else 14


@router.post("/v1/quiz-attempts")
def submit_attempt(p: AttemptBody, db: Session = Depends(get_db)):
    """Scored by the backend. Updates topic mastery, topic confidence and the next review date."""
    u = _user(db, p.user_id)
    quiz = db.query(Quiz).filter(Quiz.id == p.quiz_id, Quiz.user_id == u.id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    if db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz.id, QuizAttempt.user_id == u.id).first():
        raise HTTPException(409, "This quiz was already submitted. Generate a new one.")
    qs = quiz.questions or []
    review, score, total = [], 0, 0
    for q in qs:
        a = p.answers.get(q["id"])
        if q["type"] == "mcq":
            if a is None or not (0 <= a <= 3):
                raise HTTPException(400, f"Answer for {q['id']} must be an option index 0-3")
            ok = a == q["answer"]
            score += 1 if ok else 0
            total += 1
            review.append({"id": q["id"], "correct": ok, "your_answer": a, "correct_answer": q["answer"], "explanation": q.get("explanation", "")})
        else:
            if a is None or not (1 <= a <= 5):
                raise HTTPException(400, f"Self-rating for {q['id']} must be 1-5")
            score += a - 1
            total += 4
            review.append({"id": q["id"], "self_rating": a})
    frac = score / total if total else 0.0
    m = db.query(TopicMastery).filter(TopicMastery.user_id == u.id, TopicMastery.topic_id == quiz.topic_id).first()
    if not m:
        m = TopicMastery(user_id=u.id, topic_id=quiz.topic_id, mastery=round(frac, 3), attempts=0)
        db.add(m)
    else:
        m.mastery = round(0.6 * float(m.mastery or 0) + 0.4 * frac, 3)
    m.attempts = (m.attempts or 0) + 1
    m.last_score = round(frac, 3)
    t = db.query(Topic).filter(Topic.id == quiz.topic_id).first()
    nxt = date.today() + timedelta(days=_next_review(frac))
    if t:
        t.confidence = max(1, min(5, round(1 + 4 * float(m.mastery))))
        t.last_revised = date.today()
        t.next_review = nxt
        if t.status == "not_started":
            t.status = "in_progress"
    db.add(QuizAttempt(user_id=u.id, quiz_id=quiz.id, topic_id=quiz.topic_id, answers=p.answers, score=score, total=total))
    db.commit()
    audit(db, u.id, "quiz.attempt", {"quiz_id": quiz.id}, {"fraction": round(frac, 3)}, "low")
    return {"score": score, "total": total, "fraction": round(frac, 3), "mastery": float(m.mastery), "attempts": m.attempts,
            "topic_confidence": t.confidence if t else None, "next_review": nxt.isoformat(), "review": review}


@router.get("/v1/mastery")
def list_mastery(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = (db.query(TopicMastery, Topic).join(Topic, Topic.id == TopicMastery.topic_id)
            .filter(TopicMastery.user_id == u.id).order_by(TopicMastery.mastery.asc()).all())
    return [{"topic_id": t.id, "topic": t.name, "mastery": float(m.mastery or 0), "attempts": m.attempts,
             "last_score": float(m.last_score) if m.last_score is not None else None,
             "next_review": t.next_review.isoformat() if t.next_review else None} for m, t in rows]


# ================================================================ BUILDER OS
def _own_project(db: Session, uid: str, pid: str) -> Project:
    pr = db.query(Project).filter(Project.id == pid, Project.user_id == uid).first()
    if not pr:
        raise HTTPException(404, "Project not found")
    return pr


class MilestoneCreate(BaseModel):
    user_id: str
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[date] = None


class MilestoneUpdate(BaseModel):
    user_id: str
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    due_date: Optional[date] = None
    status: Optional[str] = None


def _ms_out(m: Milestone, tasks: List[Task]) -> Dict[str, Any]:
    mine = [t for t in tasks if t.milestone_id == m.id]
    return {"id": m.id, "title": m.title, "due_date": m.due_date.isoformat() if m.due_date else None, "status": m.status,
            "tasks_done": sum(1 for t in mine if t.status == "done"), "tasks_total": len(mine)}


@router.post("/v1/projects/{project_id}/milestones")
def add_milestone(project_id: str, p: MilestoneCreate, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    pr = _own_project(db, u.id, project_id)
    pos = db.query(Milestone).filter(Milestone.project_id == pr.id).count()
    m = Milestone(user_id=u.id, project_id=pr.id, title=p.title.strip(), due_date=p.due_date, position=pos)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _ms_out(m, [])


@router.patch("/v1/projects/{project_id}/milestones/{milestone_id}")
def update_milestone(project_id: str, milestone_id: str, p: MilestoneUpdate, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    _own_project(db, u.id, project_id)
    m = db.query(Milestone).filter(Milestone.id == milestone_id, Milestone.project_id == project_id).first()
    if not m:
        raise HTTPException(404, "Milestone not found")
    if p.status is not None:
        if p.status not in ("todo", "in_progress", "done"):
            raise HTTPException(400, "status must be todo, in_progress or done")
        m.status = p.status
    if p.title is not None:
        m.title = p.title.strip()
    if p.due_date is not None:
        m.due_date = p.due_date
    db.commit()
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    return _ms_out(m, tasks)


class BreakdownBody(BaseModel):
    user_id: str
    max_tasks: int = Field(default=5, ge=2, le=8)


@router.post("/v1/projects/{project_id}/milestones/{milestone_id}/breakdown")
def breakdown_milestone(project_id: str, milestone_id: str, p: BreakdownBody, db: Session = Depends(get_db)):
    """Turns a milestone into concrete tasks. Internal, low-risk: tasks are created directly and visible in the project."""
    u = _user(db, p.user_id)
    pr = _own_project(db, u.id, project_id)
    m = db.query(Milestone).filter(Milestone.id == milestone_id, Milestone.project_id == pr.id).first()
    if not m:
        raise HTTPException(404, "Milestone not found")
    gen = _llm_json("Break a project milestone into small concrete tasks (each 20-120 minutes). "
                    "Return JSON {\"tasks\": [{\"title\": str, \"minutes\": int}]}.",
                    f"PROJECT: {pr.title}\nDESCRIPTION: {pr.description}\nSTACK: {pr.tech_stack}\nMILESTONE: {m.title}\nMAX: {p.max_tasks}")
    items = []
    for t in ((gen or {}).get("tasks") or [])[:p.max_tasks]:
        if isinstance(t, dict) and isinstance(t.get("title"), str) and t["title"].strip():
            mins = t.get("minutes") if isinstance(t.get("minutes"), int) else 45
            items.append((t["title"].strip()[:200], max(15, min(180, mins))))
    source = "groq"
    if not items:
        source = "template"
        items = [(f"Define what 'done' means for: {m.title}", 20), (f"Build: {m.title}", 90), (f"Test and document: {m.title}", 45)]
    created = []
    for title, mins in items:
        t = Task(user_id=u.id, project_id=pr.id, title=title, type="project", estimated_minutes=mins, status="todo",
                 milestone_id=m.id, due_date=m.due_date)
        db.add(t)
        created.append(t)
    if m.status == "todo":
        m.status = "in_progress"
    db.commit()
    audit(db, u.id, "project.breakdown", {"milestone_id": m.id}, {"tasks": len(created), "source": source}, "low")
    return {"milestone_id": m.id, "source": source,
            "tasks": [{"id": t.id, "title": t.title, "estimated_minutes": t.estimated_minutes} for t in created]}


class BlockerBody(BaseModel):
    user_id: str
    text: Optional[str] = Field(default=None, max_length=300)


@router.post("/v1/projects/{project_id}/blocker")
def set_blocker(project_id: str, p: BlockerBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    pr = _own_project(db, u.id, project_id)
    pr.blocker = (p.text or "").strip() or None
    db.commit()
    return {"project_id": pr.id, "blocker": pr.blocker}


@router.get("/v1/projects/{project_id}/dashboard")
def project_dashboard(project_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    pr = _own_project(db, u.id, project_id)
    tasks = db.query(Task).filter(Task.project_id == pr.id, Task.user_id == u.id).all()
    open_tasks = [t for t in tasks if t.status != "done"]
    open_tasks.sort(key=lambda t: (t.due_date is None, t.due_date or date.max))
    ms = db.query(Milestone).filter(Milestone.project_id == pr.id).order_by(Milestone.position).all()
    nxt = open_tasks[0] if open_tasks else None
    nearest = [m.due_date for m in ms if m.status != "done" and m.due_date]
    return {"id": pr.id, "title": pr.title, "status": pr.status,
            "progress": {"done": len(tasks) - len(open_tasks), "total": len(tasks)},
            "next_task": {"id": nxt.id, "title": nxt.title, "estimated_minutes": nxt.estimated_minutes} if nxt else None,
            "blocker": pr.blocker, "deadline": min(nearest).isoformat() if nearest else None,
            "milestones": [_ms_out(m, tasks) for m in ms]}


class ScopeBody(BaseModel):
    user_id: str
    requirements: Optional[List[str]] = None
    timeline: Optional[str] = Field(default=None, max_length=120)
    price: Optional[str] = Field(default=None, max_length=120)
    confirm: bool = False


@router.post("/v1/requests/{request_id}/scope")
def scope_request(request_id: str, p: ScopeBody, db: Session = Depends(get_db)):
    """Two steps. Without confirm=true: extract proposed requirements and change nothing.
    With confirm=true: save the (possibly edited) requirements and move the request to Scoped."""
    u = _user(db, p.user_id)
    r = db.query(ClientRequest).filter(ClientRequest.id == request_id, ClientRequest.user_id == u.id).first()
    if not r:
        raise HTTPException(404, "Request not found")
    if not p.confirm:
        gen = _llm_json("Extract the concrete deliverables a client is asking for. Do not invent requirements. "
                        "Return JSON {\"requirements\": [str], \"open_questions\": [str]}.", f"CLIENT ASK: {r.ask}")
        reqs = [x.strip() for x in ((gen or {}).get("requirements") or []) if isinstance(x, str) and x.strip()]
        questions = [x.strip() for x in ((gen or {}).get("open_questions") or []) if isinstance(x, str) and x.strip()]
        source = "groq"
        if not reqs:
            source = "heuristic"
            parts = re.split(r"(?<=[.!?])\s+|\n+|;\s*|\band\b(?=\s+(?:a|an|the|build|add|make|create)\b)", r.ask or "")
            reqs = [s.strip(" -•*.") for s in parts if len(s.strip(" -•*.")) > 8][:8]
            questions = ["What is the deadline?", "What is the budget?"] if not r.timeline and not r.price else []
        return {"request_id": r.id, "status": r.status, "proposed_requirements": reqs, "open_questions": questions,
                "source": source, "saved": False, "next": "Review/edit, then call again with confirm=true and requirements."}
    reqs = [x.strip() for x in (p.requirements or []) if x and x.strip()]
    if not reqs:
        raise HTTPException(400, "Send the confirmed requirements list.")
    r.scope = "\n".join(f"- {x}" for x in reqs)
    if p.timeline is not None:
        r.timeline = p.timeline
    if p.price is not None:
        r.price = p.price
    if r.status == "New":
        r.status = "Scoped"
    db.commit()
    audit(db, u.id, "request.scope", {"request_id": r.id}, {"requirements": len(reqs)}, "low")
    return {"request_id": r.id, "status": r.status, "scope": r.scope, "timeline": r.timeline, "price": r.price, "saved": True}
