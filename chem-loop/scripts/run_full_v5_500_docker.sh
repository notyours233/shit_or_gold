#!/usr/bin/env bash
set -euo pipefail

# Docker runner: generate a "full" experience library on the pre-sampled v5_500 dataset (500 samples).
#
# Why this script exists
# - We already have a pre-sampled dataset file under the repo:
#     youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset_v5_500.jsonl  (500 lines)
# - We want to run Training-Free GRPO inside Docker against the shared /state/test.db,
#   and persist artifacts under /state/ so they survive container rebuilds.
#
# Defaults (user-selected):
# - batch_size=4, grpo_n=2 (lab-friendly incremental update cadence)
# - rollout_concurrency=4 (stable for WSL/docker; raise cautiously)
#
# Usage:
#   cd project/chem-loop
#   bash scripts/run_full_v5_500_docker.sh
#
# Common overrides:
#   EXP=single_full_v5_500_b4_n2_$(date +%Y%m%d_%H%M%S) bash scripts/run_full_v5_500_docker.sh
#   ROLLOUT_CONCURRENCY=2 bash scripts/run_full_v5_500_docker.sh
#   PROMOTE=1 bash scripts/run_full_v5_500_docker.sh   # overwrite /state/experience_youtu.yaml after run

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

SERVICE="${CHEMCOUNCIL_SERVICE:-chemcouncil}"

# ---------------------------------------------------------------------------
# Dataset: pre-sampled 500
DATASET_NAME="${DATASET_NAME:-chem_performance_v5_500}"
TOTAL_SAMPLES="${TOTAL_SAMPLES:-500}"
TRUNCATE="${TRUNCATE:-${TOTAL_SAMPLES}}"

# Copy into /state for audit/repro (host-persisted).
DATASET_SRC_IN_CONTAINER="/app/youtu-chem-loop/data/processed/chem_performance/chem_performance_dataset_v5_500.jsonl"
DATASET_FILE="/state/datasets/${DATASET_NAME}.jsonl"

# ---------------------------------------------------------------------------
# GRPO settings (only tune these when doing sweeps; here we lock in b4/n2)
EPOCHS="${EPOCHS:-1}"
BATCH_SIZE="${BATCH_SIZE:-4}"
GRPO_N="${GRPO_N:-2}"

# Fixed knobs
ROLLOUT_CONCURRENCY="${ROLLOUT_CONCURRENCY:-4}"
RESTART_STEP="${RESTART_STEP:-0}"

# Experience distillation style (prompt pack selection)
EXPERIENCE_STYLE="${EXPERIENCE_STYLE:-chem}"
UTU_EXPERIENCE_PROMPT_PACK="${UTU_EXPERIENCE_PROMPT_PACK:-}"

EXTRA_GRPO_ARGS=""
case "${EXPERIENCE_STYLE}" in
  broad)
    : "${UTU_EXPERIENCE_PROMPT_PACK:=generic}"
    EXTRA_GRPO_ARGS+=" --learning_objective 'Improve strict format compliance and improve numeric prediction quality.'"
    EXTRA_GRPO_ARGS+=" --num_experiences_per_query 2"
    ;;
  chem|micro|casecard|"")
    : "${UTU_EXPERIENCE_PROMPT_PACK:=chem}"
    ;;
  *)
    echo "[full_v5_500] WARNING: unknown EXPERIENCE_STYLE='${EXPERIENCE_STYLE}'. Using defaults from config."
    ;;
esac

# If empty => do not pass seed_experience_yaml (start from empty pool).
# NOTE: use `${VAR-default}` (not `:-`) so the user can intentionally set it to empty.
SEED_EXPERIENCE_YAML="${SEED_EXPERIENCE_YAML-configs/agents/practice/experience.yaml}"
SEED_ARG=""
if [[ -n "${SEED_EXPERIENCE_YAML}" ]]; then
  SEED_ARG="--seed_experience_yaml ${SEED_EXPERIENCE_YAML}"
fi

PROMOTE="${PROMOTE:-0}" # 1 => promote normalized pack into /state/experience_youtu.yaml + /state/experience_mad.yaml

