#!/usr/bin/env bash
set -euo pipefail

# Docker smoke run for a *balanced* 9-reaction subset (5 per reaction_type; CO2RR includes both tasks).
#
# This is the recommended "Step B" after format compliance has been validated:
# - covers all 9 reaction types (HER/OER/ORR/HOR/UOR/EOR/HzOR/O5H/CO2RR)
# - includes CO2RR Task 1 (product classification) + Task 2 (partial current density regression)
# - produces:
#   - format compliance report (DB-based)
#   - conclude payload samples (tool-call structured JSON)
#   - a guideline content report (format vs chemistry vs method)
#
# Usage:
#   cd project/chem-loop
#   ./scripts/run_balanced5_smoke.sh
#
# Optional overrides:
#   DATASET_NAME=chem_performance_v5_balanced5_seed7 SEED=7 ./scripts/run_balanced5_smoke.sh
#   INPUT_DATASET_FILE=data/processed/chem_performance/chem_performance_dataset_v4.jsonl ./scripts/run_balanced5_smoke.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

SERVICE="${CHEMCOUNCIL_SERVICE:-chemcouncil}"

SEED="${SEED:-42}"
PER_REACTION="${PER_REACTION:-5}"
CO2RR_PER_TASK="${CO2RR_PER_TASK:-5}"

INPUT_DATASET_FILE="${INPUT_DATASET_FILE:-data/processed/chem_performance/chem_performance_dataset_v5.jsonl}"

DATASET_NAME="${DATASET_NAME:-chem_performance_v5_balanced5_seed${SEED}}"
DATASET_FILE="/state/datasets/${DATASET_NAME}.jsonl"

# Total samples: 8 regression reactions + CO2RR has 2 tasks per record id.
TOTAL_SAMPLES="${TOTAL_SAMPLES:-$((8 * PER_REACTION + 2 * CO2RR_PER_TASK))}"

EPOCHS="${EPOCHS:-1}"
GRPO_N="${GRPO_N:-1}"
# Rollout concurrency controls how many single-agent samples run in parallel inside one GRPO run.
# Higher values are faster but can increase memory usage significantly (especially when RAG/Chroma is enabled).
# If you hit OOM / returncode=-9, lower this back to 1.
ROLL_OUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"
TRUNCATE="${TRUNCATE:-${TOTAL_SAMPLES}}"

# Default to "one batch" to keep the smoke simple.
BATCH_SIZE="${BATCH_SIZE:-${TRUNCATE}}"
RESTART_STEP="${RESTART_STEP:-0}"

# Experience distillation style (prompt + objective overrides).
# - chem: chemistry micro-cards (current default)
# - broad: legacy "generic" experiences (pre micro-card prompt)
EXPERIENCE_STYLE="${EXPERIENCE_STYLE:-chem}"
UTU_EXPERIENCE_PROMPT_PACK="${UTU_EXPERIENCE_PROMPT_PACK:-}"

EXTRA_GRPO_ARGS=""
case "${EXPERIENCE_STYLE}" in
  broad)
    # Match the "pre-modification" behavior as closely as possible:
    # - generic prompt pack
    # - format/numeric quality learning objective (broad)
    : "${UTU_EXPERIENCE_PROMPT_PACK:=generic}"
    EXTRA_GRPO_ARGS+=" --learning_objective 'Improve strict format compliance (<think>/<answer>, JSON-only numbers, exact key matching) and improve numeric prediction quality.'"
    EXTRA_GRPO_ARGS+=" --num_experiences_per_query 2"
    ;;
  chem|micro|casecard|"")
    : "${UTU_EXPERIENCE_PROMPT_PACK:=chem}"
    ;;
  *)
    echo "[balanced5] WARNING: unknown EXPERIENCE_STYLE='${EXPERIENCE_STYLE}'. Using defaults from config."
    ;;
esac

TS="$(date +%Y%m%d_%H%M%S)"
EXP="${EXP:-balanced5_smoke_${TS}}"

echo "== balanced5 smoke =="
echo "- service: ${SERVICE}"
echo "- input_dataset: ${INPUT_DATASET_FILE}"
echo "- dataset: ${DATASET_NAME} (file=${DATASET_FILE})"
echo "- per_reaction: ${PER_REACTION} (CO2RR per task: ${CO2RR_PER_TASK})"
echo "- total_samples: ${TOTAL_SAMPLES} truncate=${TRUNCATE}"
echo "- grpo: e=${EPOCHS} b=${BATCH_SIZE} n=${GRPO_N} rollout_concurrency=${ROLL_OUT_CONCURRENCY}"
echo "- restart_step: ${RESTART_STEP} (0=fresh, 1+=reuse cache)"
echo "- experience_style: ${EXPERIENCE_STYLE} (UTU_EXPERIENCE_PROMPT_PACK=${UTU_EXPERIENCE_PROMPT_PACK})"
echo "- experiment: ${EXP}"
echo

