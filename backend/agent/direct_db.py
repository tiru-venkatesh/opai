"""
Direct-database answers for read-only questions ("how many applications do I have",
"which tasks are pending", "when is my next exam", "what are my skills").

Why this exists: RAG returns *similar text*. For lists, counts and deadlines the
relational tables are the source of truth, so we answer from them exactly - no
embedding, no LLM, no chance of a hallucinated date or a missed row.

Safety rules:
  * READ-ONLY. Nothing here writes to the database.
  * Every query is filtered by user_id, so one user can never see another's rows.
  * Messages containing a write verb (add/create/delete/update/...) are skipped, so
    this layer never swallows a request that should reach the router/tools.
  * Returns None when the message isn't a clear read question about a known topic,
    and the normal router -> RAG flow takes over.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database import (
    User, Application, Project, Task, Academic, Course, Exam, ClientRequest, OutboxItem,
)

MAX_LINES = 10
MAX_TOPICS = 3

# A message with any of these is an action, not a lookup - leave it to the router.
_WRITE = re.compile(
    r"\b(add|create|delete|remove|draft|send|update|change|edit|mark|plan|schedule|"
    r"generate|remind|reschedule|approve|reject|apply to)\b"
)
# Looks like a question / lookup (English + a few Tenglish cue words).
_READ = re.compile(
    r"\b(how many|count|list|show|what|whats|which|when|who|do i have|have i|any|status|"
    r"tell me|enni|entha|unnayi|chupinchu|cheppu)\b|\?"
)
# Asks about the CONTENT of things ("which project uses embeddings?", "what does the Acme role need?") are
# semantic questions: they go to RAG, not to a table dump.
_CONTENT = re.compile(
    r"\b(uses?|using|used|about|mention\w*|contains?|containing|involv\w*|built with|made with|related to|regarding|"
    r"explain|why|how (?:does|do|did|can|to)|needs?|needed|requires?|required|requirements?|skills? (?:does|do|for)|"
    r"tech(?:nolog\w+)?|stack|summar\w+|describe|compare|difference)\b"
)
_PERSONAL = re.compile(r"\b(my|mine|i|ive|i've|our|naa|na|nenu|mana)\b")
_COUNT = re.compile(r"\b(how many|count|number of|enni|entha)\b")

# (topic key, regex over the lowercased message)
_TOPICS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("deadlines", re.compile(r"deadline|due\b|overdue")),
    ("applications", re.compile(r"applicat|\bapplied\b")),
    ("tasks", re.compile(r"\btasks?\b|to-?do\b|pending work")),
    ("projects", re.compile(r"\bprojects?\b")),
    ("exams", re.compile(r"\bexams?\b|\bcourses?\b|\bsubjects?\b|academic")),
    ("requests", re.compile(r"\brequests?\b|\bclients?\b|freelance|proposal")),
    ("outbox", re.compile(r"outbox|awaiting approval|pending approval|\bdrafts?\b")),
    ("profile", re.compile(r"\bprofile\b|\bskills?\b|\bcgpa\b|\bbranch\b|\bdegree\b|\bgithub\b")),
]


# ------------------------------------------------------------------ helpers
def _when(d: Optional[date]) -> str:
    if not d:
        return "no date"
    n = (d - date.today()).days
    tag = "today" if n == 0 else "tomorrow" if n == 1 else f"in {n}d" if n > 1 else f"{-n}d overdue"
    return f"{d.strftime('%d %b %Y')} ({tag})"


def _cap(lines: List[str]) -> List[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return lines[:MAX_LINES] + [f"...and {len(lines) - MAX_LINES} more"]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# ------------------------------------------------------------------ topics
# Each returns (count, count_sentence, header, lines).
def _applications(db: Session, uid: str, msg: str):
    rows = db.query(Application).filter(Application.user_id == uid).all()
    rows.sort(key=lambda r: (r.deadline is None, r.deadline or date.max))
    by = Counter((r.status or "To Apply") for r in rows)
    breakdown = ", ".join(f"{v} {k}" for k, v in by.most_common())
    sentence = f"You have {_plural(len(rows), 'application')}" + (f" ({breakdown})." if rows else ".")
    lines = [
        f"- {r.company} - {r.role} [{r.status or 'To Apply'}]"
        + (f", deadline {_when(r.deadline)}" if r.deadline else "")
        for r in rows
    ]
    return len(rows), sentence, "Your applications:", lines


def _tasks(db: Session, uid: str, msg: str):
    rows = db.query(Task).filter(Task.user_id == uid).all()
    open_ = [t for t in rows if (t.status or "todo") != "done"]
    open_.sort(key=lambda t: (t.due_date is None, t.due_date or date.max))
    done = len(rows) - len(open_)
    sentence = f"You have {len(open_)} open {'task' if len(open_) == 1 else 'tasks'} ({done} done)."
    lines = [
        f"- {t.title} [{t.status or 'todo'}]" + (f", due {_when(t.due_date)}" if t.due_date else "")
        for t in open_
    ]
    return len(open_), sentence, "Your open tasks:", lines


def _projects(db: Session, uid: str, msg: str):
    rows = db.query(Project).filter(Project.user_id == uid).all()
    by = Counter((r.status or "Planning") for r in rows)
    breakdown = ", ".join(f"{v} {k}" for k, v in by.most_common())
    sentence = f"You have {_plural(len(rows), 'project')}" + (f" ({breakdown})." if rows else ".")
    lines = [
        f"- {r.title} [{r.status or 'Planning'}]"
        + (f" - {', '.join((r.tech_stack or [])[:4])}" if r.tech_stack else "")
        for r in rows
    ]
    return len(rows), sentence, "Your projects:", lines


def _exams(db: Session, uid: str, msg: str):
    items: List[Tuple[Optional[date], str]] = []
    courses = {c.id: c for c in db.query(Course).filter(Course.user_id == uid).all()}
    for e in db.query(Exam).filter(Exam.user_id == uid, Exam.status != "completed").all():
        c = courses.get(e.course_id)
        name = c.name if c else "Exam"
        extra = "".join([f" at {e.exam_time}" if e.exam_time else "", f", venue {e.venue}" if e.venue else ""])
        items.append((e.exam_date, f"- {name}: {e.exam_type or 'Exam'} on {_when(e.exam_date)}{extra}"))
    for a in db.query(Academic).filter(Academic.user_id == uid, Academic.done.isnot(True)).all():
        if a.exam_date:
            items.append((a.exam_date, f"- {a.subject}: exam on {_when(a.exam_date)} [priority {a.priority or 'med'}]"))
    items.sort(key=lambda x: (x[0] is None, x[0] or date.max))
    lines = [t for _, t in items]

    header = "Your upcoming exams:"
    sentence = f"You have {_plural(len(lines), 'upcoming exam')}."
    # If they asked about courses/subjects specifically, list those instead.
    if re.search(r"\bcourses?\b|\bsubjects?\b", msg) and not re.search(r"\bexams?\b", msg):
        rows = list(courses.values())
        sentence = f"You have {_plural(len(rows), 'course')}."
        header = "Your courses:"
        lines = [
            f"- {c.name}" + (f" ({c.code})" if c.code else "") + (f" - {c.faculty}" if c.faculty else "")
            for c in rows
        ]
        return len(rows), sentence, header, lines
    return len(lines), sentence, header, lines


def _requests(db: Session, uid: str, msg: str):
    rows = db.query(ClientRequest).filter(ClientRequest.user_id == uid).all()
    open_ = [r for r in rows if (r.status or "New") not in ("Won", "Declined")]
    sentence = f"You have {_plural(len(open_), 'open client request')} ({len(rows)} total)."
    lines = [
        f"- {r.client}: {(r.ask or '').strip()[:80]} [{r.status or 'New'}]" + (f", price {r.price}" if r.price else "")
        for r in rows
    ]
    return len(open_), sentence, "Your client requests:", lines


def _outbox(db: Session, uid: str, msg: str):
    rows = db.query(OutboxItem).filter(OutboxItem.user_id == uid, OutboxItem.status == "pending").all()
    sentence = f"You have {_plural(len(rows), 'item')} awaiting approval in Outbox."
    lines = []
    for r in rows:
        p = r.payload or {}
        lines.append(f"- {r.channel or 'email'} to {p.get('to') or 'unknown'}: {p.get('subject') or '(no subject)'}")
    return len(rows), sentence, "Awaiting your approval:", lines


def _profile(db: Session, uid: str, msg: str):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        return 0, "I couldn't find your profile.", "", []
    fields = [("Name", u.name), ("Degree", u.degree), ("Branch", u.branch),
              ("CGPA", u.cgpa if u.cgpa is not None else None), ("GitHub", u.github),
              ("Skills", u.skills), ("Highlight", u.highlight)]
    lines = [f"- {k}: {v if v not in (None, '') else 'not set yet'}" for k, v in fields]
    return 1, "Here is your profile.", "Your profile:", lines


def _deadlines(db: Session, uid: str, msg: str):
    items: List[Tuple[date, str]] = []
    for a in db.query(Application).filter(Application.user_id == uid, Application.deadline.isnot(None)).all():
        if (a.status or "To Apply") in ("Applied", "Offer", "Rejected"):
            continue
        items.append((a.deadline, f"- Application: {a.company} - {a.role}, {_when(a.deadline)}"))
    for t in db.query(Task).filter(Task.user_id == uid, Task.due_date.isnot(None)).all():
        if (t.status or "todo") != "done":
            items.append((t.due_date, f"- Task: {t.title}, {_when(t.due_date)}"))
    for e in db.query(Exam).filter(Exam.user_id == uid, Exam.exam_date.isnot(None), Exam.status != "completed").all():
        c = db.query(Course).filter(Course.id == e.course_id).first()
        items.append((e.exam_date, f"- Exam: {c.name if c else 'Exam'}, {_when(e.exam_date)}"))
    for a in db.query(Academic).filter(Academic.user_id == uid, Academic.exam_date.isnot(None), Academic.done.isnot(True)).all():
        items.append((a.exam_date, f"- Exam: {a.subject}, {_when(a.exam_date)}"))
    items.sort(key=lambda x: x[0])
    lines = [t for _, t in items]
    return len(lines), f"You have {_plural(len(lines), 'upcoming deadline')}.", "Your deadlines (soonest first):", lines


_HANDLERS: Dict[str, Callable] = {
    "deadlines": _deadlines, "applications": _applications, "tasks": _tasks, "projects": _projects,
    "exams": _exams, "requests": _requests, "outbox": _outbox, "profile": _profile,
}


# ------------------------------------------------------------------ entry point
def answer(db: Session, user_id: str, message: str) -> Optional[dict]:
    """Returns {"reply": str, "payload": dict} or None if this isn't a direct-DB question."""
    msg = " ".join((message or "").lower().split())
    if not msg or _WRITE.search(msg) or not _READ.search(msg) or _CONTENT.search(msg):
        return None
    if not (_PERSONAL.search(msg) or len(msg.split()) <= 5):
        return None

    topics = [k for k, rx in _TOPICS if rx.search(msg)]
    if not topics:
        return None
    # "deadline" questions are answered by the aggregate view only.
    if "deadlines" in topics:
        topics = ["deadlines"]
    topics = topics[:MAX_TOPICS]

    uid = str(user_id)
    count_only = bool(_COUNT.search(msg))
    parts: List[str] = []
    counts: Dict[str, int] = {}
    for key in topics:
        n, sentence, header, lines = _HANDLERS[key](db, uid, msg)
        counts[key] = n
        if count_only or not lines:
            parts.append(sentence if lines or count_only else f"{sentence} Nothing to list yet.")
        else:
            parts.append(f"{sentence}\n{header}\n" + "\n".join(_cap(lines)))

    return {
        "reply": "\n\n".join(parts),
        "payload": {"source": "database", "answer_mode": "database", "topics": topics, "counts": counts},
    }
