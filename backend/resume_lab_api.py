"""OPAI Resume Lab: learn from the student's OWN resume versions (up to 10) and retrieve from them.

Everything here is grounded in text the user supplied:
  * the "bullet bank" is the user's real bullets, indexed one per chunk (RAG);
  * match/tailor only ever SELECT existing bullets and report gaps; nothing is invented, no skill is added;
  * insights compare the user's strongest versions with the rest using deterministic counts.
Nothing is submitted or sent anywhere.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

import rag_service as rag
from audit.logger import record as audit
from database import Application, DocumentChunk, Opportunity, Resume, User, get_db

from resume_lab_tools import (  # noqa: F401  (re-exported: tests and import_resumes_dir.py use these names)
    _BULLET_START, _CONTENT, _EMAIL, _METRIC, _PHONE, _SECTION, _STOP, _TERM_RE, _URL, _VERBS, _WEAK,
    _h, bullet_stats, clean_pdf_text, parse_resume, scrub_pii)
import resume_lab_tools as T

router = APIRouter()

MAX_VERSIONS = 10
BULLET = "resume_bullet"
def _user(db: Session, uid: str) -> User:
    u = db.query(User).filter(User.id == str(uid)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _own_resumes(db: Session, uid: str) -> List[Resume]:
    """The student's OWN versions. Reference resumes (other people's) are never returned here."""
    return (db.query(Resume).filter(Resume.user_id == str(uid), or_(Resume.kind.is_(None), Resume.kind == "own"))
            .order_by(Resume.created_at).all())


def _reference_resumes(db: Session, uid: str) -> List[Resume]:
    return db.query(Resume).filter(Resume.user_id == str(uid), Resume.kind == "reference").order_by(Resume.created_at).all()


# ---------------------------------------------------------------- bullet bank (RAG)
def sync_bank(db: Session, uid: str) -> int:
    """Index every bullet of every version, one chunk per bullet. Re-indexes only changed resumes and drops orphans."""
    uid = str(uid)
    resumes = {r.id: r for r in _own_resumes(db, uid)}
    rows = db.query(DocumentChunk).filter(DocumentChunk.user_id == uid, DocumentChunk.source_type == BULLET).all()
    by_src: Dict[str, List[DocumentChunk]] = {}
    for ch in rows:
        by_src.setdefault((ch.metadata_json or {}).get("source_id"), []).append(ch)
    changed = 0
    for sid, chunks in by_src.items():   # orphans / edited versions
        r = resumes.get(sid)
        if r is None or any((c.metadata_json or {}).get("text_hash") != _h(r.raw_text) for c in chunks):
            for c in chunks:
                db.delete(c)
            by_src[sid] = []
    for rid, r in resumes.items():
        if by_src.get(rid):
            continue
        bl = parse_resume(r.raw_text)["bullets"]
        if not bl:
            continue
        vecs, tag = rag.embed_texts([b["text"] for b in bl])
        for i, (b, v) in enumerate(zip(bl, vecs)):
            db.add(DocumentChunk(user_id=uid, source_type=BULLET, content=b["text"], embedding=v,
                                 metadata_json={"source_id": rid, "label": r.label, "target_role": r.target_role or "",
                                                "section": b["section"], "idx": i, "embedder": tag, "text_hash": _h(r.raw_text)}))
        changed += len(bl)
    db.commit()
    return changed


def _job_text(db: Session, uid: str, job_text: Optional[str], opportunity_id: Optional[str]) -> str:
    if job_text and job_text.strip():
        return job_text.strip()
    if opportunity_id:
        o = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
        if not o or (o.user_id and o.user_id != str(uid)):
            raise HTTPException(404, "Opportunity not found")
        return " ".join(x for x in (o.title, o.company_or_lab, o.description_text or o.description or "") if x)
    raise HTTPException(422, "Provide job_text or opportunity_id")


def job_terms(text: str, limit: int = 25) -> List[str]:
    """Terms the posting itself emphasises: known tech terms plus tokens repeated in the text. Deterministic."""
    low = text.lower()
    try:
        from opportunities_api import TECH_TERMS, _has
        known = [t for t in TECH_TERMS if _has(low, t)]
    except Exception:
        known = []
    cnt = Counter(t for t in _TERM_RE.findall(low) if t not in _STOP and len(t) > 3 and not t.isdigit())
    freq = [t for t, c in cnt.most_common(40) if c >= 2 and t not in known]
    out: List[str] = []
    for t in known + freq:
        if t not in out and not any(t != k and t in k.split() for k in known):
            out.append(t)
    return out[:limit]


def _contains(text_low: str, term: str) -> bool:
    return re.search(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])", text_low) is not None


# ---------------------------------------------------------------- analysis (Groq if available, deterministic otherwise)
def offline_analysis(text: str, target_role: Optional[str] = None) -> Dict[str, Any]:
    """Deterministic scoring from the text alone. Extracts only what is written; invents nothing."""
    parsed = parse_resume(text)
    st = bullet_stats(parsed["bullets"])
    skills: List[str] = []
    for ln in parsed["sections"].get("skills", []) + parsed["sections"].get("technical skills", []) + parsed["sections"].get("header", []):
        if ":" in ln and "skill" not in ln.lower().split(":")[0] and len(ln.split(":")[0]) > 25:
            continue
        body = ln.split(":", 1)[1] if ":" in ln and ln.lower().startswith(("skill", "technical", "languages", "tools", "frameworks")) else ln
        if ln.lower().startswith(("skill", "technical", "languages", "tools", "frameworks")) or ln in parsed["sections"].get("skills", []):
            skills += [x.strip() for x in re.split(r"[,;|/]", body) if 1 < len(x.strip()) <= 30]
    try:
        from opportunities_api import TECH_TERMS, _has
        low = text.lower()
        skills += [t for t in TECH_TERMS if _has(low, t) and t not in {x.lower() for x in skills}]
    except Exception:
        pass
    seen, uniq = set(), []
    for x in skills:
        if x.lower() not in seen:
            seen.add(x.lower())
            uniq.append(x)
    n = st["bullets"]
    clarity = 0 if not n else (9 if 10 <= st["avg_words"] <= 26 else 6)
    impact = round(10 * st["metric_ratio"])
    keyword = min(10, len(uniq))
    structure = min(10, 2 * len([k for k in parsed["sections"] if k != "header"]) + (2 if n >= 3 else 0))
    overall = round((clarity + impact + keyword + structure) / 4)
    weakest = min((("clarity", clarity), ("impact", impact), ("keyword_match", keyword), ("structure", structure)), key=lambda x: x[1])[0]
    notes = {"impact": "Add real numbers or outcomes to more bullets.", "clarity": "Keep bullets to one clear line (10-26 words).",
             "keyword_match": "List the tools and languages you actually used.", "structure": "Use clear Projects / Experience / Skills sections."}[weakest]
    return {"skills": uniq[:40], "summary": "", "suggested_bullets": [],
            "score": {"clarity": clarity, "impact": impact, "keyword_match": keyword, "structure": structure, "overall": overall,
                      "notes": notes, "method": "offline"}}


def _create(db: Session, uid: str, label: str, target_role: Optional[str], text: str, kind: str = "own") -> Resume:
    data = None
    if kind == "reference":
        text = scrub_pii(text)
    try:
        from agent.groq_client import groq_enabled
        if groq_enabled():
            from agent_service import _analyze_resume_text
            data = _analyze_resume_text(text, target_role)
    except Exception:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("score"), dict):
        data = offline_analysis(text, target_role)
    row = Resume(user_id=str(uid), label=label, target_role=target_role, raw_text=text, skills=data.get("skills", []),
                 summary=data.get("summary", ""), suggested_bullets=data.get("suggested_bullets", []), score=data["score"], kind=kind)
    db.add(row)
    db.commit()
    db.refresh(row)
    if kind != "reference":     # references stay out of RAG so they can never surface in the student's own answers
        rag.index_resume(db, uid, row.id, text, label=label, target_role=target_role or "")
    return row


# ---------------------------------------------------------------- import / library
MAX_REFERENCES = 30


class ResumeIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    target_role: Optional[str] = Field(default=None, max_length=120)
    text: str = Field(min_length=80, max_length=40000)
    kind: str = Field(default="own", pattern="^(own|reference)$")


class ImportBody(BaseModel):
    user_id: str
    resumes: List[ResumeIn] = Field(min_length=1, max_length=MAX_VERSIONS)


def _add_one(db: Session, uid: str, label: str, role: Optional[str], text: str, kind: str) -> Dict[str, Any]:
    """Returns {"created": {...}} or {"skipped": {...}}. Duplicates are skipped, never overwritten."""
    label = label.strip()
    pool = _reference_resumes(db, uid) if kind == "reference" else _own_resumes(db, uid)
    shown = scrub_pii(text) if kind == "reference" else text
    if _h(shown) in {_h(r.raw_text) for r in pool}:
        return {"skipped": {"label": label, "reason": "identical text already in your library"}}
    if label.lower() in {r.label.strip().lower() for r in pool}:
        return {"skipped": {"label": label, "reason": "label already used; rename it"}}
    cap = MAX_REFERENCES if kind == "reference" else MAX_VERSIONS
    if len(pool) >= cap:
        return {"skipped": {"label": label, "reason": f"library is full ({cap} {'references' if kind == 'reference' else 'versions'}); delete one first"}}
    row = _create(db, uid, label, role, text, kind)
    return {"created": {"id": row.id, "label": row.label, "kind": kind}}


@router.post("/v1/resume-lab/import")
def import_resumes(p: ImportBody, db: Session = Depends(get_db)):
    """Bulk-add resumes. kind=own (max 10 versions of the student's own) or kind=reference (other people's, benchmark only)."""
    u = _user(db, p.user_id)
    created, skipped = [], []
    for r in p.resumes:
        out = _add_one(db, u.id, r.label, r.target_role, r.text, r.kind)
        (created if "created" in out else skipped).append(out.get("created") or out["skipped"])
    sync_bank(db, u.id)
    audit(db, u.id, "resume_lab.import", {"n": len(p.resumes)}, {"created": len(created), "skipped": len(skipped)}, "low")
    return {"created": created, "skipped": skipped, "total_versions": len(_own_resumes(db, u.id)), "limit": MAX_VERSIONS,
            "total_references": len(_reference_resumes(db, u.id))}


def extract_pdf_text(data: bytes) -> str:
    """Best-effort PDF text. Tries poppler's pdftotext (handles multi-column layouts) and pypdf; keeps the one that parses to more bullets."""
    import io
    import shutil
    import subprocess
    import tempfile
    cands: List[str] = []
    if shutil.which("pdftotext"):
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                f.write(data)
                f.flush()
                cands.append(subprocess.run(["pdftotext", f.name, "-"], capture_output=True, timeout=30, check=True).stdout.decode("utf-8", "ignore"))
        except Exception:
            pass
    try:
        from pypdf import PdfReader
        cands.append("\n".join((pg.extract_text() or "") for pg in PdfReader(io.BytesIO(data)).pages))
    except Exception:
        pass
    cands = [c for c in cands if c and c.strip()]
    if not cands:
        raise HTTPException(422, "Could not read text from this PDF (is it a scanned image?). Paste the text instead.")
    return max(cands, key=lambda t: (len(parse_resume(t)["bullets"]), len(t)))


