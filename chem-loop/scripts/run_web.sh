#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    PY="$(command -v python)"
  fi
fi

cd "${ROOT}"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: missing ${ROOT}/.env" >&2
  echo "Fix: cp .env.example .env && edit it (fill API keys)" >&2
  exit 2
fi

# shellcheck disable=SC1091
set -a
source "${ROOT}/.env"
set +a

HOST="${CHEMCOUNCIL_HOST:-0.0.0.0}"
PORT="${CHEMCOUNCIL_PORT:-8000}"
JOBS_ROOT="${CHEMCOUNCIL_JOBS_ROOT:-${ROOT}/.local/chemcouncil_server/jobs}"
JOB_CONCURRENCY="${CHEMCOUNCIL_JOB_CONCURRENCY:-1}"

echo "[web] python: ${PY}"
echo "[web] host=${HOST} port=${PORT} jobs_root=${JOBS_ROOT} job_concurrency=${JOB_CONCURRENCY}"

exec "${PY}" -m chemcouncil.server \
  --host "${HOST}" \
  --port "${PORT}" \
  --jobs_root "${JOBS_ROOT}" \
  --job_concurrency "${JOB_CONCURRENCY}"

