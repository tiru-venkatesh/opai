"""File parsing: PDF (per page), DOCX, TXT, MD, CSV -> [{"page": int|None, "text": str}]."""
from __future__ import annotations

import csv
import io
import os
from typing import List

ALLOWED = {".pdf", ".docx", ".txt", ".md", ".markdown", ".csv"}
MAX_FILE_BYTES = int(os.getenv("OPAI_RAG_MAX_FILE_MB", "10")) * 1024 * 1024


class ParseError(ValueError):
    """Message is safe to show to the user."""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeError:
            continue
    return data.decode("utf-8", "replace")


def parse_file(filename: str, data: bytes) -> List[dict]:
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED:
        raise ParseError(f"unsupported file type '{ext or filename}' (use PDF, DOCX, TXT, MD or CSV)")
    if not data:
        raise ParseError("file is empty")
    if len(data) > MAX_FILE_BYTES:
        raise ParseError(f"file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                try:
                    ok = reader.decrypt("")
                except Exception:
                    ok = 0
                if not ok:
                    raise ParseError("PDF is password-protected")
            pages = [{"page": i + 1, "text": (pg.extract_text() or "").strip()} for i, pg in enumerate(reader.pages)]
            pages = [p for p in pages if p["text"]]
            if not pages:
                raise ParseError("no extractable text (scanned PDF? run OCR first)")
            return pages
        if ext == ".docx":
            import docx

            d = docx.Document(io.BytesIO(data))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            text = "\n\n".join(parts)
        elif ext == ".csv":
            rows = list(csv.reader(io.StringIO(_decode(data))))
            if not rows:
                raise ParseError("CSV has no rows")
            head, body = rows[0], rows[1:]
            lines = (
                [", ".join(f"{h}: {v}" for h, v in zip(head, r) if v.strip()) for r in body]
                if body
                else [", ".join(head)]
            )
            text = "\n".join(l for l in lines if l)
        else:
            text = _decode(data)
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"could not read file ({type(e).__name__})")
    text = text.replace("\x00", "").strip()
    if not text:
        raise ParseError("no text found in file")
    return [{"page": None, "text": text}]
