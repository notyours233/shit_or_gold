#!/usr/bin/env bash
set -euo pipefail

# Monorepo wrapper around youtu-chem-loop's closed-loop helper.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  export PYTHON_BIN="${ROOT}/.venv/bin/python"
fi

cd "${ROOT}/youtu-chem-loop"
exec ./scripts/run_closed_loop.sh "$@"
