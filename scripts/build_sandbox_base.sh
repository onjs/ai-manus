#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# Load .env if present
if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi

BASE_IMAGE="${SANDBOX_BASE_IMAGE:-ai-manus-sandbox-base:latest}"
APT_MIRROR="${SANDBOX_APT_MIRROR:-}"
INSTALL_CJK_FONTS="${SANDBOX_INSTALL_CJK_FONTS:-true}"

echo "Building sandbox base image: ${BASE_IMAGE}"
docker build \
  -f sandbox/Dockerfile.base \
  --build-arg APT_MIRROR="${APT_MIRROR}" \
  --build-arg INSTALL_CJK_FONTS="${INSTALL_CJK_FONTS}" \
  -t "${BASE_IMAGE}" \
  sandbox

echo "Done: ${BASE_IMAGE}"
