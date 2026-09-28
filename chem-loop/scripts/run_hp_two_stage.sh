#!/usr/bin/env bash
set -euo pipefail

# Two-stage hyperparameter plan (user-approved):
# Stage A: Fix grpo_n=3, sweep batch_size in {3,4,5,6,10,15,20}.
# Stage B: Pick the best batch_size from Stage A (by avg_reward), then sweep grpo_n in {2,3,4,5,6,7}.
#
# Runs inside Docker against the shared /state/test.db and a balanced 50-sample dataset
# (8 reactions * PER_REACTION + CO2RR has 2 tasks * CO2RR_PER_TASK).
#
# Concurrency policy:
# - Default to rollout_concurrency=4 for stability (WSL/docker memory pressure can disconnect the host).
# - You can still opt into higher concurrency by setting ROLLOUT_CONCURRENCY explicitly.
#
# Usage:
#   cd project/chem-loop
#   bash scripts/run_hp_two_stage.sh
#
# Common overrides:
#   # Dataset:
#   PER_REACTION=6 CO2RR_PER_TASK=6 SEED=42 bash scripts/run_hp_two_stage.sh
#
#   # Concurrency:
#   ROLLOUT_CONCURRENCY=8 ROLLOUT_CONCURRENCY_FALLBACK=4 bash scripts/run_hp_two_stage.sh
#
#   # RAG off (lower memory; keep fixed for the whole sweep):
#   RAG=0 bash scripts/run_hp_two_stage.sh
#
#   # Safety preview (commands only; no execution):
#   DRY_RUN=1 bash scripts/run_hp_two_stage.sh

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
# Two-stage plan
EPOCHS="${EPOCHS:-1}"
BATCH_SIZES_A="${BATCH_SIZES_A:-3,4,5,6,10,15,20}"
GRPO_N_A="${GRPO_N_A:-3}"
GRPO_NS_B="${GRPO_NS_B:-2,3,4,5,6,7}"

# Fixed knobs (not tuned)
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"
ROLLOUT_CONCURRENCY_FALLBACK="${ROLLOUT_CONCURRENCY_FALLBACK:-4}"
RESTART_STEP="${RESTART_STEP:-0}"

RAG="${RAG:-1}" # 1 => rag on, 0 => rag off (keep constant across both stages)
DRY_RUN="${DRY_RUN:-0}" # 1 => print commands only

TS="$(date +%Y%m%d_%H%M%S)"
EXP_ROOT="${EXP_ROOT:-single_hp2stage_bal${TOTAL_SAMPLES}_${TS}}"
EXP_PREFIX_A="${EXP_PREFIX_A:-${EXP_ROOT}_A_n${GRPO_N_A}_bsweep_}"

echo "== hp two-stage sweep (docker) =="
echo "- service: ${SERVICE}"
echo "- input_dataset: ${INPUT_DATASET_FILE}"
echo "- dataset: ${DATASET_NAME} (file=${DATASET_FILE})"
echo "- per_reaction: ${PER_REACTION} (CO2RR per task: ${CO2RR_PER_TASK}) total=${TOTAL_SAMPLES}"
echo "- truncate: ${TRUNCATE}"
echo "- stageA: grpo_n=${GRPO_N_A} batch_sizes=${BATCH_SIZES_A}"
echo "- stageB: grpo_ns=${GRPO_NS_B} batch_size=best_from_stageA"
echo "- fixed: epochs=${EPOCHS} rollout_concurrency=${ROLLOUT_CONCURRENCY} rag=${RAG} restart_step=${RESTART_STEP}"
echo "- safety: rollout_concurrency_fallback=${ROLLOUT_CONCURRENCY_FALLBACK} (auto-switch on failure)"
echo "- exp_root: ${EXP_ROOT}"
echo "- exp_prefix_A: ${EXP_PREFIX_A}"
echo "- controls: DRY_RUN=${DRY_RUN}"
echo

rag_flag="--rag"
if [[ "${RAG}" = "0" ]]; then
  rag_flag="--no-rag"
fi

dry_flag=""
if [[ "${DRY_RUN}" = "1" ]]; then
  dry_flag="--dry_run"
fi

# ------------------------------------------------------------------------------
# Step 0: Ensure /state dirs exist
docker compose exec "${SERVICE}" sh -lc '
  set -e
  mkdir -p /state/datasets /state/reports /state/experience_sweeps
'

# ------------------------------------------------------------------------------
# Step 1: Build a balanced dataset JSONL under /state (skip if already exists)
echo "[1/6] Build balanced dataset JSONL -> ${DATASET_FILE}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  if [ -f '${DATASET_FILE}' ]; then
    echo '[hp_two_stage] keep existing dataset file: ${DATASET_FILE}'
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
echo "[2/6] Upload dataset into DB (skip if present): ${DATASET_NAME}"
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
  echo "[hp_two_stage] dataset already present in DB (rows=${dataset_rows}); skip upload"
else
  echo "[hp_two_stage] dataset not found in DB; uploading ${DATASET_FILE}"
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
# Step 3: Stage A sweep (batch_size grid, grpo_n fixed)
echo
echo "[3/6] Stage A sweep: grpo_n=${GRPO_N_A} batch_sizes=${BATCH_SIZES_A}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  # Deterministic batch merge to prevent long paragraph cards from being swallowed by token limits.
  UTU_EXPERIENCE_PROMPT_PACK=chem \
  UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct \
  python scripts/run_hyperparam_sweep.py \
    --config_name chem_performance_single \
    --dataset '${DATASET_NAME}' \
    --truncate ${TRUNCATE} \
    --epochs '${EPOCHS}' \
    --batch_sizes '${BATCH_SIZES_A}' \
    --grpo_ns '${GRPO_N_A}' \
    --rollout_concurrency ${ROLLOUT_CONCURRENCY} \
    --rollout_concurrency_fallback ${ROLLOUT_CONCURRENCY_FALLBACK} \
    --restart_step ${RESTART_STEP} \
    ${rag_flag} \
    --exp_prefix '${EXP_PREFIX_A}' \
    ${dry_flag} \
  2>&1 | tee /state/reports/hp_two_stage_${EXP_ROOT}_A.log
