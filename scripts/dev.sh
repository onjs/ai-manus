#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Determine which Docker Compose command to use
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
else
    echo "Error: Neither docker compose nor docker-compose command found" >&2
    exit 1
fi


# Execute Docker Compose command
$COMPOSE \
    --project-directory "$ROOT_DIR" \
    --env-file "$ROOT_DIR/.env" \
    -f "$SCRIPT_DIR/docker-compose-development.yml" \
    "$@"
