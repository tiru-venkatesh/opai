"""One-time cleanup: delete leftover guest accounts and everything they own.

Guest mode no longer exists, but accounts created by the old /v1/auth/guest
endpoint (email guest-<12 hex>@opa.local) may still be in the database.

Usage (from backend/):
  python purge_guests.py             # dry run: shows what WOULD be deleted
  python purge_guests.py --apply     # actually deletes (SQLite is backed up first)

Works on whatever DATABASE_URL points at (SQLite or Postgres). User-owned
tables are discovered from the real database schema, so newer tables are
covered too. Only accounts matching the exact guest email pattern are touched;
add --email to include other specific accounts.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime

from sqlalchemy import MetaData, delete, func, or_, select

from database import DATABASE_URL, engine

GUEST_RE = re.compile(r"^guest-[0-9a-f]{12}@opa\.local$")


def run(apply: bool, extra_emails: list[str]) -> dict:
    meta = MetaData()
    meta.reflect(bind=engine)
    users = meta.tables["users"]

    with engine.connect() as con:
        rows = con.execute(select(users.c.id, users.c.email)).all()
    extra = {e.lower() for e in extra_emails}
    ids = [r.id for r in rows if GUEST_RE.match(r.email or "") or (r.email or "").lower() in extra]
    if not ids:
        return {"guest_users": 0, "applied": apply, "note": "nothing to delete"}

    memo: dict = {}

    def owned(table):
        """SQL condition selecting rows of `table` that belong to the doomed users, or None."""
        if table.name in memo:
            return memo[table.name]
        memo[table.name] = None  # guards against FK cycles
        parts = []
        for fk in table.foreign_keys:
            if (fk.ondelete or "").upper() == "SET NULL":
                continue  # a reference, not ownership
            parent = fk.column.table
            if parent is users:
                parts.append(fk.parent.in_(ids))
            elif parent is not table:
                sub = owned(parent)
                if sub is not None:
                    pk = list(parent.primary_key.columns)[0]
                    parts.append(fk.parent.in_(select(pk).where(sub)))
        memo[table.name] = or_(*parts) if parts else None
        return memo[table.name]

    plan = []
    for t in reversed(meta.sorted_tables):  # children before parents
        if t is users:
            continue
        cond = owned(t)
        if cond is not None:
            plan.append((t, cond))

    report = {"guest_users": len(ids), "applied": apply, "rows": {}}
    with engine.connect() as con:
        for t, cond in plan:
            n = con.execute(select(func.count()).select_from(t).where(cond)).scalar()
            if n:
                report["rows"][t.name] = n

    if not apply:
        return report

    if DATABASE_URL.startswith("sqlite"):
        path = DATABASE_URL.split("sqlite:///", 1)[-1]
        backup = f"{path}.before-guest-purge-{datetime.now():%Y%m%d%H%M%S}.bak"
        shutil.copy2(path, backup)
        report["backup"] = backup

    with engine.begin() as con:
        for t, cond in plan:
            con.execute(delete(t).where(cond))
        con.execute(delete(users).where(users.c.id.in_(ids)))
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="really delete (default is a dry run)")
    ap.add_argument("--email", action="append", default=[], help="also purge this exact account (repeatable)")
    args = ap.parse_args()
    print(json.dumps(run(args.apply, args.email), indent=2, default=str))


if __name__ == "__main__":
    main()