# ------------------------------------------------------------------------------
# Step 0: Normalize stable experience packs (prune format-only guidelines)
echo "[0/6] Normalize stable experience packs under /state"
docker compose exec "${SERVICE}" sh -lc '
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/export_experience_yaml.py \
    --source_agent_yaml /state/experience_youtu.yaml \
    --output_yaml /state/experience_youtu.yaml
  cp -f /state/experience_youtu.yaml /state/experience_mad.yaml
  grep -n "Format compliance" /state/experience_youtu.yaml || echo "no format guidelines (OK)"
'

# ------------------------------------------------------------------------------
# Step 1: Build balanced dataset JSONL (persist to /state)
echo
echo "[1/6] Build balanced dataset JSONL -> ${DATASET_FILE}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  mkdir -p /state/datasets /state/reports /state/experience_runs
  if [ -f '${DATASET_FILE}' ]; then
    echo '[balanced5] keep existing dataset file: ${DATASET_FILE}'
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
  echo "[balanced5] dataset already present in DB (rows=${dataset_rows}); skip upload"
else
  echo "[balanced5] dataset not found in DB; uploading ${DATASET_FILE}"
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
# Step 3: Run single-agent training-free GRPO rollouts
echo
echo "[3/6] Run GRPO rollout + distill experiences (this may take a while)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  UTU_EXPERIENCE_PROMPT_PACK=${UTU_EXPERIENCE_PROMPT_PACK} UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct python -m scripts.run_training_free_GRPO \
    --config_name chem_performance_single \
    --experiment_name '${EXP}' \
    --practice_dataset_name '${DATASET_NAME}' \
    --epochs ${EPOCHS} --batch_size ${BATCH_SIZE} --grpo_n ${GRPO_N} \
    --rollout_data_truncate ${TRUNCATE} \
    --rollout_concurrency ${ROLL_OUT_CONCURRENCY} \
    --restart_step ${RESTART_STEP} \
    --seed_experience_yaml configs/agents/practice/experience.yaml \
    ${EXTRA_GRPO_ARGS} \
  2>&1 | tee /state/reports/grpo_${EXP}.log
"

# Persist the generated agent YAML to /state so it survives container rebuilds.
echo
echo "[3.5/6] Persist generated agent YAML -> /state/experience_runs/${EXP}_agent.yaml"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cp -f /app/youtu-chem-loop/configs/agents/practice/${EXP}_agent.yaml /state/experience_runs/${EXP}_agent.yaml
"

# ------------------------------------------------------------------------------
# Step 4: Format compliance + conclude payload sampling (DB-based)
echo
echo "[4/6] Format compliance report (DB-based)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/report_format_compliance.py \
    --db /state/test.db \
    --exp_id '${EXP}_epoch_0' \
    --stage judged \
  2>&1 | tee /state/reports/format_${EXP}_epoch_0.txt
"

echo
echo "[4.5/6] Sample conclude() structured payloads"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/inspect_conclude_payloads.py \
    --db /state/test.db \
    --exp_id '${EXP}_epoch_0' \
    --stage judged \
    --limit 8 \
  2>&1 | tee /state/reports/conclude_${EXP}_epoch_0.txt
"

# Optional: save a markdown sample of the stitched <think>/<answer> response text.
echo
echo "[4.8/6] Persist a small rollout sample markdown"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/inspect_rollouts.py \
    --db /state/test.db \
    --exp_id '${EXP}_epoch_0' \
    --stage judged \
    --order id \
    --limit 12 \
    --include_question \
    --out_file /state/inspect_${EXP}_epoch_0.md
"

# ------------------------------------------------------------------------------
# Step 5: Guideline content report (raw agent YAML)
echo
echo "[5/6] Guideline content report (format vs chemistry vs method)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/report_guideline_content.py \
    --agent_yaml /state/experience_runs/${EXP}_agent.yaml \
    --max_show 20 \
  2>&1 | tee /state/reports/guidelines_${EXP}.txt
"

# Also export a normalized experience pack (prunes format-only guidelines) without promoting it.
echo
echo "[5.5/6] Export normalized experience pack (not promoted)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/export_experience_yaml.py \
    --source_agent_yaml /state/experience_runs/${EXP}_agent.yaml \
    --output_yaml /state/experience_runs/${EXP}_experience_normalized.yaml
"

# ------------------------------------------------------------------------------
# Done
echo
echo "[6/6] Done."
echo "Artifacts (host):"
echo "- state/reports/grpo_${EXP}.log"
echo "- state/reports/format_${EXP}_epoch_0.txt"
echo "- state/reports/conclude_${EXP}_epoch_0.txt"
echo "- state/reports/guidelines_${EXP}.txt"
echo "- state/inspect_${EXP}_epoch_0.md"
echo "- state/experience_runs/${EXP}_agent.yaml"
echo "- state/experience_runs/${EXP}_experience_normalized.yaml"
