"""Per-resource ownership for routes that address a row by id only (/v1/tasks/{id}, /v1/resumes/{id}, ...).

Those routes carry no user_id, so the token check alone cannot tell whose row it is: any signed-in user could
read, edit or delete anyone's row by UUID. `forbidden(path, uid)` looks the row up and says whether it belongs to
somebody else. Rows that do not exist return False so the handler still answers its normal 404. Shared rows
(owner column NULL, e.g. seeded opportunities) are not treated as someone else's."""
from __future__ import annotations

import re
from typing import Optional

_ID = r"([0-9a-fA-F-]{32,36})"
# (path regex, model name, owner resolution). owner "user_id" = column on the row; ("course", ...) = through its Course.
_TABLE = [
    (rf"^/v1/applications/{_ID}", "Application", "user_id"),
    (rf"^/v1/projects/{_ID}", "Project", "user_id"),
    (rf"^/v1/tasks/{_ID}", "Task", "user_id"),
    (rf"^/v1/academics/{_ID}", "Academic", "user_id"),
    (rf"^/v1/outreach/{_ID}", "OutreachHistory", "user_id"),
    (rf"^/v1/requests/{_ID}", "ClientRequest", "user_id"),
    (rf"^/v1/outbox/{_ID}", "OutboxItem", "user_id"),
    (rf"^/v1/resumes/{_ID}", "Resume", "user_id"),
    (rf"^/v1/memory/items/{_ID}", "MemoryItem", "user_id"),
    (rf"^/v1/semesters/{_ID}", "Semester", "user_id"),
    (rf"^/v1/courses/{_ID}", "Course", "user_id"),
    (rf"^/v1/topics/{_ID}", "Topic", "course"),
    (rf"^/v1/exams/{_ID}", "Exam", "user_id"),
    (rf"^/v1/study-blocks/{_ID}", "StudyBlock", "user_id"),
    (rf"^/v1/opportunities/{_ID}", "Opportunity", "user_id"),
]
_COMPILED = [(re.compile(p), m, how) for p, m, how in _TABLE]


def _owner(db, model_name: str, how: str, rid: str) -> Optional[str]:
    import database as D
    model = getattr(D, model_name, None)
    if model is None:
        return None
    row = db.query(model).filter(model.id == rid).first()
    if row is None:
        return None
    if how == "course":
        c = db.query(D.Course).filter(D.Course.id == row.course_id).first()
        return str(c.user_id).lower() if c is not None and c.user_id else None
    v = getattr(row, "user_id", None)
    return str(v).lower() if v else None


def forbidden(path: str, uid: str) -> bool:
    """True when `path` names a row that exists and belongs to a different user than `uid`."""
    for rx, model_name, how in _COMPILED:
        m = rx.match(path)
        if not m:
            continue
        from database import SessionLocal
        db = SessionLocal()
        try:
            owner = _owner(db, model_name, how, m.group(1))
        finally:
            db.close()
        return owner is not None and owner != str(uid).lower()
    return False
