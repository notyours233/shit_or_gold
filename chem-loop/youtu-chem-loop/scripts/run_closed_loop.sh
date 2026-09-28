#!/usr/bin/env bash
set -euo pipefail

# One-click closed-loop runner (experience sync + debate -> experience distillation).
#
# What it does:
# 1) Create/refresh a stable experience pack YAML:
#    - youtu-agent:   configs/agents/practice/experience.yaml
#    - debate repo:   ../MAD/experience/experience.yaml
#    Each includes `updated_at_utc` for visibility/audit.
#    During sync, we archive other YAML packs in the debate repo so only experience.yaml
#    remains active (reduces noisy retrieval).
# 2) Optionally ingest the latest debate traces (result_*.json) from the debate repo outputs
#    and distill them into updated experiences, then refresh experience.yaml again.
#
# Notes:
# - Debate execution itself happens in `project/MAD` (separate runtime).
# - To distill from reaction ranking runs, you MUST run ranking with `--save-each-reaction`
#   so per-reaction `outputs/result_*.json` files exist.

usage() {
  cat <<'EOF'
run_closed_loop.sh

Closed loop: experience pack sync + debate-trace distillation.

Default behavior:
  - Refresh youtu-agent `configs/agents/practice/experience.yaml` from a seed agent YAML
  - Copy it to debate repo `../MAD/experience/experience.yaml`
  - Archive old packs in debate repo: `../MAD/experience/archive/<tag>/`
  - Find latest debate traces under `../MAD/outputs/result_*.json`
  - Run debate -> experience distillation (LLM/network required)
  - Refresh + sync experience.yaml again

Flags:
  --seed_agent_yaml PATH      Source agent YAML used as the initial experience seed.
                              Default: configs/agents/practice/experience.yaml if exists,
                              else the v5 full pack if present.
  --debate_outputs_dir DIR    Directory containing debate outputs (default: ../MAD/outputs)
  --debate_latest_n N         How many latest result_*.json files to ingest (default: 10)
  --skip_debate_update        Only refresh/sync experience.yaml; do not distill from debate traces.
  --dry_run                   Parse debate traces and print status counts; do NOT call LLM or write updated experiences.
  --config_name NAME          Practice config name for ExperienceUpdater (default: chem_performance_single)
  --concurrency N             Concurrency for distillation LLM calls (default: 4)
  -h, --help                  Show help

Env overrides (optional):
  PYTHON_BIN                  Absolute path to python (overrides .venv/bin/python discovery)

Examples:
  ./scripts/run_closed_loop.sh
  ./scripts/run_closed_loop.sh --seed_agent_yaml configs/agents/practice/mad_full_v5_500_rag1_u1_t500_e1_b20_n6_c4_agent.yaml
  ./scripts/run_closed_loop.sh --debate_latest_n 30 --concurrency 2
  ./scripts/run_closed_loop.sh --dry_run

Tip (rank mode):
  If debate was run via `project/MAD/main.py --rank-reactions`, add `--save-each-reaction`
  otherwise you will only get rank_*.json (no debate_history) and this script can't distill experiences.
EOF
}

SEED_AGENT_YAML=""
DEBATE_OUTPUTS_DIR=""
DEBATE_LATEST_N="10"
SKIP_DEBATE_UPDATE="0"
DRY_RUN="0"
CONFIG_NAME="chem_performance_single"
CONCURRENCY="4"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed_agent_yaml)
      SEED_AGENT_YAML="${2:-}"
      shift 2
      ;;
    --debate_outputs_dir)
      DEBATE_OUTPUTS_DIR="${2:-}"
      shift 2
      ;;
    --debate_latest_n)
      DEBATE_LATEST_N="${2:-}"
      shift 2
      ;;
    --skip_debate_update)
      SKIP_DEBATE_UPDATE="1"
      shift
      ;;
    --dry_run)
      DRY_RUN="1"
      shift
      ;;
    --config_name)
      CONFIG_NAME="${2:-}"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="${2:-}"
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
PROJECT_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"
DEBATE_ROOT="${PROJECT_ROOT}/MAD"

cd "${REPO_ROOT}"

# Ensure Python can import `utu` when executing files under `scripts/`.
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

LOG_DIR="${REPO_ROOT}/logs/closed_loop"
mkdir -p "${LOG_DIR}"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/closed_loop_${TS}.log"

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

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

