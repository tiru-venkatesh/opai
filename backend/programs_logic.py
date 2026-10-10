"""Programs & Challenges: types, starter catalog, cycle status rules, official-source check, text parser.

Core rule, enforced here and not in prompts:
    A program is only ever labelled Open / Opens soon / Active / Closed when its dates were confirmed against the
    ORGANIZER'S OWN page (host check) and are still fresh. Everything else says 'Verify current cycle' or
    'Not announced'. Catalog entries carry NO dates, so an old edition can never look current."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import opp_parse as P

REVERIFY_DAYS = 14

# key -> (label, group)
TYPES: Dict[str, Dict[str, str]] = {
    "open_source_program": {"label": "Open-source program", "group": "Open source"},
    "open_source_event": {"label": "Open-source challenge", "group": "Open source"},
    "hackathon": {"label": "Hackathon", "group": "Competitions"},
    "startup_competition": {"label": "Student startup competition", "group": "Competitions"},
    "online_challenge": {"label": "Online challenge", "group": "Competitions"},
    "fellowship": {"label": "Fellowship", "group": "Fellowships & training"},
    "bootcamp": {"label": "Bootcamp / course", "group": "Fellowships & training"},
    "company_program": {"label": "Company student program", "group": "Company & institutional"},
    "research_program": {"label": "Research / academic program", "group": "Research"},
    "government_internship": {"label": "Government / institutional internship", "group": "Company & institutional"},
    "workshop": {"label": "Workshop / event", "group": "Fellowships & training"},
}

# Starter catalog: discovery aids ONLY. No dates, no 'open' claims; `official_url` is where to confirm everything.
CATALOG: List[Dict[str, Any]] = [
    {"id": "gsoc", "name": "Google Summer of Code", "organizer": "Google", "program_type": "open_source_program", "recurrence": "annual",
     "official_url": "https://developers.google.com/open-source/gsoc/timeline", "official_domains": ["developers.google.com", "summerofcode.withgoogle.com"],
     "focus_tags": ["open source", "git", "python", "c++", "javascript"],
     "blurb": "Mentored open-source contribution for newcomers. Contributor applications run in a window the organizer publishes each year."},
    {"id": "hacktoberfest", "name": "Hacktoberfest", "organizer": "DigitalOcean", "program_type": "open_source_event", "recurrence": "annual",
     "official_url": "https://hacktoberfest.com/", "official_domains": ["hacktoberfest.com"],
     "focus_tags": ["open source", "git", "github"],
     "blurb": "Month-long open-source contribution event. Read the official rules for what counts."},
    {"id": "outreachy", "name": "Outreachy", "organizer": "Outreachy", "program_type": "open_source_program", "recurrence": "recurring",
     "official_url": "https://www.outreachy.org/", "official_domains": ["outreachy.org"],
     "focus_tags": ["open source", "git", "python", "documentation"],
     "blurb": "Paid, remote open-source internships with its own eligibility rules. Check the official eligibility page."},
    {"id": "mlh_fellowship", "name": "MLH Fellowship", "organizer": "Major League Hacking", "program_type": "fellowship", "recurrence": "recurring",
     "official_url": "https://fellowship.mlh.io/", "official_domains": ["fellowship.mlh.io", "mlh.io"],
     "focus_tags": ["open source", "software engineering", "python", "javascript"],
     "blurb": "Project-based fellowship for early-career developers. Cohorts and terms are announced by the organizer."},
    {"id": "imagine_cup", "name": "Microsoft Imagine Cup", "organizer": "Microsoft", "program_type": "startup_competition", "recurrence": "annual",
     "official_url": "https://imaginecup.microsoft.com/", "official_domains": ["imaginecup.microsoft.com", "microsoft.com"],
     "focus_tags": ["startup", "ai", "azure", "product"],
     "blurb": "Student startup competition. Rules, team size and eligibility change by edition."},
    {"id": "nvidia_student", "name": "NVIDIA student programs", "organizer": "NVIDIA", "program_type": "company_program", "recurrence": "recurring",
     "official_url": "https://www.nvidia.com/en-us/programs/", "official_domains": ["nvidia.com"],
     "focus_tags": ["gpu", "cuda", "deep learning", "machine learning", "ai"],
     "blurb": "Company programs, workshops and student opportunities. Internships are listed separately by NVIDIA; check each one."},
]
CATALOG_BY_ID = {c["id"]: c for c in CATALOG}

# Preparation tasks per type: (key, title template, minutes). At most MAX_PLAN_TASKS are created, so Today is never flooded.
MAX_PLAN_TASKS = 3
PLAN: Dict[str, List[tuple]] = {
    "open_source_event": [("find", "Find 2 {name} projects matching your skills", 25), ("desc", "Prepare an open-source project description", 30), ("rules", "Read the {name} rules on what counts", 15)],
    "open_source_program": [("find", "Shortlist 2 {name} organizations that match your skills", 30), ("desc", "Prepare an open-source project description", 30), ("contrib", "Make one small contribution to a shortlisted project", 60)],
    "hackathon": [("team", "Confirm your team and roles for {name}", 20), ("idea", "Write a one-paragraph problem statement", 30), ("stack", "Pick the stack and check the judging criteria", 20)],
    "startup_competition": [("rules", "Check rules, student eligibility, team requirements and deadline for {name}", 15), ("team", "Confirm your team and roles", 20), ("pitch", "Draft a one-paragraph problem statement", 30)],
    "fellowship": [("materials", "Prepare your resume and statement for {name}", 60), ("proj", "Pick the project you will showcase", 25), ("refs", "Line up anyone you need as a reference", 15)],
    "research_program": [("interest", "Write a short research-interest statement for {name}", 45), ("cv", "Update your resume for research roles", 30)],
    "company_program": [("fit", "Read what {name} offers and pick the one that fits", 20), ("resume", "Tailor your resume to the program", 45)],
    "government_internship": [("docs", "Collect the documents {name} asks for", 30), ("elig", "Check the eligibility and the application route", 15)],
    "online_challenge": [("setup", "Set up your environment for {name}", 30), ("practice", "Do one practice problem", 30)],
    "bootcamp": [("syll", "Read the {name} syllabus and time commitment", 15), ("apply", "Prepare your application", 30)],
    "workshop": [("reg", "Check how to register for {name}", 10), ("prep", "Note 2 questions you want answered", 10)],
}
GENERIC_PLAN = [("read", "Read what {name} requires", 20), ("prep", "Prepare the materials it asks for", 45)]


# ---------------------------------------------------------------- official source check
def host_of(url: Optional[str]) -> str:
    try:
        return (urlparse(url or "").netloc or "").lower().removeprefix("www.").split(":")[0]
    except Exception:
        return ""


def official_domains(program) -> List[str]:
    cat = CATALOG_BY_ID.get(program.catalog_id or "")
    doms = list(cat["official_domains"]) if cat else []
    h = host_of(program.official_url)
    if h:
        doms.append(h)
    return doms


def is_official_source(program, source_url: Optional[str]) -> bool:
    """True only if the page the user read the dates on is on the organizer's own domain."""
    h = host_of(source_url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in official_domains(program)) and (source_url or "").lower().startswith("https://")


