#!/usr/bin/env bash
set -euo pipefail

# Docker wrapper: disciplined hyperparameter sweep for single-agent Training-Free GRPO.
#
# This follows spec-bank/hyperparam_experiments.md discipline:
# - Only tune: epochs / batch_size / grpo_n
# - Keep everything else fixed across the sweep (dataset, truncate, rollout_concurrency, RAG knobs, verify logic)
#
# Why a wrapper script?
# - Makes the sweep reproducible in Docker (shared /state DB)
# - Ensures experience merge is deterministic for long paragraph micro-cards (prevents "swallowed" experiences)
#
# Usage:
#   cd project/chem-loop
#   bash scripts/run_hp_sweep.sh
#
# Common overrides:
#   # Faster / less memory:
#   ROLLOUT_CONCURRENCY=1 bash scripts/run_hp_sweep.sh
#
#   # Larger balanced dataset (more stable comparisons, higher cost):
#   PER_REACTION=20 CO2RR_PER_TASK=20 bash scripts/run_hp_sweep.sh
#
#   # Change sweep grid (start small):
#   EPOCHS="1,2" BATCH_SIZES="16,32,50" GRPO_NS="2,3,4" bash scripts/run_hp_sweep.sh
#
# Safety controls:
#   # Preview commands only (no execution):
#   DRY_RUN=1 bash scripts/run_hp_sweep.sh
#
#   # Allow large sweeps (>12 combos):
#   YES=1 bash scripts/run_hp_sweep.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

SERVICE="${CHEMCOUNCIL_SERVICE:-chemcouncil}"

# -------------------------
# Dataset (balanced subset)
SEED="${SEED:-42}"
# Default to 60 samples total (PER_REACTION=6, CO2RR_PER_TASK=6 => 8*6 + 2*6 = 60).
PER_REACTION="${PER_REACTION:-6}"
CO2RR_PER_TASK="${CO2RR_PER_TASK:-6}"
INPUT_DATASET_FILE="${INPUT_DATASET_FILE:-data/processed/chem_performance/chem_performance_dataset_v5.jsonl}"

# Total samples: 8 regression reactions + CO2RR has 2 tasks.
TOTAL_SAMPLES="${TOTAL_SAMPLES:-$((8 * PER_REACTION + 2 * CO2RR_PER_TASK))}"
TRUNCATE="${TRUNCATE:-${TOTAL_SAMPLES}}"

DATASET_NAME="${DATASET_NAME:-chem_performance_v5_bal${PER_REACTION}_co2${CO2RR_PER_TASK}_seed${SEED}}"
DATASET_FILE="/state/datasets/${DATASET_NAME}.jsonl"

# -------------------------
# Sweep grid (only these 3 are tunable)
EPOCHS="${EPOCHS:-1}"
BATCH_SIZES="${BATCH_SIZES:-16,32,50}"
GRPO_NS="${GRPO_NS:-2,3}"

# Fixed knobs for comparability
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"
ROLLOUT_CONCURRENCY_FALLBACK="${ROLLOUT_CONCURRENCY_FALLBACK:-4}"
RESTART_STEP="${RESTART_STEP:-0}"

RAG="${RAG:-1}" # 1 => rag on, 0 => rag off
YES="${YES:-0}" # 1 => allow large sweeps (>12 combos)
DRY_RUN="${DRY_RUN:-0}" # 1 => print commands only

TS="$(date +%Y%m%d_%H%M%S)"
EXP_PREFIX="${EXP_PREFIX:-single_hp_bal${TOTAL_SAMPLES}_${TS}_}"

echo "== hyperparam sweep (docker) =="
echo "- service: ${SERVICE}"
echo "- input_dataset: ${INPUT_DATASET_FILE}"
echo "- dataset: ${DATASET_NAME} (file=${DATASET_FILE})"
echo "- per_reaction: ${PER_REACTION} (CO2RR per task: ${CO2RR_PER_TASK}) total=${TOTAL_SAMPLES}"
echo "- truncate: ${TRUNCATE}"
echo "- grid: epochs=${EPOCHS} batch_sizes=${BATCH_SIZES} grpo_ns=${GRPO_NS}"
echo "- fixed: rollout_concurrency=${ROLLOUT_CONCURRENCY} rag=${RAG} restart_step=${RESTART_STEP}"
echo "- safety: rollout_concurrency_fallback=${ROLLOUT_CONCURRENCY_FALLBACK} (auto-switch on failure)"
echo "- controls: YES=${YES} DRY_RUN=${DRY_RUN}"
echo "- exp_prefix: ${EXP_PREFIX}"
echo

# ------------------------------------------------------------------------------
# Step 0: Ensure /state dirs exist
docker compose exec "${SERVICE}" sh -lc '
  set -e
  mkdir -p /state/datasets /state/reports /state/experience_sweeps
