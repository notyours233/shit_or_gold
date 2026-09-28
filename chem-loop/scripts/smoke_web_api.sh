#!/usr/bin/env bash
set -euo pipefail

# Lightweight smoke check for the ChemCouncil Web UI server.
#
# Usage:
#   ./scripts/smoke_web_api.sh              # default http://localhost:8000
#   BASE_URL=http://127.0.0.1:8000 ./scripts/smoke_web_api.sh
#
# Expected:
#   - server already running (docker or local)
#   - curl installed

BASE_URL="${BASE_URL:-http://localhost:8000}"

_curl() {
  # -f: fail on non-2xx
  # -sS: silent but show errors
  curl -fsS "$@"
}

echo "[web-smoke] base_url=${BASE_URL}"

echo "[web-smoke] GET /"
_curl "${BASE_URL}/" >/dev/null

echo "[web-smoke] GET /api/health"
_curl "${BASE_URL}/api/health" | python3 -m json.tool >/dev/null

echo "[web-smoke] GET /api/experience/meta"
_curl "${BASE_URL}/api/experience/meta" | python3 -m json.tool

echo "[web-smoke] GET /api/experience/pack (head)"
_curl "${BASE_URL}/api/experience/pack" | head -n 25

echo "[web-smoke] GET /api/experience/history"
_curl "${BASE_URL}/api/experience/history" | python3 -m json.tool >/dev/null

echo "[web-smoke] OK"

