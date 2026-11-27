import os
os.environ["OPAI_RAG_EMBEDDER"] = "hash"
import uuid
import pytest

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "..", "examples", "corpus")
DATASET = os.path.join(HERE, "..", "examples", "dataset.jsonl")
PG_DSN = os.getenv("OPAI_TEST_PG_DSN")


@pytest.fixture
def pg_store():
    if not PG_DSN:
        pytest.skip("set OPAI_TEST_PG_DSN=postgresql://user:pass@localhost/db to run Postgres tests")
    import psycopg
    from opai_rag_pro.stores.pg import PgVectorStore
    schema = "t_" + uuid.uuid4().hex[:10]
    with psycopg.connect(PG_DSN, autocommit=True) as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in PG_DSN else "?"
    store = PgVectorStore(f"{PG_DSN}{sep}options=-csearch_path%3D{schema},public")
    yield store
    store.close()
    with psycopg.connect(PG_DSN, autocommit=True) as c:
        c.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(params=["sqlite", "chroma", "pg"])
def any_store(request, tmp_path):
    if request.param == "sqlite":
        from opai_rag.store import Store
        yield Store(str(tmp_path / "s.db"))
    elif request.param == "chroma":
        pytest.importorskip("chromadb")
        from opai_rag_pro.stores.chroma import ChromaStore
        yield ChromaStore(str(tmp_path / "chroma"))
    else:
        yield request.getfixturevalue("pg_store")
