#!/usr/bin/env bash
set -euo pipefail

# Initialize the host state directory used by Docker deployment.
#
# Design:
# - Docker image contains *code only*.
# - Persistent data (experience packs + literature Chroma DB + sqlite DB + job logs)
#   live under ./state on the host and are mounted to /state in the container.
#
# This script creates the directory structure and, if available, seeds the
# experience pack YAMLs from the current workspace files.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STATE_DIR="${STATE_DIR:-${ROOT}/state}"

mkdir -p "${STATE_DIR}/jobs" "${STATE_DIR}/experience_archive" "${STATE_DIR}/chroma_db"

seed_file_if_missing() {
  local dst="${1:-}"
  local src="${2:-}"
  local label="${3:-}"

  if [[ -z "${dst}" ]]; then
    echo "ERROR: dst missing in seed_file_if_missing" >&2
    exit 2
  fi

  if [[ -f "${dst}" ]]; then
    echo "[state] keep: ${dst}"
    return 0
  fi

  if [[ -n "${src}" && -f "${src}" ]]; then
    mkdir -p "$(dirname "${dst}")"
    cp -f "${src}" "${dst}"
    echo "[state] seeded ${label}: ${dst}  (from ${src})"
    return 0
  fi

  # Fallback: create a minimal placeholder pack.
  mkdir -p "$(dirname "${dst}")"
  cat >"${dst}" <<'YAML'
# Minimal placeholder experience pack (seed=empty).
# - This file is intentionally lightweight so the Docker image can stay data-free.
# - It will be overwritten when you run GRPO / closed-loop sync.
defaults:
  - _self_
updated_at_utc: null
source_agent_yaml: null
type: simple
agent:
  name: material_property_agent
  instructions: |
    You are a material-property performance prediction assistant.

    [G0]. Baseline materials guidance: use on-target evidence, unit discipline, and conservative plausibility ranges to
    produce best-effort numeric predictions for the requested property metrics.
toolkits: {}
YAML
  echo "[state] created placeholder ${label}: ${dst}"
}

# youtu-chem-loop stable experience pack (used by GRPO seeding + synced into MAD)
seed_file_if_missing \
  "${STATE_DIR}/experience_youtu.yaml" \
  "${ROOT}/youtu-chem-loop/configs/agents/practice/experience.yaml" \
  "youtu experience"

# MAD stable experience pack (consumed by debate/rank runtime)
seed_file_if_missing \
  "${STATE_DIR}/experience_mad.yaml" \
  "${ROOT}/MAD/experience/experience.yaml" \
  "MAD experience"

echo
echo "[state] done."
echo "Next:"
echo "  - Docker: docker compose up --build"
echo "  - If you want literature RAG, put your Chroma DB under:"
echo "      ${STATE_DIR}/chroma_db"
echo "    (or mount an external/remote volume there)."
