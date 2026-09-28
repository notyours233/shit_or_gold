#!/usr/bin/env bash
set -euo pipefail

# Monorepo wrapper around youtu-chem-loop's one-click script.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  export PYTHON_BIN="${ROOT}/.venv/bin/python"
fi

cd "${ROOT}/youtu-chem-loop"
exec ./scripts/run_full_experience_v5_500.sh "$@"
