#!/usr/bin/env bash
set -euo pipefail

# Two-stage, 19-direction hyperparameter test for single-agent Training-Free GRPO.
# Training and validation are balanced by task and globally article-disjoint.

usage() {
  cat <<'EOF'
run_material_property_param_test.sh

Build an article-disjoint 19-direction train/validation split, generate one
experience pack for every candidate, and rank candidates on held-out reward.
MAD is never used by this workflow.

Flags:
  --dry-run       Validate the allocation and print model commands. No files,
                  database rows, or model calls are created.
  --prepare-only  Build and upload train/validation datasets; make no model calls.
  -h, --help      Show help.

Primary env overrides:
  TRAIN_SAMPLES_PER_TASK       default: 3 (57 training questions)
  VALIDATION_SAMPLES_PER_TASK  default: 3 (57 validation questions)
  BALANCE_SEED                 default: 20260803
  BATCH_SIZES_A                default: 19,38,57
  GRPO_N_A                     default: 3
  GRPO_NS_B                    default: 2,3,4
  ROLLOUT_CONCURRENCY          default: 1
  HELDOUT_CONCURRENCY          default: 1
  RAG                          default: 1
  EXP_ROOT                     optional stable run name for resume

Selection order:
  1) higher held-out macro reward
  2) broader experience-card task coverage
  3) higher worst-task held-out reward
  4) lower held-out output-contract failure rate
  5) fewer estimated calls, then smaller parameter value
EOF
}

DRY_RUN="${DRY_RUN:-0}"
PREPARE_ONLY="${PREPARE_ONLY:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --prepare-only)
      PREPARE_ONLY="1"
      shift
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

if [[ "${DRY_RUN}" == "1" && "${PREPARE_ONLY}" == "1" ]]; then
  echo "ERROR: --dry-run and --prepare-only are mutually exclusive." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
YOUTU="${ROOT}/youtu-chem-loop"
cd "${YOUTU}"

CONFIG_NAME="${CONFIG_NAME:-chem_performance_single}"
TRAIN_SAMPLES_PER_TASK="${TRAIN_SAMPLES_PER_TASK:-3}"
VALIDATION_SAMPLES_PER_TASK="${VALIDATION_SAMPLES_PER_TASK:-3}"
BALANCE_SEED="${BALANCE_SEED:-20260803}"
TRAIN_TOTAL="$((19 * TRAIN_SAMPLES_PER_TASK))"
VALIDATION_TOTAL="$((19 * VALIDATION_SAMPLES_PER_TASK))"

BATCH_SIZES_A="${BATCH_SIZES_A:-19,38,57}"
GRPO_N_A="${GRPO_N_A:-3}"
GRPO_NS_B="${GRPO_NS_B:-2,3,4}"
EPOCHS="${EPOCHS:-1}"
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-1}"
ROLLOUT_CONCURRENCY_FALLBACK="${ROLLOUT_CONCURRENCY_FALLBACK:-1}"
HELDOUT_CONCURRENCY="${HELDOUT_CONCURRENCY:-1}"
RAG="${RAG:-1}"

SOURCE_JSONL="${SOURCE_JSONL:-${YOUTU}/data/processed/material_performance_19/material_performance_19_grpo_v1.jsonl}"
PARAM_DIR="${PARAM_DIR:-${YOUTU}/data/processed/material_performance_19/params}"
SPLIT_CODE="s${TRAIN_SAMPLES_PER_TASK}_v${VALIDATION_SAMPLES_PER_TASK}_seed${BALANCE_SEED}"
TRAIN_JSONL="${TRAIN_JSONL:-${PARAM_DIR}/material_performance_19_hp_train_${SPLIT_CODE}.jsonl}"
VALIDATION_JSONL="${VALIDATION_JSONL:-${PARAM_DIR}/material_performance_19_hp_validation_${SPLIT_CODE}.jsonl}"
SPLIT_MANIFEST="${SPLIT_MANIFEST:-${PARAM_DIR}/material_performance_19_hp_${SPLIT_CODE}.manifest.json}"
TRAIN_DATASET_NAME="${TRAIN_DATASET_NAME:-material_performance_19_hp_train_${SPLIT_CODE}}"
VALIDATION_DATASET_NAME="${VALIDATION_DATASET_NAME:-material_performance_19_hp_validation_${SPLIT_CODE}}"

TS="$(date +%Y%m%d_%H%M%S)"
EXP_ROOT="${EXP_ROOT:-material_performance_19_hp_${SPLIT_CODE}_${TS}}"
REPORT_ROOT="${REPORT_ROOT:-${ROOT}/state/reports/${EXP_ROOT}}"
REPORT_A="${REPORT_ROOT}/stage_a"
REPORT_B="${REPORT_ROOT}/stage_b"
EXP_PREFIX_A="${EXP_PREFIX_A:-${EXP_ROOT}_A_n${GRPO_N_A}_bsweep_}"

