#!/usr/bin/env bash
set -euo pipefail

TRANSPORT="${TRANSPORT:-streamable-http}"
MCP_HOST="${MCP_HOST:-0.0.0.0}"
MCP_PORT="${MCP_PORT:-8000}"
CONNECTION_CONFIG="${CONNECTION_CONFIG:-/data/config/connections.json}"
APP_PATH="${APP_PATH:-app.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec "${PYTHON_BIN}" "${APP_PATH}" \
  --transport "${TRANSPORT}" \
  --host "${MCP_HOST}" \
  --port "${MCP_PORT}" \
  --connection-config "${CONNECTION_CONFIG}"