"

docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/summarize_experiments.py \
    --db /state/test.db \
    --exp_prefix '${EXP_PREFIX_A}' \
    --order avg_reward_desc \
  2>&1 | tee /state/reports/hp_two_stage_${EXP_ROOT}_A_summary.txt
"

echo
echo "[4/6] Pick best batch_size from Stage A (by avg_reward)"
BEST_B="$(
  docker compose exec -T "${SERVICE}" sh -lc "
    cd /app/youtu-chem-loop
    HP_PREFIX='${EXP_PREFIX_A}' python - <<'PY'
import os
import re
import sqlite3

db = '/state/test.db'
prefix = os.environ.get('HP_PREFIX', '').strip()
if not prefix:
    raise SystemExit('missing HP_PREFIX')

con = sqlite3.connect(db)
try:
    cur = con.cursor()
    cur.execute(
        \"SELECT exp_id, COUNT(*), AVG(reward) FROM evaluation_data \"
        \"WHERE exp_id LIKE ? AND stage='judged' GROUP BY exp_id\",
        (f\"{prefix}%\",),
    )
    rows = cur.fetchall()
finally:
    con.close()

best = None  # tuple(score_tuple, batch_size, exp_id, avg_reward, n_judged)
for exp_id, n, avg in rows:
    if avg is None or n is None:
        continue
    m = re.search(r\"_b(?P<b>[0-9]+)_n(?P<n>[0-9]+)_epoch_0$\", str(exp_id))
    if not m:
        continue
    b = int(m.group('b'))
    n_grpo = int(m.group('n'))
    if n_grpo != 3:
        continue
    n = int(n)
    avg = float(avg)
    # Primary: higher avg_reward. Tie-break: smaller batch_size (cheaper).
    score = (avg, -b)
    cand = (score, b, str(exp_id), avg, n)
    if best is None or cand[0] > best[0]:
        best = cand

if best is None:
    raise SystemExit('No Stage A runs found in DB (did Stage A fail?)')

_, b, exp_id, avg, n = best
print(f\"[stageA_best] exp_id={exp_id} avg_reward={avg:.4f} n_judged={n} batch_size={b}\")
print(b)
PY
  " | tr -d '\r' | tail -n 1
)"

if [[ -z "${BEST_B}" ]] || ! [[ "${BEST_B}" =~ ^[0-9]+$ ]]; then
  echo "[hp_two_stage] ERROR: failed to pick BEST_B (got '${BEST_B}')" >&2
  exit 2
fi

EXP_PREFIX_B="${EXP_PREFIX_B:-${EXP_ROOT}_B_b${BEST_B}_nsweep_}"
echo "- BEST_B=${BEST_B}"
echo "- exp_prefix_B: ${EXP_PREFIX_B}"

# ------------------------------------------------------------------------------
# Step 5: Stage B sweep (grpo_n grid, batch_size fixed)
echo
echo "[5/6] Stage B sweep: batch_size=${BEST_B} grpo_ns=${GRPO_NS_B}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  UTU_EXPERIENCE_PROMPT_PACK=chem \
  UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct \
  python scripts/run_hyperparam_sweep.py \
    --config_name chem_performance_single \
    --dataset '${DATASET_NAME}' \
    --truncate ${TRUNCATE} \
    --epochs '${EPOCHS}' \
    --batch_sizes '${BEST_B}' \
    --grpo_ns '${GRPO_NS_B}' \
    --rollout_concurrency ${ROLLOUT_CONCURRENCY} \
    --rollout_concurrency_fallback ${ROLLOUT_CONCURRENCY_FALLBACK} \
    --restart_step ${RESTART_STEP} \
    ${rag_flag} \
    --exp_prefix '${EXP_PREFIX_B}' \
    ${dry_flag} \
  2>&1 | tee /state/reports/hp_two_stage_${EXP_ROOT}_B.log
"

docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/summarize_experiments.py \
    --db /state/test.db \
    --exp_prefix '${EXP_PREFIX_B}' \
    --order avg_reward_desc \
  2>&1 | tee /state/reports/hp_two_stage_${EXP_ROOT}_B_summary.txt
"

# ------------------------------------------------------------------------------
# Step 6: Export generated agent YAMLs for inspection
echo
echo "[6/6] Export agent YAMLs -> /state/experience_sweeps/${EXP_ROOT}/"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  out_dir='/state/experience_sweeps/${EXP_ROOT}'
  mkdir -p \"\${out_dir}\"
  for f in configs/agents/practice/${EXP_PREFIX_A}*agent.yaml configs/agents/practice/${EXP_PREFIX_B}*agent.yaml; do
    [ -f \"\${f}\" ] || continue
    cp -f \"\${f}\" \"\${out_dir}/\"
  done
  echo \"[hp_two_stage] wrote: \${out_dir}\"
"

echo
echo "Done."
echo "Artifacts (host):"
echo "- state/reports/hp_two_stage_${EXP_ROOT}_A.log"
echo "- state/reports/hp_two_stage_${EXP_ROOT}_A_summary.txt"
echo "- state/reports/hp_two_stage_${EXP_ROOT}_B.log"
echo "- state/reports/hp_two_stage_${EXP_ROOT}_B_summary.txt"
echo "- state/experience_sweeps/${EXP_ROOT}/"
