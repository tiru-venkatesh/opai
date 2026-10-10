"""Bulk-import resume files from a folder.

  cd backend && python import_resumes_dir.py <folder> <user_id> [--reference]

Use --reference for resumes that are NOT yours (sample/best resumes). They are stripped of emails, phone numbers
and links, kept out of your matches and tailoring, and used only as anonymous statistics.
Do not commit or deploy a folder of other people's resumes.
"""
import io
import sys
from pathlib import Path

from database import SessionLocal, init_db
import resume_lab_api as L


def text_of(path: Path) -> str:
    data = path.read_bytes()
    low = path.suffix.lower()
    if low == ".pdf":
        return L.extract_pdf_text(data)
    if low == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    return data.decode("utf-8", "ignore")


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    folder, uid = Path(argv[1]), argv[2]
    kind = "reference" if "--reference" in argv else "own"
    init_db()
    with SessionLocal() as db:
        L._user(db, uid)
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() not in (".pdf", ".docx", ".txt", ".md"):
                continue
            try:
                t = L.clean_pdf_text(text_of(f)).strip()
                out = L._add_one(db, uid, f.stem[:80], None, t[:40000], kind) if len(t) >= 80 else {"skipped": {"reason": "too little text"}}
            except Exception as e:  # keep going on one bad file
                out = {"skipped": {"reason": f"{type(e).__name__}: {e}"}}
            print(f.name, "->", "added" if "created" in out else "skipped: " + out["skipped"]["reason"])
        L.sync_bank(db, uid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