# ---------------------------------------------------------------- cycle status
def is_confirmed(c) -> bool:
    return c.verification == "official" and c.source_checked_at is not None


def cycle_status(c, today: Optional[date] = None) -> Dict[str, Any]:
    """status + flags. Never returns Open/Active/Closed for unconfirmed data."""
    today = today or date.today()
    if not is_confirmed(c):
        if c.announced is False:
            return {"status": "Not announced", "confirmed": False, "needs_reverify": False,
                    "why": "The organizer has not announced this cycle. Nothing here is a date."}
        why = ("Dates were read from a non-official page, so they are not trusted." if c.verification == "third_party"
               else "No official source has confirmed this cycle yet.")
        return {"status": "Verify current cycle", "confirmed": False, "needs_reverify": False, "why": why}
    o, d, es, ee = c.applications_open, c.deadline, c.event_start, c.event_end
    last = max([x for x in (d, ee) if x] or [None], default=None)
    st = None
    if o and d:
        if o <= today <= d:
            st = "Open"
        elif today < o:
            st = "Opens soon" if (o - today).days <= 30 else "Upcoming"
    elif d and today <= d:
        st = "Open"
    elif o and not d and today >= o:
        st = "Open"
    elif o and today < o:
        st = "Opens soon" if (o - today).days <= 30 else "Upcoming"
    if st is None and es and ee and es <= today <= ee:
        st = "Active"
    if st is None and es and today < es:
        st = "Opens soon" if (es - today).days <= 30 else "Upcoming"
    if st is None:
        if last and today > last:
            st = "Ended" if (ee and today > ee) else "Closed"
        else:
            st = "Verify current cycle"
    stale = bool(c.source_checked_at and (datetime.utcnow() - c.source_checked_at).days > REVERIFY_DAYS and st in ("Open", "Opens soon", "Upcoming", "Active"))
    return {"status": st, "confirmed": True, "needs_reverify": stale,
            "why": ("Confirmed on the organizer's page" + (f" on {c.source_checked_at.date().isoformat()}" if c.source_checked_at else "") + ".") +
                   (" It was checked more than %d days ago; re-check before relying on it." % REVERIFY_DAYS if stale else "")}


