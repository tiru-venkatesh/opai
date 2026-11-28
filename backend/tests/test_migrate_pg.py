"""SQLite -> Postgres copy. Needs a throwaway Postgres: OPAI_TEST_PG=postgresql://user:pass@localhost:5432/opai_mig_test
(skipped otherwise). The target database is wiped first: never point this at real data."""
import os
import sqlite3
import subprocess
import sys

import pytest

PG = os.getenv("OPAI_TEST_PG", "")
pytestmark = pytest.mark.skipif(not PG, reason="set OPAI_TEST_PG to run the Postgres migration test")


def test_copy_is_complete_idempotent_and_reports_orphans(tmp_path):
    import psycopg2
    src = tmp_path / "src.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{src}"}
    subprocess.run([sys.executable, "-c", "import database as D; D.init_db()"], check=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)))
    c = sqlite3.connect(src)
    c.execute("INSERT INTO users (id,email,name) VALUES ('u1','a@b.c',?)", ("A\x00B",))
    c.execute("INSERT INTO document_chunks (id,user_id,source_type,content) VALUES ('c1','u1','resume','ok')")
    c.execute("INSERT INTO document_chunks (id,user_id,source_type,content) VALUES ('c2','ghost','resume','orphan')")
    c.commit()
    c.close()
    pg = psycopg2.connect(PG)
    pg.autocommit = True
    pg.cursor().execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    cmd = [sys.executable, "scripts/migrate_sqlite_to_postgres.py", "--source", str(src), "--target", PG]
    cwd = os.path.dirname(os.path.dirname(__file__))
    for _ in range(2):                                     # second run must change nothing
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        assert r.returncode == 0, r.stdout + r.stderr
    cur = pg.cursor()
    cur.execute("SELECT name FROM users WHERE id='u1'")
    assert cur.fetchone()[0] == "AB"                       # NUL stripped
    cur.execute("SELECT id FROM document_chunks ORDER BY id")
    assert [x[0] for x in cur.fetchall()] == ["c1"]         # orphan not copied...
    assert "c2" in r.stdout                                 # ...but reported, never silent
