"""OPAI database audit/repair utility.

Usage:
  python db_maintenance.py audit
  python db_maintenance.py repair --email you@example.com --name "Your Name"

The repair command is intentionally conservative: it fixes ownership/data
contamination discovered in a development SQLite database, removes obvious
foreign demo records, and refuses to invent application data.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).with_name("opa.db")

USER_TABLES = [
    "resumes", "document_chunks", "applications", "outreach_history",
    "projects", "tasks", "academics", "daily_plans", "client_requests",
    "outbox_items", "user_memory", "memory_items", "agent_activity_log",
    "semesters", "sems_courses", "sems_exams", "sems_study_blocks",
]


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def audit(path: Path) -> dict:
    con = connect(path)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    counts = {}
    for t in tables:
        counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]

    users = [dict(r) for r in con.execute("SELECT id,email,name,branch,degree,cgpa FROM users ORDER BY email")]
    foreign_keys = con.execute("PRAGMA foreign_key_check").fetchall()

    integrity = []
    for t in USER_TABLES:
        if t not in tables:
            continue
        cols = {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
        if "user_id" not in cols:
            continue
        bad = con.execute(f'''SELECT COUNT(*) FROM "{t}" x
            LEFT JOIN users u ON u.id = x.user_id
            WHERE x.user_id IS NOT NULL AND u.id IS NULL''').fetchone()[0]
        if bad:
            integrity.append({"table": t, "orphan_user_rows": bad})

    report = {
        "database": str(path),
        "tables": tables,
        "counts": counts,
        "users": users,
        "foreign_key_violations": len(foreign_keys),
        "orphan_user_rows": integrity,
    }
    con.close()
    return report


def delete_user_scoped_rows(con: sqlite3.Connection, user_id: str) -> None:
    # Delete explicit children first so this remains safe even on older DB files
    # that had foreign_keys disabled when those rows were created.
    for t in [
        "document_chunks", "resumes", "outreach_history", "sems_study_blocks",
        "sems_exams", "sems_topics", "sems_courses", "tasks", "applications",
        "academics", "daily_plans", "client_requests", "outbox_items",
        "memory_items", "user_memory", "agent_activity_log", "projects", "semesters",
    ]:
        if t == "sems_topics":
            con.execute(
                "DELETE FROM sems_topics WHERE course_id IN (SELECT id FROM sems_courses WHERE user_id=?)",
                (user_id,),
            )
            continue
        if t == "sems_exams":
            con.execute(
                "DELETE FROM sems_exams WHERE course_id IN (SELECT id FROM sems_courses WHERE user_id=?) OR user_id=?",
                (user_id, user_id),
            )
            continue
        if t == "sems_study_blocks":
            con.execute("DELETE FROM sems_study_blocks WHERE user_id=?", (user_id,))
            continue
        if t == "sems_courses":
            con.execute("DELETE FROM sems_courses WHERE user_id=?", (user_id,))
            continue
        con.execute(f'DELETE FROM "{t}" WHERE user_id=?', (user_id,))


def repair(path: Path, email: str, name: str) -> dict:
    backup = path.with_suffix(path.suffix + ".before-repair.bak")
    if not backup.exists():
        shutil.copy2(path, backup)

    con = connect(path)
    users = con.execute("SELECT id,email,name FROM users WHERE email=?", (email,)).fetchall()
    if not users:
        raise SystemExit(f"No user found for {email!r}; repair aborted without modifying the DB.")
    canonical = users[0]
    canonical_id = canonical["id"]

    # Development DB had a second, unrelated identity containing unrelated resume data.
    other_users = con.execute("SELECT id,email,name FROM users WHERE id<>?", (canonical_id,)).fetchall()

    # Preserve the one semester record already present, but attach it to the real
    # account because it is course/semester metadata rather than identity data.
    for row in other_users:
        uid = row["id"]
        semesters = con.execute("SELECT id, college, degree, branch, academic_year, exam_period_start, exam_period_end FROM semesters WHERE user_id=?", (uid,)).fetchall()
        if semesters:
            for sem in semesters:
                con.execute("UPDATE semesters SET user_id=? WHERE id=?", (canonical_id, sem["id"]))
            con.execute("UPDATE sems_study_blocks SET user_id=? WHERE user_id=?", (canonical_id, uid))

        # Remove all other demonstration data, especially the unrelated resume.
        delete_user_scoped_rows(con, uid)
        con.execute("DELETE FROM users WHERE id=?", (uid,))

    con.execute("UPDATE users SET name=? WHERE id=?", (name, canonical_id))

    # The imported semester contains an obvious year typo: an exam period ending
    # in 2007 inside an academic year 2026-27 beginning in 2026. Repair only this
    # mechanically inconsistent value.
    con.execute("""
        UPDATE semesters
           SET exam_period_end='2026-11-30'
         WHERE user_id=?
           AND academic_year='2026-27'
           AND exam_period_start='2026-11-23'
           AND exam_period_end='2007-11-30'
    """, (canonical_id,))

    con.commit()
    con.execute("PRAGMA foreign_key_check")
    after = audit(path)
    con.close()
    return {"backup": str(backup), "canonical_user_id": canonical_id, "after": after}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["audit", "repair"])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--email")
    ap.add_argument("--name")
    args = ap.parse_args()
    if args.command == "audit":
        print(json.dumps(audit(args.db), indent=2, default=str))
        return
    if not args.email or not args.name:
        ap.error("repair requires --email and --name")
    print(json.dumps(repair(args.db, args.email, args.name), indent=2, default=str))

if __name__ == "__main__":
    main()
