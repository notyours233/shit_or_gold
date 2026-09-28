#!/usr/bin/env bash
set -euo pipefail

# One-click runner for the final chem_performance_v5 experience library (500 samples).
#
# Features:
# - Creates a timestamped log file via `tee`
# - Preflight checks (venv / literature DB / dataset size)
# - Auto resume (if an exp already exists in DB, we default to resume mode)
# - On failure, prints clear rerun hints (resume vs fresh, lower concurrency, etc.)
#
# Usage examples:
#   ./scripts/run_full_experience_v5_500.sh
#   ./scripts/run_full_experience_v5_500.sh --fresh
#   ./scripts/run_full_experience_v5_500.sh --resume
#   ./scripts/run_full_experience_v5_500.sh --restart_step 10
#   EXP_NAME=... ROLLOUT_CONCURRENCY=2 ./scripts/run_full_experience_v5_500.sh --resume

usage() {
  cat <<'EOF'
run_full_experience_v5_500.sh

Runs Training-free GRPO to generate a full experience library on the 500-sample v5 subset.

Flags:
  --fresh              Force a full rerun (passes --restart_step 0)
  --resume             Resume/reuse cached steps (omits --restart_step)
  --restart_step N     Explicit restart_step (steps < N use cache; steps >= N recompute)
  --exp_name NAME      Override experiment name (default comes from $EXP_NAME)
  -h, --help           Show help

Env overrides (optional):
  PYTHON_BIN (absolute path to python; overrides .venv/bin/python discovery)
  EXP_NAME, DATASET_NAME, CONFIG_NAME
  EPOCHS, BATCH_SIZE, GRPO_N, TRUNCATE, ROLLOUT_CONCURRENCY
  CHEM_GRPO_RAG_ENABLED, CHEM_GRPO_RAG_LIMIT, CHEM_LITERATURE_CHROMA_MAX_DISTANCE, VOYAGE_TIMEOUT
  UTU_DB_URL (defaults to sqlite:///test.db), SQLITE_TMPDIR, TMPDIR
EOF
}

MODE="auto"         # auto|fresh|resume|explicit
EXPLICIT_RESTART=""

# Defaults (can be overridden by env or --exp_name)
EXP_NAME="${EXP_NAME:-single_full_v5_500_rag1_u1_t500_e1_b20_n6_c4}"
CONFIG_NAME="${CONFIG_NAME:-chem_performance_single}"
DATASET_NAME="${DATASET_NAME:-chem_performance_v5_500}"

EPOCHS="${EPOCHS:-1}"
BATCH_SIZE="${BATCH_SIZE:-20}"
GRPO_N="${GRPO_N:-6}"
TRUNCATE="${TRUNCATE:-500}"
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fresh)
      MODE="fresh"
      shift
      ;;
    --resume)
      MODE="resume"
      shift
      ;;
    --restart_step)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --restart_step requires an integer argument" >&2
        exit 2
      fi
      MODE="explicit"
      EXPLICIT_RESTART="$2"
      shift 2
      ;;
    --exp_name)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --exp_name requires a value" >&2
        exit 2
      fi
      EXP_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/${EXP_NAME}_${TS}.log"

# ---------------------------------------------------------------------------
# Preflight env defaults

export UTU_DB_URL="${UTU_DB_URL:-sqlite:///test.db}"
export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
export TMPDIR="${TMPDIR:-/tmp}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

# Ensure Python can import `utu` when executing files under `scripts/`.
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# Prefer the fully-built Chroma DB by default.
export CHEM_LITERATURE_BACKEND="${CHEM_LITERATURE_BACKEND:-chroma}"
# Monorepo default: share MAD's Chroma DB to avoid keeping duplicate huge stores.
export CHEM_LITERATURE_CHROMA_DIR="${CHEM_LITERATURE_CHROMA_DIR:-../MAD/data/chroma_db}"
# youtu-chem-loop uses Voyage query embeddings -> default to the Voyage-built collection.
export CHEM_LITERATURE_CHROMA_COLLECTION="${CHEM_LITERATURE_CHROMA_COLLECTION:-literature_agent2}"

# Single-agent literature retrieval; held-out DOI masking is injected per rollout.
export CHEM_GRPO_RAG_ENABLED="${CHEM_GRPO_RAG_ENABLED:-1}"
export CHEM_GRPO_RAG_LIMIT="${CHEM_GRPO_RAG_LIMIT:-5}"
export CHEM_LITERATURE_CHROMA_MAX_DISTANCE="${CHEM_LITERATURE_CHROMA_MAX_DISTANCE:-0.35}"
export VOYAGE_TIMEOUT="${VOYAGE_TIMEOUT:-30}"

