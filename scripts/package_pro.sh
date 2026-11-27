#!/usr/bin/env bash
# Builds dist/opai-rag-starter-pro-<version>.zip: the file you sell. Contains Pro only (no app code, no history).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/packages/opai-rag-starter-pro"
VER="$(sed -n 's/^version = "\(.*\)"/\1/p' "$SRC/pyproject.toml" | head -1)"
OUT="$ROOT/dist"; mkdir -p "$OUT"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir "$TMP/opai-rag-starter-pro"
tar -C "$SRC" --exclude='__pycache__' --exclude='*.egg-info' --exclude='.pytest_cache' --exclude='chroma_data' --exclude='deploy/docker-compose.monorepo.yml' -cf - . | tar -C "$TMP/opai-rag-starter-pro" -xf -
mkdir -p "$TMP/opai-rag-starter-pro/.github/workflows"
cp "$ROOT/packages/opai-rag-starter-pro/ci.standalone.yml" "$TMP/opai-rag-starter-pro/.github/workflows/ci.yml"
rm -f "$TMP/opai-rag-starter-pro/ci.standalone.yml"
(cd "$TMP" && zip -qr "$OUT/opai-rag-starter-pro-$VER.zip" opai-rag-starter-pro)
echo "Built $OUT/opai-rag-starter-pro-$VER.zip"
