#!/usr/bin/env bash
set -euo pipefail

# One-click incremental experience update from a lab XLSX.
#
# Steps (with tee logging):
# 1) XLSX -> experimental_records CSV (long table)
# 2) CSV -> processed JSONL (unit/metric normalization)
# 3) processed -> dataset JSONL (uploadable default format)
# 4) upload dataset into sqlite DB
# 5) run Training-free GRPO on the new experimental batch (rollout + experience distill)
# 6) export stable `experience.yaml` and sync into MAD/experience/, archiving old packs
#
# This script makes network calls during step (5) (LLM rollouts + distillation).

usage() {
  cat <<'EOF'
run_experimental_update_from_xlsx.sh

Env overrides (optional):
  XLSX_PATH              Path to the lab XLSX (default: ./样品中金属比例.xlsx)
  DATE                   YYYYMMDD (default: local date)
  TAG                    Short batch tag (default: lab_metal_ratio)
  RESUME_DATASET_NAME    If set, skip steps 1-4 and reuse an already-uploaded dataset name.
  BATCH_SIZE             GRPO batch_size (default: 20)
  GRPO_N                 GRPO group size (default: 6)
  ROLLOUT_CONCURRENCY    LLM concurrency for rollouts/distillation (default: 4)
  SEED_EXPERIENCE_YAML   Seed [G*] pack (default: configs/agents/practice/experience.yaml)
  RESTART_STEP           GRPO restart_step (default: empty -> use cache to resume if possible)
  DATASET_IF_EXISTS      upload behavior when dataset already exists: skip|error|append (default: skip)

Notes:
  - HER is treated as η@10 mA cm^-2 (mV) in this pipeline (per current project rule).
  - For OER/HER/UOR, smaller is better when choosing between two reported groups.

Examples:
  ./scripts/run_experimental_update_from_xlsx.sh
  TAG=labA DATE=20260303 ./scripts/run_experimental_update_from_xlsx.sh
  RESUME_DATASET_NAME=chem_performance_exp_20260304_lab_metal_ratio_65 ./scripts/run_experimental_update_from_xlsx.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  echo "ERROR: python not found at: ${PY}" >&2
  echo "Fix: run ./scripts/setup_venv.sh (from repo root) or set PYTHON_BIN=/path/to/python" >&2
  exit 2
fi

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: missing ${ROOT}/.env" >&2
  echo "Fix: cp .env.example .env && edit it (fill API keys)" >&2
  exit 2
fi

XLSX_PATH="${XLSX_PATH:-${ROOT}/样品中金属比例.xlsx}"
DATE="${DATE:-$(date +%Y%m%d)}"
TAG="${TAG:-lab_metal_ratio}"
RESUME_DATASET_NAME="${RESUME_DATASET_NAME:-}"
BATCH_SIZE="${BATCH_SIZE:-20}"
GRPO_N="${GRPO_N:-6}"
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"
SEED_EXPERIENCE_YAML="${SEED_EXPERIENCE_YAML:-configs/agents/practice/experience.yaml}"
RESTART_STEP="${RESTART_STEP:-}"
DATASET_IF_EXISTS="${DATASET_IF_EXISTS:-skip}"

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/exp_update_${TS}.log"

quote_cmd() {
  local out=""
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

set +e
(
  set -euo pipefail
  echo "== ChemCouncil experimental update =="
  echo "ts: ${TS}"
  echo "root: ${ROOT}"
  echo "python: ${PY}"
  echo "log: ${LOG_FILE}"
  echo "xlsx: ${XLSX_PATH}"
  echo "date: ${DATE} tag: ${TAG}"
  echo "grpo: batch_size=${BATCH_SIZE} grpo_n=${GRPO_N} rollout_concurrency=${ROLLOUT_CONCURRENCY}"
  echo

  cd "${ROOT}"

  # Load .env into this shell (no-op if already exported). Avoid printing secrets.
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/.env"
  set +a

  export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
  export TMPDIR="${TMPDIR:-/tmp}"

  # Prefer enabling RAG during rollouts if the user configured a local Chroma DB + keys.
  export MAD_ENABLE_RAG="${MAD_ENABLE_RAG:-1}"
  export MAD_RAG_LIMIT="${MAD_RAG_LIMIT:-5}"
  export MAD_RAG_MAX_DISTANCE="${MAD_RAG_MAX_DISTANCE:-0.35}"
  export MAD_RAG_TIMEOUT_S="${MAD_RAG_TIMEOUT_S:-30}"

  cd "${ROOT}/youtu-chem-loop"

  DS=""
  CSV_PATH=""
  N=""

  if [[ -n "${RESUME_DATASET_NAME}" ]]; then
    echo "[resume] RESUME_DATASET_NAME=${RESUME_DATASET_NAME}"
    DS="${RESUME_DATASET_NAME}"
    # Best-effort parse DATE/TAG/N from the dataset name for stable exp_id naming.
    if [[ "${DS}" =~ ^chem_performance_exp_([0-9]{8})_(.+)_([0-9]+)$ ]]; then
      DATE="${BASH_REMATCH[1]}"
      TAG="${BASH_REMATCH[2]}"
      N="${BASH_REMATCH[3]}"
    fi
  else
    echo "[1/6] XLSX -> experimental_records CSV (long table)"
    echo "\$ $(quote_cmd "${PY}" -m scripts.data.import_experimental_xlsx --xlsx_path "${XLSX_PATH}" --date "${DATE}" --tag "${TAG}" --output_dir data/experimental --quiet)"
    meta="$("${PY}" -m scripts.data.import_experimental_xlsx \
      --xlsx_path "${XLSX_PATH}" \
      --date "${DATE}" \
      --tag "${TAG}" \
      --output_dir data/experimental \
      --quiet)"
    echo "${meta}"
    DS="$(echo "${meta}" | rg -n '^DATASET_NAME=' | head -n 1 | cut -d= -f2-)"
    CSV_PATH="$(echo "${meta}" | rg -n '^OUTPUT_CSV=' | head -n 1 | cut -d= -f2-)"
    N="$(echo "${meta}" | rg -n '^RECORDS=' | head -n 1 | cut -d= -f2-)"
    if [[ -z "${DS}" || -z "${CSV_PATH}" || -z "${N}" ]]; then
      echo "ERROR: failed to parse DATASET_NAME/OUTPUT_CSV/RECORDS from converter output" >&2
      exit 3
    fi
    echo
    echo "[batch] dataset_name=${DS} records=${N}"
    echo

    echo "[2/6] CSV -> processed JSONL"
    echo "\$ $(quote_cmd "${PY}" -m scripts.data.import_experimental_csv --csv_path "${CSV_PATH}" --output_dir data/processed/chem_performance_experimental --output_name "${DS}__processed.jsonl" --require_eta10_condition)"
    "${PY}" -m scripts.data.import_experimental_csv \
      --csv_path "${CSV_PATH}" \
      --output_dir data/processed/chem_performance_experimental \
      --output_name "${DS}__processed.jsonl" \
      --require_eta10_condition
    echo

    echo "[3/6] processed -> dataset JSONL"
    echo "\$ $(quote_cmd "${PY}" -m scripts.data.build_chem_performance_dataset --input_dir data/processed/chem_performance_experimental --output_file "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" --include_unit_hint)"
    "${PY}" -m scripts.data.build_chem_performance_dataset \
      --input_dir data/processed/chem_performance_experimental \
      --output_file "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" \
      --include_unit_hint
    echo

    echo "[4/6] upload dataset -> sqlite DB"
    # Guard against accidental duplicate uploads when rerunning after a failure.
    existing_count="$(
      DS="${DS}" "${PY}" - <<'PY'
import os
from utu.db import DBService, DatasetSample

ds = os.environ.get("DS") or ""
rows = DBService.query(DatasetSample, filters={"dataset": ds}) or []
print(len(rows))
PY
    )"

    if [[ "${existing_count}" -gt 0 ]]; then
      echo "[db] dataset already exists: ${DS} rows=${existing_count}"
      case "${DATASET_IF_EXISTS}" in
        skip)
          echo "[db] skip upload (DATASET_IF_EXISTS=skip)"
          ;;
        error)
          echo "ERROR: dataset already exists in DB: ${DS} (rows=${existing_count})." >&2
          echo "Fix: set TAG/DATE to create a new dataset name, or set DATASET_IF_EXISTS=skip/append." >&2
          exit 6
          ;;
        append)
          echo "[db] append mode: uploading will DUPLICATE datapoints (DATASET_IF_EXISTS=append)"
          echo "\$ $(quote_cmd "${PY}" -m scripts.data.upload_dataset --file_path "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" --dataset_name "${DS}" --data_format default)"
          "${PY}" -m scripts.data.upload_dataset \
            --file_path "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" \
            --dataset_name "${DS}" \
            --data_format default
          ;;
        *)
          echo "ERROR: invalid DATASET_IF_EXISTS=${DATASET_IF_EXISTS} (expected: skip|error|append)" >&2
          exit 6
          ;;
      esac
    else
      echo "\$ $(quote_cmd "${PY}" -m scripts.data.upload_dataset --file_path "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" --dataset_name "${DS}" --data_format default)"
      "${PY}" -m scripts.data.upload_dataset \
        --file_path "data/processed/chem_performance_experimental/${DS}__dataset.jsonl" \
        --dataset_name "${DS}" \
        --data_format default
    fi
    echo
  fi

  if [[ -z "${DS}" ]]; then
    echo "ERROR: dataset name is empty (DS). Set RESUME_DATASET_NAME or run from XLSX." >&2
    exit 3
  fi

  # Always compute N from DB for resume mode to avoid stale counters.
  N_DB="$(
    DS="${DS}" "${PY}" - <<'PY'
