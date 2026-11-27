#!/usr/bin/env bash
# "Can a stranger use this without my help?" Uses only the artifacts you would ship:
# the exported Lite folder and the Pro zip, in brand-new virtualenvs, outside the monorepo.
# Set OPAI_TEST_PG_DSN=postgresql://user:pass@host/db to include the Postgres tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
export OPAI_RAG_EMBEDDER=hash
unset ANTHROPIC_API_KEY || true
step() { printf '\n== %s\n' "$*"; }

step "export Lite and build the Pro zip"
"$ROOT/scripts/export_lite.sh" "$W/lite" >/dev/null
"$ROOT/scripts/package_pro.sh" >/dev/null
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/packages/opai-rag-starter-pro/pyproject.toml" | head -1)"
ZIP="$ROOT/dist/opai-rag-starter-pro-$VER.zip"
(cd "$W" && unzip -q "$ZIP")

step "Pro zip must not contain app code, secrets, databases or personal files"
if unzip -l "$ZIP" | awk '{print $4}' | grep -Eq '(^|/)(backend|frontend)/|\.env$|\.db$|resumes/|\.pdf$'; then
  echo "FAIL: forbidden files in the Pro zip"; unzip -l "$ZIP" | grep -E 'backend|frontend|\.env|\.db|resumes|\.pdf'; exit 1
fi
echo "ok"

step "Lite: install and follow the README quickstart in a new virtualenv"
python3 -m venv "$W/v-lite"
"$W/v-lite/bin/pip" install -q "$W/lite"
(cd "$W/lite" && "$W/v-lite/bin/opai-rag" --db "$W/q.db" ingest examples/handbook.md \
  && "$W/v-lite/bin/opai-rag" --db "$W/q.db" ask "Can I get a refund after three weeks?" | tee "$W/ask.txt")
grep -q "14 days" "$W/ask.txt" && grep -q "Sources:" "$W/ask.txt" && echo "ok: answer cites its source"

step "Lite: its own tests"
"$W/v-lite/bin/pip" install -q "$W/lite[dev]"
(cd "$W/lite" && "$W/v-lite/bin/python" -m pytest -q -p no:cacheprovider | tail -1)

step "Pro: install from the zip (Lite from the export) in another new virtualenv"
python3 -m venv "$W/v-pro"
"$W/v-pro/bin/pip" install -q "$W/lite"
"$W/v-pro/bin/pip" install -q "$W/opai-rag-starter-pro[dev,chroma]"
(cd "$W/opai-rag-starter-pro" && "$W/v-pro/bin/python" -m pytest -q -p no:cacheprovider | tail -1)

step "Pro: evaluation harness with a quality gate"
(cd "$W/opai-rag-starter-pro" && "$W/v-pro/bin/opai-rag-eval" --corpus examples/corpus --dataset examples/dataset.jsonl --min-hit 0.85)

if [ -z "${OPAI_TEST_PG_DSN:-}" ]; then
  echo; echo "NOTE: OPAI_TEST_PG_DSN not set, so Postgres tests were skipped above."
fi
echo; echo "CLEAN INSTALL TEST PASSED"