TS="$(date +%Y%m%d_%H%M%S)"
EXP="${EXP:-single_full_v5_500_rag1_u1_t${TRUNCATE}_e${EPOCHS}_b${BATCH_SIZE}_n${GRPO_N}_c${ROLLOUT_CONCURRENCY}_${TS}}"

echo "== full v5_500 (docker) =="
echo "- service: ${SERVICE}"
echo "- dataset: ${DATASET_NAME} (expected_rows=${TOTAL_SAMPLES}, truncate=${TRUNCATE})"
echo "- grpo: e=${EPOCHS} b=${BATCH_SIZE} n=${GRPO_N} rollout_concurrency=${ROLLOUT_CONCURRENCY}"
echo "- restart_step: ${RESTART_STEP} (0=fresh, 1+=reuse cache)"
echo "- experience_style: ${EXPERIENCE_STYLE} (UTU_EXPERIENCE_PROMPT_PACK=${UTU_EXPERIENCE_PROMPT_PACK})"
if [[ -n "${SEED_EXPERIENCE_YAML}" ]]; then
  echo "- seed_experience_yaml: ${SEED_EXPERIENCE_YAML}"
else
  echo "- seed_experience_yaml: <none>"
fi
echo "- promote: ${PROMOTE}"
echo "- experiment: ${EXP}"
echo

# ------------------------------------------------------------------------------
# Step 0: Normalize stable experience packs under /state (prune format-only guidelines)
echo "[0/7] Normalize stable experience packs under /state"
docker compose exec "${SERVICE}" sh -lc '
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/export_experience_yaml.py \
    --source_agent_yaml /state/experience_youtu.yaml \
    --output_yaml /state/experience_youtu.yaml
  cp -f /state/experience_youtu.yaml /state/experience_mad.yaml
'

