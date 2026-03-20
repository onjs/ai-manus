#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

BASE_IMAGE="${SANDBOX_BASE_IMAGE:-ai-manus-sandbox-base:latest}"

echo "Building sandbox runtime image with base: ${BASE_IMAGE}"
./scripts/dev.sh build sandbox

echo "Done: sandbox runtime image built"
