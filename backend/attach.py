"""Attach & analyze: files / photos / PDFs from any section -> AI analysis. Nothing is stored."""
import base64, io, os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import groq_client

router = APIRouter(prefix="/v1/attach", tags=["attach"])
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 5
MAX_TEXT = 24000
VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

SECTION_HINTS = {
    "applications": "The user tracks internship/job/research applications. Pull out company, role, deadline, requirements and next steps.",
    "opportunities": "The user tracks opportunities. Extract title, org, deadline, eligibility, and whether it is worth applying.",
    "outreach": "The user emails professors/companies for internships. Extract names, labs, research areas, emails, and suggest an outreach angle.",
    "projects": "The user manages software projects. Extract tasks, requirements, risks and a sensible task breakdown.",
    "academics": "The user is a B.Tech student. Extract subjects, topics, exam dates and give a short study plan.",
    "sems": "Exam/course context. Extract course names, codes, exam dates, and weak-risk topics.",
    "requests": "The user is a freelancer. Extract the client's ask, scope, budget/deadline hints and propose a scope summary.",
    "outbox": "The user reviews outgoing drafts. Check tone, clarity and mistakes; suggest improvements.",
    "resume": "Resume review: strengths, gaps, ATS issues, and concrete rewrite suggestions.",
    "today": "Daily planning. Extract actionable items and suggest how to schedule them today.",
    "overview": "General workspace context. Summarize and list action items.",
    "jarvis": "General assistant chat. Answer the question about the attachment directly.",
}
BASE = ("You are OPAI's document analyst. Analyze the attachment(s) for the user. Be concise and structured: "
        "a 2-line summary, key facts, then action items. Never invent details that are not in the file. "
        "If something is unreadable, say so. Reply in the same language as the user's question.")


class AttachFile(BaseModel):
    name: str
    mime: str = ""
    data_base64: str


class AttachRequest(BaseModel):
    section: str = "overview"
    question: Optional[str] = None
    files: List[AttachFile]


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in r.pages)


@router.post("/analyze")
def analyze(req: AttachRequest):
    if not groq_client.groq_enabled():
        raise HTTPException(503, "GROQ_API_KEY is not configured on the backend")
    if not req.files or len(req.files) > MAX_FILES:
        raise HTTPException(400, f"Attach 1 to {MAX_FILES} files")
    texts, images = [], []
    for f in req.files:
        try:
            raw = base64.b64decode(f.data_base64, validate=False)
        except Exception:
            raise HTTPException(400, f"{f.name}: invalid file data")
        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(413, f"{f.name} is larger than 8 MB")
        n, m = f.name.lower(), (f.mime or "").lower()
        if m.startswith("image/"):
            images.append((f.name, m, f.data_base64))
        elif m == "application/pdf" or n.endswith(".pdf"):
            try:
                t = _pdf_text(raw).strip()
            except Exception:
                raise HTTPException(400, f"{f.name}: could not read PDF")
            if not t:
                raise HTTPException(422, f"{f.name}: no selectable text (scanned PDF). Upload pages as photos instead.")
            texts.append((f.name, t))
        else:
            texts.append((f.name, raw.decode("utf-8", errors="replace")))
    budget = MAX_TEXT // max(len(texts), 1)
    doc = "\n\n".join(f"=== {n} ===\n{t[:budget]}" for n, t in texts)
    q = (req.question or "").strip() or "Analyze this and tell me what matters."
    system = BASE + " " + SECTION_HINTS.get(req.section, "")
    try:
        if images:
            content = [{"type": "text", "text": f"{q}\n\n{doc}".strip()}]
            for _, m, b in images:
                content.append({"type": "image_url", "image_url": {"url": f"data:{m};base64,{b}"}})
            out = groq_client.get_client().chat.completions.create(
                model=VISION_MODEL,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
                temperature=0.2,
            ).choices[0].message.content or ""
        else:
            out = groq_client.generate_text(system, f"{q}\n\n{doc}")
    except Exception as e:
        raise HTTPException(502, f"AI analysis failed: {e}")
    return {"analysis": out, "files": [f.name for f in req.files]}
