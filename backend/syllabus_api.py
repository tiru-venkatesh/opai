"""Academics intake: the user gives a syllabus file (or pasted text) and the course map + RAG build themselves.

  upload/paste -> parse -> extract units/topics -> create Course + Topic rows -> index the whole document and one
  chunk per unit (tagged course/topic) into document_chunks -> return a draft + the questions KARNA still needs answered.
Nothing is silently final: exams are only created from the user's answers (/answers), as 'tentative'.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

import rag_api
import rag_service as rag
from database import Course, Exam, Semester, Topic, User, get_db
from syllabus_parse import course_labels, extract_structure, pick_course, split_courses

log = logging.getLogger("opa.syllabus")
router = APIRouter(prefix="/v1/academics", tags=["academics-intake"])
SYLLABUS = "syllabus"


def _user(db: Session, uid: str) -> str:
    uid = str(uid)
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


def _semester(db: Session, uid: str) -> Semester:
    s = db.query(Semester).filter(Semester.user_id == uid, Semester.is_current == True).first()  # noqa: E712
    if not s:
        s = Semester(user_id=uid, is_current=True)
        db.add(s)
        db.flush()
    return s


def _course(db: Session, uid: str, sem: Semester, name: str, code: Optional[str], credits: Optional[float]) -> Course:
    q = db.query(Course).filter(Course.user_id == uid, Course.semester_id == sem.id).all()
    for c in q:
        if (code and c.code and c.code.lower() == code.lower()) or c.name.strip().lower() == name.strip().lower():
            if code and not c.code:
                c.code = code
            return c
    c = Course(user_id=uid, semester_id=sem.id, name=name.strip()[:120], code=code, credits=credits, source="syllabus")
    db.add(c)
    db.flush()
    return c


def build_from_text(db: Session, uid: str, text: str, filename: str, course_name: str = "",
                    course_code: str = "") -> Dict:
    courses = split_courses(text)
    if len(courses) >= 3:                                     # a whole booklet: build ONE course, never the whole book
        i = pick_course(courses, course_name)
        if i is None:
            labels = course_labels(courses)
            return {"ok": True, "needs_choice": True, "filename": filename,
                    "message": f"This file has {len(courses)} courses. Which one should I build?",
                    "courses": [{"label": l, "title": c["title"], "year_sem": c["year_sem"]}
                                for l, c in zip(labels, courses)]}
        course_name = course_labels(courses)[i]
        text = courses[i]["text"]
    text = text.replace("\f", "\n")
    st = extract_structure(text)
    name = (course_name or "").strip() or os.path.splitext(filename)[0].replace("_", " ").strip() or "New course"
    code = (course_code or "").strip() or st["code"]
    sem = _semester(db, uid)
    course = _course(db, uid, sem, name, code, st["credits"])

    existing = {(t.unit or "", t.name.lower()) for t in db.query(Topic).filter(Topic.course_id == course.id).all()}
    created = 0
    for u in st["units"]:
        per = max(30, min(120, (u["hours"] * 60 // max(1, len(u["topics"]))) if u.get("hours") else 60))
        for t in u["topics"]:
            if (u["unit"], t.lower()) in existing:
                continue
            db.add(Topic(course_id=course.id, unit=u["unit"], name=t[:200], estimated_minutes=per))
            created += 1
    db.commit()

    # RAG self-build: whole document (citable, page-aware) + one tagged chunk per unit
    doc = rag_api.ingest(db, uid, f"Syllabus: {name}", [{"page": None, "text": text}], kind=rag.UPLOAD)
    for u in st["units"]:
        body = f"Course {name}" + (f" ({code})" if code else "") + f". {u['unit']}. Topics: " + "; ".join(u["topics"]) + "."
        rag.safe(rag.index_source, db, uid, SYLLABUS, f"{course.id}:{u['unit']}", body,
                 title=f"Syllabus: {name} / {u['unit']}", meta={"course_id": course.id, "unit": u["unit"]})
    rag.safe(rag.index_course, db, course)

    return {"course_id": course.id, "course": name, "code": code, "credits": st["credits"],
            "units": st["units"], "topics_created": created, "chunks_indexed": doc["chunks"],
            "questions": st["questions"]}


@router.post("/syllabus")
async def upload_syllabus(user_id: str = Form(...), course_name: str = Form(""), course_code: str = Form(""),
                          files: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    out = []
    for f in files[:5]:
        fname = os.path.basename(f.filename or "syllabus")[:200]
        try:
            data = await f.read(rag_api.MAX_FILE_BYTES + 1)
            pages = rag_api.parse_file(fname, data)
            text = "\n\f\n".join(p["text"] for p in pages)
            out.append({"ok": True, "filename": fname, **build_from_text(db, uid, text, fname, course_name, course_code)})
        except rag_api.ParseError as e:
            out.append({"ok": False, "filename": fname, "error": str(e)})
        except Exception as e:
            db.rollback()
            log.exception("syllabus build failed for %s", fname)
            out.append({"ok": False, "filename": fname, "error": f"could not build from this file ({type(e).__name__})"})
    return {"results": out}


class SyllabusText(BaseModel):
    user_id: str
    text: str
    course_name: str = ""
    course_code: str = ""


@router.post("/syllabus/text")
def syllabus_from_text(body: SyllabusText, db: Session = Depends(get_db)):
    uid = _user(db, body.user_id)
    if len(body.text.strip()) < 20:
        raise HTTPException(400, "Paste the syllabus text (units and topics)")
    return build_from_text(db, uid, body.text[:rag_api.MAX_DOC_CHARS], body.course_name or "Pasted syllabus",
                           body.course_name, body.course_code)


class Answers(BaseModel):
    user_id: str
    course_id: str
    exam_type: str = "End Semester"
    exam_date: Optional[str] = None          # YYYY-MM-DD
    exam_time: Optional[str] = None
    venue: Optional[str] = None
    weightage: Optional[int] = None
    unit_confidence: Dict[str, int] = {}     # {"Unit 2: Trees": 2}


@router.post("/syllabus/answers")
def save_answers(body: Answers, db: Session = Depends(get_db)):
    """The user's replies to KARNA's clarification questions. Exam stays 'tentative' until they confirm it."""
    uid = _user(db, body.user_id)
    course = db.query(Course).filter(Course.id == body.course_id, Course.user_id == uid).first()
    if not course:
        raise HTTPException(404, "Course not found")
    for unit, conf in (body.unit_confidence or {}).items():
        c = max(1, min(5, int(conf)))
        for t in db.query(Topic).filter(Topic.course_id == course.id, Topic.unit == unit).all():
            t.confidence = c
    exam = None
    if body.exam_date:
        try:
            d = date.fromisoformat(body.exam_date)
        except ValueError:
            raise HTTPException(400, "exam_date must be YYYY-MM-DD")
        exam = db.query(Exam).filter(Exam.course_id == course.id, Exam.exam_type == body.exam_type).first()
        if not exam:
            exam = Exam(user_id=uid, course_id=course.id, exam_type=body.exam_type, status="tentative")
            db.add(exam)
        exam.exam_date, exam.exam_time, exam.venue = d, body.exam_time, body.venue
        if body.weightage:
            exam.weightage = max(1, min(100, body.weightage))
    db.commit()
    rag.safe(rag.index_course, db, course)
    return {"course_id": course.id, "exam_id": exam.id if exam else None, "exam_status": "tentative" if exam else None}