import os
from utu.db import DBService, DatasetSample

ds = os.environ.get("DS") or ""
rows = DBService.query(DatasetSample, filters={"dataset": ds}) or []
print(len(rows))
PY
  )"
  if [[ -z "${N_DB}" || "${N_DB}" -le 0 ]]; then
    echo "ERROR: dataset has no rows in DB: ${DS}" >&2
    exit 6
  fi
  N="${N_DB}"

  EXP="single_update_exp_${DATE}_${TAG}_${N}_rag1_u1_t${N}_e1_b${BATCH_SIZE}_n${GRPO_N}_c${ROLLOUT_CONCURRENCY}"

  echo "[5/6] Training-free GRPO on experimental batch (network)"
  echo "exp_id: ${EXP}"
  # IMPORTANT: run as a module so `utu` imports resolve (avoid sys.path[0]=scripts/).
  CMD_GRPO=(
    "${PY}" -m scripts.run_training_free_GRPO
    --config_name chem_performance_single
    --experiment_name "${EXP}"
    --practice_dataset_name "${DS}"
    --epochs 1
    --batch_size "${BATCH_SIZE}"
    --grpo_n "${GRPO_N}"
    --rollout_data_truncate "${N}"
    --rollout_concurrency "${ROLLOUT_CONCURRENCY}"
    --seed_experience_yaml "${SEED_EXPERIENCE_YAML}"
  )
  if [[ -n "${RESTART_STEP}" ]]; then
    CMD_GRPO+=(--restart_step "${RESTART_STEP}")
  fi
  echo "\$ $(quote_cmd "${CMD_GRPO[@]}")"
  "${CMD_GRPO[@]}"
  echo

  SEED_AGENT_YAML="configs/agents/practice/${EXP}_agent.yaml"
  if [[ ! -f "${SEED_AGENT_YAML}" ]]; then
    echo "ERROR: expected agent YAML not found: ${SEED_AGENT_YAML}" >&2
    exit 4
  fi

  echo "[6/6] Export stable experience.yaml + sync into MAD (skip debate distill)"
  cd "${ROOT}"
  echo "\$ $(quote_cmd "${ROOT}/scripts/run_closed_loop.sh" --seed_agent_yaml "configs/agents/practice/${EXP}_agent.yaml" --skip_debate_update)"
  "${ROOT}/scripts/run_closed_loop.sh" \
    --seed_agent_yaml "configs/agents/practice/${EXP}_agent.yaml" \
    --skip_debate_update

  echo
  echo "OK."
  echo "Key outputs:"
  echo "  - dataset_name: ${DS}"
  echo "  - experimental CSV: ${CSV_PATH}"
  echo "  - uploaded dataset JSONL: ${ROOT}/youtu-chem-loop/data/processed/chem_performance_experimental/${DS}__dataset.jsonl"
  echo "  - new agent YAML: ${ROOT}/youtu-chem-loop/configs/agents/practice/${EXP}_agent.yaml"
  echo "  - synced pack: ${ROOT}/MAD/experience/experience.yaml"
) 2>&1 | tee "${LOG_FILE}"

status="${PIPESTATUS[0]}"
set -e
if [[ "${status}" -ne 0 ]]; then
  echo >&2
  echo "FAILED (exit=${status}). Log: ${LOG_FILE}" >&2
  echo "Rerun tips:" >&2
  echo "  - Reduce rollout concurrency:" >&2
  echo "      ROLLOUT_CONCURRENCY=1 ./scripts/run_experimental_update_from_xlsx.sh" >&2
  echo "  - Reduce grpo_n (cheaper, but weaker signal):" >&2
  echo "      GRPO_N=3 ./scripts/run_experimental_update_from_xlsx.sh" >&2
fi
exit "${status}"
