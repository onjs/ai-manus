#!/bin/bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export BUILDX_NO_DEFAULT_ATTESTATIONS=1
docker buildx bake "$@"
