#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TODO_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --todo)
      TODO_PATH="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$TODO_PATH" ]]; then
  echo "ERROR: --todo <path> is required" >&2
  exit 1
fi

if [[ ! -f "$TODO_PATH" ]]; then
  echo "ERROR: TODO.md not found at $TODO_PATH" >&2
  exit 1
fi

PHASE=$(grep -E '^## Phase [0-9]+:' "$TODO_PATH" | grep -v 'COMPLETE' | head -1)
PHASE_ID=$(echo "$PHASE" | grep -oP 'Phase \K[0-9]+' || echo "")
PHASE_TITLE=$(echo "$PHASE" | grep -oP ': \K.*' || echo "")

if [[ -z "$PHASE_ID" ]]; then
  echo '{"phase_id": null, "phase_title": null, "status": "complete"}'
  exit 0
fi

echo "{\"phase_id\": \"P${PHASE_ID}\", \"phase_title\": \"${PHASE_TITLE}\", \"status\": \"active\"}" > "$ROOT_DIR/.state/current_phase.json"
echo "Phase: P${PHASE_ID} - ${PHASE_TITLE}"