export UTU_DB_URL="${UTU_DB_URL:-sqlite:///test.db}"
export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
export TMPDIR="${TMPDIR:-/tmp}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONPATH="${YOUTU}${PYTHONPATH:+:${PYTHONPATH}}"
export CHEM_LITERATURE_BACKEND="${CHEM_LITERATURE_BACKEND:-chroma}"
export CHEM_LITERATURE_CHROMA_DIR="${CHEM_LITERATURE_CHROMA_DIR:-../MAD/data/chroma_db}"
export CHEM_LITERATURE_CHROMA_COLLECTION="${CHEM_LITERATURE_CHROMA_COLLECTION:-literature_agent2}"
export CHEM_GRPO_RAG_ENABLED="${RAG}"
export CHEM_GRPO_RAG_LIMIT="${CHEM_GRPO_RAG_LIMIT:-5}"
export CHEM_LITERATURE_CHROMA_MAX_DISTANCE="${CHEM_LITERATURE_CHROMA_MAX_DISTANCE:-0.35}"
export UTU_EXPERIENCE_BATCH_UPDATE_MODE="${UTU_EXPERIENCE_BATCH_UPDATE_MODE:-direct}"

PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"
if [[ ! -x "${PY}" ]]; then
  echo "ERROR: project Python not found or not executable: ${PY}" >&2
  exit 3
fi
if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
  echo "ERROR: Selected Python cannot import youtu-chem-loop: ${PY}" >&2
  exit 3
fi
if [[ "${CONFIG_NAME}" == *mad* ]]; then
  echo "ERROR: GRPO hyperparameter tests require chem_performance_single; MAD configs are forbidden." >&2
  exit 3
fi
for value in "${TRAIN_SAMPLES_PER_TASK}" "${VALIDATION_SAMPLES_PER_TASK}" "${GRPO_N_A}" \
  "${ROLLOUT_CONCURRENCY}" "${HELDOUT_CONCURRENCY}"; do
  if ! [[ "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: expected positive integer, got '${value}'." >&2
    exit 3
  fi
done

quote_cmd() {
  local out=""
  local arg
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

print_or_run() {
  echo "\$ $(quote_cmd "$@")"
  if [[ "${DRY_RUN}" != "1" ]]; then
    "$@"
  fi
}

dataset_status() {
  local dataset_name="$1"
  local jsonl_path="$2"
  MP19_DATASET_NAME="${dataset_name}" MP19_JSONL_PATH="${jsonl_path}" "${PY}" - <<'PY'
import json
import os

from sqlmodel import select

from utu.db import DatasetSample
from utu.utils import SQLModelUtils

dataset = os.environ["MP19_DATASET_NAME"]
path = os.environ["MP19_JSONL_PATH"]
with open(path, encoding="utf-8") as handle:
    expected = [json.loads(line) for line in handle if line.strip()]
expected_ids = [str((row.get("meta") or {}).get("sample_id") or "") for row in expected]
with SQLModelUtils.create_session() as session:
    rows = session.exec(
        select(DatasetSample).where(DatasetSample.dataset == dataset).order_by(DatasetSample.index)
    ).all()
if not rows:
    print("missing")
else:
    actual_ids = [str((row.meta or {}).get("sample_id") or "") for row in rows]
    print("match" if actual_ids == expected_ids else "mismatch")
PY
}

ensure_dataset() {
  local dataset_name="$1"
  local jsonl_path="$2"
  local status
  status="$(dataset_status "${dataset_name}" "${jsonl_path}" | tail -n 1)"
  case "${status}" in
    missing)
      print_or_run "${PY}" scripts/data/upload_dataset.py \
        --file_path "${jsonl_path}" \
        --dataset_name "${dataset_name}" \
        --data_format default
      ;;
    match)
      echo "DB dataset verified: ${dataset_name}"
      ;;
    *)
      echo "ERROR: DB dataset '${dataset_name}' does not match ${jsonl_path}." >&2
      echo "Use a new dataset name; stale rows are not deleted automatically." >&2
      exit 5
      ;;
  esac
}

rag_flag=(--rag)
if [[ "${RAG}" == "0" ]]; then
  rag_flag=(--no-rag)
fi

echo "== 19-direction single-agent GRPO hyperparameter test =="
echo "mode: dry_run=${DRY_RUN} prepare_only=${PREPARE_ONLY}"
echo "split: train=${TRAIN_SAMPLES_PER_TASK}/task (${TRAIN_TOTAL}) validation=${VALIDATION_SAMPLES_PER_TASK}/task (${VALIDATION_TOTAL})"
echo "seed: ${BALANCE_SEED} (sample_id and doc_id disjoint)"
echo "stage A: grpo_n=${GRPO_N_A} batch_sizes=${BATCH_SIZES_A}"
echo "stage B: best_batch_size grpo_ns=${GRPO_NS_B}"
echo "fixed: epochs=${EPOCHS} rollout_concurrency=${ROLLOUT_CONCURRENCY} heldout_concurrency=${HELDOUT_CONCURRENCY} rag=${RAG}"
echo "exp_root: ${EXP_ROOT}"
echo "report_root: ${REPORT_ROOT}"
echo

