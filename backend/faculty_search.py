"""RAG-style search over IIT_Faculty_Dataset.csv: BM25 + embedding similarity, fused.

The dataset was scraped by a third party, so every result is labelled 'dataset, unverified'. Adding a professor
creates a normal Contact (email_verification='unverified'); the existing research-brief -> draft -> Outbox approval
flow still applies before anything is emailed. Nothing here sends or fetches anything.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import threading
from typing import Any, Dict, List, Optional

import rag_service as rag

CSV_PATH = os.path.join(os.path.dirname(__file__), "IIT_Faculty_Dataset.csv")
_DOMAIN = {"iitd": "IIT Delhi", "iith": "IIT Hyderabad", "iitkgp": "IIT Kharagpur", "iitrpr": "IIT Ropar", "iitr": "IIT Roorkee", "iitism": "IIT (ISM) Dhanbad"}
_COLLEGE = {"iit-d": "IIT Delhi", "iit-hyderabad": "IIT Hyderabad", "iit-kharagpur": "IIT Kharagpur", "iit-ropar": "IIT Ropar", "iit-r": "IIT Roorkee", "iit (ism) dhanbad": "IIT (ISM) Dhanbad"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.Lock()
_cache: Dict[str, Any] = {}


def _institute(email: str, college: str) -> str:
    dom = email.split("@")[-1].lower().strip()
    for part in dom.split("."):
        if part in _DOMAIN:
            return _DOMAIN[part]
    return _COLLEGE.get((college or "").strip().lower(), (college or "").strip() or "IIT")


def load_rows() -> List[Dict[str, Any]]:
    """Cleaned faculty rows. The CSV has a header banner and some junk rows; rows without a valid email and name are dropped."""
    if "rows" in _cache:
        return _cache["rows"]
    try:
        raw = open(CSV_PATH, encoding="utf-8", errors="replace").read()
    except OSError:
        _cache["rows"] = []
        return []
    start = raw.find("college,dept,email")
    rows, seen = [], set()
    for r in csv.DictReader(io.StringIO(raw[start:] if start >= 0 else raw)):
        email = (r.get("email") or "").strip().lower()
        name = re.sub(r"\s+", " ", (r.get("name") or "")).strip()
        if not _EMAIL.match(email) or not name or email in seen:
            continue
        seen.add(email)
        on_leave = bool(re.search(r"on\s+leave", name, re.I))
        name = re.sub(r"\(.*?\)", "", name).strip(" ,")
        areas_raw = (r.get("research_areas") or "").strip()
        areas = [a.strip(" .") for a in re.split(r",|;|\band\b", areas_raw) if len(a.strip(" .")) > 2][:15]
        site = (r.get("website") or "").strip()
        rows.append({"id": hashlib.sha1(email.encode()).hexdigest()[:12], "name": name, "email": email,
                     "institute": _institute(email, r.get("college") or ""), "department": (r.get("dept") or "").strip(),
                     "research_areas": areas, "research_text": areas_raw, "designation": (r.get("position") or "").strip(), "website": site if site.startswith("http") else None, "on_leave": on_leave})
    _cache["rows"] = rows
    return rows


def _doc_text(r: Dict[str, Any]) -> str:
    return f"{r['research_text']} {r['department']} {r['institute']}"


def _index():
    with _lock:
        if "idx" in _cache:
            return _cache["idx"]
        rows = load_rows()
        toks = [rag.tokenize(_doc_text(r)) for r in rows]
        try:
            vecs, tag = rag.embed_texts([_doc_text(r) or r["name"] for r in rows]) if rows else ([], "none")
        except Exception:
            vecs, tag = [], "none"
        _cache["idx"] = {"toks": toks, "vecs": vecs, "tag": tag}
        return _cache["idx"]


def institutes() -> List[str]:
    return sorted({r["institute"] for r in load_rows()})


def search(query: str, institute: Optional[str] = None, limit: int = 10, include_on_leave: bool = False,
           exclude_emails: Optional[set] = None) -> List[Dict[str, Any]]:
    rows = load_rows()
    q = (query or "").strip()
    if not rows or not q:
        return []
    idx = _index()
    qt = rag.tokenize(q)
    bm = rag.bm25_scores(qt, idx["toks"]) if qt else [0.0] * len(rows)
    bmax = max(bm) or 1.0
    cos = [0.0] * len(rows)
    if idx["vecs"]:
        try:
            qv = rag.embed_one(q)
            cos = [max(0.0, rag.cosine_similarity(qv, v)) for v in idx["vecs"]]
        except Exception:
            pass
    cmax = max(cos) or 1.0
    qset = set(qt)
    out = []
    for i, r in enumerate(rows):
        if institute and r["institute"].lower() != institute.lower():
            continue
        if r["on_leave"] and not include_on_leave:
            continue
        if exclude_emails and r["email"] in exclude_emails:
            continue
        matched = sorted(qset & set(idx["toks"][i]))
        score = 0.65 * (bm[i] / bmax) + 0.35 * (cos[i] / cmax)
        if not matched and bm[i] <= 0:
            score *= 0.4            # embedding-only hits are weaker evidence
        if score < 0.12:
            continue
        out.append({**{k: r[k] for k in ("id", "name", "institute", "department", "designation", "research_areas", "website", "email", "on_leave")},
                    "score": round(score * 100), "matched_terms": matched[:8],
                    "why": (("Research areas mention: " if r["research_areas"] else "Department matches: ") + ", ".join(matched[:5])) if matched else "Related by meaning to your query (no exact keyword match).",
                    "data_status": "from scraped dataset, unverified"})
    out.sort(key=lambda x: -x["score"])
    return out[:max(1, min(limit, 60))]


def browse(institute: Optional[str] = None, limit: int = 20, include_on_leave: bool = False,
           exclude_emails: Optional[set] = None) -> Dict[str, Any]:
    """No query: list the dataset (optionally one institute), A-Z, so the data is always visible."""
    rows = [r for r in load_rows() if (not institute or r["institute"].lower() == institute.lower())
            and (include_on_leave or not r["on_leave"]) and not (exclude_emails and r["email"] in exclude_emails)]
    rows.sort(key=lambda r: (r["institute"], r["name"].lower()))
    items = [{**{k: r[k] for k in ("id", "name", "institute", "department", "designation", "research_areas", "website", "email", "on_leave")},
              "score": None, "matched_terms": [], "why": "Listed in the dataset. Type a research area to rank by fit.",
              "data_status": "from scraped dataset, unverified"} for r in rows[:max(1, min(limit, 100))]]
    return {"items": items, "total": len(rows)}


def get(faculty_id: str) -> Optional[Dict[str, Any]]:
    return next((r for r in load_rows() if r["id"] == faculty_id), None)
