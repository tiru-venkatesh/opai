"""Static route contract: every /v1/... path the frontend calls must be served by the backend.

Needs only the standard library (no FastAPI, no database), so it runs in CI before anything is installed and
against a checkout that cannot be imported. It reads routes from the Python source (APIRouter prefixes,
@router.get/post/..., include_router prefixes) and compares them with the paths in frontend/*.html and *.js.

    python scripts/route_contract.py            # exit 1 if any page calls a route the backend lacks
    python scripts/route_contract.py --list     # print the backend route table (only routers main.py registers)

Limits (stated so nobody trusts it too much): it checks PATHS, not HTTP methods or response shapes, and a path built
from several runtime pieces is only checked as far as its literal parts. tests/test_frontend_contract.py (OpenAPI,
needs FastAPI) remains the authoritative check where it can run.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from typing import Dict, List, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BACK = os.path.dirname(HERE)
FRONT = os.path.join(os.path.dirname(BACK), "frontend")
VERBS = {"get", "post", "put", "patch", "delete"}


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def backend_routes() -> List[Tuple[str, str, str]]:
    """[(METHOD, path, source_file)] including router prefixes and include_router prefixes."""
    mods: Dict[str, Dict] = {}
    for fn in sorted(os.listdir(BACK)):
        if not fn.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(BACK, fn), encoding="utf-8").read())
        prefixes: Dict[str, str] = {}
        routes: List[Tuple[str, str, str]] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") in ("APIRouter", "FastAPI"):
                pre = next((_const(k.value) for k in n.value.keywords if k.arg == "prefix"), "") or ""
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        prefixes[t.id] = pre
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in n.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in VERBS and isinstance(d.func.value, ast.Name) and d.args:
                        p = _const(d.args[0])
                        if p is not None:
                            routes.append((d.func.attr.upper(), prefixes.get(d.func.value.id, "") + p, fn))
        mods[fn[:-3]] = {"routes": routes}
        mods[fn[:-3]]["tree"] = tree
    # include_router(alias, prefix=...) in any module; alias resolved through "from mod import router as alias"
    extra: Dict[str, List[str]] = {}
    for name, m in mods.items():
        alias_to_mod: Dict[str, str] = {}
        for n in ast.walk(m["tree"]):
            if isinstance(n, ast.ImportFrom) and n.module:
                for a in n.names:
                    alias_to_mod[a.asname or a.name] = n.module.split(".")[-1]
        for n in ast.walk(m["tree"]):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "include_router" and n.args and isinstance(n.args[0], ast.Name):
                pre = next((_const(k.value) for k in n.keywords if k.arg == "prefix"), "") or ""
                target = alias_to_mod.get(n.args[0].id)
                if target in mods:
                    extra.setdefault(target, []).append(pre)
    out = []
    for name, m in mods.items():
        # A router that no module registers with include_router serves NOTHING, however many routes its file defines.
        # (main.py's own @app routes are always served.)
        if name != "main" and name not in extra:
            continue
        for meth, p, fn in m["routes"]:
            for pre in (extra.get(name) or [""]):
                out.append((meth, pre + p, fn))
    return out


def unregistered_routers() -> List[Tuple[str, int]]:
    """Modules that define routes but are never included by main.py: [(module_file, route_count)]."""
    counted = {fn for _, _, fn in backend_routes()}
    res = []
    for fn in sorted(os.listdir(BACK)):
        if not fn.endswith(".py") or fn in counted:
            continue
        tree = ast.parse(open(os.path.join(BACK, fn), encoding="utf-8").read())
        n = sum(1 for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) for d in x.decorator_list
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in VERBS and d.args and _const(d.args[0]) is not None)
        if n:
            res.append((fn, n))
    return res


_LIT = re.compile(r"""(['"`])(/v1/[^'"`\s]*)\1""")
_CONCAT = re.compile(r"""(['"])(/v1/[^'"\s]*)\1\s*\+\s*[^+'"]+?\s*\+\s*(['"])(/[^'"\s]*)\3""")
_TPL = re.compile(r"`(/v1/[^`\s]*)`")


def frontend_paths() -> Dict[str, Set[str]]:
    found: Dict[str, Set[str]] = {}
    for fn in sorted(os.listdir(FRONT)):
        if not fn.endswith((".html", ".js")) or fn == "sw.js":
            continue
        src = open(os.path.join(FRONT, fn), encoding="utf-8", errors="ignore").read()
        paths: Set[str] = set()
        for m in _CONCAT.finditer(src):
            paths.add((m.group(2) + "{x}" + m.group(4)).split("?")[0])
        for m in _TPL.finditer(src):
            paths.add(re.sub(r"\$\{[^}]*\}", "{x}", m.group(1)).split("?")[0])
        for m in _LIT.finditer(src):
            p = m.group(2).split("?")[0]
            if "${" in p:
                p = re.sub(r"\$\{[^}]*\}", "{x}", p)
            paths.add(p)
        if paths:
            found[fn] = paths
    return found


def check() -> List[str]:
    routes = backend_routes()
    norm = [re.sub(r"\{[^}]+\}", "{x}", p) for _, p, _ in routes]          # /v1/actions/{action_id}/approve -> /v1/actions/{x}/approve
    pats = [re.compile("^" + re.escape(n).replace(re.escape("{x}"), "[^/]+") + "/?$") for n in norm]
    missing = []
    for page, paths in frontend_paths().items():
        for p in sorted(paths):
            if p.endswith("/") or p.endswith("{x}"):   # the rest of the path is built at runtime (e.g. '/v1/actions/'+id+'/'+verb)
                ok = any(n.startswith(p) or n.startswith(p[:-3] if p.endswith("{x}") else p) for n in norm)
            else:
                ok = any(rx.match(p) for rx in pats)
            if not ok:
                missing.append(f"{page}: {p}")
    return missing


if __name__ == "__main__":
    if "--list" in sys.argv:
        for meth, p, fn in sorted(backend_routes(), key=lambda r: (r[1], r[0])):
            print(f"{meth:6} {p}   ({fn})")
        sys.exit(0)
    miss = check()
    n_routes = len(backend_routes())
    for fn, n in unregistered_routers():
        print(f"NOTE: {fn} defines {n} route(s) but main.py never registers it, so they are NOT served.")
    if miss:
        print(f"{len(miss)} frontend path(s) have no backend route ({n_routes} routes read):")
        print("\n".join("  " + m for m in miss))
        sys.exit(1)
    print(f"OK: every /v1 path in the frontend is served ({n_routes} backend routes read).")