@router.post("/v1/resume-lab/import-file")
async def import_file(user_id: str = Form(...), kind: str = Form("own"), label: Optional[str] = Form(None),
                      target_role: Optional[str] = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload one PDF, DOCX or TXT resume. Mark kind=reference for resumes that are not yours."""
    u = _user(db, user_id)
    if kind not in ("own", "reference"):
        raise HTTPException(422, "kind must be own or reference")
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "File is larger than 5 MB")
    name = (file.filename or "resume").rsplit("/", 1)[-1]
    low = name.lower()
    if low.endswith(".pdf") or data[:4] == b"%PDF":
        text = extract_pdf_text(data)
    elif low.endswith(".docx"):
        import io
        from docx import Document
        text = "\n".join(pp.text for pp in Document(io.BytesIO(data)).paragraphs)
    elif low.endswith((".txt", ".md")):
        text = data.decode("utf-8", "ignore")
    else:
        raise HTTPException(422, "Upload a PDF, DOCX or TXT file")
    text = clean_pdf_text(text).strip()
    if len(text) < 80:
        raise HTTPException(422, "Not enough text found in this file")
    lab = (label or re.sub(r"\.[A-Za-z0-9]+$", "", name))[:80]
    out = _add_one(db, u.id, lab, target_role, text[:40000], kind)
    sync_bank(db, u.id)
    audit(db, u.id, "resume_lab.import_file", {"kind": kind}, {"created": "created" in out}, "low")
    return out


@router.get("/v1/resume-lab/references")
def references(user_id: str, db: Session = Depends(get_db)):
    """Reference resumes appear as anonymous benchmarks: label and statistics only, never their text."""
    u = _user(db, user_id)
    items = [_version_card(r) for r in _reference_resumes(db, u.id)]
    for it in items:
        it.pop("skills", None)
    return {"references": items, "count": len(items), "limit": MAX_REFERENCES}


@router.delete("/v1/resume-lab/references/{rid}")
def delete_reference(rid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    r = db.query(Resume).filter(Resume.id == rid, Resume.user_id == u.id, Resume.kind == "reference").first()
    if not r:
        raise HTTPException(404, "Reference not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


def _version_card(r: Resume) -> Dict[str, Any]:
    parsed = parse_resume(r.raw_text)
    st = bullet_stats(parsed["bullets"])
    return {"id": r.id, "label": r.label, "target_role": r.target_role, "kind": r.kind or "own", "words": len(r.raw_text.split()),
            "sections": [s for s in parsed["sections"] if s != "header"], "skills": r.skills or [],
            "overall_score": (r.score or {}).get("overall"), **st}


@router.get("/v1/resume-lab/library")
def library(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    items = [_version_card(r) for r in _own_resumes(db, u.id)]
    return {"versions": items, "count": len(items), "limit": MAX_VERSIONS}


# ---------------------------------------------------------------- insights (what your own best versions do)
@router.get("/v1/resume-lab/insights")
def insights(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rs = _own_resumes(db, u.id)
    refs = [_version_card(r) for r in _reference_resumes(db, u.id)]
    if len(rs) < 2 and not (rs and refs):
        return {"ready": False, "note": "Add at least 2 of your versions (or 1 plus some reference resumes) to compare.", "versions": len(rs)}
    cards = [_version_card(r) for r in rs]
    scored = [c for c in cards if c["overall_score"] is not None]
    scored.sort(key=lambda c: -c["overall_score"])
    k = max(1, len(scored) // 3) if scored else 0
    top, rest = scored[:k], scored[k:]

    def avg(group, key):
        return round(sum(g[key] for g in group) / len(group), 2) if group else None
    traits = {key: {"best": avg(top, key), "others": avg(rest, key)} for key in ("metric_ratio", "verb_ratio", "avg_words", "bullets")}
    tips: List[str] = []
    if top and rest:
        if traits["metric_ratio"]["best"] > traits["metric_ratio"]["others"] + 0.1:
            tips.append(f"Your strongest versions put numbers in {round(100 * traits['metric_ratio']['best'])}% of bullets "
                        f"vs {round(100 * traits['metric_ratio']['others'])}% elsewhere. Add real figures to the weaker ones.")
        if traits["verb_ratio"]["best"] > traits["verb_ratio"]["others"] + 0.1:
            tips.append("Your strongest versions start more bullets with action verbs. Rewrite weaker bullets to lead with what you did.")
    weak_total: Counter = Counter()
    for c in cards:
        weak_total.update(c["weak"])
    for w, n in weak_total.most_common(3):
        tips.append(f"\"{w}\" appears {n} time(s) across your versions; replace it with the specific action and result.")
    benchmark = None
    if refs and cards:
        def mean(group, key):
            vals = [g[key] for g in group if g["bullets"]]
            return round(sum(vals) / len(vals), 2) if vals else None
        benchmark = {"references": len(refs)}
        for key in ("metric_ratio", "verb_ratio", "avg_words", "bullets"):
            benchmark[key] = {"yours": mean(cards, key), "references": mean(refs, key)}
        y, r_ = benchmark["metric_ratio"]["yours"], benchmark["metric_ratio"]["references"]
        if y is not None and r_ is not None and r_ > y + 0.1:
            tips.append(f"Your reference resumes put numbers in {round(100 * r_)}% of bullets; yours average {round(100 * y)}%. Add real figures where you have them.")
        y, r_ = benchmark["verb_ratio"]["yours"], benchmark["verb_ratio"]["references"]
        if y is not None and r_ is not None and r_ > y + 0.1:
            tips.append("Your reference resumes lead more bullets with an action verb than yours do.")
        y, r_ = benchmark["bullets"]["yours"], benchmark["bullets"]["references"]
        if y is not None and r_ is not None and r_ >= 1.5 * max(y, 1):
            tips.append(f"Your reference resumes carry about {round(r_)} bullets; yours average {round(y)}. You may be underselling your work.")
    skill_sets = {c["label"]: {s.lower() for s in c["skills"]} for c in cards}
    allsk = Counter(s for v in skill_sets.values() for s in v)
    only_one = sorted(s for s, n in allsk.items() if n == 1)[:12]
    return {"ready": True, "versions": len(rs), "best_versions": [c["label"] for c in top], "traits": traits, "benchmark": benchmark,
            "common_skills": [s for s, n in allsk.most_common(10)], "skills_in_only_one_version": only_one,
            "tips": tips, "basis": "Counts computed from resume text. Reference resumes are used only as anonymous statistics; their wording is never reused."}


# ---------------------------------------------------------------- match + bullet search + tailor
class MatchBody(BaseModel):
    user_id: str
    job_text: Optional[str] = Field(default=None, max_length=30000)
    opportunity_id: Optional[str] = None


@router.post("/v1/resume-lab/match")
def match(p: MatchBody, db: Session = Depends(get_db)):
    """Rank the student's versions for a posting. Reports coverage and honest gaps; never edits anything."""
    u = _user(db, p.user_id)
    rs = _own_resumes(db, u.id)
    if not rs:
        raise HTTPException(409, "Import at least one resume first.")
    text = _job_text(db, u.id, p.job_text, p.opportunity_id)
    terms = job_terms(text)
    sync_bank(db, u.id)
    hits = rag.retrieve(db, u.id, text[:2000], k=30, source_types=[BULLET], min_score=0.0)
    sem: Counter = Counter()
    for h in hits:
        sem[h["meta"].get("source_id")] += h["score"]
    maxsem = max(sem.values()) if sem else 1.0
    ranked = []
    for r in rs:
        low = r.raw_text.lower()
        have = [t for t in terms if _contains(low, t)]
        cov = len(have) / len(terms) if terms else 0.0
        score = round(100 * (0.65 * cov + 0.35 * (sem.get(r.id, 0) / maxsem if maxsem else 0)))
        ranked.append({"resume_id": r.id, "label": r.label, "target_role": r.target_role, "fit": score,
                       "term_coverage": round(cov, 2), "terms_present": have, "terms_missing": [t for t in terms if t not in have]})
    ranked.sort(key=lambda x: -x["fit"])
    all_low = " ".join(r.raw_text.lower() for r in rs)
    gaps = [t for t in terms if not _contains(all_low, t)]
    elsewhere = {t: [x["label"] for x in ranked[1:] if t in x["terms_present"]] for t in ranked[0]["terms_missing"]} if ranked else {}
    return {"job_terms": terms, "ranking": ranked, "best": ranked[0] if ranked else None,
            "gaps_in_every_version": gaps,
            "present_in_other_versions": {t: v for t, v in elsewhere.items() if v},
            "note": "Gaps are terms the posting emphasises that none of your resumes mention. Add them only if they are true for you."}


class SearchBody(BaseModel):
    user_id: str
    query: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=6, ge=1, le=20)
    resume_id: Optional[str] = None


