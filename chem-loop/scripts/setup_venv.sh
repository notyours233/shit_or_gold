#!/usr/bin/env bash
set -euo pipefail

# One-shot dependency setup for the Chem Loop workspace.
#
# This creates ONE venv at repo root and installs a flat dependency set from:
#   chem-loop/requirements.txt
#
# We intentionally do NOT `pip install -e` any subproject:
# - Each subproject is executed from its own directory, so imports resolve via cwd.
# - This keeps the workspace feeling like "one project" (no nested requirement includes).
#
# Usage:
#   ./scripts/setup_venv.sh
#   PYTHON_BIN=python3.12 ./scripts/setup_venv.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PY_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[setup] creating venv: ${VENV_DIR}"
  "${PY_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[setup] python: $(command -v python)"
python -m pip install --upgrade pip setuptools wheel

echo "[setup] installing monorepo requirements (this can take a while)..."
python -m pip install -r "${ROOT}/requirements.txt"

echo
echo "[setup] done."
echo "Next:"
echo "  1) Create env file (if you haven't):"
echo "       cp .env.example .env"
echo "  2) Activate venv:"
echo "       source .venv/bin/activate"
echo "  3) Smoke run:"
echo "       ./scripts/run_grpo_smoke.sh"
