"""Public entry points: generate / get-or-create a brief of any type."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from . import BRIEF_TYPES, core
from .builders import BUILDERS


def generate(db: Session, uid: str, btype: str, params: Optional[Dict[str, Any]] = None, narrative: bool = False) -> Dict[str, Any]:
    if btype not in BUILDERS:
        raise core.BriefError(422, f"Unknown brief type '{btype}'. Use one of: {', '.join(BRIEF_TYPES)}")
    params = {k: v for k, v in (params or {}).items() if v is not None}
    ctx = core.Ctx(db, uid, btype, params)
    res = BUILDERS[btype](ctx)
    scope, expires = res.pop("_scope"), res.pop("_expires")
    out = core.persist(ctx, res, scope_key=scope, expires_at=expires)
    return core.add_narrative(db, out) if narrative else out


def get_or_create(db: Session, uid: str, btype: str, scope_key: str, params: Optional[Dict[str, Any]] = None, narrative: bool = False) -> Dict[str, Any]:
    row = core.latest(db, uid, btype, scope_key)
    if row:
        if row.status == "generated":
            row.status = "shown"
            db.commit()
        return core.serialize(db, row)
    return generate(db, uid, btype, params, narrative)


def refresh(db: Session, uid: str, brief_id: str, narrative: bool = False) -> Dict[str, Any]:
    row = core.get_row(db, uid, brief_id)
    return generate(db, uid, row.type, dict(row.params or {}), narrative)


def daily_scope(day: Optional[date] = None) -> str:
    return (day or date.today()).isoformat()