if [[ ! -f "${SOURCE_JSONL}" ]]; then
  echo "ERROR: 19-direction GRPO source not found: ${SOURCE_JSONL}" >&2
  exit 4
fi

split_cmd=(
  "${PY}" scripts/data/split_material_performance_19_param.py
  --input-file "${SOURCE_JSONL}"
  --train-file "${TRAIN_JSONL}"
  --validation-file "${VALIDATION_JSONL}"
  --manifest-file "${SPLIT_MANIFEST}"
  --train-per-task "${TRAIN_SAMPLES_PER_TASK}"
  --validation-per-task "${VALIDATION_SAMPLES_PER_TASK}"
  --seed "${BALANCE_SEED}"
)
if [[ "${DRY_RUN}" == "1" ]]; then
  split_cmd+=(--check-only)
fi
echo "[1/6] Build/check deterministic train-validation split"
echo "\$ $(quote_cmd "${split_cmd[@]}")"
"${split_cmd[@]}"

if [[ "${DRY_RUN}" != "1" ]]; then
  train_rows="$(grep -cve '^[[:space:]]*$' "${TRAIN_JSONL}")"
  validation_rows="$(grep -cve '^[[:space:]]*$' "${VALIDATION_JSONL}")"
  if [[ "${train_rows}" -ne "${TRAIN_TOTAL}" || "${validation_rows}" -ne "${VALIDATION_TOTAL}" ]]; then
    echo "ERROR: split row gate failed: train=${train_rows}/${TRAIN_TOTAL} validation=${validation_rows}/${VALIDATION_TOTAL}" >&2
    exit 5
  fi

  echo
  echo "[2/6] Upload or verify exact DB datasets"
  ensure_dataset "${TRAIN_DATASET_NAME}" "${TRAIN_JSONL}"
  ensure_dataset "${VALIDATION_DATASET_NAME}" "${VALIDATION_JSONL}"
else
  echo
  echo "[2/6] Dry-run: database uploads are intentionally skipped."
  echo "Would verify/upload: ${TRAIN_DATASET_NAME} (${TRAIN_TOTAL})"
  echo "Would verify/upload: ${VALIDATION_DATASET_NAME} (${VALIDATION_TOTAL})"
fi

if [[ "${PREPARE_ONLY}" == "1" ]]; then
  echo
  echo "Prepared without model calls:"
  echo "  train=${TRAIN_DATASET_NAME} (${TRAIN_TOTAL})"
  echo "  validation=${VALIDATION_DATASET_NAME} (${VALIDATION_TOTAL})"
  echo "  manifest=${SPLIT_MANIFEST}"
  exit 0
fi

mkdir_cmd=(mkdir -p "${REPORT_A}" "${REPORT_B}")
print_or_run "${mkdir_cmd[@]}"

BASELINE_EXP="${EXP_ROOT}_baseline_heldout"
BASELINE_REPORT="${REPORT_ROOT}/baseline.json"
echo
echo "[3/6] Held-out baseline without generated experiences"
baseline_eval=(
  "${PY}" scripts/eval_material_performance_experience.py
  --agent-config configs/agents/practice/chem_performance_agent_single.yaml
  --dataset "${VALIDATION_DATASET_NAME}"
  --exp-id "${BASELINE_EXP}"
  --concurrency "${HELDOUT_CONCURRENCY}"
)
print_or_run "${baseline_eval[@]}"
baseline_report=(
  "${PY}" scripts/db/report_material_performance_hp.py
  --db test.db
  --heldout-exp-id "${BASELINE_EXP}"
  --agent-config configs/agents/practice/chem_performance_agent_single.yaml
  --expected-heldout-questions "${VALIDATION_TOTAL}"
  --output "${BASELINE_REPORT}"
)
print_or_run "${baseline_report[@]}"

