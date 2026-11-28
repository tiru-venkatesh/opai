"""Optional storage of the ORIGINAL files users upload, so they can download them again.

Off by default: until you set OPAI_FILE_STORE the app behaves exactly as before (files are parsed to text and the
original bytes are thrown away). Because that changes what the privacy policy says, turn it on only after you
have updated privacy.html.

  OPAI_FILE_STORE   off (default) | local (disk, for dev / a persistent volume) | r2 (Cloudflare R2)
  OPAI_FILE_DIR     local mode folder (default ./user_files)
  OPAI_FILE_MAX_MB  largest single file kept (default 10)
  OPAI_FILE_QUOTA_MB  JSON {"free":50,"pro":1000,"max":5000} total stored per user (defaults shown)
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET   (R2_ENDPOINT overrides the URL)

Saving is best effort: a storage problem is logged and never fails the upload itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

log = logging.getLogger("opai.files")

DEFAULT_QUOTA_MB = {"free": 50, "pro": 1000, "max": 5000}
KINDS = ("doc", "syllabus", "resume")
# Only these are sent back with their real type; everything else downloads as an opaque attachment,
# so a stored .html/.svg can never run as a page on our origin.
SAFE_TYPES = {
    ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def mode() -> str:
    m = os.getenv("OPAI_FILE_STORE", "off").strip().lower()
    return m if m in ("local", "r2") else "off"


def enabled() -> bool:
    return mode() != "off"


def max_bytes() -> int:
    try:
        return int(float(os.getenv("OPAI_FILE_MAX_MB", "10")) * 1024 * 1024)
    except ValueError:
        return 10 * 1024 * 1024


def quota_bytes(plan_name: str) -> int:
    table = dict(DEFAULT_QUOTA_MB)
    raw = os.getenv("OPAI_FILE_QUOTA_MB", "").strip()
    if raw:
        try:
            table.update({k: float(v) for k, v in json.loads(raw).items()})
        except (ValueError, TypeError, AttributeError):
            log.warning("OPAI_FILE_QUOTA_MB is not valid JSON; using defaults")
    return int(table.get(plan_name, table["free"]) * 1024 * 1024)


# ---- backends ---------------------------------------------------------------------------------------
class LocalBackend:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _path(self, key: str) -> str:
        p = os.path.abspath(os.path.join(self.root, key))
        if not p.startswith(self.root + os.sep):          # key traversal guard
            raise ValueError("bad storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as fh:
            return fh.read()

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class R2Backend:
    """Cloudflare R2 through its S3-compatible API (boto3)."""

    def __init__(self, client: Any, bucket: str):
        self.c, self.bucket = client, bucket

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.c.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type or "application/octet-stream")

    def get(self, key: str) -> bytes:
        return self.c.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.c.delete_object(Bucket=self.bucket, Key=key)


_backend: Optional[Any] = None


def _make_r2() -> R2Backend:
    try:
        import boto3  # optional dependency, only needed in r2 mode
        from botocore.config import Config
    except ImportError as e:
        raise RuntimeError("OPAI_FILE_STORE=r2 needs boto3 (pip install boto3)") from e
    acct, bucket = os.getenv("R2_ACCOUNT_ID", ""), os.getenv("R2_BUCKET", "")
    key, secret = os.getenv("R2_ACCESS_KEY_ID", ""), os.getenv("R2_SECRET_ACCESS_KEY", "")
    if not (bucket and key and secret and (acct or os.getenv("R2_ENDPOINT"))):
        raise RuntimeError("R2 is not configured (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET)")
    client = boto3.client("s3", endpoint_url=os.getenv("R2_ENDPOINT") or f"https://{acct}.r2.cloudflarestorage.com",
                          aws_access_key_id=key, aws_secret_access_key=secret, region_name="auto",
                          config=Config(signature_version="s3v4", retries={"max_attempts": 3}))
    return R2Backend(client, bucket)


def backend():
    global _backend
    if _backend is None:
        _backend = _make_r2() if mode() == "r2" else LocalBackend(os.getenv("OPAI_FILE_DIR", "user_files"))
    return _backend


def reset_backend(b: Optional[Any] = None) -> None:
    """Tests and config reloads."""
    global _backend
    _backend = b


# ---- helpers ----------------------------------------------------------------------------------------
def _ext(name: str) -> str:
    m = re.search(r"\.[A-Za-z0-9]{1,6}$", name or "")
    return m.group(0).lower() if m else ""


def content_type_for(name: str) -> str:
    return SAFE_TYPES.get(_ext(name), "application/octet-stream")


def _norm(uid: str) -> str:
    return str(uid).strip().lower()


def _row_dict(r) -> Dict[str, Any]:
    return {"id": r.id, "kind": r.kind, "filename": r.filename, "size": r.size or 0,
            "content_type": content_type_for(r.filename), "ref_id": r.ref_id,
            "created_at": r.created_at.isoformat() if r.created_at else None}


def used_bytes(db, uid: str) -> int:
    from sqlalchemy import func
    from database import UserFile
    return int(db.query(func.coalesce(func.sum(UserFile.size), 0)).filter(UserFile.user_id == _norm(uid)).scalar() or 0)


def usage(db, uid: str) -> Dict[str, Any]:
    import metering
    from database import UserFile
    plan = metering.plan_for(db, _norm(uid))["name"]
    n = db.query(UserFile).filter(UserFile.user_id == _norm(uid)).count()
    return {"files": n, "bytes": used_bytes(db, uid), "quota_bytes": quota_bytes(plan), "plan": plan}


# ---- public API -------------------------------------------------------------------------------------
def save(db, user_id: str, kind: str, filename: str, data: bytes, ref_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Keep the original. Returns the stored record, or None when storing is off / skipped / failed. Never raises."""
    if not enabled() or kind not in KINDS or not data:
        return None
    from database import UserFile
    uid, name = _norm(user_id), (os.path.basename(filename or "file")[:200] or "file")
    try:
        if len(data) > max_bytes():
            log.info("file_store: %s skipped (over per-file limit)", name)
            return None
        digest = hashlib.sha256(data).hexdigest()
        same = db.query(UserFile).filter(UserFile.user_id == uid, UserFile.kind == kind, UserFile.filename == name).all()
        for r in same:
            if r.sha256 == digest:                      # identical re-upload: keep the one we have
                if ref_id and r.ref_id != ref_id:
                    r.ref_id = ref_id
                    db.commit()
                return _row_dict(r)
        freed = sum(r.size or 0 for r in same)
        info = usage(db, uid)
        if info["bytes"] - freed + len(data) > info["quota_bytes"]:
            log.info("file_store: %s skipped (storage quota for %s)", name, uid)
            return None
        key = f"u/{uid}/{uuid.uuid4().hex}{_ext(name)}"
        backend().put(key, data, content_type_for(name))
        for r in same:                                  # a newer upload with the same name replaces the old copy
            _remove_object(r.storage_key)
            db.delete(r)
        row = UserFile(user_id=uid, kind=kind, filename=name, content_type=content_type_for(name), size=len(data),
                       sha256=digest, storage_key=key, ref_id=ref_id)
        db.add(row)
        db.commit()
        return _row_dict(row)
    except Exception:  # noqa: BLE001  storage must never break an upload
        log.exception("file_store: could not keep %s", name)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def _remove_object(key: str) -> None:
    try:
        backend().delete(key)
    except Exception:  # noqa: BLE001
        log.exception("file_store: could not delete object %s", key)