@router.post("/v1/resume-lab/bullets/search")
def search_bullets(p: SearchBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    sync_bank(db, u.id)
    where = (lambda m: m.get("source_id") == p.resume_id) if p.resume_id else None
    hits = rag.retrieve(db, u.id, p.query, k=p.k, source_types=[BULLET], where=where, min_score=0.0)
    return {"results": [{"bullet": h["content"], "from": h["meta"].get("label"), "resume_id": h["meta"].get("source_id"),
                         "section": h["meta"].get("section"), "score": h["score"]} for h in hits]}


class TailorBody(MatchBody):
    resume_id: Optional[str] = None      # base version; defaults to the best match
    max_bullets: int = Field(default=6, ge=1, le=12)


@router.post("/v1/resume-lab/tailor")
def tailor(p: TailorBody, db: Session = Depends(get_db)):
    """Suggest the best base version and the user's own strongest bullets for the posting. Selection only, no rewriting."""
    u = _user(db, p.user_id)
    m = match(MatchBody(user_id=p.user_id, job_text=p.job_text, opportunity_id=p.opportunity_id), db)
    rs = {r.id: r for r in _own_resumes(db, u.id)}
    base_id = p.resume_id or m["best"]["resume_id"]
    if base_id not in rs:
        raise HTTPException(404, "Resume not found")
    text = _job_text(db, u.id, p.job_text, p.opportunity_id)
    hits = rag.retrieve(db, u.id, text[:2000], k=p.max_bullets * 2, source_types=[BULLET], min_score=0.0)
    in_base = [h for h in hits if h["meta"].get("source_id") == base_id][:p.max_bullets]
    from_others = [h for h in hits if h["meta"].get("source_id") != base_id][:max(0, p.max_bullets - len(in_base)) or 3]
    fmt = lambda h: {"bullet": h["content"], "from": h["meta"].get("label"), "resume_id": h["meta"].get("source_id")}  # noqa: E731
    audit(db, u.id, "resume_lab.tailor", {"base": base_id}, {"gaps": len(m["gaps_in_every_version"])}, "low")
    return {"base_resume": {"id": base_id, "label": rs[base_id].label},
            "lead_with": [fmt(h) for h in in_base],
            "consider_from_other_versions": [fmt(h) for h in from_others],
            "gaps": m["gaps_in_every_version"],
            "note": "These are your own bullets, unchanged. Review before use; nothing is saved or submitted."}


# =====================================================================================================
# Review, coach, compare, builder, export, attach
# Thin layer over resume_lab_tools.py. Nothing here sends or submits anything.
# =====================================================================================================
MAX_BUILDS = 30
EXPORT_TYPES = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "pdf": "application/pdf", "txt": "text/plain; charset=utf-8"}