'

# ------------------------------------------------------------------------------
# Step 1: Build a balanced dataset JSONL under /state (skip if already exists)
echo "[1/4] Build balanced dataset JSONL -> ${DATASET_FILE}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  if [ -f '${DATASET_FILE}' ]; then
    echo '[hp_sweep] keep existing dataset file: ${DATASET_FILE}'
    exit 0
  fi
  cd /app/youtu-chem-loop
  python scripts/data/sample_chem_performance_balanced_dataset.py \
    --input_file '${INPUT_DATASET_FILE}' \
    --output_file '${DATASET_FILE}' \
    --per_reaction ${PER_REACTION} \
    --co2rr_per_task ${CO2RR_PER_TASK} \
    --seed ${SEED}
"

# ------------------------------------------------------------------------------
# Step 2: Upload dataset to sqlite DB (skip if already present)
echo
echo "[2/4] Upload dataset into DB (skip if present): ${DATASET_NAME}"
dataset_rows="$(
  docker compose exec -T "${SERVICE}" sh -lc "
    cd /app/youtu-chem-loop
    DATASET_NAME='${DATASET_NAME}' python - <<'PY'
import os
from utu.utils import SQLModelUtils
from utu.db import DatasetSample
from sqlalchemy import func
from sqlmodel import select

name = os.environ.get('DATASET_NAME', '').strip()
with SQLModelUtils.create_session() as session:
    n = session.exec(select(func.count()).select_from(DatasetSample).where(DatasetSample.dataset == name)).one()
print(int(n or 0))
PY
  " | tr -d '\r' | tail -n 1
)"

if [[ "${dataset_rows}" =~ ^[0-9]+$ ]] && [[ "${dataset_rows}" -gt 0 ]]; then
  echo "[hp_sweep] dataset already present in DB (rows=${dataset_rows}); skip upload"
else
  echo "[hp_sweep] dataset not found in DB; uploading ${DATASET_FILE}"
  docker compose exec "${SERVICE}" sh -lc "
    set -e
    cd /app/youtu-chem-loop
    python -m scripts.data.upload_dataset \
      --file_path '${DATASET_FILE}' \
      --dataset_name '${DATASET_NAME}' \
      --data_format default
  "
fi

# ------------------------------------------------------------------------------
# Step 3: Run the sweep (uses stdlib-only runner)
echo
echo "[3/4] Run sweep (this can take a while)"
rag_flag="--rag"
if [[ "${RAG}" = "0" ]]; then
  rag_flag="--no-rag"
fi

yes_flag=""
if [[ "${YES}" = "1" ]]; then
  yes_flag="--yes"
fi

dry_flag=""
if [[ "${DRY_RUN}" = "1" ]]; then
  dry_flag="--dry_run"
fi

docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  # Deterministic batch merge to prevent long paragraph cards from being swallowed by token limits.
  UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct \
  python scripts/run_hyperparam_sweep.py \
    --config_name chem_performance_single \
    --dataset '${DATASET_NAME}' \
    --truncate ${TRUNCATE} \
    --epochs '${EPOCHS}' \
    --batch_sizes '${BATCH_SIZES}' \
    --grpo_ns '${GRPO_NS}' \
    --rollout_concurrency ${ROLLOUT_CONCURRENCY} \
    --rollout_concurrency_fallback ${ROLLOUT_CONCURRENCY_FALLBACK} \
    --restart_step ${RESTART_STEP} \
    ${rag_flag} \
    --exp_prefix '${EXP_PREFIX}' \
    ${yes_flag} \
    ${dry_flag} \
  2>&1 | tee /state/reports/hp_sweep_${TS}.log
"

# ------------------------------------------------------------------------------
# Step 4: Export artifacts to /state for inspection
echo
echo "[4/4] Export agent YAMLs + summary reports -> /state"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  out_dir='/state/experience_sweeps/${EXP_PREFIX}'
  mkdir -p \"\${out_dir}\"

  # Copy all generated agent configs for this sweep prefix.
  for f in configs/agents/practice/${EXP_PREFIX}*agent.yaml; do
    [ -f \"\${f}\" ] || continue
    cp -f \"\${f}\" \"\${out_dir}/\"
  done

  # Save a final table (reward + guideline count) for quick comparison.
  python scripts/db/summarize_experiments.py \
    --db /state/test.db \
    --exp_prefix '${EXP_PREFIX}' \
    --order avg_reward_desc \
  2>&1 | tee /state/reports/hp_summary_${TS}.txt
"

echo
echo "Done."
echo "Artifacts (host):"
echo "- state/reports/hp_sweep_${TS}.log"
echo "- state/reports/hp_summary_${TS}.txt"
echo "- state/experience_sweeps/${EXP_PREFIX}/ (agent YAMLs for this sweep)"
