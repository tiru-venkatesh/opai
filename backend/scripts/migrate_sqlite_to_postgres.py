#!/usr/bin/env python3
"""Copy an OPAI SQLite database into Postgres. Safe to re-run: rows that already exist are skipped (ON CONFLICT DO NOTHING).

    cd backend
    python scripts/migrate_sqlite_to_postgres.py --source ./opa.db --target postgresql://user:pass@host:5432/db --dry-run
    python scripts/migrate_sqlite_to_postgres.py --source ./opa.db --target postgresql://user:pass@host:5432/db

What it does
  1. creates any missing tables in Postgres from the app's own models (same as the app does on boot);
  2. copies every table in foreign-key order, in batches, keeping ids exactly as they are (all keys are UUID strings,
     so there are no sequences to reset);
  3. strips NUL characters (SQLite allows them, Postgres rejects them);
  4. rows that Postgres refuses (e.g. orphans whose parent row was deleted while SQLite foreign keys were off) are skipped
     one by one and listed at the end, never silently dropped;
  5. compares row counts per table and exits non-zero if anything is missing other than the listed skipped rows.
Stop the app (or put it in maintenance) while you run it, then point DATABASE_URL at Postgres and start the app.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict


def _clean(v):
    if isinstance(v, str):
        return v.replace("\x00", "")
    if isinstance(v, list):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {_clean(k): _clean(x) for k, x in v.items()}
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="./opa.db", help="path to the SQLite file (default ./opa.db)")
    ap.add_argument("--target", default=os.getenv("DATABASE_URL", ""), help="Postgres URL (default: $DATABASE_URL)")
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true", help="read and count only; write nothing")
    a = ap.parse_args(argv)

    target = a.target.strip()
    if target.startswith("postgres://"):
        target = "postgresql+psycopg2://" + target[len("postgres://"):]
    elif target.startswith("postgresql://"):
        target = "postgresql+psycopg2://" + target[len("postgresql://"):]
    if not target.startswith("postgresql"):
        print("error: --target must be a postgresql:// URL", file=sys.stderr)
        return 2
    if not os.path.exists(a.source):
        print(f"error: source file {a.source} not found", file=sys.stderr)
        return 2

    os.environ["DATABASE_URL"] = target                   # database.py binds its engine at import time
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import database as D
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    src = create_engine("sqlite:///" + os.path.abspath(a.source), connect_args={"check_same_thread": False})
    dst = D.engine
    if not a.dry_run:
        D.Base.metadata.create_all(bind=dst)
        try:
            import feedback_api  # noqa: F401  (creates feedback_items / feedback_votes with its own raw SQL at import)
        except Exception as e:
            print(f"warning: could not import feedback_api ({e}); feedback tables will be reported as missing")

    src_tables = set(__import__("sqlalchemy").inspect(src).get_table_names())
    skipped = defaultdict(list)
    report = []
    import sqlalchemy as sa
    src_meta = sa.MetaData()
    extras = sorted(n for n in src_tables if n not in D.Base.metadata.tables and not n.startswith("sqlite_"))
    if extras:
        src_meta.reflect(bind=src, only=extras)
    dst_meta = sa.MetaData()
    if extras and not a.dry_run:
        dst_meta.reflect(bind=dst, only=[n for n in extras if sa.inspect(dst).has_table(n)])

    def copy_table(sc, t_src, t_dst, label):
        n_src = sc.execute(select(func.count()).select_from(t_src)).scalar() or 0
        if t_dst is None and not a.dry_run:
            report.append((label, n_src, 0, "table missing in Postgres"))
            return
        if n_src and not a.dry_run:
            cols = [c.name for c in t_src.columns if c.name in t_dst.columns]
            res = sc.execution_options(stream_results=True).execute(select(*[t_src.c[c] for c in cols]))
            while True:
                rows = res.fetchmany(a.batch)
                if not rows:
                    break
                batch = [{k: _clean(v) for k, v in r._mapping.items()} for r in rows]
                try:
                    with dst.begin() as dc:
                        dc.execute(pg_insert(t_dst).on_conflict_do_nothing(), batch)
                except Exception:                              # a bad row must not sink the whole batch
                    for row in batch:
                        try:
                            with dst.begin() as dc:
                                dc.execute(pg_insert(t_dst).on_conflict_do_nothing(), [row])
                        except Exception as e:
                            pk = ",".join(str(row.get(c.name)) for c in t_src.primary_key.columns) or str(next(iter(row.values())))
                            skipped[label].append((pk, str(e).splitlines()[0][:110]))
        with dst.connect() as dc:
            n_dst = 0 if a.dry_run else (dc.execute(select(func.count()).select_from(t_dst)).scalar() or 0)
        report.append((label, n_src, n_dst, ""))

    with src.connect() as sc:
        for t in D.Base.metadata.sorted_tables:                 # parents before children
            if t.name not in src_tables:
                report.append((t.name, 0, 0, "not in source"))
                continue
            copy_table(sc, t, t, t.name)
        for t in src_meta.sorted_tables:                        # tables created outside the models (e.g. feedback)
            copy_table(sc, t, dst_meta.tables.get(t.name), t.name + "  (extra)")

    print(f"{'table':32}{'source':>9}{'target':>9}")
    bad = 0
    for name, ns, nd, note in report:
        if ns == 0 and nd == 0 and not note:
            continue
        flag = ""
        if not a.dry_run and (note.startswith("table missing") or (not note and nd < ns - len(skipped.get(name, [])))):
            flag, bad = "  <-- MISSING ROWS", bad + 1
        print(f"{name:32}{ns:>9}{nd if not a.dry_run else '-':>9}  {note}{flag}")
    for name, rows in skipped.items():
        print(f"\nskipped {len(rows)} row(s) in {name}:")
        for pk, why in rows[:20]:
            print(f"   id={pk}: {why}")
    if a.dry_run:
        print("\ndry run: nothing was written.")
    elif bad:
        print("\nFAILED: some tables have fewer rows than the source (see above).")
        return 1
    else:
        print("\nOK: every source row is in Postgres" + (f" except {sum(map(len, skipped.values()))} skipped above." if skipped else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
