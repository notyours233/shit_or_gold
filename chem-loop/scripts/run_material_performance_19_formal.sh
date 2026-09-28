#!/usr/bin/env bash
set -euo pipefail

# Gated single-agent GRPO workflow for the 19-direction formal experience pack.
# Stable experience packs are protected until an explicit, post-audit promotion.

usage() {
  cat <<'EOF'
run_material_performance_19_formal.sh

Safe formal workflow for the selected 19-direction GRPO parameters.

Exactly one mode is required:
  --prepare-only  Build/upload the article-disjoint formal and canary datasets.
  --canary-only   Prepare, run/resume the isolated 19-question canary, and audit it.
  --formal        Start a new 950-question formal run after a passing canary audit.
  --resume        Resume the formal run after a passing canary audit.
  --promote       Archive stable packs and promote an already passing formal result.
  -h, --help      Show this help.

Fixed selected parameters:
  batch_size=19, grpo_n=3, epochs=1, RAG=1, rollout_concurrency=4
  formal_samples_per_task=50, formal_questions=950, formal_rollouts=2850
  task_timeout=300 seconds per rollout attempt (existing retry policy remains active)

Safety properties:
  - GRPO always uses chem_performance_single; MAD configs are forbidden.
  - Both canary and formal generation start from the empty experience seed.
  - Dataset identity is checked by ordered sample IDs, not only row count.
  - The 57-question hyperparameter validation document set remains excluded.
  - Canary/formal outputs do not modify stable experience.yaml files.
  - Promotion is a separate action and requires a passing 19/19 formal audit.
EOF
}

MODE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare-only|--canary-only|--formal|--resume|--promote)
      if [[ -n "${MODE}" ]]; then
        echo "ERROR: choose exactly one workflow mode." >&2
        exit 2
      fi
      MODE="$1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  echo "ERROR: one workflow mode is required." >&2
  usage >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
YOUTU="${ROOT}/youtu-chem-loop"
DB_PATH="${YOUTU}/test.db"
PY="${PYTHON_BIN:-${ROOT}/.venv/bin/python}"

CONFIG_NAME="chem_performance_single"
BATCH_SIZE="19"
GRPO_N="3"
EPOCHS="1"
ROLLOUT_CONCURRENCY="4"
TASK_TIMEOUT="300"
FORMAL_PER_TASK="50"
FORMAL_TOTAL="950"
CANARY_PER_TASK="1"
CANARY_TOTAL="19"
SEED="20260805"

DATA_ROOT="${YOUTU}/data/processed/material_performance_19"
SOURCE_JSONL="${DATA_ROOT}/material_performance_19_grpo_v1.jsonl"
HELDOUT_JSONL="${DATA_ROOT}/params/material_performance_19_hp_validation_s3_v3_seed20260803.jsonl"
FORMAL_JSONL="${DATA_ROOT}/formal/material_performance_19_formal_s50_seed${SEED}.jsonl"
FORMAL_MANIFEST="${DATA_ROOT}/formal/material_performance_19_formal_s50_seed${SEED}.manifest.json"
CANARY_JSONL="${DATA_ROOT}/pilots/material_performance_19_pilot_s1_v1.jsonl"
EMPTY_SEED="${DATA_ROOT}/pilots/empty_experience_v1.yaml"

FORMAL_DATASET="material_performance_19_formal_s50_seed${SEED}"
CANARY_DATASET="material_performance_19_formal_canary_s1_seed${SEED}"
FORMAL_EXP="material_performance_19_formal_s50_seed${SEED}_b19_n3_rag1"
CANARY_EXP="material_performance_19_formal_canary_s1_seed${SEED}_b19_n3_rag1"

REPORT_ROOT="${ROOT}/state/reports/${FORMAL_EXP}"
CANARY_REPORT_DIR="${REPORT_ROOT}/canary"
FORMAL_REPORT_DIR="${REPORT_ROOT}/formal"
CANARY_AUDIT="${CANARY_REPORT_DIR}/audit.json"
FORMAL_AUDIT="${FORMAL_REPORT_DIR}/audit.json"
AUDIT_SCRIPT="${YOUTU}/scripts/db/audit_material_performance_19_run.py"
SAMPLER_SCRIPT="${YOUTU}/scripts/data/sample_material_performance_19_formal.py"

