"""List, download and delete the caller's stored original uploads. See file_store.py (off by default)."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

import file_store
from database import User, get_db

router = APIRouter()


def _user(db: Session, user_id: str) -> str:
    uid = (user_id or "").strip().lower()
    if not db.query(User).filter(User.id == uid).first():
        raise HTTPException(404, "User not found")
    return uid


@router.get("/v1/files")
def list_files(user_id: str, kind: Optional[str] = None, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    if not file_store.enabled():
        return {"enabled": False, "files": [], "usage": None}
    return {"enabled": True, "files": file_store.list_files(db, uid, kind if kind in file_store.KINDS else None),
            "usage": file_store.usage(db, uid)}


@router.get("/v1/files/{file_id}/download")
def download(file_id: str, user_id: str, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    if not file_store.enabled():
        raise HTTPException(404, "File storage is not turned on")
    row = file_store.get_row(db, uid, file_id)
    if not row:
        raise HTTPException(404, "File not found")
    try:
        data = file_store.read(row)
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "Could not read the stored file right now. Try again in a moment.")
    safe = re.sub(r'[^\w.\- ]', "_", row.filename)[:120] or "file"
    return Response(content=data, media_type=file_store.content_type_for(row.filename), headers={
        "Content-Disposition": f'attachment; filename="{safe}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.delete("/v1/files/{file_id}")
def remove(file_id: str, user_id: str, db: Session = Depends(get_db)):
    uid = _user(db, user_id)
    if not file_store.delete(db, uid, file_id):
        raise HTTPException(404, "File not found")
    return {"deleted": True, "usage": file_store.usage(db, uid) if file_store.enabled() else None}
