#!/usr/bin/env bash
set -euo pipefail

# End-to-end online smoke test for the ChemCouncil closed loop (except lab CSV feedback).
#
# What it tests (in order):
# 1) Literature RAG retrieval (Chroma + Voyage) + doc masking
# 2) Single-agent Training-free GRPO rollout (LLM API calls) and experience YAML generation
# 3) MAD multi-agent debate (rank mode; saves result_*.json traces)
# 4) Distill/update experiences from the debate traces and re-sync experience.yaml
#
# This script makes network calls (LLM + embeddings) and can incur cost.

usage() {
  cat <<'EOF'
run_e2e_smoke.sh

Runs an end-to-end closed-loop smoke test (requires network + API keys).

Env overrides (optional):
  PYTHON_BIN                 Python to use (default: ./.venv/bin/python)
  COMPONENTS                 5-metal composition string for MAD (default is a known 5-metal example)
  REACTION_TYPES             Comma-separated subset for rank mode (default: "OER,HER")
  DEBATE_MAX_PAR             Max parallel reactions in rank mode (default: 1)
  DEBATE_TOP_K               Top-K reactions to print (default: 1)
  DEBATE_LATEST_N            How many latest result_*.json to distill (default: 2)
  DISTILL_CONCURRENCY        LLM concurrency for distillation (default: 1)

Examples:
  ./scripts/run_e2e_smoke.sh
  COMPONENTS="Pt,Pd,Ru,Ir,Rh" REACTION_TYPES="OER,ORR" ./scripts/run_e2e_smoke.sh
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

TS="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/e2e_smoke_${TS}.log"

quote_cmd() {
  local out=""
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

require_env() {
  local k="$1"
  if [[ -z "${!k:-}" ]]; then
    echo "ERROR: missing env var: ${k}" >&2
    return 1
  fi
  return 0
}

set +e
(
  set -euo pipefail
  echo "== ChemCouncil E2E Smoke Test =="
  echo "ts: ${TS}"
  echo "root: ${ROOT}"
  echo "python: ${PY}"
  echo "log: ${LOG_FILE}"
  echo

  cd "${ROOT}"

  # Load .env into this shell (no-op if already exported). Avoid printing secrets.
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/.env"
  set +a

  # Preflight: key presence (do NOT print values).
  echo "[preflight] checking required env vars (presence only)"
  require_env UTU_LLM_API_KEY
  require_env UTU_LLM_BASE_URL
  require_env UTU_LLM_MODEL
  require_env VOYAGE_API_KEY
  require_env OPENAI_API_KEY
  require_env DEEPSEEK_API_KEY
  require_env GOOGLE_API_KEY
  require_env QWEN_API_KEY
  echo "[preflight] OK"
  echo

  # Global stability knobs for Chroma/SQLite.
  export SQLITE_TMPDIR="${SQLITE_TMPDIR:-/tmp}"
  export TMPDIR="${TMPDIR:-/tmp}"

  # Force-enable literature RAG in the single GRPO agent.
  export CHEM_GRPO_RAG_ENABLED="${CHEM_GRPO_RAG_ENABLED:-1}"
  export CHEM_GRPO_RAG_LIMIT="${CHEM_GRPO_RAG_LIMIT:-5}"
  export CHEM_LITERATURE_CHROMA_MAX_DISTANCE="${CHEM_LITERATURE_CHROMA_MAX_DISTANCE:-0.35}"

  # -----------------------------------------------------------------------
  # 1) Literature RAG smoke (ytu runner): retrieval + masking
  echo "[1/4] RAG smoke (chroma + voyage) + masking"
  "${PY}" - <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path.cwd()
py = sys.executable
ytu_root = root / "youtu-chem-loop"
runner = ytu_root / "utu" / "external_engines" / "chem_literature_runner.py"

assert runner.exists(), f"runner missing: {runner}"

payload = {
    "query": "OER overpotential 10 mA cm-2 nickel iron catalyst",
    "limit": 3,
    "reaction_type": "OER",
    "max_distance": float(os.getenv("CHEM_LITERATURE_CHROMA_MAX_DISTANCE", "0.35")),
    "masked_doc_ids": [],
}

out = subprocess.check_output([str(py), str(runner)], input=json.dumps(payload).encode("utf-8"), cwd=str(ytu_root))
hits = json.loads(out.decode("utf-8"))
if not isinstance(hits, list) or not hits:
    raise SystemExit("RAG smoke failed: empty/non-list output")

first = hits[0]
if isinstance(first, dict) and first.get("hit") is False:
    raise SystemExit(f"RAG smoke failed: {first.get('error') or first.get('message') or first}")

doc_id = None
for h in hits:
    if isinstance(h, dict) and h.get("doc_id"):
        doc_id = str(h["doc_id"])
        break

if not doc_id:
    raise SystemExit("RAG smoke failed: could not find doc_id in hits")

payload2 = dict(payload)
payload2["masked_doc_ids"] = [doc_id]
out2 = subprocess.check_output([str(py), str(runner)], input=json.dumps(payload2).encode("utf-8"), cwd=str(ytu_root))
hits2 = json.loads(out2.decode("utf-8"))

masked_ok = True
for h in hits2 if isinstance(hits2, list) else []:
    if isinstance(h, dict) and str(h.get("doc_id") or "") == doc_id:
        masked_ok = False
        break

if not masked_ok:
    raise SystemExit(f"Masking failed: masked doc_id still appears in results: {doc_id}")

print(f"RAG OK. hits={len(hits)} doc_id={doc_id} masked_hits={len(hits2) if isinstance(hits2, list) else 'N/A'}")
PY
  echo

  # -----------------------------------------------------------------------
  # 2) Single-agent Training-free GRPO smoke (calls LLM)
  echo "[2/4] Single-agent Training-free GRPO smoke (RAG enabled)"
  echo "\$ $(quote_cmd "${ROOT}/scripts/run_grpo_smoke.sh")"
  "${ROOT}/scripts/run_grpo_smoke.sh"
  echo

  # Find the newest smoke agent pack as the seed for experience.yaml export.
  SEED_DIR="${ROOT}/youtu-chem-loop/configs/agents/practice"
  SEED_AGENT_YAML="$(ls -1t "${SEED_DIR}"/single_agent_smoke*_agent.yaml 2>/dev/null | head -n 1 || true)"
  if [[ -z "${SEED_AGENT_YAML}" || ! -f "${SEED_AGENT_YAML}" ]]; then
    echo "ERROR: could not find a single_agent_smoke*_agent.yaml under: ${SEED_DIR}" >&2
    exit 3
  fi
  echo "[2/4] seed_agent_yaml: ${SEED_AGENT_YAML}"
  echo

  # -----------------------------------------------------------------------
  # 3) Sync experience.yaml -> MAD, then run MAD rank mode (saves traces)
  echo "[3/4] Sync experience.yaml to MAD (skip distillation)"
  echo "\$ $(quote_cmd "${ROOT}/scripts/run_closed_loop.sh" --seed_agent_yaml "${SEED_AGENT_YAML}" --skip_debate_update)"
  "${ROOT}/scripts/run_closed_loop.sh" --seed_agent_yaml "${SEED_AGENT_YAML}" --skip_debate_update
  echo

  COMPONENTS="${COMPONENTS:-Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)}"
  REACTION_TYPES="${REACTION_TYPES:-OER,HER}"
  DEBATE_MAX_PAR="${DEBATE_MAX_PAR:-1}"
  DEBATE_TOP_K="${DEBATE_TOP_K:-1}"

  echo "[3/4] MAD rank mode (network; saves debate traces)"
  echo "components: ${COMPONENTS}"
  echo "reaction_types: ${REACTION_TYPES}"
  echo "\$ $(quote_cmd "${PY}" main.py --components "${COMPONENTS}" --rank-reactions --reaction-types "${REACTION_TYPES}" --top-k-reactions "${DEBATE_TOP_K}" --max-parallel-reactions "${DEBATE_MAX_PAR}" --save-each-reaction)"
  (cd "${ROOT}/MAD" && "${PY}" main.py \
    --components "${COMPONENTS}" \
    --rank-reactions \
    --reaction-types "${REACTION_TYPES}" \
    --top-k-reactions "${DEBATE_TOP_K}" \
    --max-parallel-reactions "${DEBATE_MAX_PAR}" \
    --save-each-reaction)
  echo

  # -----------------------------------------------------------------------
  # 4) Distill experiences from newest debate traces and re-sync.
  DEBATE_LATEST_N="${DEBATE_LATEST_N:-2}"
  DISTILL_CONCURRENCY="${DISTILL_CONCURRENCY:-1}"

  echo "[4/4] Distill/update experiences from debate traces + resync experience.yaml"
  echo "\$ $(quote_cmd "${ROOT}/scripts/run_closed_loop.sh" --seed_agent_yaml "${SEED_AGENT_YAML}" --debate_latest_n "${DEBATE_LATEST_N}" --concurrency "${DISTILL_CONCURRENCY}")"
  "${ROOT}/scripts/run_closed_loop.sh" \
    --seed_agent_yaml "${SEED_AGENT_YAML}" \
    --debate_latest_n "${DEBATE_LATEST_N}" \
    --concurrency "${DISTILL_CONCURRENCY}"

  echo
  echo "E2E smoke completed OK."
  echo "Key outputs:"
  echo "  - youtu experience.yaml: ${ROOT}/youtu-chem-loop/configs/agents/practice/experience.yaml"
  echo "  - MAD debate outputs:    ${ROOT}/MAD/outputs/"
  echo "  - logs:                 ${LOG_FILE}"
) 2>&1 | tee "${LOG_FILE}"

status="${PIPESTATUS[0]}"
set -e
if [[ "${status}" -ne 0 ]]; then
  echo >&2
  echo "FAILED (exit=${status}). Log: ${LOG_FILE}" >&2
  echo "Rerun tips:" >&2
  echo "  - Reduce distillation concurrency:" >&2
  echo "      DISTILL_CONCURRENCY=1 ./scripts/run_e2e_smoke.sh" >&2
  echo "  - Reduce MAD rank parallelism:" >&2
  echo "      DEBATE_MAX_PAR=1 ./scripts/run_e2e_smoke.sh" >&2
fi
exit "${status}"