# Only require `utu` imports when we actually run distillation (online mode).
# For `--skip_debate_update`, we only need PyYAML for the exporter script.
if [[ "${SKIP_DEBATE_UPDATE}" == "1" ]]; then
  if ! "${PY}" -c 'import yaml' >/dev/null 2>&1; then
    echo "ERROR: Selected python is missing PyYAML (required to export experience.yaml): ${PY}" >&2
    echo "Fix: install deps in your env (from repo root):" >&2
    echo "  python -m pip install -e ." >&2
    exit 3
  fi
else
  if ! "${PY}" -c 'import utu' >/dev/null 2>&1; then
    echo "ERROR: Selected python cannot import this repo (import utu failed): ${PY}" >&2
    echo "Fix: install deps in your env (from repo root):" >&2
    echo "  python -m pip install -e ." >&2
    exit 3
  fi
fi

EXPORT_PY="${REPO_ROOT}/scripts/closed_loop/export_experience_yaml.py"
if [[ ! -f "${EXPORT_PY}" ]]; then
  echo "ERROR: exporter script missing: ${EXPORT_PY}" >&2
  exit 4
fi

EXPERIENCE_YAML="${REPO_ROOT}/configs/agents/practice/experience.yaml"
DEBATE_EXPERIENCE_YAML="${DEBATE_ROOT}/experience/experience.yaml"
STATE_EXPERIENCE_YAML="/state/experience_youtu.yaml"
STATE_DEBATE_EXPERIENCE_YAML="/state/experience_mad.yaml"

if [[ -z "${SEED_AGENT_YAML}" ]]; then
  if [[ -f "${EXPERIENCE_YAML}" ]]; then
    SEED_AGENT_YAML="${EXPERIENCE_YAML}"
  elif [[ -f "${REPO_ROOT}/configs/agents/practice/mad_full_v5_500_rag1_u1_t500_e1_b20_n6_c4_agent.yaml" ]]; then
    SEED_AGENT_YAML="${REPO_ROOT}/configs/agents/practice/mad_full_v5_500_rag1_u1_t500_e1_b20_n6_c4_agent.yaml"
  else
    echo "ERROR: --seed_agent_yaml not provided and no default seed found." >&2
    echo "Tried:" >&2
    echo "  - ${EXPERIENCE_YAML}" >&2
    echo "  - configs/agents/practice/mad_full_v5_500_rag1_u1_t500_e1_b20_n6_c4_agent.yaml" >&2
    exit 5
  fi
fi

if [[ -z "${DEBATE_OUTPUTS_DIR}" ]]; then
  DEBATE_OUTPUTS_DIR="${DEBATE_ROOT}/outputs"
fi

quote_cmd() {
  local out=""
  for arg in "$@"; do
    out="${out} $(printf '%q' "${arg}")"
  done
  echo "${out# }"
}

copy_file_following_symlink() {
  # GNU cp supports --dereference; macOS/BSD cp does not. For our local workflow a
  # plain copy is enough, and Docker/Linux can keep dereference behavior.
  local src="${1:-}"
  local dst="${2:-}"
  if cp --help >/dev/null 2>&1; then
    cp -f --dereference -- "${src}" "${dst}"
  else
    cp -f "${src}" "${dst}"
  fi
}