def days_to(c, today: Optional[date] = None) -> Optional[int]:
    today = today or date.today()
    ds = [x for x in (c.deadline, c.applications_open, c.event_start) if x and x >= today]
    return (min(ds) - today).days if ds else None


# ---------------------------------------------------------------- fit
def fit_for(program, skills: List[str]) -> Dict[str, Any]:
    tags = [t.lower() for t in (program.focus_tags or [])]
    mine = {s.lower() for s in skills}
    hits = [t for t in tags if any(t == s or (len(s) > 2 and (s in t or t in s)) for s in mine)]
    if not skills:
        return {"level": "unknown", "why": "Add and confirm your skills to see how this fits.", "matched": []}
    if hits:
        return {"level": "good" if len(hits) >= 2 else "some", "why": "Matches your skills: " + ", ".join(hits) + ".", "matched": hits}
    return {"level": "unclear", "why": "No overlap with your listed skills was found. Read the official page before deciding.", "matched": []}


# ---------------------------------------------------------------- text parser (text the user pasted from the official page)
_AMT = re.compile(r"(?:\$|USD\s?|₹|INR\s?|Rs\.?\s?|€|£)\s?\d[\d,]*(?:\.\d+)?\s?[kKmM]?")
_RANGE = re.compile(r"(.{3,40}?)\s*(?:to|–|—|-|through|until)\s*(.{3,40})", re.I)
_OPEN_KEY = re.compile(r"(applications?|registrations?)\s+(open|start|begin)|opens?\s+(on|from)|open\s+from", re.I)
_DEAD_KEY = re.compile(r"deadline|apply\s+(by|before)|last\s+date|closes?\b|closing|due\s+(by|on)|submissions?\s+(due|close)", re.I)
_EVENT_KEY = re.compile(r"\b(event|hackathon|runs?|takes\s+place|program(me)?\s+(dates|period|runs)|dates?|period|coding\s+period|duration)\b", re.I)
_YEAR = re.compile(r"\b20\d{2}\b")


def _date_in(s: str, today: date):
    d = P.parse_date_text(s, today)
    if not d:
        return None, None
    has_year = bool(_YEAR.search(s))
    return d, ("found" if has_year else "inferred")


