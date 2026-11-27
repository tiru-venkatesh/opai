"""opai-rag-pro keys create --name acme [--namespace acme] | keys list | keys revoke ID | usage ID

Reads the database from OPAI_RAG_DSN. A new key is printed ONCE and cannot be recovered (only its hash is stored).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .stores.pg import PgVectorStore


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="opai-rag-pro")
    sub = p.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys").add_subparsers(dest="sub", required=True)
    c = k.add_parser("create"); c.add_argument("--name", required=True); c.add_argument("--namespace")
    k.add_parser("list")
    r = k.add_parser("revoke"); r.add_argument("id", type=int)
    u = sub.add_parser("usage"); u.add_argument("id", type=int)
    a = p.parse_args(argv)

    dsn = os.getenv("OPAI_RAG_DSN")
    if not dsn:
        print("set OPAI_RAG_DSN=postgresql://user:pass@host/db", file=sys.stderr)
        return 2
    store = PgVectorStore(dsn)
    try:
        if a.cmd == "keys" and a.sub == "create":
            raw = store.create_key(a.name, a.namespace)
            print(f"API key for '{a.name}' (shown once, store it now):\n{raw}")
        elif a.cmd == "keys" and a.sub == "list":
            for row in store.list_keys():
                print(f"{row['id']:>3}  {row['name']:<20} ns={row['namespace']:<20} {'REVOKED' if row['revoked'] else 'active'}  "
                      f"{time.strftime('%Y-%m-%d', time.gmtime(row['created_at']))}")
        elif a.cmd == "keys" and a.sub == "revoke":
            print("revoked" if store.revoke_key(a.id) else "not found or already revoked")
        elif a.cmd == "usage":
            print(f"asks today: {store.usage_today(a.id)}")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
