#!/usr/bin/env bash
set -euo pipefail

# Minimal smoke run for single-agent training-free GRPO.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT}/youtu-chem-loop"

SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
TMPDIR="${TMPDIR:-/tmp}"
export SQLITE_TMPDIR TMPDIR

# Ensure Python can import `utu` when we execute files under `scripts/`.
export PYTHONPATH="${PWD}${PYTHONPATH:+:${PYTHONPATH}}"

# Default to the repo-local sqlite DB in this folder.
# (If you set UTU_DB_URL in `.env`, that wins.)
export UTU_DB_URL="${UTU_DB_URL:-sqlite:///test.db}"

# Prefer an explicit python, then the monorepo venv, then the currently activated venv, then PATH.
PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PY="${VIRTUAL_ENV}/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    PY="$(command -v python)"
  fi
fi

if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
  echo "ERROR: Selected python cannot import youtu-chem-loop (import utu failed): ${PY}" >&2
  echo "Fix: create the venv and install editable:" >&2
  echo "  cd ${ROOT} && ./scripts/setup_venv.sh" >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Bootstrap DB dataset (for fresh clones)
DATASET_NAME="chem_performance_v2_350_noher_co2rr"
DATASET_FILE="data/processed/chem_performance/chem_performance_dataset_v2_350_noher_co2rr.jsonl"

dataset_rows="$("${PY}" - <<PY
from utu.utils import SQLModelUtils
from utu.db import DatasetSample
from sqlalchemy import func
from sqlmodel import select

name = "${DATASET_NAME}"
with SQLModelUtils.create_session() as session:
    n = session.exec(select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset == name)).one()
print(int(n or 0))
PY
)"

if [[ "${dataset_rows}" -eq 0 ]]; then
  echo "[smoke] dataset '${DATASET_NAME}' not found in DB; uploading from ${DATASET_FILE}"
  "${PY}" scripts/data/upload_dataset.py \
    --file_path "${DATASET_FILE}" \
    --dataset_name "${DATASET_NAME}" \
    --data_format default
else
  echo "[smoke] dataset '${DATASET_NAME}' already present in DB (rows=${dataset_rows}); skip upload"
fi

"${PY}" scripts/run_training_free_GRPO.py \
  --config_name chem_performance_single \
  --experiment_name single_agent_smoke \
  --practice_dataset_name "${DATASET_NAME}" \
  --epochs 1 --batch_size 2 --grpo_n 1 \
  --rollout_data_truncate 5 \
  --rollout_concurrency 1 \
  --restart_step 0
