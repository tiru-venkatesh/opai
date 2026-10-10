"""Deterministic parsing for the Opportunities pipeline.

Everything here works on text or URLs the USER supplied. Nothing in this module makes a network request,
and nothing touches LinkedIn: a pasted LinkedIn link is only normalised and stored as a reference the user
can open themselves. Every extracted field carries a confidence so the review card can ask the user to
confirm anything that was guessed.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

SKILL_VOCAB = [
    "python", "java", "c++", "c#", "javascript", "typescript", "go", "rust", "sql", "react", "node.js", "nodejs",
    "fastapi", "django", "flask", "docker", "kubernetes", "aws", "gcp", "azure", "git", "linux", "pytorch",
    "tensorflow", "scikit-learn", "pandas", "numpy", "machine learning", "deep learning", "nlp", "computer vision",
    "llm", "rag", "langchain", "agents", "data structures", "algorithms", "html", "css", "mongodb", "postgresql",
    "rest api", "graphql", "figma", "flutter", "android", "ios", "statistics", "reinforcement learning",
]

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "trk", "trackingid", "refid",
             "midtoken", "midsig", "eid", "otptoken", "ref", "src", "source"}


# ------------------------------------------------------------------ URLs
def normalize_url(url: Optional[str]) -> Dict[str, Optional[str]]:
    """Returns {url, source_type, job_id}. Rejects non-http(s) schemes. Never fetches anything."""
    raw = (url or "").strip()
    if not raw:
        return {"url": None, "source_type": None, "job_id": None}
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.netloc:
        return {"url": None, "source_type": None, "job_id": None}
    host = p.netloc.lower().split("@")[-1]
    if host.endswith("linkedin.com"):
        m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", p.path) or re.search(r"/comm/jobs/view/(\d{6,})", p.path)
        job_id = m.group(1) if m else (parse_qs(p.query).get("currentJobId") or [None])[0]
        if job_id and str(job_id).isdigit():
            return {"url": f"https://www.linkedin.com/jobs/view/{job_id}/", "source_type": "linkedin_user_saved",
                    "job_id": str(job_id)}
        return {"url": f"https://www.linkedin.com{p.path}".rstrip("/") or None, "source_type": "linkedin_user_saved",
                "job_id": None}
    q = [(k, v) for k, v in parse_qs(p.query, keep_blank_values=False).items() if k.lower() not in _TRACKING]
    qs = "&".join(f"{k}={v[0]}" for k, v in q)
    clean = f"{p.scheme}://{p.netloc}{p.path}" + (f"?{qs}" if qs else "")
    return {"url": clean[:500], "source_type": "career_page", "job_id": None}


# ------------------------------------------------------------------ dates
def _mk(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date_text(s: str, today: Optional[date] = None) -> Optional[date]:
    today = today or date.today()
    s = s.strip().lower()
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", s)
    if m:
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+([a-z]{3,9})\.?,?(?:[\s\-/]+(20\d{2}))?\b", s)
    if m and m[2][:3] in _MONTHS:
        y = int(m[3]) if m[3] else today.year
        d = _mk(y, _MONTHS[m[2][:3]], int(m[1]))
        if d and not m[3] and d < today:
            d = _mk(y + 1, _MONTHS[m[2][:3]], int(m[1]))
        return d
    m = re.search(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(20\d{2}))?\b", s)
    if m and m[1][:3] in _MONTHS:
        y = int(m[3]) if m[3] else today.year
        d = _mk(y, _MONTHS[m[1][:3]], int(m[2]))
        if d and not m[3] and d < today:
            d = _mk(y + 1, _MONTHS[m[1][:3]], int(m[2]))
        return d
    m = re.search(r"\b(\d{1,2})[/\.](\d{1,2})[/\.](20\d{2})\b", s)  # dd/mm/yyyy (India)
    if m:
        return _mk(int(m[3]), int(m[2]), int(m[1]))
    return None


_DEADLINE_KEY = re.compile(r"(deadline|apply\s+(?:by|before)|last\s+date|closes?(?:\s+on)?|applications?\s+close|due\s+(?:by|on))", re.I)


def find_deadline(text: str, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    for m in _DEADLINE_KEY.finditer(text):
        window = text[m.start(): m.end() + 70]
        d = parse_date_text(window, today)
        if d:
            return {"value": d, "confidence": "stated", "evidence": window.strip()[:100]}
    return None


# ------------------------------------------------------------------ posting
_LABELS = {
    "company": re.compile(r"^(?:company|organi[sz]ation|employer|lab|institute)\s*[:\-]\s*(.+)$", re.I),
    "title": re.compile(r"^(?:job\s+title|title|role|position)\s*[:\-]\s*(.+)$", re.I),
    "location": re.compile(r"^(?:location|based\s+in)\s*[:\-]\s*(.+)$", re.I),
}
_REQ_HEAD = re.compile(r"^(?:requirements?|qualifications?|what\s+you(?:'|’)ll\s+need|who\s+you\s+are|eligibility|skills?\s+required|"
                       r"must\s+have|basic\s+qualifications?)\b.{0,30}:?$", re.I)
_STOP_HEAD = re.compile(r"^(?:responsibilities|what\s+you(?:'|’)ll\s+do|about\s+(?:us|the)|benefits|perks|how\s+to\s+apply|"
                        r"nice\s+to\s+have|preferred)\b.{0,30}:?$", re.I)


def detect_work_mode(text: str) -> Optional[str]:
    t = text.lower()
    if re.search(r"\bhybrid\b", t):
        return "hybrid"
    if re.search(r"\b(on-?site|in-?office|work\s+from\s+office)\b", t):
        return "onsite"
    if re.search(r"\b(remote|work\s+from\s+home|wfh)\b", t):
        return "remote"
    return None


def detect_role_type(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(research|rsip|summer\s+research|ra\s+position|phd|lab)\b", t) and "intern" not in t[:120]:
        return "research"
    if re.search(r"\bintern(ship)?\b", t):
        return "internship"
    if re.search(r"\bpart[\s-]?time\b", t):
        return "part-time"
    return "internship" if "trainee" in t else "job"


def extract_skills(text: str) -> List[str]:
    t = " " + text.lower() + " "
    out = []
    for s in SKILL_VOCAB:
        pat = r"(?<![a-z0-9+#])" + re.escape(s) + r"(?![a-z0-9+#])"
        if re.search(pat, t):
            out.append("node.js" if s == "nodejs" else s)
    return sorted(set(out))


def extract_requirements(text: str) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines()]
    reqs, on = [], False
    for ln in lines:
        bare = ln.strip("*#:- \t")
        if _REQ_HEAD.match(bare):
            on = True
            continue
        if on and (_STOP_HEAD.match(bare) or (not ln and len(reqs) >= 3)):
            on = False
        if on and ln:
            item = re.sub(r"^[\-\*•·▪●\d\.\)\s]+", "", ln).strip()
            if 8 <= len(item) <= 220:
                reqs.append(item)
    if not reqs:  # fall back to sentences that clearly state a requirement
        for ln in lines:
            item = re.sub(r"^[\-\*•·▪●\d\.\)\s]+", "", ln).strip()
            if 12 <= len(item) <= 220 and re.search(r"\b(must|should|required|eligible|pursuing|final[\s-]?year|cgpa|gpa|graduat)", item, re.I):
                reqs.append(item)
    return reqs[:12]


def parse_posting(text: str, url: Optional[str] = None, today: Optional[date] = None) -> Dict[str, Any]:
    """Heuristic extraction. Returns {fields: {name: {value, confidence}}, needs_confirmation: [...], ...}.
    confidence: 'stated' (labelled in the text / explicit pattern) | 'guess' (position or wording heuristic) | 'missing'."""
    text = (text or "").replace("\r", "")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    fields: Dict[str, Dict[str, Any]] = {}

    def put(name: str, value: Any, conf: str, evidence: str = ""):
        if value in (None, "", []):
            fields[name] = {"value": None, "confidence": "missing"}
        else:
            fields[name] = {"value": value, "confidence": conf, **({"evidence": evidence} if evidence else {})}

    for ln in lines[:60]:
        for k, rx in _LABELS.items():
            m = rx.match(ln.strip("*# "))
            if m and k not in fields:
                put(k, m.group(1).strip(" .")[:160], "stated", ln[:100])

    if "title" not in fields and lines:
        first = lines[0]
        if not re.match(r"^https?://", first) and len(first) <= 120:
            m = re.match(r"^(?P<org>.+?)\s+(?:is\s+)?hiring\s*[:\-]?\s*(?P<t>.+)$", first, re.I)
            if m:
                put("title", m["t"].strip(), "guess", first)
                if "company" not in fields:
                    put("company", m["org"].strip(), "guess", first)
            else:
                m = re.match(r"^(?P<t>.+?)\s+(?:at|@|\|)\s+(?P<org>[^|]+)$", first)
                if m:
                    put("title", m["t"].strip(), "guess", first)
                    if "company" not in fields:
                        put("company", m["org"].strip(), "guess", first)
                else:
                    put("title", first, "guess", first)
    if "company" not in fields and len(lines) > 1:
        second = lines[1]
        head = re.split(r"\s+[·•|\-–—]\s+", second)[0].strip()
        if head and len(head) <= 80 and not re.search(r"(intern|engineer|developer|apply|http)", head, re.I):
            put("company", head, "guess", second)
    if "location" not in fields:
        m = re.search(r"\(([^()]{3,40})\)", " ".join(lines[:4]))
        cand = None
        for ln in lines[1:4]:
            parts = re.split(r"\s+[·•|]\s+", ln)
            if len(parts) > 1:
                cand = parts[1].strip(" ()")
                break
        if cand:
            put("location", re.sub(r"\((?:remote|hybrid|on-?site)\)", "", cand, flags=re.I).strip(" ,"), "guess", cand)
        elif m:
            put("location", m.group(1), "guess")

    wm = detect_work_mode(text)
    put("work_mode", wm, "stated" if wm else "missing")
    put("role_type", detect_role_type(text[:1500] + " " + (fields.get("title", {}).get("value") or "")), "guess")
    dl = find_deadline(text, today)
    if dl:
        put("deadline", dl["value"].isoformat(), "stated", dl["evidence"])
    else:
        put("deadline", None, "missing")
    reqs = extract_requirements(text)
    put("requirements", reqs, "stated" if reqs else "missing")
    skills = extract_skills(text)
    put("tags", skills, "stated" if skills else "missing")

    nu = normalize_url(url)
    needs = [k for k in ("title", "company", "location", "deadline") if fields.get(k, {}).get("confidence") in ("guess", "missing")]
    if not (text or "").strip():
        needs = ["title", "company", "deadline", "requirements"]
    return {"fields": fields, "needs_confirmation": needs, "source_url": nu["url"], "source_type": nu["source_type"] or "manual",
            "job_id": nu["job_id"], "description_text": text.strip()[:8000]}


# ------------------------------------------------------------------ job-alert emails
_LI_LINK = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:comm/)?jobs/view/(?:[^\s/?#\"'>)]*-)?(\d{6,})[^\s\"'>)]*", re.I)


def parse_alert_email(text: str) -> List[Dict[str, Any]]:
    """Candidate postings from pasted/forwarded alert email text. The user confirms each one before it is saved."""
    text = (text or "").replace("\r", "")
    lines = text.split("\n")
    seen, out = set(), []
    for i, ln in enumerate(lines):
        for m in _LI_LINK.finditer(ln):
            jid = m.group(1)
            if jid in seen:
                continue
            seen.add(jid)
            ctx = [c.strip() for c in lines[max(0, i - 4): i] if c.strip() and not _LI_LINK.search(c)
                   and not re.match(r"^(view job|apply|see all|unsubscribe|new jobs)", c.strip(), re.I)]
            title = ctx[-2] if len(ctx) >= 2 else (ctx[-1] if ctx else None)
            company = ctx[-1] if len(ctx) >= 2 else None
            loc = None
            if company and re.search(r"[·•|]", company):
                parts = re.split(r"\s*[·•|]\s*", company)
                company, loc = parts[0], (parts[1] if len(parts) > 1 else None)
            out.append({"job_id": jid, "source_url": f"https://www.linkedin.com/jobs/view/{jid}/", "source_type": "email_alert",
                        "title": (title or "")[:140] or None, "company": (company or "")[:120] or None, "location": loc,
                        "confidence": "guess"})
            if len(out) >= 25:
                return out
    return out


# ------------------------------------------------------------------ professor listings
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def parse_faculty_listing(text: str) -> List[Dict[str, Any]]:
    """Pulls (name, email, research hints) rows out of a pasted faculty page. Nothing is saved from here."""
    rows, lines = [], [ln.strip() for ln in (text or "").replace("\r", "").split("\n")]
    for i, ln in enumerate(lines):
        for m in _EMAIL.finditer(ln):
            email = m.group(0).lower()
            if any(r["email"] == email for r in rows):
                continue
            ctx = [c for c in lines[max(0, i - 3): i + 1] if c]
            name = None
            for c in reversed(ctx):
                mm = re.search(r"((?:Prof\.?|Dr\.?|Professor)\s+[A-Z][\w\.\- ]{2,50})", c)
                if mm:
                    name = mm.group(1).strip()
                    break
            if not name:
                head = re.sub(_EMAIL, "", ctx[0] if ctx else "").strip(" ,:-|")
                name = head[:60] or None
            areas = [s for s in extract_skills(" ".join(ctx))]
            rows.append({"name": name, "email": email, "research_hints": areas, "confidence": "guess"})
            if len(rows) >= 40:
                return rows
    return rows
