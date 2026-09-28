#!/usr/bin/env bash
set -euo pipefail

# Promote a source agent YAML (with distilled experiences) into the Docker/WEB stable pack under ./state/.
#
# This updates:
# - state/experience_youtu.yaml  (served by the Web UI in Docker; symlinked in the image)
# - state/experience_mad.yaml    (loaded by MAD in Docker; symlinked in the image)
# and snapshots the previous pack into:
# - state/experience_archive/<timestamp>_<tag>/experience.yaml
#
# Usage:
#   bash scripts/promote_experience_pack_to_state.sh --source_agent_yaml state/experience_runs/<EXP>_agent.yaml
#
# Optional:
#   TAG=full_v5_500 bash scripts/promote_experience_pack_to_state.sh --source_agent_yaml ...

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT}"

SOURCE_AGENT_YAML=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source_agent_yaml)
      SOURCE_AGENT_YAML="${2:-}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 --source_agent_yaml <path>" >&2
      exit 0
      ;;
    *)
      echo "ERROR: Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${SOURCE_AGENT_YAML}" ]]; then
  echo "ERROR: --source_agent_yaml is required." >&2
  exit 2
fi

if [[ ! -f "${SOURCE_AGENT_YAML}" ]]; then
  echo "ERROR: source_agent_yaml not found: ${SOURCE_AGENT_YAML}" >&2
  exit 2
fi

OUT_YOUTU="state/experience_youtu.yaml"
OUT_MAD="state/experience_mad.yaml"

TAG="${TAG:-promote}"
TS="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_DIR="state/experience_archive/${TS}_${TAG}"

mkdir -p "$(dirname "${OUT_YOUTU}")" "$(dirname "${OUT_MAD}")" "${ARCHIVE_DIR}"

if [[ -f "${OUT_YOUTU}" ]]; then
  cp -f "${OUT_YOUTU}" "${ARCHIVE_DIR}/experience.yaml"
fi

echo "== promote experience pack to state =="
echo "- source_agent_yaml: ${SOURCE_AGENT_YAML}"
echo "- out_youtu: ${OUT_YOUTU}"
echo "- out_mad: ${OUT_MAD}"
echo "- archived_previous: ${ARCHIVE_DIR}/experience.yaml"
echo

python3 youtu-chem-loop/scripts/closed_loop/export_experience_yaml.py \
  --source_agent_yaml "${SOURCE_AGENT_YAML}" \
  --output_yaml "${OUT_YOUTU}"

cp -f "${OUT_YOUTU}" "${OUT_MAD}"

echo
echo "Done."
echo "Tip:"
echo "- Docker Web UI uses /state/experience_youtu.yaml (mounted from ./state/experience_youtu.yaml)."
echo "- If the container is already running, just refresh the Experience page; no rebuild is needed."