# Prefer an explicit python, then the repo venv, then the monorepo venv, then the currently activated venv, then PATH.
PY="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  if [[ -x "${REPO_ROOT}/../.venv/bin/python" ]]; then
    PY="${REPO_ROOT}/../.venv/bin/python"
  elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PY="${VIRTUAL_ENV}/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PY="$(command -v python)"
  else
    echo "ERROR: python not found." >&2
    echo "Fix: create ${REPO_ROOT}/.venv or set PYTHON_BIN=/path/to/python" >&2
    exit 3
  fi
fi

if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
  echo "ERROR: Selected python cannot import this repo (import utu failed): ${PY}" >&2
  echo "Fix: install deps in your env (from repo root):" >&2
  echo "  python -m pip install -e ." >&2
  exit 3
fi

# ---------------------------------------------------------------------------
# Helper: query DB state via the repo venv (works for sqlite/postgres via UTU_DB_URL)

db_count_dataset() {
  local dataset="$1"
  "${PY}" - <<PY
from utu.utils import SQLModelUtils
from utu.db import DatasetSample
from sqlalchemy import func
from sqlmodel import select

dataset = "${dataset}"
with SQLModelUtils.create_session() as session:
    n = session.exec(select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset == dataset)).one()
print(int(n or 0))
PY
}

db_count_eval_rows() {
  local exp_id="$1"
  "${PY}" - <<PY
from utu.utils import SQLModelUtils
from utu.db import EvaluationSample
from sqlalchemy import func
from sqlmodel import select

exp_id = "${exp_id}"
with SQLModelUtils.create_session() as session:
    n = session.exec(select(func.count()).select_from(EvaluationSample).where(EvaluationSample.exp_id == exp_id)).one()
print(int(n or 0))
PY
}

db_latest_cached_step() {
  local experiment_name="$1"
  "${PY}" - <<PY
from utu.utils import SQLModelUtils
from utu.db import ExperienceCacheModel
from sqlalchemy import func
from sqlmodel import select

name = "${experiment_name}"
with SQLModelUtils.create_session() as session:
    m = session.exec(select(func.max(ExperienceCacheModel.step)).where(ExperienceCacheModel.experiment_name == name)).one()
print("" if m is None else int(m))
PY
}