YOUTU_STABLE="${YOUTU}/configs/agents/practice/experience.yaml"
MAD_STABLE="${ROOT}/MAD/experience/experience.yaml"
CHROMA_DIR="${ROOT}/MAD/data/chroma_db"
CHROMA_COLLECTION="literature_agent2"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: project Python not found or not executable: ${PY}" >&2
  exit 3
fi
if [[ "${CONFIG_NAME}" == *mad* ]]; then
  echo "ERROR: MAD configs are forbidden for GRPO." >&2
  exit 3
fi
if [[ ! -f "${SOURCE_JSONL}" || ! -f "${HELDOUT_JSONL}" || ! -f "${CANARY_JSONL}" ]]; then
  echo "ERROR: one or more required material-performance datasets are missing." >&2
  exit 4
fi
if [[ ! -f "${EMPTY_SEED}" ]]; then
  echo "ERROR: isolated empty experience seed is missing: ${EMPTY_SEED}" >&2
  exit 4
fi

cd "${YOUTU}"
export UTU_DB_URL="sqlite:///test.db"
export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
export TMPDIR="${TMPDIR:-/tmp}"
export PYTHONUNBUFFERED="1"
export PYTHONPATH="${YOUTU}${PYTHONPATH:+:${PYTHONPATH}}"
export CHEM_LITERATURE_BACKEND="chroma"
export CHEM_LITERATURE_CHROMA_DIR="../MAD/data/chroma_db"
export CHEM_LITERATURE_CHROMA_COLLECTION="${CHROMA_COLLECTION}"
export CHEM_GRPO_RAG_ENABLED="1"
export CHEM_GRPO_RAG_LIMIT="${CHEM_GRPO_RAG_LIMIT:-5}"
export CHEM_LITERATURE_CHROMA_MAX_DISTANCE="${CHEM_LITERATURE_CHROMA_MAX_DISTANCE:-0.35}"
export UTU_EXPERIENCE_BATCH_UPDATE_MODE="direct"
export UTU_EXPERIENCE_PROMPT_PACK="chem"

if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
  echo "ERROR: selected Python cannot import utu: ${PY}" >&2
  exit 3
fi

quote_cmd() {
  local out=""
  local arg
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

json_status() {
  local path="$1"
  "${PY}" - "${path}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print("missing")
else:
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(str(payload.get("status") or "unknown"))
PY
}

exp_row_count() {
  local exp_id="$1"
  "${PY}" - "${DB_PATH}" "${exp_id}_epoch_0" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as con:
    value = con.execute(
        "SELECT COUNT(*) FROM evaluation_data WHERE exp_id=?", (sys.argv[2],)
    ).fetchone()[0]
print(int(value or 0))
PY
}

dataset_status() {
  local dataset_name="$1"
  local dataset_jsonl="$2"
  "${PY}" "${AUDIT_SCRIPT}" dataset-status \
    --db "${DB_PATH}" \
    --dataset-name "${dataset_name}" \
    --dataset-jsonl "${dataset_jsonl}" | tail -n 1
}

ensure_dataset() {
  local dataset_name="$1"
  local dataset_jsonl="$2"
  local status
  status="$(dataset_status "${dataset_name}" "${dataset_jsonl}")"
  case "${status}" in
    missing)
      "${PY}" scripts/data/upload_dataset.py \
        --file_path "${dataset_jsonl}" \
        --dataset_name "${dataset_name}" \
        --data_format default
      ;;
    match)
      echo "DB dataset verified by ordered sample IDs: ${dataset_name}"
      ;;
    *)
      echo "ERROR: DB dataset '${dataset_name}' does not exactly match ${dataset_jsonl}." >&2
      echo "Use a new versioned dataset name; this workflow will not delete stale rows." >&2
      exit 5
      ;;
  esac
  status="$(dataset_status "${dataset_name}" "${dataset_jsonl}")"
  if [[ "${status}" != "match" ]]; then
    echo "ERROR: DB dataset verification failed after upload: ${dataset_name}" >&2
    exit 5
  fi
}

snapshot_stable_packs() {
  local output="$1"
  "${PY}" "${AUDIT_SCRIPT}" snapshot \
    --file "${YOUTU_STABLE}" \
    --file "${MAD_STABLE}" \
    --output "${output}"
}