def list_files(db, user_id: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    from database import UserFile
    q = db.query(UserFile).filter(UserFile.user_id == _norm(user_id))
    if kind:
        q = q.filter(UserFile.kind == kind)
    return [_row_dict(r) for r in q.order_by(UserFile.created_at.desc()).all()]


def get_row(db, user_id: str, file_id: str):
    """The caller's own file row, or None. Other users' ids look exactly like missing ones."""
    from database import UserFile
    return db.query(UserFile).filter(UserFile.id == file_id, UserFile.user_id == _norm(user_id)).first()


def read(row) -> bytes:
    return backend().get(row.storage_key)


def delete(db, user_id: str, file_id: str) -> bool:
    row = get_row(db, user_id, file_id)
    if not row:
        return False
    _remove_object(row.storage_key)
    db.delete(row)
    db.commit()
    return True


def delete_for_ref(db, user_id: str, ref_id: str) -> int:
    """Drop the stored original when the thing it belongs to (a document, a resume) is deleted."""
    if not enabled() or not ref_id:
        return 0
    from database import UserFile
    try:
        rows = db.query(UserFile).filter(UserFile.user_id == _norm(user_id), UserFile.ref_id == ref_id).all()
        for r in rows:
            _remove_object(r.storage_key)
            db.delete(r)
        db.commit()
        return len(rows)
    except Exception:  # noqa: BLE001
        log.exception("file_store: delete_for_ref failed")
        db.rollback()
        return 0


def delete_all_for_user(db, user_id: str) -> int:
    from database import UserFile
    rows = db.query(UserFile).filter(UserFile.user_id == _norm(user_id)).all()
    for r in rows:
        _remove_object(r.storage_key)
        db.delete(r)
    db.commit()
    return len(rows)
