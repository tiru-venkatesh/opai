"""Writes frontend/build.json: the API contract number this frontend was built against.
Run it as part of the frontend deploy:   python backend/scripts/stamp_build.py
opai-conn.js reads build.json and GET /v1/version; if the backend's number is lower, users see "OPAI is updating"."""
import json, os, re, subprocess
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); BACK = os.path.dirname(HERE); FRONT = os.path.join(os.path.dirname(BACK), "frontend")
src = open(os.path.join(BACK, "version_api.py"), encoding="utf-8").read()
contract = int(re.search(r"^API_CONTRACT\s*=\s*(\d+)", src, re.M).group(1))
try:
    sha = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=BACK, capture_output=True, text=True, timeout=5).stdout.strip() or None
except Exception:
    sha = None
out = {"api_contract": contract, "git_sha": sha, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
with open(os.path.join(FRONT, "build.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
print("wrote frontend/build.json", out)
