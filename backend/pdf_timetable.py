"""PDF timetable -> AI draft -> chat refine -> confirm. Nothing is saved until /confirm."""
import base64, io, json
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Semester, Course, Exam
from agent import groq_client

router = APIRouter(prefix="/v1/timetable/pdf", tags=["timetable-pdf"])
MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_TEXT = 24000

SYSTEM = (
    "You extract a college semester exam timetable into JSON. Schema: "
    '{"semester":{"college":str|null,"degree":str|null,"branch":str|null,"semester_number":int|null,'
    '"academic_year":str|null,"exam_period_start":"YYYY-MM-DD"|null,"exam_period_end":"YYYY-MM-DD"|null},'
    '"courses":[{"code":str|null,"name":str,"credits":number|null,"faculty":str|null,'
    '"exam_date":"YYYY-MM-DD"|null,"exam_time":str|null,"venue":str|null}],"reply":str}. '
    "Never invent data; use null when absent. One entry per course. Dates must be ISO."
)


class DraftCourse(BaseModel):
    code: Optional[str] = None
    name: str
    credits: Optional[float] = None
    faculty: Optional[str] = None
    exam_date: Optional[date] = None
    exam_time: Optional[str] = None
    venue: Optional[str] = None


class DraftSemester(BaseModel):
    college: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    semester_number: Optional[int] = None
    academic_year: Optional[str] = None
    exam_period_start: Optional[date] = None
    exam_period_end: Optional[date] = None


class Draft(BaseModel):
    semester: DraftSemester = DraftSemester()
    courses: List[DraftCourse] = []


class AnalyzeIn(BaseModel):
    pdf_base64: str


class RefineIn(BaseModel):
    draft: Draft
    message: str
    history: List[dict] = []


class ConfirmIn(BaseModel):
    user_id: UUID
    draft: Draft
    semester_id: Optional[UUID] = None


def _pdf_text(b64: str) -> str:
    try:
        from pypdf import PdfReader
        raw = base64.b64decode(b64.split(",")[-1], validate=False)
        if len(raw) > MAX_PDF_BYTES:
            raise HTTPException(413, "PDF too large (max 8 MB)")
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this PDF")
    if len(text.strip()) < 20:
        raise HTTPException(422, "No text found - scanned PDFs are not supported yet")
    return text[:MAX_TEXT]


def _llm(user_prompt: str) -> dict:
    if not groq_client.groq_enabled():
        raise HTTPException(503, "AI is not configured on the server")
    try:
        return groq_client.generate_json(SYSTEM, user_prompt)
    except Exception as e:
        raise HTTPException(502, f"AI analysis failed: {e}")


def _to_draft(data: dict) -> Draft:
    try:
        d = Draft(semester=data.get("semester") or {}, courses=data.get("courses") or [])
    except Exception:
        raise HTTPException(502, "AI returned an unusable timetable")
    seen, out = set(), []
    for c in d.courses:  # de-dupe by code, else name
        k = (c.code or c.name).strip().lower()
        if k and k not in seen:
            seen.add(k); out.append(c)
    d.courses = out
    return d


def _warnings(d: Draft) -> List[dict]:
    w, s = [], d.semester
    by_slot = {}
    for c in d.courses:
        if not c.exam_date:
            w.append({"level": "warn", "text": f"{c.name}: no exam date."}); continue
        if s.exam_period_start and s.exam_period_end and not (s.exam_period_start <= c.exam_date <= s.exam_period_end):
            w.append({"level": "warn", "text": f"{c.name} ({c.exam_date}) is outside the exam period."})
        by_slot.setdefault((c.exam_date, (c.exam_time or "").strip().lower()), []).append(c.name)
    for (dt, _), names in by_slot.items():
        if len(names) > 1:
            w.append({"level": "bad", "text": f"Clash on {dt}: {', '.join(names)}."})
    w.append({"level": "info", "text": f"{len(d.courses)} courses · {sum(1 for c in d.courses if c.exam_date)} exams."})
    return w


@router.post("/analyze")
def analyze(p: AnalyzeIn):
    text = _pdf_text(p.pdf_base64)
    data = _llm("Extract the timetable from this PDF text:\n\n" + text)
    d = _to_draft(data)
    if not d.courses:
        raise HTTPException(422, "No courses found in this PDF")
    return {"draft": d, "warnings": _warnings(d), "reply": data.get("reply") or "Here is what I found. Ask me to change anything, then confirm."}


@router.post("/refine")
def refine(p: RefineIn):
    hist = "\n".join(f"{m.get('role')}: {m.get('text')}" for m in p.history[-6:])
    data = _llm(
        "Current draft JSON:\n" + p.draft.model_dump_json() +
        "\n\nRecent chat:\n" + hist +
        "\n\nUser request: " + p.message +
        "\n\nApply the request. Return the FULL updated draft in the schema; put a one-line answer in \"reply\". "
        "If the user only asks a question, return the draft unchanged."
    )
    d = _to_draft(data) if data.get("courses") else p.draft
    return {"draft": d, "warnings": _warnings(d), "reply": data.get("reply") or "Updated."}


@router.post("/confirm")
def confirm(p: ConfirmIn, db: Session = Depends(get_db)):
    uid, s = str(p.user_id), p.draft.semester
    if not p.draft.courses:
        raise HTTPException(400, "Nothing to create")
    sem = db.query(Semester).filter(Semester.id == str(p.semester_id)).first() if p.semester_id else None
    if not sem:
        sem = db.query(Semester).filter(Semester.user_id == uid, Semester.semester_number == s.semester_number,
                                        Semester.academic_year == s.academic_year).first()
    fields = {k: v for k, v in s.model_dump().items() if v is not None}
    if sem:
        for k, v in fields.items():
            setattr(sem, k, v)
    else:
        db.query(Semester).filter(Semester.user_id == uid, Semester.is_current == True).update({"is_current": False})  # noqa: E712
        sem = Semester(user_id=uid, is_current=True, **fields)
        db.add(sem)
    db.flush()
    existing = db.query(Course).filter(Course.semester_id == sem.id).all()
    n_new = n_exam = 0
    for c in p.draft.courses:
        key = (c.code or c.name).strip().lower()
        row = next((x for x in existing if (x.code or x.name).strip().lower() == key), None)
        if not row:
            row = Course(user_id=uid, semester_id=sem.id, code=c.code, name=c.name, credits=c.credits,
                         faculty=c.faculty, source="pdf_import")
            db.add(row); db.flush(); existing.append(row); n_new += 1
        else:
            row.credits = c.credits if c.credits is not None else row.credits
            row.faculty = c.faculty or row.faculty
        if c.exam_date:
            ex = db.query(Exam).filter(Exam.course_id == row.id, Exam.exam_type == "End Semester").first()
            if not ex:
                ex = Exam(user_id=uid, course_id=row.id, exam_type="End Semester", status="confirmed")
                db.add(ex)
            ex.exam_date, ex.exam_time, ex.venue, ex.status = c.exam_date, c.exam_time, c.venue, "confirmed"
            n_exam += 1
    db.commit()
    return {"semester_id": sem.id, "courses": len(p.draft.courses), "new_courses": n_new, "exams": n_exam}