def _version(db: Session, uid: str, rid: str, allow_tailored: bool = True) -> Resume:
    """One of the student's own resumes (or one of their tailored builds). Reference resumes and other people's rows are 404."""
    kinds = ("own", "tailored") if allow_tailored else ("own",)
    r = db.query(Resume).filter(Resume.id == str(rid), Resume.user_id == str(uid)).first()
    if not r or (r.kind or "own") not in kinds:
        raise HTTPException(404, "Resume not found")
    return r


def _terms_for(db: Session, uid: str, job_text: Optional[str], opportunity_id: Optional[str]) -> Optional[List[str]]:
    if not (job_text and job_text.strip()) and not opportunity_id:
        return None
    return job_terms(_job_text(db, uid, job_text, opportunity_id)) or None


# ---------------------------------------------------------------- 1. review
class ReviewBody(MatchBody):
    resume_id: str


@router.post("/v1/resume-lab/review")
def review(p: ReviewBody, db: Session = Depends(get_db)):
    """ATS and quality review of one version. Deterministic; with a posting it also checks keyword coverage."""
    u = _user(db, p.user_id)
    r = _version(db, u.id, p.resume_id)
    terms = _terms_for(db, u.id, p.job_text, p.opportunity_id)
    out = T.review_resume(r.raw_text, terms)
    audit(db, u.id, "resume_lab.review", {"resume_id": r.id, "with_posting": bool(terms)}, {"overall": out["overall"]}, "low")
    return {"resume_id": r.id, "label": r.label, "kind": r.kind or "own", "job_terms": terms or [], **out}


