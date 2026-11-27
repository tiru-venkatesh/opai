#!/usr/bin/env bash
# Copies ONLY the free Lite package into a fresh folder, ready to `git init` and push as the public repo.
# Refuses to run if anything from Pro, the app, or personal data would end up in it.
set -euo pipefail
DEST="${1:?usage: scripts/export_lite.sh <destination-dir>}"
SRC="$(cd "$(dirname "$0")/../packages/opai-rag-starter-lite" && pwd)"
[ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ] && { echo "refusing: $DEST is not empty"; exit 1; }
mkdir -p "$DEST"
tar -C "$SRC" --exclude='__pycache__' --exclude='*.egg-info' --exclude='.pytest_cache' --exclude='*.db' -cf - . | tar -C "$DEST" -xf -
if grep -rIl --exclude-dir=.git -e 'opai_rag_pro' -e 'PgVectorStore' -e 'Developer Licence' "$DEST" >/dev/null 2>&1; then
  echo "ABORT: Pro-only code or licence text found in the export"; rm -rf "$DEST"; exit 1
fi
echo "Exported Lite to $DEST"
echo "Next: cd $DEST && git init && git add . && git commit -m 'Initial release' && (create the GitHub repo and push)"
