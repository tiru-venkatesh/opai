"""Post-deploy contract check. Standard library only.

    python scripts/check_deploy.py https://opa-52ug.onrender.com --origin https://www.opai.live

Exit code 1 if anything FAILs (WARN and SKIP do not fail). Run it right after a deploy, from your laptop or CI.
It only sends harmless requests: GETs, one CORS preflight, and one POST to a Gmail-send URL for an outbox id that cannot exist.

What it checks, and what it deliberately does not:
  wake      /v1/health answers (waits up to --wait seconds for a sleeping free-tier backend, and reports how long it took)
  health    /v1/system/health and /v1/system/scheduler-status answer with JSON
  version   /v1/version exists and its api_contract >= the one in frontend/build.json (run scripts/stamp_build.py first)
  routes    every /v1 path the frontend calls is in the deployed /openapi.json  (this is the stale-deploy detector)
  cors      a preflight from --origin is allowed
  identity  an identity-less call is refused (this app identifies users by user_id, not tokens: there is no 401 to expect)
  gmail     the send endpoint answers an unknown outbox id with a clean 4xx JSON error, not a 5xx crash
  tick      only if /v1/system/tick exists: it must reject a request without the secret (SKIP when the route does not exist)
"""
import argparse, json, os, re, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import route_contract as RC  # noqa: E402

RESULTS = []


def rec(status, name, detail=""):
    RESULTS.append(status)
    print(f"{status:5} {name}" + (f"  - {detail}" if detail else ""))


def call(method, url, body=None, headers=None, timeout=20):
    req = urllib.request.Request(url, method=method, data=(json.dumps(body).encode() if body is not None else None),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return 0, str(e), {}


def js(raw):
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("--origin", default=None); ap.add_argument("--wait", type=int, default=90)
    a = ap.parse_args(); base = a.base.rstrip("/")

    t0 = time.time(); code = 0
    while time.time() - t0 < a.wait:
        code, _, _ = call("GET", base + "/v1/health", timeout=15)
        if code == 200:
            break
        time.sleep(3)
    secs = round(time.time() - t0, 1)
    if code != 200:
        rec("FAIL", "wake", f"/v1/health gave {code or 'no answer'} after {secs}s"); return 1
    rec("PASS", "wake", f"backend answered after {secs}s" + (" (it was asleep)" if secs > 5 else ""))

    c, raw, _ = call("GET", base + "/v1/system/health"); d = js(raw)
    rec("PASS" if c == 200 and isinstance(d, dict) else "FAIL", "health /v1/system/health", f"{c}" + (f" keys={sorted(d)[:8]}" if isinstance(d, dict) else ""))
    c, raw, _ = call("GET", base + "/v1/system/scheduler-status"); d = js(raw)
    rec("PASS" if c == 200 and isinstance(d, dict) else "FAIL", "scheduler /v1/system/scheduler-status", f"{c}")

    build = None
    try:
        build = json.load(open(os.path.join(RC.FRONT, "build.json")))
    except Exception:  # noqa: BLE001
        pass
    c, raw, _ = call("GET", base + "/v1/version"); d = js(raw)
    if c != 200 or not isinstance(d, dict):
        rec("FAIL", "version /v1/version", f"{c}: the deployed backend predates the version endpoint (stale deploy)")
    elif build is None:
        rec("WARN", "version", f"backend contract {d.get('api_contract')}; no frontend/build.json to compare (run scripts/stamp_build.py)")
    elif d.get("api_contract", 0) < build["api_contract"]:
        rec("FAIL", "version", f"backend contract {d.get('api_contract')} < frontend {build['api_contract']}: deploy the backend")
    else:
        rec("PASS", "version", f"backend contract {d.get('api_contract')} >= frontend {build['api_contract']}, sha {d.get('git_sha')}")

    c, raw, _ = call("GET", base + "/openapi.json"); spec = js(raw)
    deployed = None
    if c == 200 and isinstance(spec, dict) and "paths" in spec:
        deployed = list(spec["paths"].keys())
        norm = [re.sub(r"\{[^}]+\}", "{x}", p) for p in deployed]
        pats = [re.compile("^" + re.escape(n).replace(re.escape("{x}"), "[^/]+") + "/?$") for n in norm]
        missing = []
        for page, paths in RC.frontend_paths().items():
            for p in sorted(paths):
                ok = any(n.startswith(p) for n in norm) if (p.endswith("/") or p.endswith("{x}")) else any(rx.match(p) for rx in pats)
                if not ok:
                    missing.append(f"{page}: {p}")
        if missing:
            rec("FAIL", "routes", f"{len(missing)} frontend path(s) not served by the deployed backend (version mismatch):")
            for m in missing[:25]:
                print("        " + m)
        else:
            rec("PASS", "routes", f"all frontend /v1 paths are served ({len(deployed)} deployed paths)")
    else:
        rec("WARN", "routes", f"/openapi.json not available ({c}); cannot compare routes")

    if a.origin:
        c, _, h = call("OPTIONS", base + "/v1/health", headers={"Origin": a.origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        allow = {k.lower(): v for k, v in h.items()}.get("access-control-allow-origin")
        if c in (200, 204) and allow in (a.origin, "*"):
            rec("PASS" if allow == a.origin else "WARN", "cors", f"allows {a.origin}" + (" via '*' (set CORS_ORIGINS to lock it down)" if allow == "*" else ""))
        else:
            rec("FAIL", "cors", f"preflight from {a.origin} -> {c}, Access-Control-Allow-Origin={allow}")
    else:
        rec("SKIP", "cors", "pass --origin https://your-frontend to check it")

    c, _, _ = call("GET", base + "/v1/opp/profile")
    rec("PASS" if c in (401, 403, 422) else "FAIL", "identity", f"/v1/opp/profile without user_id -> {c} (expected 401/403/422)")
    c, _, _ = call("POST", base + "/v1/auth/guest")
    rec("PASS" if c in (404, 405) else "FAIL", "no guest login", f"/v1/auth/guest -> {c}")

    c, raw, h = call("POST", base + "/v1/opp/outbox/does-not-exist/send", body={"user_id": "check-deploy"}, headers={"X-Gmail-Token": ""})
    d = js(raw)
    rec("PASS" if 400 <= c < 500 and isinstance(d, dict) and "detail" in d else "FAIL", "gmail send error handling", f"unknown outbox id -> {c}" + ("" if isinstance(d, dict) else " (not a JSON error)"))

    if deployed and "/v1/system/tick" in deployed:
        c, _, _ = call("POST", base + "/v1/system/tick")
        rec("PASS" if c in (401, 403, 422) else "FAIL", "tick requires secret", f"POST /v1/system/tick without secret -> {c}")
    else:
        rec("SKIP", "tick", "no /v1/system/tick route in this backend")

    fails = RESULTS.count("FAIL")
    print(f"\n{RESULTS.count('PASS')} passed, {RESULTS.count('WARN')} warning(s), {fails} failed, {RESULTS.count('SKIP')} skipped")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