echo
echo "[4/6] Stage A: choose batch_size using generated-pack held-out evaluation"
stage_a=(
  "${PY}" scripts/run_hyperparam_sweep.py
  --config_name "${CONFIG_NAME}"
  --dataset "${TRAIN_DATASET_NAME}"
  --truncate "${TRAIN_TOTAL}"
  --epochs "${EPOCHS}"
  --batch_sizes "${BATCH_SIZES_A}"
  --grpo_ns "${GRPO_N_A}"
  --rollout_concurrency "${ROLLOUT_CONCURRENCY}"
  --rollout_concurrency_fallback "${ROLLOUT_CONCURRENCY_FALLBACK}"
  --restart_step 0
  "${rag_flag[@]}"
  --exp_prefix "${EXP_PREFIX_A}"
  --heldout_dataset "${VALIDATION_DATASET_NAME}"
  --heldout_expected_questions "${VALIDATION_TOTAL}"
  --heldout_concurrency "${HELDOUT_CONCURRENCY}"
  --report_dir "${REPORT_A}"
)
if [[ "${DRY_RUN}" == "1" ]]; then
  stage_a+=(--dry_run)
fi
echo "\$ $(quote_cmd "${stage_a[@]}")"
"${stage_a[@]}"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo
  echo "[5/6] Stage B runs only after Stage A selects BEST_B."
  echo "Planned grpo_n candidates: ${GRPO_NS_B}; batch_size comes from Stage A."
  echo "[6/6] Dry run complete. No files, DB rows, or model calls were created."
  exit 0
fi

selector_a=(
  "${PY}" scripts/db/select_material_performance_hp.py
  --report-glob "${REPORT_A}/*.json"
  --parameter batch_size
)
"${selector_a[@]}" | tee "${REPORT_ROOT}/stage_a_selection.txt"
BEST_B="$("${selector_a[@]}" --value-only | tail -n 1)"
if ! [[ "${BEST_B}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: invalid Stage A batch size: ${BEST_B}" >&2
  exit 7
fi

echo
echo "[5/6] Stage B: choose grpo_n with held-out evaluation (batch_size=${BEST_B})"
EXP_PREFIX_B="${EXP_PREFIX_B:-${EXP_ROOT}_B_b${BEST_B}_nsweep_}"
stage_b=(
  "${PY}" scripts/run_hyperparam_sweep.py
  --config_name "${CONFIG_NAME}"
  --dataset "${TRAIN_DATASET_NAME}"
  --truncate "${TRAIN_TOTAL}"
  --epochs "${EPOCHS}"
  --batch_sizes "${BEST_B}"
  --grpo_ns "${GRPO_NS_B}"
  --rollout_concurrency "${ROLLOUT_CONCURRENCY}"
  --rollout_concurrency_fallback "${ROLLOUT_CONCURRENCY_FALLBACK}"
  --restart_step 0
  "${rag_flag[@]}"
  --exp_prefix "${EXP_PREFIX_B}"
  --heldout_dataset "${VALIDATION_DATASET_NAME}"
  --heldout_expected_questions "${VALIDATION_TOTAL}"
  --heldout_concurrency "${HELDOUT_CONCURRENCY}"
  --report_dir "${REPORT_B}"
)
"${stage_b[@]}"

selector_b=(
  "${PY}" scripts/db/select_material_performance_hp.py
  --report-glob "${REPORT_B}/*.json"
  --parameter grpo_n
)
"${selector_b[@]}" | tee "${REPORT_ROOT}/stage_b_selection.txt"
BEST_N="$("${selector_b[@]}" --value-only | tail -n 1)"
if ! [[ "${BEST_N}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: invalid Stage B grpo_n: ${BEST_N}" >&2
  exit 8
fi

FINAL_SAMPLES_PER_TASK="${FINAL_SAMPLES_PER_TASK:-50}"
FINAL_TOTAL="$((19 * FINAL_SAMPLES_PER_TASK))"
RECOMMENDATION_REPORT="${REPORT_ROOT}/recommended_params.txt"
{
  echo "Recommended 19-direction Training-Free GRPO parameters"
  echo "selection_protocol=article_disjoint_generated_pack_heldout_v1"
  echo "train_dataset=${TRAIN_DATASET_NAME}"
  echo "validation_dataset=${VALIDATION_DATASET_NAME}"
  echo "train_questions=${TRAIN_TOTAL}"
  echo "validation_questions=${VALIDATION_TOTAL}"
  echo "batch_size=${BEST_B}"
  echo "grpo_n=${BEST_N}"
  echo "epochs=${EPOCHS}"
  echo "rag=${RAG}"
  echo "rollout_concurrency=${ROLLOUT_CONCURRENCY}"
  echo "final_samples_per_task=${FINAL_SAMPLES_PER_TASK}"
  echo "final_total_samples=${FINAL_TOTAL}"
  echo "baseline_report=${BASELINE_REPORT}"
  echo "stage_a_reports=${REPORT_A}"
  echo "stage_b_reports=${REPORT_B}"
} | tee "${RECOMMENDATION_REPORT}"

echo
echo "[6/6] Hyperparameter test complete"
echo "Recommended: BATCH_SIZE=${BEST_B} GRPO_N=${BEST_N}"
echo "Report: ${RECOMMENDATION_REPORT}"
echo "The 950-row final experience build is a separate, explicitly launched run."