run_preflight() {
  local dataset_name="$1"
  local dataset_jsonl="$2"
  local questions="$3"
  local per_task="$4"
  local output="$5"
  "${PY}" "${AUDIT_SCRIPT}" preflight \
    --db "${DB_PATH}" \
    --dataset-name "${dataset_name}" \
    --dataset-jsonl "${dataset_jsonl}" \
    --expected-questions "${questions}" \
    --expected-per-task "${per_task}" \
    --chroma-dir "${CHROMA_DIR}" \
    --chroma-collection "${CHROMA_COLLECTION}" \
    --output "${output}"
}

prepare_datasets() {
  mkdir -p "${REPORT_ROOT}"
  echo "[prepare] Build deterministic 950-question formal sample"
  "${PY}" "${SAMPLER_SCRIPT}" \
    --input-file "${SOURCE_JSONL}" \
    --output-file "${FORMAL_JSONL}" \
    --manifest-file "${FORMAL_MANIFEST}" \
    --exclude-file "${HELDOUT_JSONL}" \
    --per-task "${FORMAL_PER_TASK}" \
    --seed "${SEED}"

  echo "[prepare] Verify/upload exact DB datasets"
  ensure_dataset "${FORMAL_DATASET}" "${FORMAL_JSONL}"
  ensure_dataset "${CANARY_DATASET}" "${CANARY_JSONL}"

  "${PY}" - "${FORMAL_MANIFEST}" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert manifest["formal"]["total_samples"] == 950
assert manifest["formal"]["unique_doc_ids"] == 950
assert set(manifest["formal"]["counts_by_task"].values()) == {50}
assert not any(manifest["leakage_checks"].values())
print("formal_manifest_gate=pass")
PY
}

run_grpo_and_audit() {
  local stage="$1"
  local dataset_name="$2"
  local dataset_jsonl="$3"
  local exp_name="$4"
  local questions="$5"
  local per_task="$6"
  local min_experience_tasks="$7"
  local resume="$8"
  local report_dir="$9"

  mkdir -p "${report_dir}"
  local log_file="${report_dir}/run.log"
  local preflight_report="${report_dir}/preflight.json"
  local protected_snapshot="${report_dir}/protected_packs_before.json"
  local audit_report="${report_dir}/audit.json"
  local agent_config="${YOUTU}/configs/agents/practice/${exp_name}_agent.yaml"

  snapshot_stable_packs "${protected_snapshot}"
  run_preflight "${dataset_name}" "${dataset_jsonl}" "${questions}" "${per_task}" "${preflight_report}"

  local cmd=(
    "${PY}" scripts/run_training_free_GRPO.py
    --config_name "${CONFIG_NAME}"
    --experiment_name "${exp_name}"
    --practice_dataset_name "${dataset_name}"
    --epochs "${EPOCHS}"
    --batch_size "${BATCH_SIZE}"
    --grpo_n "${GRPO_N}"
    --rollout_data_truncate "${questions}"
    --rollout_concurrency "${ROLLOUT_CONCURRENCY}"
    --task_timeout "${TASK_TIMEOUT}"
    --seed_experience_yaml "${EMPTY_SEED}"
  )
  if [[ "${resume}" != "1" ]]; then
    cmd+=(--restart_step 0)
  fi

  echo "[${stage}] Single-agent Training-Free GRPO"
  echo "dataset=${dataset_name} questions=${questions} expected_rollouts=$((questions * GRPO_N))"
  echo "exp_name=${exp_name} resume=${resume}"
  echo "\$ $(quote_cmd "${cmd[@]}")"
  set +e
  "${cmd[@]}" 2>&1 | tee "${log_file}"
  local run_status="${PIPESTATUS[0]}"
  set -e
  if [[ "${run_status}" -ne 0 ]]; then
    echo "ERROR: ${stage} GRPO failed (exit=${run_status}). Log: ${log_file}" >&2
    if [[ "${stage}" == "formal" ]]; then
      echo "Resume with: ${ROOT}/scripts/run_material_performance_19_formal.sh --resume" >&2
    fi
    exit "${run_status}"
  fi

  echo "[${stage}] Audit judged rows, task coverage, single-agent boundary, experiences, and protected packs"
  "${PY}" "${AUDIT_SCRIPT}" audit \
    --db "${DB_PATH}" \
    --dataset-name "${dataset_name}" \
    --dataset-jsonl "${dataset_jsonl}" \
    --exp-id "${exp_name}_epoch_0" \
    --agent-config "${agent_config}" \
    --log-file "${log_file}" \
    --protected-snapshot "${protected_snapshot}" \
    --expected-questions "${questions}" \
    --grpo-n "${GRPO_N}" \
    --expected-per-task "${per_task}" \
    --min-experience-task-coverage "${min_experience_tasks}" \
    --output "${audit_report}"
}

