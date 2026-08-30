#!/usr/bin/env bash
# verify_phase.sh - Verify all tasks in the current phase passed.
# Called after refactoring.

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT_DIR/.state"
QUEUE_DIR="$ROOT_DIR/.queue"

PHASE_ID=$(python3 -c "import json; print(json.load(open('$STATE/current_phase.json'))['phase_id'])" 2>/dev/null || echo "")

if [[ -z "$PHASE_ID" ]]; then
  echo '{"phase_verification": "NO_PHASE"}'
  exit 0
fi

FAILED=0
TOTAL=0
for subphase_dir in "$QUEUE_DIR/$PHASE_ID"*/; do
  [[ -d "$subphase_dir" ]] || continue
  for task_file in "$subphase_dir"*.json; do
    [[ -f "$task_file" ]] || continue
    TOTAL=$((TOTAL+1))
    TASK_STATUS=$(python3 -c "import json; print(json.load(open('$task_file'))['status'])" 2>/dev/null || echo "pending")
    if [[ "$TASK_STATUS" != "done" ]]; then
      FAILED=$((FAILED+1))
    fi
  done
done

echo "Phase verification: $((TOTAL-FAILED))/$TOTAL tasks passed"
[[ "$FAILED" -gt 0 ]] && exit 1
exit 0