quote_cmd() {
  # Print a command as a single shell-safe line (best-effort).
  # Note: `printf %q` is bash-specific and good enough for rerun hints.
  local out=""
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

# ---------------------------------------------------------------------------
# Main (wrapped so everything is captured by tee)

set +e
(
  set -euo pipefail
  echo "== run_full_experience_v5_500 =="
  echo "repo_root: ${REPO_ROOT}"
  echo "log_file: ${LOG_FILE}"
  echo
  echo "Config:"
  echo "  EXP_NAME=${EXP_NAME}"
  echo "  CONFIG_NAME=${CONFIG_NAME}"
  echo "  DATASET_NAME=${DATASET_NAME}"
  echo "  epochs=${EPOCHS} batch_size=${BATCH_SIZE} grpo_n=${GRPO_N} truncate=${TRUNCATE}"
  echo "  rollout_concurrency=${ROLLOUT_CONCURRENCY}"
  echo
  echo "Env:"
  echo "  UTU_DB_URL=${UTU_DB_URL}"
  echo "  CHEM_GRPO_RAG_ENABLED=${CHEM_GRPO_RAG_ENABLED} CHEM_GRPO_RAG_LIMIT=${CHEM_GRPO_RAG_LIMIT} CHEM_LITERATURE_CHROMA_MAX_DISTANCE=${CHEM_LITERATURE_CHROMA_MAX_DISTANCE}"
  echo "  CHEM_LITERATURE_BACKEND=${CHEM_LITERATURE_BACKEND} CHEM_LITERATURE_CHROMA_DIR=${CHEM_LITERATURE_CHROMA_DIR}"
  echo

  # Sanity check dataset size (avoid accidental duplicates in DB).
  expected="${TRUNCATE}"
  actual="$(db_count_dataset "${DATASET_NAME}")"
  echo "Dataset check: ${DATASET_NAME} has ${actual} rows in DB (expected ${expected})"
  if [[ "${actual}" -ne "${expected}" ]]; then
    echo "ERROR: dataset '${DATASET_NAME}' size mismatch." >&2
    echo "This usually means the dataset was uploaded multiple times (duplicates) or not uploaded." >&2
    echo "Fix options:" >&2
    echo "  1) Use a new dataset name (recommended), OR" >&2
    echo "  2) Clean the DB dataset rows, then upload exactly ${expected} samples." >&2
    exit 10
  fi

  # Decide restart behavior
  restart_args=()
  if [[ "${MODE}" == "auto" ]]; then
    existing_epoch_rows="$(db_count_eval_rows "${EXP_NAME}_epoch_0")"
    if [[ "${existing_epoch_rows}" -gt 0 ]]; then
      echo "Auto mode: found existing evaluation_data rows (${existing_epoch_rows}) for ${EXP_NAME}_epoch_0 -> resume"
      MODE="resume"
    else
      echo "Auto mode: no existing rows for ${EXP_NAME}_epoch_0 -> fresh"
      MODE="fresh"
    fi
  fi

  if [[ "${MODE}" == "fresh" ]]; then
    restart_args=(--restart_step 0)
  elif [[ "${MODE}" == "resume" ]]; then
    restart_args=()
  elif [[ "${MODE}" == "explicit" ]]; then
    restart_args=(--restart_step "${EXPLICIT_RESTART}")
  else
    echo "ERROR: invalid MODE=${MODE}" >&2
    exit 11
  fi

  echo "Run mode: ${MODE}"
  if [[ "${#restart_args[@]}" -gt 0 ]]; then
    echo "restart_args: ${restart_args[*]}"
  else
    echo "restart_args: (none)"
  fi
  echo

  cmd=(
    "${PY}" scripts/run_training_free_GRPO.py
    --config_name "${CONFIG_NAME}"
    --experiment_name "${EXP_NAME}"
    --practice_dataset_name "${DATASET_NAME}"
    --epochs "${EPOCHS}"
    --batch_size "${BATCH_SIZE}"
    --grpo_n "${GRPO_N}"
    --rollout_data_truncate "${TRUNCATE}"
    --rollout_concurrency "${ROLLOUT_CONCURRENCY}"
  )
  if [[ "${#restart_args[@]}" -gt 0 ]]; then
    cmd+=("${restart_args[@]}")
  fi

  echo "Command:"
  echo "  $(quote_cmd "${cmd[@]}")"
  echo

  start_ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "Start: ${start_ts}"
  echo

  "${cmd[@]}"
  exit_code=$?
  echo
  end_ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "End: ${end_ts} (exit_code=${exit_code})"
  exit "${exit_code}"
) 2>&1 | tee -a "${LOG_FILE}"
exit_code="${PIPESTATUS[0]}"
set -e

if [[ "${exit_code}" -ne 0 ]]; then
  echo
  echo "RUN FAILED (exit_code=${exit_code})"
  echo "Log saved at: ${LOG_FILE}"
  echo
  echo "Rerun hints:"
  echo "  - Resume (recommended after transient API errors):"
  echo "      ./scripts/run_full_experience_v5_500.sh --resume --exp_name ${EXP_NAME}"
  echo "  - Force a full rerun (ignores cached steps):"
  echo "      ./scripts/run_full_experience_v5_500.sh --fresh --exp_name ${EXP_NAME}"
  echo "  - If you see 429/rate-limit/timeouts, lower concurrency:"
  echo "      ROLLOUT_CONCURRENCY=2 ./scripts/run_full_experience_v5_500.sh --resume --exp_name ${EXP_NAME}"
  echo "      ROLLOUT_CONCURRENCY=1 ./scripts/run_full_experience_v5_500.sh --resume --exp_name ${EXP_NAME}"
  echo "  - If RAG calls time out, increase VOYAGE_TIMEOUT:"
  echo "      VOYAGE_TIMEOUT=60 ./scripts/run_full_experience_v5_500.sh --resume --exp_name ${EXP_NAME}"
  echo
  latest_step="$(db_latest_cached_step "${EXP_NAME}" || true)"
  if [[ -n "${latest_step}" ]]; then
    next_step=$((latest_step + 1))
    echo "DB cache status: latest cached step = ${latest_step}"
    echo "You can also restart from the next step explicitly:"
    echo "  ./scripts/run_full_experience_v5_500.sh --restart_step ${next_step} --exp_name ${EXP_NAME}"
    echo
  else
    echo "DB cache status: no cached steps found yet for experiment_name='${EXP_NAME}'"
    echo
  fi
fi

exit "${exit_code}"