# ---------------------------------------------------------------- 2. coach
class CoachBody(BaseModel):
    user_id: str
    resume_id: str
    bullet: Optional[str] = Field(default=None, max_length=600)    # coach one bullet the user pasted
    limit: int = Field(default=5, ge=1, le=10)
    rewrite: bool = False                                            # ask the model for rewrites (verified before they are shown)


_COACH_SYSTEM = ("You improve ONE resume bullet for clarity. Use ONLY the facts in the bullet. Never add numbers, tools, names, employers or results "
                 "that are not in it. If a number or result would help but is missing, put a bracketed placeholder such as [add number] so the student "
                 "fills in a true value. Start with a strong action verb, no first person, at most 28 words. "
                 "Return JSON: {\"rewrites\": [string, string]}.")


def _model_rewrites(bullet: str, issues: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Asks Groq for rewrites and keeps only those that pass verify_rewrite. Returns None when the model is unavailable."""
    try:
        from agent.groq_client import generate_json, groq_enabled
        if not groq_enabled():
            return None
        raw = generate_json(_COACH_SYSTEM, f"BULLET: {bullet}\nPROBLEMS: " + "; ".join(i["message"] for i in issues))
    except Exception:
        return None
    cands = [c for c in (raw.get("rewrites") if isinstance(raw, dict) else None) or [] if isinstance(c, str)][:3]
    good, rejected = [], 0
    for c in cands:
        ok, _ = T.verify_rewrite(bullet, c)
        if ok and c.strip() != bullet.strip():
            good.append({"text": c.strip(), "has_placeholder": bool(T._PLACEHOLDER.search(c))})
        else:
            rejected += 1
    return {"rewrites": good, "rejected": rejected}


@router.post("/v1/resume-lab/coach")
def coach(p: CoachBody, db: Session = Depends(get_db)):
    """Weakest bullets first, each with what is wrong and the questions only the student can answer.
    Optional model rewrites are shown only if they add no new numbers, tools or names."""
    u = _user(db, p.user_id)
    r = _version(db, u.id, p.resume_id)
    items = T.coach_bullets(r.raw_text, p.limit, only=p.bullet)
    status = "off"
    if p.rewrite:
        status = "unavailable"
        for it in items:
            if not it["issues"]:
                continue
            res = _model_rewrites(it["bullet"], it["issues"])
            if res is not None:
                status = "ok"
                it["rewrites"], it["rewrites_rejected"] = res["rewrites"], res["rejected"]
    audit(db, u.id, "resume_lab.coach", {"resume_id": r.id, "rewrite": p.rewrite}, {"bullets": len(items), "rewrite_status": status}, "low")
    return {"resume_id": r.id, "label": r.label, "bullets": items, "rewrite_status": status,
            "note": "Answer the questions with facts that are true for you. Placeholders like [add number] must be replaced or removed before use."}


# ---------------------------------------------------------------- 3. compare
class CompareBody(MatchBody):
    resume_a: str
    resume_b: str


@router.post("/v1/resume-lab/compare")
def compare(p: CompareBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if p.resume_a == p.resume_b:
        raise HTTPException(422, "Choose two different versions.")
    a, b = _version(db, u.id, p.resume_a), _version(db, u.id, p.resume_b)
    terms = _terms_for(db, u.id, p.job_text, p.opportunity_id)
    out = T.compare_texts(a.raw_text, b.raw_text, a.label, b.label, a.skills or [], b.skills or [], terms)
    out["a"]["id"], out["b"]["id"] = a.id, b.id
    return out


# ---------------------------------------------------------------- 4. builder
class BuildSuggest(MatchBody):
    base_resume_id: Optional[str] = None
    max_bullets: int = Field(default=14, ge=4, le=24)


def _own_texts(db: Session, uid: str) -> Dict[str, Any]:
    return {r.id: (r.label, r.raw_text) for r in _own_resumes(db, uid)}


@router.post("/v1/resume-lab/builds/suggest")
def build_suggest(p: BuildSuggest, db: Session = Depends(get_db)):
    """A draft for one posting: the base resume reordered and trimmed. Nothing is added, nothing is saved."""
    u = _user(db, p.user_id)
    own = _own_texts(db, u.id)
    if not own:
        raise HTTPException(409, "Import at least one resume first.")
    terms = _terms_for(db, u.id, p.job_text, p.opportunity_id)
    if not terms:
        raise HTTPException(422, "Provide job_text or opportunity_id so the draft can be aimed at a posting.")
    base_id = p.base_resume_id
    if base_id is None:
        base_id = match(MatchBody(user_id=u.id, job_text=p.job_text, opportunity_id=p.opportunity_id), db)["best"]["resume_id"]
    if base_id not in own:
        raise HTTPException(404, "Resume not found")
    out = T.suggest_build(own[base_id][1], base_id, own[base_id][0], own, terms, max_total=p.max_bullets)
    out["job_terms"] = terms
    return out


class BuildItem(BaseModel):
    type: str = "bullet"
    text: str = Field(max_length=1000)
    user_added: bool = False
    edited: bool = False


class BuildSection(BaseModel):
    name: str = Field(max_length=80)
    items: List[BuildItem] = Field(max_length=60)


class BuildBody(BaseModel):
    header: List[str] = Field(default=[], max_length=8)
    summary: Optional[str] = Field(default=None, max_length=1000)
    sections: List[BuildSection] = Field(max_length=12)
    skills: List[str] = Field(default=[], max_length=80)
    user_added_skills: List[str] = Field(default=[], max_length=40)


class BuildCreate(BaseModel):
    user_id: str
    label: str = Field(min_length=1, max_length=80)
    base_resume_id: Optional[str] = None
    target_role: Optional[str] = Field(default=None, max_length=120)
    opportunity_id: Optional[str] = None
    build: BuildBody


def _clean_build(db: Session, uid: str, body: BuildBody) -> Dict[str, Any]:
    own = _own_texts(db, uid)
    if not own:
        raise HTTPException(409, "Import at least one resume first.")
    clean, errors = T.validate_build(body.model_dump(), own)
    if errors:
        raise HTTPException(422, {"message": "Some items are not yours yet.", "errors": errors})
    return clean


def _build_out(r: Resume, full: bool = False) -> Dict[str, Any]:
    b = r.build or {}
    out = {"id": r.id, "label": r.label, "target_role": r.target_role, "base_resume_id": b.get("base_resume_id"), "provenance": b.get("provenance", {}),
           "created_at": r.created_at.isoformat() if r.created_at else None, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
           "words": len((r.raw_text or "").split())}
    if full:
        out["build"] = {k: b.get(k) for k in ("header", "summary", "sections", "skills")}
    return out


@router.post("/v1/resume-lab/builds")
def build_create(p: BuildCreate, db: Session = Depends(get_db)):
    """Saves a tailored resume. Every bullet must come from one of your own resumes or be marked as written by you."""
    u = _user(db, p.user_id)
    existing = db.query(Resume).filter(Resume.user_id == u.id, Resume.kind == "tailored").all()
    if len(existing) >= MAX_BUILDS:
        raise HTTPException(409, f"You already have {MAX_BUILDS} tailored resumes. Delete one first.")
    if p.label.strip().lower() in {x.label.strip().lower() for x in existing + _own_resumes(db, u.id)}:
        raise HTTPException(409, "That label is already used. Choose another.")
    if p.base_resume_id:
        _version(db, u.id, p.base_resume_id, allow_tailored=False)
    clean = _clean_build(db, u.id, p.build)
    text = T.render_text(T.build_to_struct(clean))
    data = offline_analysis(text, p.target_role)
    meta = {**clean, "base_resume_id": p.base_resume_id, "opportunity_id": p.opportunity_id}
    row = Resume(user_id=u.id, label=p.label.strip(), target_role=p.target_role, raw_text=text, skills=[s["text"] for s in clean["skills"]],
                 summary="", suggested_bullets=[], score=data["score"], kind="tailored", build=meta)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, u.id, "resume_lab.build_create", {"resume_id": row.id, "base": p.base_resume_id}, {"provenance": clean["provenance"]}, "low")
    return {**_build_out(row, full=True), "review_overall": T.review_resume(text)["overall"]}


@router.get("/v1/resume-lab/builds")
def build_list(user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    rows = db.query(Resume).filter(Resume.user_id == u.id, Resume.kind == "tailored").order_by(Resume.created_at.desc()).all()
    used = Counter(a.resume_id for a in db.query(Application).filter(Application.user_id == u.id, Application.resume_id.isnot(None)).all())
    return {"builds": [{**_build_out(r), "attached_to": used.get(r.id, 0)} for r in rows], "count": len(rows), "limit": MAX_BUILDS}


def _own_build(db: Session, uid: str, bid: str) -> Resume:
    r = db.query(Resume).filter(Resume.id == str(bid), Resume.user_id == str(uid), Resume.kind == "tailored").first()
    if not r:
        raise HTTPException(404, "Tailored resume not found")
    return r


@router.get("/v1/resume-lab/builds/{bid}")
def build_get(bid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    return _build_out(_own_build(db, u.id, bid), full=True)


class BuildUpdate(BaseModel):
    user_id: str
    label: Optional[str] = Field(default=None, min_length=1, max_length=80)
    build: BuildBody


@router.put("/v1/resume-lab/builds/{bid}")
def build_update(bid: str, p: BuildUpdate, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    r = _own_build(db, u.id, bid)
    if p.label and p.label.strip().lower() != r.label.strip().lower():
        taken = {x.label.strip().lower() for x in db.query(Resume).filter(Resume.user_id == u.id, Resume.id != r.id, or_(Resume.kind.is_(None), Resume.kind.in_(("own", "tailored")))).all()}
        if p.label.strip().lower() in taken:
            raise HTTPException(409, "That label is already used. Choose another.")
        r.label = p.label.strip()
    clean = _clean_build(db, u.id, p.build)
    r.raw_text = T.render_text(T.build_to_struct(clean))
    r.skills = [s["text"] for s in clean["skills"]]
    r.score = offline_analysis(r.raw_text, r.target_role)["score"]
    r.build = {**clean, "base_resume_id": (r.build or {}).get("base_resume_id"), "opportunity_id": (r.build or {}).get("opportunity_id")}
    for a in db.query(Application).filter(Application.user_id == u.id, Application.resume_id == r.id).all():
        a.resume_bullets = [it["text"] for s in clean["sections"] for it in s["items"] if it["type"] == "bullet"]
    db.commit()
    db.refresh(r)
    return _build_out(r, full=True)


@router.delete("/v1/resume-lab/builds/{bid}")
def build_delete(bid: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    r = _own_build(db, u.id, bid)
    detached = 0
    for a in db.query(Application).filter(Application.user_id == u.id, Application.resume_id == r.id).all():
        a.resume_id, a.tailored_at, a.resume_bullets = None, None, []
        detached += 1
    db.delete(r)
    db.commit()
    return {"deleted": bid, "detached_applications": detached}


# ---------------------------------------------------------------- 5. export
def _struct_for(r: Resume) -> Dict[str, Any]:
    if (r.kind or "own") == "tailored" and r.build:
        return T.build_to_struct(r.build)
    return T.to_structure(r.raw_text)


@router.get("/v1/resume-lab/resumes/{rid}/export")
def export(rid: str, user_id: str, format: str = "docx", db: Session = Depends(get_db)):
    """Download one of your versions as DOCX, PDF or plain text. Reference resumes can never be exported."""
    u = _user(db, user_id)
    fmt = format.lower()
    if fmt not in EXPORT_TYPES:
        raise HTTPException(422, "format must be docx, pdf or txt")
    r = _version(db, u.id, rid)
    st = _struct_for(r)
    headers = {"Content-Disposition": f'attachment; filename="{T.safe_filename(r.label, fmt)}"', "Cache-Control": "no-store"}
    try:
        if fmt == "docx":
            body = T.render_docx(st)
        elif fmt == "pdf":
            body, warns = T.render_pdf(st)
            if warns:
                headers["X-Export-Warnings"] = "; ".join(warns)[:300]
        else:
            body = T.render_text(st).encode("utf-8")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    audit(db, u.id, "resume_lab.export", {"resume_id": r.id, "format": fmt}, {"bytes": len(body)}, "low")
    return Response(content=body, media_type=EXPORT_TYPES[fmt], headers=headers)


# ---------------------------------------------------------------- 6. attach to an application
class AttachBody(BaseModel):
    user_id: str
    application_id: str
    resume_id: str


def _attachment_row(a: Application, r: Optional[Resume]) -> Dict[str, Any]:
    return {"application_id": a.id, "company": a.company, "role": a.role, "status": a.status,
            "resume_id": a.resume_id if r else None, "resume_label": r.label if r else None, "resume_kind": (r.kind or "own") if r else None,
            "tailored_at": a.tailored_at.isoformat() if a.tailored_at else None}


@router.post("/v1/resume-lab/attach")
def attach(p: AttachBody, db: Session = Depends(get_db)):
    """Links a version to an application. Records which resume you intend to submit; it submits nothing."""
    u = _user(db, p.user_id)
    a = db.query(Application).filter(Application.id == p.application_id, Application.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    r = _version(db, u.id, p.resume_id)
    a.resume_id = r.id
    if (r.kind or "own") == "tailored":
        from datetime import datetime
        a.tailored_at = datetime.utcnow()
        a.resume_bullets = [it["text"] for s in (r.build or {}).get("sections", []) for it in s["items"] if it["type"] == "bullet"]
    db.commit()
    audit(db, u.id, "resume_lab.attach", {"application_id": a.id, "resume_id": r.id}, {"kind": r.kind or "own"}, "low")
    return _attachment_row(a, r)


@router.delete("/v1/resume-lab/attach/{application_id}")
def detach(application_id: str, user_id: str, db: Session = Depends(get_db)):
    u = _user(db, user_id)
    a = db.query(Application).filter(Application.id == application_id, Application.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "Application not found")
    a.resume_id, a.tailored_at = None, None
    db.commit()
    return _attachment_row(a, None)


@router.get("/v1/resume-lab/attachments")
def attachments(user_id: str, db: Session = Depends(get_db)):
    """Every application with the resume version attached to it, so the page can show and change it."""
    u = _user(db, user_id)
    res = {r.id: r for r in db.query(Resume).filter(Resume.user_id == u.id, or_(Resume.kind.is_(None), Resume.kind.in_(("own", "tailored")))).all()}
    apps = db.query(Application).filter(Application.user_id == u.id).order_by(Application.deadline.is_(None), Application.deadline).all()
    return {"applications": [_attachment_row(a, res.get(a.resume_id)) for a in apps]}
