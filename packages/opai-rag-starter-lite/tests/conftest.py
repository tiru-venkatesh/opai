import os
os.environ["OPAI_RAG_EMBEDDER"] = "hash"  # keep tests offline and fast
import pytest
from opai_rag import RAG

HANDBOOK = open(os.path.join(os.path.dirname(__file__), "..", "examples", "handbook.md"), "rb").read()


@pytest.fixture
def rag(tmp_path):
    r = RAG(str(tmp_path / "t.db"), llm=None)
    r._llm_resolved = True  # force extractive unless a test sets an llm
    yield r
    r.close()
