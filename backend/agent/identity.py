"""Questions about the user's OWN profile ("what is my name", "which college do I study in", "my skills ...").

These are answered straight from the user's rows: exact, no LLM, so personal details never leave the server for
them, and it works in both Workspace and General mode (and without a GROQ key).

Rules:
  * Never guess. A missing field is reported as missing and the answer says where to add it.
  * Date of birth is private: KARNA does not look it up or read it out.
  * Things OPAI does not store (phone, favourites, weight, height, ID numbers...) are said not to be stored.
  * Only QUESTIONS are handled. Anything that changes data ("update my college", "add my skills") or is about
    another topic ("my emails", "my projects", "my college timetable") falls through to the normal pipeline.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from database import MemoryItem, Semester, User

UNSET_NAMES = {"", "user", "guest"}

# ---------------------------------------------------------------- normalisation
_TYPOS = {r"\bmky\b": "my", r"\bmyy\b": "my", r"\bwaht\b": "what", r"\bwwhat\b": "what", r"\bwhta\b": "what", r"\bwat\b": "what",
          r"\bwhts\b": "whats", r"\bcolage\b": "college", r"\bcollege?s?\b(?=\s+name)": "college", r"\bgmial\b": "gmail",
          r"\bskils\b": "skills", r"\b(?:stydy|studdy|studay|studie)\b": "study", r"\bstydies\b": "studies", r"\bgithb\b": "github"}
_NEXT_FIELD = r"(name|college|university|year|sem|semester|course|branch|degree|e-?mail|gmail|skills?|goals?|github|linked ?in|cgpa|gpa|portfolio|timezone|phone|dob)"


def _norm(msg: str) -> str:
    m = " ".join((msg or "").lower().replace("’", "'").split())
    for rx, rep in _TYPOS.items():
        m = re.sub(rx, rep, m)
    m = re.sub(r"[?!.,;]+", " ", m)
    m = re.sub(r"\band (?=" + _NEXT_FIELD + r"\b)", "and my ", m)        # "my name and college" -> "my name and my college"
    m = re.sub(r"\bmy (?=my\b)", "", m)
    m = " ".join(m.split())
    return re.sub(r"^(?:please|pls|plz|hey karna|hey|hi|hello|karna)[ ,]+", "", m)


_WRITE = re.compile(r"\b(add|update|change|set|edit|delete|remove|create|save|send|draft|write|make|compose|reply|forward|fix|correct|"
                    r"rename|replace|import|upload|remind|schedule|plan|apply)\b")
_STOP_AFTER = r"(?!\s+(?:timetable|time table|exams?|schedule|projects?|deadlines?|assignments?|calendar|fees?|notes?|placements?|events?|"
_STOP_AFTER += r"drafts?|templates?|outbox|replies|reply|threads?|to\b|from\b))"

_PATTERNS: List[tuple] = [
    ("private", re.compile(r"\bmy (?:dob|date of birth|birth ?date|birth ?day|b'?day|age)\b|\bhow old am i\b|\bwhen (?:was i born|is my birth ?day)\b")),
    ("phone", re.compile(r"\bmy (?:phone|mobile|contact|whatsapp|cell)(?: number| no)?\b|\bphone number\b|\bmobile number\b")),
    ("not_stored", re.compile(r"\bmy (?:fav\w*|favou?rite \w+|weight|height|blood group|address|aadhaa?r|pan(?: card)?|passport|religion|salary|income)\b|"
                              r"\bhow (?:tall|heavy|much do i weigh)\b")),
    ("about", re.compile(r"^(?:about me|about myself|me)$|\bwhat do you know about me\b|\btell me about (?:me|myself)\b|\bwho am i\b|\bwhat (?:do you have|info do you have) (?:about|on) me\b|"
                         r"\bmy (?:details|info|information)\b")),
    ("name", re.compile(r"\bmy name\b|\bwhat am i called\b|\bdo you know (?:my name|who i am)\b")),
    ("college", re.compile(r"\bmy (?:college|university|institute|institution|campus)\b" + _STOP_AFTER + r"|\bwhere do i (?:study|go to college)\b|"
                           r"\b(?:which|what) (?:college|university|institute) (?:do i|am i|i)\b|\b(?:college|university) (?:i|do i) (?:study|attend|go)\b")),
    ("year", re.compile(r"\bmy (?:year|current year|year of study|batch|passing year|passout year|graduation(?: year| date)?)\b" + _STOP_AFTER +
                        r"|\b(?:which|what) year (?:am i|i am|do i)\b|\bam i in (?:\d|first|second|third|fourth|final)")),
    ("semester", re.compile(r"\bmy (?:sem|semester)\b" + _STOP_AFTER + r"|\b(?:which|what) (?:sem|semester) (?:am i|i am|do i)\b")),
    ("course", re.compile(r"\bmy (?:course|degree|branch|major|stream|department|dept|program(?:me)?)\b" + _STOP_AFTER +
                          r"|\bwhat (?:do i|am i) (?:study|studying)\b|\b(?:which|what) (?:course|branch|degree) (?:do i|am i|i)\b")),
    ("email", re.compile(r"\bmy (?:e-?mail|gmail|mail)(?: id| address)?\b(?!s)" + _STOP_AFTER + r"|\b(?:what|which) (?:is )?(?:my )?(?:e-?mail|gmail)(?: id| address)?\b(?! (?:draft|reply))")),
    ("skills", re.compile(r"\bmy skills?\b|\bwhat skills do i (?:have|know)\b|\bwhich skills do i (?:have|know)\b|\bskills i (?:have|know)\b")),
    ("goals", re.compile(r"\bmy (?:goals?|targets?|aims?|ambitions?|dream|career (?:goals?|plans?|targets?))\b")),
    ("github", re.compile(r"\bmy github(?: id| link| url| profile| username)?\b")),
    ("linkedin", re.compile(r"\bmy linked ?in\b")),
    ("portfolio", re.compile(r"\bmy portfolio\b")),
    ("cgpa", re.compile(r"\bmy (?:cgpa|gpa)\b|\bwhat(?:s| is) my (?:cgpa|gpa)\b")),
    ("timezone", re.compile(r"\bmy (?:time ?zone|tz)\b")),
]
_COMMAND_HEAD = re.compile(r"^(?:email|mail|message|text|whatsapp|call|open|go to|take me|find|search|apply|help me|please|can you (?:email|send|draft|write|add|update|change|set))\b")
_QUESTION_HEAD = re.compile(r"^(?:what|whats|which|who|where|when|how|tell|show|give|do you|can you|am i|is|my|and|also|then)\b")


def detect(message: str) -> List[str]:
    """Which profile topics this message asks about (in the order found); [] if it is not a profile question."""
    m = _norm(message)
    if not m or len(m.split()) > 18 or _WRITE.search(m) or _COMMAND_HEAD.search(m):
        return []
    if not _QUESTION_HEAD.search(m) and len(m.split()) > 6:
        return []
    found: List[str] = []
    for key, rx in _PATTERNS:
        if rx.search(m):
            found.append(key)
    if not found and re.search(r"\bmy (?:study|studies)\b", m):          # "my study" = what / where / which year
        found = ["course", "college", "year"]
    if "about" in found:                      # "what do you know about me" subsumes the individual fields
        return ["about"]
    return found


# ---------------------------------------------------------------- facts (read from the user's own rows)
def facts(db: Session, uid: str) -> Dict[str, Any]:
    u = db.query(User).filter(User.id == str(uid)).first()
    if not u:
        return {}
    prefs = dict(u.preferences or {})
    op = dict(prefs.get("opportunity_profile") or {})
    sems = db.query(Semester).filter(Semester.user_id == str(uid)).all()
    cur = next((s for s in sems if getattr(s, "is_current", False)), None) or (sems[-1] if sems else None)
    college = getattr(u, "college_name", None) or (cur.college if cur and cur.college else None) or next((s.college for s in sems if s.college), None) or op.get("college") or prefs.get("college")
    year = getattr(u, "current_year", None) or op.get("year")
    skills = [x.strip() for x in (u.skills or "").split(",") if x.strip()]
    goals: List[str] = []
    t = u.targets if isinstance(u.targets, dict) else {}
    for k, v in t.items():
        if isinstance(v, (str, int, float)) and str(v).strip():
            goals.append(f"{k}: {v}")
        elif isinstance(v, list) and v:
            goals.append(f"{k}: " + ", ".join(str(x) for x in v if str(x).strip()))
    if op.get("role_types"):
        goals.append("looking for " + ", ".join(op["role_types"]))
    branch_mem = None
    for mi in db.query(MemoryItem).filter(MemoryItem.user_id == str(uid), MemoryItem.status == "active", MemoryItem.source == "chat").order_by(MemoryItem.created_at.asc()).all():
        c = mi.content or ""                                   # things the user told KARNA in chat fill gaps, never override saved rows
        if c.startswith("College: ") and not college:
            college = c[9:]
        elif c.startswith("Skills: "):
            for x in c[8:].split(","):
                x = x.strip()
                if x and x.lower() not in {y.lower() for y in skills}:
                    skills.append(x)
        elif c.startswith("Goal: "):
            goals.append(c[6:])
        elif c.startswith("Branch / course: ") and not (u.branch or (cur.branch if cur else None)):
            branch_mem = c[17:]
    degree = u.degree or (cur.degree if cur else None)
    branch = u.branch or (cur.branch if cur else None) or branch_mem
    return {
        "name": u.name if (u.name or "").strip().lower() not in UNSET_NAMES else None,
        "email": u.email or None,
        "college": college,
        "year": year,
        "graduation": op.get("graduation_date"),
        "semester": getattr(u, "current_semester", None) or (cur.semester_number if cur and cur.semester_number else None),
        "academic_year": cur.academic_year if cur and cur.academic_year else None,
        "degree": degree, "branch": branch,
        "course": " ".join(x for x in (degree, branch) if x) or None,
        "skills": skills, "goals": goals,
        "github": u.github or op.get("github_url") or None,
        "linkedin": getattr(u, "linkedin_url", None) or op.get("linkedin_url") or prefs.get("linkedin") or None,
        "portfolio": getattr(u, "portfolio_url", None) or op.get("portfolio_url") or None,
        "cgpa": float(u.cgpa) if u.cgpa else None,
        "timezone": getattr(u, "timezone", None) or prefs.get("timezone") or None,
    }


# where a missing field can be filled in
_WHERE = {
    "name": "your Profile tab on the Overview page", "email": "your sign-in email", "college": "Academics, in the semester setup",
    "year": "your opportunity profile (Opportunities, Edit my profile)", "semester": "Academics, in the semester setup",
    "course": "your Profile tab on the Overview page", "skills": "your Profile tab on the Overview page",
    "goals": "your Profile tab on the Overview page", "github": "your Profile tab on the Overview page",
    "linkedin": "your opportunity profile (Opportunities, Edit my profile)", "portfolio": "your opportunity profile (Opportunities, Edit my profile)",
    "cgpa": "your Profile tab on the Overview page", "timezone": "Plan, by chatting with KARNA in your time zone",
}
_LABEL = {"name": "name", "email": "email", "college": "college", "year": "year", "semester": "semester", "course": "course", "skills": "skills",
          "goals": "goals", "github": "GitHub", "linkedin": "LinkedIn", "portfolio": "portfolio", "cgpa": "CGPA", "timezone": "time zone"}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _line(key: str, f: Dict[str, Any]) -> Optional[str]:
    """(label, value) sentence for a key, or None if the value is missing."""
    if key == "name" and f.get("name"):
        return f"Your name is {f['name']}."
    if key == "email" and f.get("email"):
        return f"Your email is {f['email']}."
    if key == "college" and f.get("college"):
        return f"You study at {f['college']}."
    if key == "year" and (f.get("year") or f.get("graduation")):
        bits = []
        if f.get("year"):
            bits.append(f"You are in your {_ordinal(int(f['year']))} year" + (f" of {f['course']}" if f.get("course") else "") + ".")
        if f.get("graduation"):
            bits.append(f"Graduation: {f['graduation']}.")
        return " ".join(bits)
    if key == "semester" and f.get("semester"):
        return f"You are in semester {f['semester']}" + (f" ({f['academic_year']})" if f.get("academic_year") else "") + "."
    if key == "course" and f.get("course"):
        return f"You study {f['course']}."
    if key == "skills" and f.get("skills"):
        return "Your skills: " + ", ".join(f["skills"]) + "."
    if key == "goals" and f.get("goals"):
        return "Your goals: " + "; ".join(f["goals"]) + "."
    if key == "github" and f.get("github"):
        return f"Your GitHub: {f['github']}"
    if key == "linkedin" and f.get("linkedin"):
        return f"Your LinkedIn: {f['linkedin']}"
    if key == "portfolio" and f.get("portfolio"):
        return f"Your portfolio: {f['portfolio']}"
    if key == "cgpa" and f.get("cgpa") is not None:
        return f"Your CGPA is {f['cgpa']:g}."
    if key == "timezone" and f.get("timezone"):
        return f"Your time zone is {f['timezone']}."
    return None


def _missing(key: str) -> str:
    return f"I don't have your {_LABEL[key]} yet. You can add it in {_WHERE[key]}."


def summary_lines(f: Dict[str, Any]) -> List[str]:
    """Bulleted profile used by 'what do you know about me' and the profile listing."""
    rows = [("Name", f.get("name")), ("Email", f.get("email")), ("College", f.get("college")),
            ("Year", (f"{_ordinal(int(f['year']))} year" if f.get("year") else None)),
            ("Semester", f.get("semester")), ("Course", f.get("course")), ("CGPA", f.get("cgpa")),
            ("Skills", ", ".join(f.get("skills") or []) or None), ("Goals", "; ".join(f.get("goals") or []) or None),
            ("GitHub", f.get("github")), ("LinkedIn", f.get("linkedin")), ("Portfolio", f.get("portfolio")), ("Time zone", f.get("timezone"))]
    return [f"- {k}: {v if v not in (None, '') else 'not set yet'}" for k, v in rows]


def answer(db: Session, user_id: str, message: str) -> Optional[Dict[str, Any]]:
    """{'reply', 'payload'} for a profile question, else None (so the normal pipeline handles it)."""
    topics = detect(message)
    if not topics:
        return None
    f = facts(db, str(user_id))
    if not f:
        return None
    parts: List[str] = []
    fields: List[str] = []
    if "private" in topics:
        parts.append("Your date of birth and age are private. KARNA doesn't look them up or read them out.")
    if "phone" in topics:
        parts.append("There is no phone number saved in OPAI, so I don't have one for you.")
    if "not_stored" in topics:
        parts.append("OPAI doesn't store that kind of personal detail, so I can't tell you. If you want KARNA to use something like it, "
                     "keep it as a note under Knowledge and ask in Workspace mode.")
    if topics == ["about"]:
        parts.append("Here is what OPAI has saved for you:\n" + "\n".join(summary_lines(f)))
        fields = ["about"]
    else:
        keys = [t for t in topics if t in _LABEL]
        lines = []
        for k in keys:
            fields.append(k)
            lines.append(_line(k, f) or _missing(k))
        if len(lines) == 1:
            parts.append(lines[0])
        elif lines:
            parts.append("\n".join("- " + l for l in lines))
    if not parts:
        return None
    return {"reply": "\n\n".join(parts), "payload": {"intent": "profile_lookup", "source": "profile", "llm": False, "fields": fields or topics}}
