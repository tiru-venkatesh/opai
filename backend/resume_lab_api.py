"""OPAI Resume Lab: learn from the student's OWN resume versions (up to 10) and retrieve from them.

Everything here is grounded in text the user supplied:
  * the "bullet bank" is the user's real bullets, indexed one per chunk (RAG);
  * match/tailor only ever SELECT existing bullets and report gaps; nothing is invented, no skill is added;
  * insights compare the user's strongest versions with the rest using deterministic counts.
Nothing is submitted or sent anywhere.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import rag_service as rag
from audit.logger import record as audit
from database import Application, DocumentChunk, Opportunity, Resume, User, get_db

from resume_lab_core import (  # noqa: F401  (pure logic lives in resume_lab_core so it can be tested without FastAPI)
    RENDERERS, _BULLET_START, _METRIC, _SECTION, _STOP, _TERM_RE, _VERBS, _WEAK, _contains, _h, _norm_b, ats_review,
    build_tailored, bullet_stats, coach_bullet, compare_versions, doc_bullets, parse_resume, render_txt, rewrite_is_grounded,
)

router = APIRouter()

MAX_VERSIONS = 10
BULLET = "resume_bullet"


def _user(db: Session, uid: str) -> User:
    u = db.query(User).filter(User.id == str(uid)).first()
    if not u:
        raise HTTPException(404, "User not found")
    return u




def _own_resumes(db: Session, uid: str) -> List[Resume]:
    return db.query(Resume).filter(Resume.user_id == str(uid)).order_by(Resume.created_at).all()


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


def _analyze(text: str, target_role: Optional[str]) -> Dict[str, Any]:
    data = None
    try:
        from agent.groq_client import groq_enabled
        if groq_enabled():
            from agent_service import _analyze_resume_text
            data = _analyze_resume_text(text, target_role)
    except Exception:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("score"), dict):
        data = offline_analysis(text, target_role)
    return data


def _create(db: Session, uid: str, label: str, target_role: Optional[str], text: str) -> Resume:
    data = _analyze(text, target_role)
    row = Resume(user_id=str(uid), label=label, target_role=target_role, raw_text=text, skills=data.get("skills", []),
                 summary=data.get("summary", ""), suggested_bullets=data.get("suggested_bullets", []), score=data["score"])
    db.add(row)
    db.commit()
    db.refresh(row)
    rag.index_resume(db, uid, row.id, text, label=label, target_role=target_role or "")
    return row


# ---------------------------------------------------------------- import / library
class ResumeIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    target_role: Optional[str] = Field(default=None, max_length=120)
    text: str = Field(min_length=80, max_length=40000)


class ImportBody(BaseModel):
    user_id: str
    resumes: List[ResumeIn] = Field(min_length=1, max_length=MAX_VERSIONS)


@router.post("/v1/resume-lab/import")
def import_resumes(p: ImportBody, db: Session = Depends(get_db)):
    """Bulk-add resume versions (max 10 per student). Exact duplicates are skipped, not overwritten."""
    u = _user(db, p.user_id)
    existing = _own_resumes(db, u.id)
    seen = {_h(r.raw_text) for r in existing}
    labels = {r.label.strip().lower() for r in existing}
    created, skipped = [], []
    for r in p.resumes:
        if _h(r.text) in seen:
            skipped.append({"label": r.label, "reason": "identical text already in your library"})
            continue
        if r.label.strip().lower() in labels:
            skipped.append({"label": r.label, "reason": "label already used; rename it"})
            continue
        if len(existing) + len(created) >= MAX_VERSIONS:
            skipped.append({"label": r.label, "reason": f"library is full ({MAX_VERSIONS} versions); delete one first"})
            continue
        row = _create(db, u.id, r.label.strip(), r.target_role, r.text)
        seen.add(_h(r.text))
        labels.add(r.label.strip().lower())
        created.append({"id": row.id, "label": row.label})
    sync_bank(db, u.id)
    audit(db, u.id, "resume_lab.import", {"n": len(p.resumes)}, {"created": len(created), "skipped": len(skipped)}, "low")
    return {"created": created, "skipped": skipped, "total_versions": len(existing) + len(created), "limit": MAX_VERSIONS}


@router.post("/v1/resume-lab/import-files")
async def import_resume_files(user_id: str = Form(...), target_role: Optional[str] = Form(None),
                              files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Upload PDF / DOCX / TXT resumes (several at once). Same rules as /import: exact duplicates and a full
    library are skipped with a reason, and every bullet is indexed into the bullet bank."""
    import rag_api
    u = _user(db, user_id)
    existing = _own_resumes(db, u.id)
    seen = {_h(r.raw_text) for r in existing}
    labels = {r.label.strip().lower() for r in existing}
    created, skipped = [], []
    for f in files[:MAX_VERSIONS * 2]:
        name = f.filename or "resume"
        label = re.sub(r"\.[A-Za-z0-9]+$", "", name).strip()[:80] or "Resume"
        data = await f.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            skipped.append({"label": name, "reason": "file is larger than 5 MB"})
            continue
        try:
            text = "\n".join(pg["text"] for pg in rag_api.parse_file(name, data)).strip()
        except rag_api.ParseError as e:
            skipped.append({"label": name, "reason": str(e)})
            continue
        if len(text) < 80:
            skipped.append({"label": name, "reason": "no readable text (a scanned image PDF?)"})
            continue
        if _h(text) in seen:
            skipped.append({"label": name, "reason": "identical text already in your library"})
            continue
        if label.lower() in labels:
            label = f"{label[:70]} ({len(existing) + len(created) + 1})"
        if len(existing) + len(created) >= MAX_VERSIONS:
            skipped.append({"label": name, "reason": f"library is full ({MAX_VERSIONS} versions); delete one first"})
            continue
        row = _create(db, u.id, label, (target_role or "").strip()[:120] or None, text[:40000])
        seen.add(_h(text))
        labels.add(label.lower())
        created.append({"id": row.id, "label": row.label})
    sync_bank(db, u.id)
    audit(db, u.id, "resume_lab.import_files", {"n": len(files)}, {"created": len(created), "skipped": len(skipped)}, "low")
    return {"created": created, "skipped": skipped, "total_versions": len(existing) + len(created), "limit": MAX_VERSIONS}


