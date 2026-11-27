"""opai-rag ingest <files...> | ask "<question>" | docs | rm <doc_id>"""
from __future__ import annotations

import argparse
import sys

from . import RAG, ParseError


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="opai-rag", description="Document Q&A with citations.")
    p.add_argument("--db", default="opai_rag.db", help="SQLite file (default: opai_rag.db)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest", help="index one or more files"); s.add_argument("files", nargs="+")
    s = sub.add_parser("ask", help="ask a question"); s.add_argument("question"); s.add_argument("-k", type=int, default=5)
    sub.add_parser("docs", help="list ingested documents")
    s = sub.add_parser("rm", help="remove a document"); s.add_argument("doc_id")
    a = p.parse_args(argv)

    rag = RAG(a.db)
    try:
        if a.cmd == "ingest":
            rc = 0
            for f in a.files:
                try:
                    r = rag.ingest_file(f)
                    print(f"ok   {r['filename']}: {r['chunks']} chunks ({r['embedder']})")
                except (ParseError, OSError) as e:
                    print(f"FAIL {f}: {e}", file=sys.stderr); rc = 1
            return rc
        if a.cmd == "ask":
            r = rag.ask(a.question, k=a.k)
            print(r["answer"])
            if r["sources"]:
                print("\nSources:")
                for s in r["sources"]:
                    print(f"  [{s['n']}] {s['title']}" + (f", page {s['page']}" if s["page"] else "") + f"  (score {s['score']})")
            if r["mode"] == "extractive":
                print("\n(no LLM configured: showing extracted passages. Set ANTHROPIC_API_KEY for full answers.)")
            return 0
        if a.cmd == "docs":
            for d in rag.documents():
                print(f"{d['id']}  {d['filename']}  ({d['chunks']} chunks)")
            return 0
        if a.cmd == "rm":
            print("removed" if rag.delete(a.doc_id) else "not found")
            return 0
    finally:
        rag.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