def parse_program_text(text: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Pasted official page -> candidate fields. Each is found | inferred | missing; a date with no year is only
    'inferred' (never trusted) so a past edition cannot be mistaken for the current one."""
    today = today or date.today()
    lines = [re.sub(r"\s+", " ", l).strip(" \t•*-") for l in (text or "").replace("\r", "").split("\n") if l.strip()]
    f: Dict[str, Dict[str, Any]] = {}

    def put(k, v, state="found"):
        f[k] = {"value": v, "state": state if v not in (None, "", []) else "missing"}

    ao = dl = es = ee = None
    states = {}
    for l in lines:
        if _DEAD_KEY.search(l) and dl is None:
            dl, states["deadline"] = _date_in(l, today)
        elif _OPEN_KEY.search(l) and ao is None:
            ao, states["applications_open"] = _date_in(l, today)
    for l in lines:
        if _DEAD_KEY.search(l) or _OPEN_KEY.search(l):
            continue
        m = _RANGE.search(l)
        if m and (_EVENT_KEY.search(l) or True):
            a, b = P.parse_date_text(m[1], today), P.parse_date_text(m[2], today)
            if a and b and a <= b and es is None:
                es, ee = a, b
                states["event"] = "found" if (_YEAR.search(m[1]) or _YEAR.search(m[2])) else "inferred"
    put("applications_open", ao.isoformat() if ao else None, states.get("applications_open", "found"))
    put("deadline", dl.isoformat() if dl else None, states.get("deadline", "found"))
    put("event_start", es.isoformat() if es else None, states.get("event", "found"))
    put("event_end", ee.isoformat() if ee else None, states.get("event", "found"))

    tm = tM = None
    for l in lines:
        m = re.search(r"teams?\s+of\s+(\d+)(?:\s*(?:-|to|–)\s*(\d+))?", l, re.I) or re.search(r"(?:up\s+to|maximum\s+of|max\.?)\s+(\d+)\s+(?:members|people|students|participants)", l, re.I)
        if m:
            tm = int(m[1]) if m.re.pattern.startswith("teams") and m[2] else None
            tM = int(m[2]) if (m.re.pattern.startswith("teams") and m[2]) else int(m[1])
            if m.re.pattern.startswith("teams") and not m[2]:
                tm = tM = int(m[1])
            break
    put("team_min", tm); put("team_max", tM)

    reward = next((l[:160] for l in lines if _AMT.search(l) and re.search(r"stipend|prize|award|grant|scholarship|win", l, re.I)), None)
    put("reward", reward)
    tc = next((m[0] for l in lines for m in [re.search(r"\d+\s*(?:-|–|to)?\s*\d*\s*(?:hours?|hrs?)\s*(?:/|per|a)\s*week|\d+[- ]week", l, re.I)] if m), None)
    put("time_commitment", tc)
    elig = [l[:220] for l in lines if re.search(r"eligib|must be|open to|students?\b.*\b(enrolled|currently|pursuing)|age|18\+|at least 18|university|college", l, re.I) and not _DEAD_KEY.search(l)]
    put("eligibility", " ".join(elig[:4]) if elig else None)
    stages = [l[:140] for l in lines if re.search(r"\b(round|stage|phase|semi-?finals?|finals?|shortlist|interview|screening|selection)\b", l, re.I) and len(l) < 160]
    put("stages", stages[:6])
    reqs = [l[:160] for l in lines if re.search(r"\b(submit|submission|required|deliverables?|proposal|resume|cv|video|demo|pitch\s+deck|repository|essay|statement|portfolio)\b", l, re.I) and len(l) < 180 and not _DEAD_KEY.search(l)]
    put("requirements", reqs[:8])

    review = [k for k, v in f.items() if v["state"] != "found" and k in ("applications_open", "deadline", "event_start", "eligibility")]
    review += [k for k, v in f.items() if v["state"] == "inferred"]
    return {"fields": f, "needs_review": sorted(set(review)),
            "note": "Read from text you pasted. Nothing is trusted until you confirm it against the organizer's official page."}


# ---------------------------------------------------------------- plan
def plan_tasks(program, cycle, st: Dict[str, Any], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """The few preparation tasks that make sense right now. Never more than MAX_PLAN_TASKS."""
    today = today or date.today()
    name = program.name
    out: List[tuple] = []
    if st["status"] in ("Closed", "Ended"):
        return []
    if st["status"] == "Not announced":
        out = [("profile", "Prepare your profile and explore past {name} projects", 30), ("watch", "Check the {name} page for the next announcement", 10)]
    else:
        if not st["confirmed"]:
            out.append(("verify", "Check {name} cycle, eligibility and deadline on the official page", 15))
        out += PLAN.get(program.program_type, GENERIC_PLAN)
    out = out[:MAX_PLAN_TASKS]
    last = cycle.deadline or cycle.event_start
    n = len(out)
    res = []
    for i, (k, title, mins) in enumerate(out):
        if k in ("verify", "watch"):
            due = today + timedelta(days=2)
        elif last and last > today:
            span = max(1, (last - today).days - 1)
            due = today + timedelta(days=min(span, max(2, round(span * (i + 1) / (n + 1)))))
        else:
            due = today + timedelta(days=2 + 2 * i)
        res.append({"key": k, "title": title.format(name=name), "minutes": mins, "due": due})
    return res
