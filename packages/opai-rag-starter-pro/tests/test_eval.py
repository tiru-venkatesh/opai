import json
import pytest
from opai_rag_pro.eval.harness import load_dataset, run
from opai_rag_pro.eval.cli import main
from conftest import CORPUS, DATASET


def test_sample_dataset_quality_floor():
    r = run(CORPUS, DATASET, k=5, chunk_sizes=(600,))[0]
    assert r["hit_at_5"] >= 0.9 and r["abstain_accuracy"] == 1.0 and r["documents"] == 3


def test_chunk_size_comparison_returns_one_result_each():
    res = run(CORPUS, DATASET, k=5, chunk_sizes=(300, 600, 900))
    assert [r["chunk_chars"] for r in res] == [300, 600, 900]


def test_cli_gate_fails_when_threshold_unreachable(capsys):
    assert main(["--corpus", CORPUS, "--dataset", DATASET, "--min-hit", "0.99", "--chunk-sizes", "900"]) == 1
    assert main(["--corpus", CORPUS, "--dataset", DATASET, "--min-hit", "0.5"]) == 0


def test_json_report_written(tmp_path):
    out = tmp_path / "r.json"
    main(["--corpus", CORPUS, "--dataset", DATASET, "--json", str(out)])
    assert json.loads(out.read_text())[0]["questions"] == 18


def test_bad_dataset_line_names_the_line(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text('{"q": "ok"}\n{not json}\n')
    with pytest.raises(ValueError, match=":2:"):
        load_dataset(str(p))


def test_postgres_retrieval_matches_sqlite(pg_store):
    from opai_rag_pro.eval.harness import evaluate, ingest_dir, load_dataset
    from opai_rag import RAG
    import tempfile, os
    items = load_dataset(DATASET)
    sq = RAG(os.path.join(tempfile.mkdtemp(), "s.db")); sq._llm_resolved = True
    pg = RAG(store=pg_store); pg._llm_resolved = True
    ingest_dir(sq, CORPUS); ingest_dir(pg, CORPUS)
    a, b = evaluate(sq, items), evaluate(pg, items)
    assert (a["hit_at_5"], a["abstain_accuracy"]) == (b["hit_at_5"], b["abstain_accuracy"])