# ------------------------------------------------------------------------------
# Step 1: Ensure dataset file exists under /state/datasets (copy from repo if missing)
echo
echo "[1/7] Prepare dataset file -> ${DATASET_FILE}"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  mkdir -p /state/datasets /state/reports /state/experience_runs
  if [ -f '${DATASET_FILE}' ]; then
    echo '[full_v5_500] keep existing dataset file: ${DATASET_FILE}'
  else
    cp -f '${DATASET_SRC_IN_CONTAINER}' '${DATASET_FILE}'
    echo '[full_v5_500] copied dataset file: ${DATASET_FILE}  (from ${DATASET_SRC_IN_CONTAINER})'
  fi
  n=\$(wc -l < '${DATASET_FILE}')
  echo \"[full_v5_500] dataset lines: \${n}\"
  if [ \"\${n}\" -ne ${TOTAL_SAMPLES} ]; then
    echo \"ERROR: dataset line-count mismatch: got \${n}, expected ${TOTAL_SAMPLES}.\" >&2
    exit 2
  fi
"

# ------------------------------------------------------------------------------
# Step 2: Upload dataset into DB (skip if present)
echo
echo "[2/7] Upload dataset into DB (skip if present): ${DATASET_NAME}"
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

if [[ "${dataset_rows}" =~ ^[0-9]+$ ]] && [[ "${dataset_rows}" -eq "${TOTAL_SAMPLES}" ]]; then
  echo "[full_v5_500] dataset already present in DB (rows=${dataset_rows}); skip upload"
elif [[ "${dataset_rows}" =~ ^[0-9]+$ ]] && [[ "${dataset_rows}" -eq 0 ]]; then
  echo "[full_v5_500] dataset not found in DB; uploading ${DATASET_FILE}"
  docker compose exec "${SERVICE}" sh -lc "
    set -e
    cd /app/youtu-chem-loop
    python -m scripts.data.upload_dataset \
      --file_path '${DATASET_FILE}' \
      --dataset_name '${DATASET_NAME}' \
      --data_format default
  "
else
  echo "[full_v5_500] ERROR: dataset '${DATASET_NAME}' exists in DB but rows=${dataset_rows} (expected ${TOTAL_SAMPLES})." >&2
  echo "[full_v5_500] This usually means the dataset was uploaded multiple times (duplicates) or has the wrong name." >&2
  echo "[full_v5_500] Fix: use a new DATASET_NAME, or clean DB rows for this dataset then upload exactly ${TOTAL_SAMPLES}." >&2
  exit 3
fi

# ------------------------------------------------------------------------------
# Step 3: Run single-agent training-free GRPO rollouts
echo
echo "[3/7] Run GRPO rollout + distill experiences (this may take a while)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  UTU_EXPERIENCE_PROMPT_PACK=${UTU_EXPERIENCE_PROMPT_PACK} UTU_EXPERIENCE_BATCH_UPDATE_MODE=direct python -m scripts.run_training_free_GRPO \
    --config_name chem_performance_single \
    --experiment_name '${EXP}' \
    --practice_dataset_name '${DATASET_NAME}' \
    --epochs ${EPOCHS} --batch_size ${BATCH_SIZE} --grpo_n ${GRPO_N} \
    --rollout_data_truncate ${TRUNCATE} \
    --rollout_concurrency ${ROLLOUT_CONCURRENCY} \
    --restart_step ${RESTART_STEP} \
    ${SEED_ARG} \
    ${EXTRA_GRPO_ARGS} \
  2>&1 | tee /state/reports/grpo_${EXP}.log
"

# Persist the generated agent YAML to /state so it survives container rebuilds.
echo
echo "[3.5/7] Persist generated agent YAML -> /state/experience_runs/${EXP}_agent.yaml"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cp -f /app/youtu-chem-loop/configs/agents/practice/${EXP}_agent.yaml /state/experience_runs/${EXP}_agent.yaml
"

# ------------------------------------------------------------------------------
# Step 4: Format compliance + conclude payload sampling (DB-based)
echo
echo "[4/7] Format compliance report (DB-based)"
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
echo "[4.5/7] Sample conclude() structured payloads"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/db/inspect_conclude_payloads.py \
    --db /state/test.db \
    --exp_id '${EXP}_epoch_0' \
    --stage judged \
    --limit 10 \
  2>&1 | tee /state/reports/conclude_${EXP}_epoch_0.txt
"

# ------------------------------------------------------------------------------
# Step 5: Guideline content report + normalized pack export
echo
echo "[5/7] Guideline content report (format vs chemistry vs method)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/report_guideline_content.py \
    --agent_yaml /state/experience_runs/${EXP}_agent.yaml \
    --max_show 20 \
  2>&1 | tee /state/reports/guidelines_${EXP}.txt
"

echo
echo "[5.5/7] Export normalized experience pack (not promoted unless PROMOTE=1)"
docker compose exec "${SERVICE}" sh -lc "
  set -e
  cd /app/youtu-chem-loop
  python scripts/closed_loop/export_experience_yaml.py \
    --source_agent_yaml /state/experience_runs/${EXP}_agent.yaml \
    --output_yaml /state/experience_runs/${EXP}_experience_normalized.yaml
"

# ------------------------------------------------------------------------------
# Step 6: Optional promote
echo
echo "[6/7] Promote to stable pack? (PROMOTE=${PROMOTE})"
if [[ "${PROMOTE}" == "1" ]]; then
  docker compose exec "${SERVICE}" sh -lc "
    set -e
    cd /app/youtu-chem-loop
    python scripts/closed_loop/export_experience_yaml.py \
      --source_agent_yaml /state/experience_runs/${EXP}_agent.yaml \
      --output_yaml /state/experience_youtu.yaml
    cp -f /state/experience_youtu.yaml /state/experience_mad.yaml
    echo '[full_v5_500] promoted to: /state/experience_youtu.yaml and /state/experience_mad.yaml'
  "
else
  echo "[full_v5_500] skip promote"
fi

# ------------------------------------------------------------------------------
# Done
echo
echo "[7/7] Done."
echo "Artifacts (host):"
echo "- state/reports/grpo_${EXP}.log"
echo "- state/reports/format_${EXP}_epoch_0.txt"
echo "- state/reports/conclude_${EXP}_epoch_0.txt"
echo "- state/reports/guidelines_${EXP}.txt"
echo "- state/experience_runs/${EXP}_agent.yaml"
echo "- state/experience_runs/${EXP}_experience_normalized.yaml"
if [[ "${PROMOTE}" == "1" ]]; then
  echo "- state/experience_youtu.yaml (updated)"
  echo "- state/experience_mad.yaml (updated)"
fi
