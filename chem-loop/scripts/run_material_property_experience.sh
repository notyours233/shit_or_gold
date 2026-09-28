#!/usr/bin/env bash
set -euo pipefail

# Build the unified 19-direction material-performance experience library.
#
# Flow:
#   audited material-performance sources + established truth
#     -> canonical records + point-value DatasetSample JSONL
#     -> youtu-chem-loop DB dataset
#     -> Training-Free GRPO experience generation
#     -> stable experience.yaml synced to MAD/experience/experience.yaml
#
# The recommendation/rank stage should be run only after this script has produced
# and synced a fresh experience pack.

usage() {
  cat <<'EOF'
run_material_property_experience.sh

Generate/sync the unified 19-direction experience library from the audited
material-performance dataset.

Flags:
  --prepare-only       Build/upload dataset only; do not run GRPO.
  --fresh             Force GRPO from step 0 (passes --restart_step 0).
  --resume            Reuse cached GRPO steps when available (omits --restart_step).
  --restart_step N    Explicit restart_step for GRPO.
  --sync-only         Skip dataset/GRPO and sync an existing agent YAML into experience.yaml.
  --seed_agent_yaml P Source YAML for --sync-only or GRPO seeding.
  --exp_name NAME     Override experiment name.
  -h, --help          Show help.

Env overrides:
  PYTHON_BIN
  DATASET_JSONL
  DATASET_NAME
  REBUILD_DATASET
  CONFIG_NAME
  EXP_NAME
  EPOCHS
  BATCH_SIZE
  GRPO_N
  TRUNCATE
  ROLLOUT_CONCURRENCY
  CHEM_GRPO_RAG_ENABLED
  CHEM_GRPO_RAG_LIMIT
  CHEM_LITERATURE_CHROMA_COLLECTION

Default dataset is material_performance_19_v1 (11,291 point-value samples across
9 electrochemical and 10 material/new-performance directions). Prepare-only
rebuilds and uploads data but makes no model calls.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
YOUTU="${ROOT}/youtu-chem-loop"

MODE="auto"  # auto|fresh|resume|explicit
EXPLICIT_RESTART=""
PREPARE_ONLY="0"
SYNC_ONLY="0"
SEED_AGENT_YAML="${SEED_AGENT_YAML:-}"

CONFIG_NAME="${CONFIG_NAME:-chem_performance_single}"
DATASET_NAME="${DATASET_NAME:-material_performance_19_v1}"
EXP_NAME="${EXP_NAME:-material_performance_19_v1_rag1_e1_b50_n3_c1}"
REBUILD_DATASET="${REBUILD_DATASET:-1}"

DATASET_JSONL="${DATASET_JSONL:-${YOUTU}/data/processed/material_performance_19/material_performance_19_grpo_v1.jsonl}"
DATASET_MANIFEST="${DATASET_MANIFEST:-${YOUTU}/data/processed/material_performance_19/manifest_v1.json}"

EPOCHS="${EPOCHS:-1}"
BATCH_SIZE="${BATCH_SIZE:-50}"
GRPO_N="${GRPO_N:-3}"
TRUNCATE="${TRUNCATE:-11291}"
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-1}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare-only)
      PREPARE_ONLY="1"
      shift
      ;;
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
    --sync-only)
      SYNC_ONLY="1"
      shift
      ;;
    --seed_agent_yaml)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --seed_agent_yaml requires a path" >&2
        exit 2
      fi
      SEED_AGENT_YAML="$2"
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

cd "${YOUTU}"

export UTU_DB_URL="${UTU_DB_URL:-sqlite:///test.db}"
export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
export TMPDIR="${TMPDIR:-/tmp}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONPATH="${YOUTU}${PYTHONPATH:+:${PYTHONPATH}}"

# Unified literature RAG defaults. Existing exported env values still win.
export CHEM_LITERATURE_BACKEND="${CHEM_LITERATURE_BACKEND:-chroma}"
export CHEM_LITERATURE_CHROMA_DIR="${CHEM_LITERATURE_CHROMA_DIR:-../MAD/data/chroma_db}"
export CHEM_LITERATURE_CHROMA_COLLECTION="${CHEM_LITERATURE_CHROMA_COLLECTION:-literature_agent2}"
export CHEM_GRPO_RAG_ENABLED="${CHEM_GRPO_RAG_ENABLED:-1}"
export CHEM_GRPO_RAG_LIMIT="${CHEM_GRPO_RAG_LIMIT:-5}"
export CHEM_LITERATURE_CHROMA_MAX_DISTANCE="${CHEM_LITERATURE_CHROMA_MAX_DISTANCE:-0.35}"

PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PY="${VIRTUAL_ENV}/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PY="$(command -v python)"
  else
    echo "ERROR: python not found." >&2
    exit 3
  fi
fi

if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
  echo "ERROR: Selected python cannot import youtu-chem-loop (import utu failed): ${PY}" >&2
  echo "Fix: cd ${ROOT} && ./scripts/setup_venv.sh" >&2
  exit 3
fi

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

quote_cmd() {
  local out=""
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

LOG_DIR="${YOUTU}/logs/material_performance_19"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/${EXP_NAME}_${TS}.log"

set +e
(
  set -euo pipefail
  echo "== run_material_property_experience =="
  echo "root: ${ROOT}"
  echo "log_file: ${LOG_FILE}"
  echo
  echo "Config:"
  echo "  dataset_jsonl=${DATASET_JSONL}"
  echo "  dataset_manifest=${DATASET_MANIFEST}"
  echo "  dataset_name=${DATASET_NAME}"
  echo "  rebuild_dataset=${REBUILD_DATASET}"
  echo "  exp_name=${EXP_NAME}"
  echo "  epochs=${EPOCHS} batch_size=${BATCH_SIZE} grpo_n=${GRPO_N} truncate=${TRUNCATE}"
  echo "  rollout_concurrency=${ROLLOUT_CONCURRENCY}"
  echo "  prepare_only=${PREPARE_ONLY} sync_only=${SYNC_ONLY}"
  echo
  echo "RAG:"
  echo "  CHEM_LITERATURE_CHROMA_COLLECTION=${CHEM_LITERATURE_CHROMA_COLLECTION}"
  echo "  CHEM_GRPO_RAG_ENABLED=${CHEM_GRPO_RAG_ENABLED}"
  echo "  CHEM_GRPO_RAG_LIMIT=${CHEM_GRPO_RAG_LIMIT}"
  echo

  if [[ "${SYNC_ONLY}" == "1" ]]; then
    if [[ -z "${SEED_AGENT_YAML}" ]]; then
      echo "ERROR: --sync-only requires --seed_agent_yaml" >&2
      exit 2
    fi
    echo "[sync-only] Sync stable experience.yaml from: ${SEED_AGENT_YAML}"
    "${ROOT}/scripts/run_closed_loop.sh" \
      --seed_agent_yaml "${SEED_AGENT_YAML}" \
      --skip_debate_update \
      --config_name "${CONFIG_NAME}"
    exit 0
  fi

  if [[ "${REBUILD_DATASET}" == "1" || ! -f "${DATASET_JSONL}" || ! -f "${DATASET_MANIFEST}" ]]; then
    echo "[1/4] Deterministically rebuild the audited 19-direction dataset"
    build_args=("${PY}" scripts/data/build_material_performance_19_dataset.py)
    echo "\$ $(quote_cmd "${build_args[@]}")"
    "${build_args[@]}"
  else
    echo "[1/4] Reuse existing audited 19-direction dataset (REBUILD_DATASET=${REBUILD_DATASET})"
  fi

  if [[ ! -f "${DATASET_JSONL}" ]]; then
    echo "ERROR: GRPO dataset not found after build: ${DATASET_JSONL}" >&2
    exit 4
  fi

  expected_rows="$(grep -cve '^[[:space:]]*$' "${DATASET_JSONL}")"
  echo "[1/4] dataset_jsonl_rows=${expected_rows}"
  if [[ "${expected_rows}" -ne 11291 ]]; then
    echo "ERROR: expected audited v1 GRPO row count 11291, got ${expected_rows}." >&2
    echo "Re-audit the dataset before changing this release gate." >&2
    exit 5
  elif [[ "${expected_rows}" -le 0 ]]; then
    echo "ERROR: built dataset is empty: ${DATASET_JSONL}" >&2
    exit 5
  fi

  echo "[2/4] Ensure DB dataset exists exactly once: ${DATASET_NAME}"
  actual_rows="$(db_count_dataset "${DATASET_NAME}")"
  echo "[2/4] db_rows=${actual_rows} expected_rows=${expected_rows}"
  if [[ "${actual_rows}" -eq 0 ]]; then
    "${PY}" scripts/data/upload_dataset.py \
      --file_path "${DATASET_JSONL}" \
      --dataset_name "${DATASET_NAME}" \
      --data_format default
  elif [[ "${actual_rows}" -eq "${expected_rows}" ]]; then
    echo "[2/4] DB dataset already present; skip upload."
  else
    echo "ERROR: DB dataset '${DATASET_NAME}' has ${actual_rows} rows, expected ${expected_rows}." >&2
    echo "Use a fresh DATASET_NAME or clean duplicate rows before continuing." >&2
    exit 6
  fi

  if [[ "${PREPARE_ONLY}" == "1" ]]; then
    echo "[3/4] Skipped GRPO (--prepare-only)."
    echo "Prepared dataset: ${DATASET_NAME} (${expected_rows} rows)"
    exit 0
  fi

  restart_args=()
  if [[ "${MODE}" == "auto" ]]; then
    existing_epoch_rows="$(db_count_eval_rows "${EXP_NAME}_epoch_0")"
    if [[ "${existing_epoch_rows}" -gt 0 ]]; then
      echo "Auto mode: found ${existing_epoch_rows} rows for ${EXP_NAME}_epoch_0 -> resume"
      MODE="resume"
    else
      echo "Auto mode: no existing rows for ${EXP_NAME}_epoch_0 -> fresh"
      MODE="fresh"
    fi
  fi

  if [[ "${MODE}" == "fresh" ]]; then
    restart_args=(--restart_step 0)
  elif [[ "${MODE}" == "explicit" ]]; then
    restart_args=(--restart_step "${EXPLICIT_RESTART}")
  elif [[ "${MODE}" == "resume" ]]; then
    restart_args=()
  else
    echo "ERROR: invalid mode: ${MODE}" >&2
    exit 7
  fi

  seed_args=()
  if [[ -n "${SEED_AGENT_YAML}" ]]; then
    seed_args=(--seed_experience_yaml "${SEED_AGENT_YAML}")
  elif [[ -f "configs/agents/practice/experience.yaml" ]]; then
    seed_args=(--seed_experience_yaml "configs/agents/practice/experience.yaml")
  fi

  echo "[3/4] Training-Free GRPO"
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
    "${restart_args[@]}"
    "${seed_args[@]}"
  )
  echo "\$ $(quote_cmd "${cmd[@]}")"
  "${cmd[@]}"

  agent_yaml="configs/agents/practice/${EXP_NAME}_agent.yaml"
  if [[ ! -f "${agent_yaml}" ]]; then
    echo "ERROR: expected GRPO agent YAML not found: ${agent_yaml}" >&2
    exit 8
  fi

  echo "[4/4] Sync stable experience.yaml for MAD recommendations"
  "${ROOT}/scripts/run_closed_loop.sh" \
    --seed_agent_yaml "${YOUTU}/${agent_yaml}" \
    --skip_debate_update \
    --config_name "${CONFIG_NAME}"

  echo
  echo "Done."
  echo "  youtu experience: ${YOUTU}/configs/agents/practice/experience.yaml"
  echo "  MAD experience:   ${ROOT}/MAD/experience/experience.yaml"
) 2>&1 | tee "${LOG_FILE}"

status="${PIPESTATUS[0]}"
set -e

if [[ "${status}" -ne 0 ]]; then
  echo
  echo "FAILED (exit=${status}). Log: ${LOG_FILE}" >&2
  echo "Rerun examples:" >&2
  echo "  ${ROOT}/scripts/run_material_property_experience.sh --prepare-only" >&2
  echo "  TRUNCATE=60 BATCH_SIZE=10 GRPO_N=2 ROLLOUT_CONCURRENCY=1 ${ROOT}/scripts/run_material_property_experience.sh --fresh" >&2
  echo "  bash ${ROOT}/scripts/run_material_property_param_test.sh --dry-run" >&2
  echo "  ${ROOT}/scripts/run_material_property_experience.sh --resume" >&2
fi

exit "${status}"
