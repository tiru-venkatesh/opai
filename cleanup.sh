#!/usr/bin/env bash
# Run from the repo root. Stops tracking junk files; your local copies are kept.
set -e
git rm --cached -q backend/opa.db.backup 2>/dev/null || true
git rm -r --cached -q backend/__pycache__ backend/agent/__pycache__ 2>/dev/null || true
git add .gitignore
git commit -m "Clean up: ignore db backups/pycache, update attach panel"
echo "Done. Now push."