promote_formal_pack() {
  if [[ "$(json_status "${FORMAL_AUDIT}")" != "pass" ]]; then
    echo "ERROR: formal audit is not passing: ${FORMAL_AUDIT}" >&2
    exit 8
  fi
  local source_agent="${YOUTU}/configs/agents/practice/${FORMAL_EXP}_agent.yaml"
  if [[ ! -f "${source_agent}" ]]; then
    echo "ERROR: audited formal agent YAML is missing: ${source_agent}" >&2
    exit 8
  fi

  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  local archive_dir="${FORMAL_REPORT_DIR}/promotion_archive/${ts}"
  mkdir -p "${archive_dir}"
  if [[ -f "${YOUTU_STABLE}" ]]; then
    cp -f "${YOUTU_STABLE}" "${archive_dir}/youtu_experience.yaml"
  fi
  if [[ -f "${MAD_STABLE}" ]]; then
    cp -f "${MAD_STABLE}" "${archive_dir}/mad_experience.yaml"
  fi

  echo "[promote] Archived previous stable packs under: ${archive_dir}"
  "${ROOT}/scripts/run_closed_loop.sh" \
    --seed_agent_yaml "${source_agent}" \
    --skip_debate_update \
    --config_name "${CONFIG_NAME}"
  echo "[promote] Stable experience packs updated from audited formal result."
}

case "${MODE}" in
  --prepare-only)
    prepare_datasets
    mkdir -p "${REPORT_ROOT}"
    run_preflight "${FORMAL_DATASET}" "${FORMAL_JSONL}" "${FORMAL_TOTAL}" "${FORMAL_PER_TASK}" "${REPORT_ROOT}/prepare_preflight.json"
    echo "Prepared without model calls: ${FORMAL_DATASET} (${FORMAL_TOTAL})"
    ;;
  --canary-only)
    prepare_datasets
    canary_rows="$(exp_row_count "${CANARY_EXP}")"
    canary_resume="0"
    if [[ "${canary_rows}" -gt 0 ]]; then
      canary_resume="1"
      echo "Canary has ${canary_rows} existing rows; resuming cached state."
    fi
    run_grpo_and_audit \
      "canary" "${CANARY_DATASET}" "${CANARY_JSONL}" "${CANARY_EXP}" \
      "${CANARY_TOTAL}" "${CANARY_PER_TASK}" "0" "${canary_resume}" "${CANARY_REPORT_DIR}"
    echo "Canary gate passed. Formal launch is now eligible."
    ;;
  --formal)
    prepare_datasets
    if [[ "$(json_status "${CANARY_AUDIT}")" != "pass" ]]; then
      echo "ERROR: canary audit must pass before formal launch: ${CANARY_AUDIT}" >&2
      exit 7
    fi
    formal_rows="$(exp_row_count "${FORMAL_EXP}")"
    if [[ "${formal_rows}" -ne 0 ]]; then
      echo "ERROR: formal experiment already has ${formal_rows} rows; use --resume." >&2
      exit 7
    fi
    run_grpo_and_audit \
      "formal" "${FORMAL_DATASET}" "${FORMAL_JSONL}" "${FORMAL_EXP}" \
      "${FORMAL_TOTAL}" "${FORMAL_PER_TASK}" "19" "0" "${FORMAL_REPORT_DIR}"
    echo "Formal audit passed. Stable packs remain unchanged; promotion is still separate."
    ;;
  --resume)
    prepare_datasets
    if [[ "$(json_status "${CANARY_AUDIT}")" != "pass" ]]; then
      echo "ERROR: canary audit must pass before formal resume: ${CANARY_AUDIT}" >&2
      exit 7
    fi
    formal_rows="$(exp_row_count "${FORMAL_EXP}")"
    if [[ "${formal_rows}" -eq 0 ]]; then
      echo "ERROR: no formal state exists to resume; use --formal." >&2
      exit 7
    fi
    run_grpo_and_audit \
      "formal" "${FORMAL_DATASET}" "${FORMAL_JSONL}" "${FORMAL_EXP}" \
      "${FORMAL_TOTAL}" "${FORMAL_PER_TASK}" "19" "1" "${FORMAL_REPORT_DIR}"
    echo "Formal resume and audit passed. Stable packs remain unchanged."
    ;;
  --promote)
    promote_formal_pack
    ;;
esac