def _version_card(r: Resume) -> Dict[str, Any]:
    parsed = parse_resume(r.raw_text)
    st = bullet_stats(parsed["bullets"])
    return {"id": r.id, "label": r.label, "target_role": r.target_role, "words": len(r.raw_text.split()),
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
    if len(rs) < 2:
        return {"ready": False, "note": "Add at least 2 versions to compare. Import your resumes first.", "versions": len(rs)}
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
    skill_sets = {c["label"]: {s.lower() for s in c["skills"]} for c in cards}
    allsk = Counter(s for v in skill_sets.values() for s in v)
    only_one = sorted(s for s, n in allsk.items() if n == 1)[:12]
    return {"ready": True, "versions": len(rs), "best_versions": [c["label"] for c in top], "traits": traits,
            "common_skills": [s for s, n in allsk.most_common(10)], "skills_in_only_one_version": only_one,
            "tips": tips, "basis": "Counts computed from your own resume text; scores come from the existing resume analyzer."}


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


# ====================================================================================================
# Review / coach / compare / tailored build / export / attach
# Everything below is derived from the student's own text. Nothing is sent or submitted anywhere.
# ====================================================================================================
def _resume(db: Session, uid: str, rid: str) -> Resume:
    r = db.query(Resume).filter(Resume.id == str(rid), Resume.user_id == str(uid)).first()
    if not r:
        raise HTTPException(404, "Resume not found")
    return r


def _opt_terms(db: Session, uid: str, job_text: Optional[str], opportunity_id: Optional[str]) -> Optional[List[str]]:
    if (job_text and job_text.strip()) or opportunity_id:
        return job_terms(_job_text(db, uid, job_text, opportunity_id)) or None
    return None


class ReviewBody(MatchBody):
    resume_id: str


@router.post("/v1/resume-lab/review")
def review(p: ReviewBody, db: Session = Depends(get_db)):
    """ATS-readiness checklist for one of your versions, optionally against a posting's keywords."""
    u = _user(db, p.user_id)
    r = _resume(db, u.id, p.resume_id)
    out = ats_review(r.raw_text, _opt_terms(db, u.id, p.job_text, p.opportunity_id))
    out.update({"resume_id": r.id, "label": r.label})
    audit(db, u.id, "resume_lab.review", {"resume": r.id}, {"score": out["score"]}, "low")
    return out


class CoachBody(MatchBody):
    bullet: str = Field(min_length=3, max_length=600)
    facts: str = Field(default="", max_length=600)      # extra TRUE details the student supplies (e.g. "200 students used it")
    use_ai: bool = True


def _ai_rewrite(original: str, facts: str) -> Optional[str]:
    try:
        from agent.groq_client import get_client, groq_enabled
        if not groq_enabled():
            return None
        r = get_client().chat.completions.create(
            model=os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b"), temperature=0.2, max_tokens=120,
            messages=[{"role": "system", "content": "Rewrite ONE resume bullet to be clearer. Use ONLY facts present in ORIGINAL or FACTS. "
                       "Do not add numbers, tools, employers, people or outcomes. Start with an action verb. One line, at most 25 words. "
                       "Reply with the bullet text only."},
                      {"role": "user", "content": f"ORIGINAL: {original}\nFACTS: {facts or 'none'}"}])
        out = (r.choices[0].message.content or "").strip().strip('"').lstrip("-* ").strip()
        return out or None
    except Exception:
        return None


@router.post("/v1/resume-lab/coach")
def coach(p: CoachBody, db: Session = Depends(get_db)):
    """Diagnose one bullet and ask the student for the missing TRUE details. An AI rewrite is shown only if it adds nothing new."""
    u = _user(db, p.user_id)
    terms = _opt_terms(db, u.id, p.job_text, p.opportunity_id)
    out = coach_bullet(p.bullet, terms)
    out["rewrite"], out["rewrite_note"] = None, None
    if p.use_ai and not out["ok"]:
        cand = _ai_rewrite(out["bullet"], p.facts)
        if cand:
            try:
                from opportunities_api import TECH_TERMS
                known = list(TECH_TERMS)
            except Exception:
                known = []
            ok, probs = rewrite_is_grounded(out["bullet"], cand, p.facts, known + (terms or []))
            if ok:
                out["rewrite"] = cand
                out["rewrite_note"] = "Suggestion only. It uses nothing beyond what you wrote; check it is accurate before using it."
            else:
                out["rewrite_note"] = "An AI rewrite was discarded because it " + "; ".join(probs) + "."
    audit(db, u.id, "resume_lab.coach", {}, {"issues": len(out["issues"]), "rewrite": bool(out["rewrite"])}, "low")
    return out


class CompareBody(MatchBody):
    a_id: str
    b_id: str


@router.post("/v1/resume-lab/compare")
def compare(p: CompareBody, db: Session = Depends(get_db)):
    u = _user(db, p.user_id)
    if p.a_id == p.b_id:
        raise HTTPException(422, "Pick two different versions")
    a, b = _resume(db, u.id, p.a_id), _resume(db, u.id, p.b_id)
    out = compare_versions(a.raw_text, b.raw_text, _opt_terms(db, u.id, p.job_text, p.opportunity_id))
    out["a"], out["b"] = {"id": a.id, "label": a.label}, {"id": b.id, "label": b.label}
    return out


class ExtraIn(BaseModel):
    text: str = Field(min_length=5, max_length=600)
    section: Optional[str] = Field(default=None, max_length=40)


class BuildBody(MatchBody):
    resume_id: str
    exclude: List[str] = Field(default_factory=list, max_length=40)
    extras: List[ExtraIn] = Field(default_factory=list, max_length=12)
    reorder: bool = True
    max_per_group: Optional[int] = Field(default=None, ge=1, le=12)


def _build(db: Session, p: BuildBody):
    u = _user(db, p.user_id)
    base = _resume(db, u.id, p.resume_id)
    if p.extras:  # extras must be the student's own bullets, verbatim, from any of their versions
        own = {_norm_b(b["text"]) for r in _own_resumes(db, u.id) for b in parse_resume(r.raw_text)["bullets"]}
        bad = [e.text for e in p.extras if _norm_b(e.text) not in own]
        if bad:
            raise HTTPException(422, "These are not bullets from your own versions, so they were not added: " + " | ".join(bad[:3]))
    terms = _opt_terms(db, u.id, p.job_text, p.opportunity_id)
    doc = build_tailored(base.raw_text, p.exclude, [e.model_dump() for e in p.extras], terms if p.reorder else None, p.max_per_group)
    return u, base, doc, terms


@router.post("/v1/resume-lab/build")
def build(p: BuildBody, db: Session = Depends(get_db)):
    """Preview a tailored resume: your base version with bullets re-ordered or removed, plus your own bullets from other versions."""
    u, base, doc, terms = _build(db, p)
    return {"base": {"id": base.id, "label": base.label}, "sections": doc["sections"], "dropped": doc["dropped"], "added": doc["added"],
            "bullets": len(doc_bullets(doc)), "text": render_txt(doc),
            "review": ats_review(render_txt(doc), terms),
            "note": "Your wording is unchanged. Review before use; nothing is saved or sent."}


class ExportBody(BuildBody):
    format: str = Field(default="docx", pattern="^(txt|docx|pdf)$")


@router.post("/v1/resume-lab/export")
def export(p: ExportBody, db: Session = Depends(get_db)):
    u, base, doc, _ = _build(db, p)
    mime, fn = RENDERERS[p.format]
    try:
        data = fn(doc)
    except ImportError:
        raise HTTPException(501, f"{p.format.upper()} export needs an extra package on the server (python-docx / reportlab)")
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", base.label).strip() or "resume"
    audit(db, u.id, "resume_lab.export", {"resume": base.id, "format": p.format}, {"bytes": len(data)}, "low")
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="Tailored - {safe}.{p.format}"'})


class AttachBody(BuildBody):
    application_id: str


@router.post("/v1/resume-lab/attach")
def attach(p: AttachBody, db: Session = Depends(get_db)):
    """Save the tailored resume as a version and link it to one application. Does not submit anything."""
    u, base, doc, _ = _build(db, p)
    app = db.query(Application).filter(Application.id == str(p.application_id), Application.user_id == u.id).first()
    if not app:
        raise HTTPException(404, "Application not found")
    text = render_txt(doc)
    label = f"Tailored: {app.company} - {app.role}"[:80]
    prev = db.query(Resume).filter(Resume.id == app.resume_id, Resume.user_id == u.id).first() if app.resume_id else None
    if prev and (prev.label or "").startswith("Tailored: "):
        data = _analyze(text, app.role)
        prev.raw_text, prev.label, prev.target_role = text, label, app.role
        prev.skills, prev.summary, prev.score = data.get("skills", []), data.get("summary", ""), data["score"]
        db.commit()
        rag.delete_source(db, u.id, rag.RESUME, prev.id)
        rag.index_resume(db, u.id, prev.id, text, label=label, target_role=app.role or "")
        row, replaced = prev, True
    else:
        existing = _own_resumes(db, u.id)
        if len(existing) >= MAX_VERSIONS:
            raise HTTPException(409, f"Your library is full ({MAX_VERSIONS} versions). Delete one, then attach again.")
        taken = {r.label.strip().lower() for r in existing}
        lab, n = label, 2
        while lab.strip().lower() in taken:
            lab = f"{label[:74]} ({n})"
            n += 1
        row, replaced = _create(db, u.id, lab, app.role, text), False
    app.resume_id, app.tailored_at = row.id, datetime.utcnow()
    app.resume_bullets = doc_bullets(doc)[:6]
    db.commit()
    sync_bank(db, u.id)
    audit(db, u.id, "resume_lab.attach", {"application": app.id, "base": base.id}, {"resume": row.id, "replaced": replaced}, "low")
    return {"resume_id": row.id, "label": row.label, "application_id": app.id, "replaced_previous": replaced,
            "bullets": len(doc_bullets(doc)), "added_from_other_versions": len(doc["added"]), "note": "Saved to your library and linked to this application. Nothing was submitted."}
