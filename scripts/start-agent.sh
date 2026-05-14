#!/usr/bin/env bash
set -euo pipefail

MCPO_HOST="${MCPO_HOST:-0.0.0.0}"
MCPO_PORT="${MCPO_PORT:-8000}"
CONNECTION_CONFIG="${CONNECTION_CONFIG:-/data/config/connections.json}"
APP_PATH="${APP_PATH:-/app/app.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec mcpo \
  --host "${MCPO_HOST}" \
  --port "${MCPO_PORT}" \
  -- "${PYTHON_BIN}" "${APP_PATH}" \
       --connection-config "${CONNECTION_CONFIG}"