archive_debate_experience_packs() {
  # Keep the debate repo's ./experience directory clean:
  # - Only keep `experience.yaml` at top-level (the active pack).
  # - Move any other *.yaml/*.yml packs to ./experience/archive/<tag>/.
  # - Also archive the *previous* experience.yaml before overwriting it.
  #
  # IMPORTANT: Do NOT move Python code under experience/ (only YAML packs).
  local experience_dir="${1:-}"
  local tag="${2:-}"

  if [[ -z "${experience_dir}" || -z "${tag}" ]]; then
    echo "ERROR: archive_debate_experience_packs requires: experience_dir tag" >&2
    return 2
  fi
  if [[ ! -d "${experience_dir}" ]]; then
    # Nothing to archive.
    return 0
  fi

  # If there is nothing to archive, avoid creating empty archive folders.
  local has_any="0"
  if [[ -f "${experience_dir}/experience.yaml" ]]; then
    has_any="1"
  fi
  shopt -s nullglob
  local yaml_candidates=("${experience_dir}"/*.yaml "${experience_dir}"/*.yml)
  shopt -u nullglob
  if [[ "${#yaml_candidates[@]}" -gt 0 ]]; then
    # If the only YAML file is experience.yaml and it does not exist, has_any remains 0.
    has_any="1"
  fi
  if [[ "${has_any}" != "1" ]]; then
    return 0
  fi

  local archive_dir="${experience_dir}/archive/${tag}"
  mkdir -p "${archive_dir}"

  if [[ -f "${experience_dir}/experience.yaml" ]]; then
    # NOTE: In Docker deployment we may wire `experience.yaml` as a symlink to a host-mounted
    # file under /state. Moving the symlink would break persistence. So we snapshot the
    # previous content into archive, then keep the active path intact for the overwrite.
    copy_file_following_symlink "${experience_dir}/experience.yaml" "${archive_dir}/experience.yaml"
  fi

  shopt -s nullglob
  for fp in "${experience_dir}"/*.yaml "${experience_dir}"/*.yml; do
    local base
    base="$(basename "${fp}")"
    if [[ "${base}" == "experience.yaml" ]]; then
      continue
    fi
    mv -f -- "${fp}" "${archive_dir}/${base}"
  done
  shopt -u nullglob
}

sync_state_experience_packs() {
  local source_yaml="${1:-}"
  local tag="${2:-}"

  if [[ -z "${source_yaml}" || -z "${tag}" ]]; then
    echo "ERROR: sync_state_experience_packs requires: source_yaml tag" >&2
    return 2
  fi
  if [[ ! -d "/state" ]]; then
    echo "State sync skipped: /state not mounted."
    return 0
  fi

  local archive_dir="/state/experience_archive/${tag}"
  mkdir -p "/state" "${archive_dir}"

  if [[ -f "${STATE_EXPERIENCE_YAML}" ]]; then
    copy_file_following_symlink "${STATE_EXPERIENCE_YAML}" "${archive_dir}/experience.yaml"
  fi

  local src_resolved state_youtu_resolved state_mad_resolved
  src_resolved="$(readlink -f "${source_yaml}" 2>/dev/null || realpath "${source_yaml}")"
  state_youtu_resolved="$(readlink -f "${STATE_EXPERIENCE_YAML}" 2>/dev/null || realpath -m "${STATE_EXPERIENCE_YAML}")"
  state_mad_resolved="$(readlink -f "${STATE_DEBATE_EXPERIENCE_YAML}" 2>/dev/null || realpath -m "${STATE_DEBATE_EXPERIENCE_YAML}")"

  if [[ "${src_resolved}" == "${state_youtu_resolved}" ]]; then
    echo "Synced -> ${STATE_EXPERIENCE_YAML} (already same file)"
  else
    cp -f "${source_yaml}" "${STATE_EXPERIENCE_YAML}"
    echo "Synced -> ${STATE_EXPERIENCE_YAML}"
  fi

  if [[ "${src_resolved}" == "${state_mad_resolved}" ]]; then
    echo "Synced -> ${STATE_DEBATE_EXPERIENCE_YAML} (already same file)"
  else
    cp -f "${source_yaml}" "${STATE_DEBATE_EXPERIENCE_YAML}"
    echo "Synced -> ${STATE_DEBATE_EXPERIENCE_YAML}"
  fi
}

set +e
(
  set -euo pipefail
  echo "== run_closed_loop =="
  echo "repo_root: ${REPO_ROOT}"
  echo "debate_root: ${DEBATE_ROOT}"
  echo "log_file: ${LOG_FILE}"
  echo
  echo "Config:"
  echo "  seed_agent_yaml=${SEED_AGENT_YAML}"
  echo "  config_name=${CONFIG_NAME}"
  echo "  concurrency=${CONCURRENCY}"
  echo "  debate_outputs_dir=${DEBATE_OUTPUTS_DIR}"
  echo "  debate_latest_n=${DEBATE_LATEST_N}"
  echo "  skip_debate_update=${SKIP_DEBATE_UPDATE} dry_run=${DRY_RUN}"
  echo
  echo "Outputs:"
  echo "  youtu experience.yaml: ${EXPERIENCE_YAML}"
  echo "  debate experience.yaml: ${DEBATE_EXPERIENCE_YAML}"
  if [[ -d "/state" ]]; then
    echo "  state experience.yaml: ${STATE_EXPERIENCE_YAML}"
    echo "  state debate experience.yaml: ${STATE_DEBATE_EXPERIENCE_YAML}"
  fi
  echo

  # -------------------------------------------------------------------------
  # Step 1: refresh stable experience.yaml in youtu-agent, with timestamp
  echo "[1/3] Export stable experience.yaml (with updated_at_utc)"
  "${PY}" "${EXPORT_PY}" --source_agent_yaml "${SEED_AGENT_YAML}" --output_yaml "${EXPERIENCE_YAML}"

  # Step 2: sync to debate repo (fixed filename)
  echo
  echo "[2/3] Sync experience.yaml to debate repo"
  mkdir -p "$(dirname "${DEBATE_EXPERIENCE_YAML}")"
  archive_debate_experience_packs "$(dirname "${DEBATE_EXPERIENCE_YAML}")" "${TS}_sync1"
  cp -f "${EXPERIENCE_YAML}" "${DEBATE_EXPERIENCE_YAML}"
  echo "Synced -> ${DEBATE_EXPERIENCE_YAML}"
  sync_state_experience_packs "${EXPERIENCE_YAML}" "${TS}_sync1"

  if [[ "${SKIP_DEBATE_UPDATE}" == "1" ]]; then
    echo
    echo "[3/3] Skipped debate trace distillation (--skip_debate_update=1)."
    echo "Done (sync-only)."
    exit 0
  fi

  # -------------------------------------------------------------------------
  # Step 3: distill experiences from latest debate result traces
  echo
  echo "[3/3] Distill experiences from debate traces"
  if [[ ! -d "${DEBATE_OUTPUTS_DIR}" ]]; then
    echo "WARNING: debate outputs dir not found: ${DEBATE_OUTPUTS_DIR}" >&2
    echo "Nothing to distill. (You can still run debate and re-run this script.)" >&2
    exit 0
  fi

  # Collect latest result_*.json files (rank_*.json does not contain debate_history).
  # Avoid `mapfile` so this script works with the Bash 3.x shipped on macOS.
  DEBATE_JSONS=()
  while IFS= read -r fp; do
    [[ -n "${fp}" ]] && DEBATE_JSONS+=("${fp}")
  done < <(ls -1t "${DEBATE_OUTPUTS_DIR}"/result_*.json 2>/dev/null | head -n "${DEBATE_LATEST_N}" || true)
  if [[ "${#DEBATE_JSONS[@]}" -eq 0 ]]; then
    echo "No debate traces found at: ${DEBATE_OUTPUTS_DIR}/result_*.json"
    echo "Hint: in MAD, if you used --rank-reactions, add --save-each-reaction to save result_*.json files."
    exit 0
  fi

  UPDATED_AGENT_YAML="${REPO_ROOT}/configs/agents/practice/debate_update_${TS}_agent.yaml"
  REPORT_PATH="${LOG_DIR}/debate_update_${TS}_report.json"

  CMD=(
    "${PY}" scripts/debate/update_experiences_from_debate.py
    --config_name "${CONFIG_NAME}"
    --seed_agent_yaml "${EXPERIENCE_YAML}"
    --concurrency "${CONCURRENCY}"
    --output_agent_yaml "${UPDATED_AGENT_YAML}"
    --report_path "${REPORT_PATH}"
  )
  if [[ "${DRY_RUN}" == "1" ]]; then
    CMD+=(--dry_run)
  fi
  for fp in "${DEBATE_JSONS[@]}"; do
    CMD+=(--debate_json "${fp}")
  done

  echo "\$ $(quote_cmd "${CMD[@]}")"
  "${CMD[@]}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    echo
    echo "Dry-run completed (no LLM calls, no updated experience.yaml written)."
    exit 0
  fi

  # Refresh the stable experience.yaml from the newly written agent YAML, then sync again.
  echo
  echo "Refresh stable experience.yaml from: ${UPDATED_AGENT_YAML}"
  "${PY}" "${EXPORT_PY}" --source_agent_yaml "${UPDATED_AGENT_YAML}" --output_yaml "${EXPERIENCE_YAML}"
  archive_debate_experience_packs "$(dirname "${DEBATE_EXPERIENCE_YAML}")" "${TS}_sync2"
  cp -f "${EXPERIENCE_YAML}" "${DEBATE_EXPERIENCE_YAML}"
  echo "Updated + synced -> ${DEBATE_EXPERIENCE_YAML}"
  sync_state_experience_packs "${EXPERIENCE_YAML}" "${TS}_sync2"

  echo
  echo "Done."
) 2>&1 | tee "${LOG_FILE}"

status="${PIPESTATUS[0]}"
set -e

if [[ "${status}" -ne 0 ]]; then
  echo
  echo "FAILED (exit=${status}). Log: ${LOG_FILE}" >&2
  echo "Rerun hints:" >&2
  echo "  - First check with dry-run parsing only:" >&2
  echo "      ./scripts/run_closed_loop.sh --dry_run" >&2
  echo "  - If LLM rate-limited, lower concurrency:" >&2
  echo "      ./scripts/run_closed_loop.sh --concurrency 2" >&2
  echo "  - If no debate traces are found, ensure debate repo saved result_*.json:" >&2
  echo "      (rank mode) add --save-each-reaction" >&2
fi

exit "${status}"
