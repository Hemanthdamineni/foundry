#!/usr/bin/env bash
# loop.sh - Outer execution loop with crash recovery.
# State checkpointing at every orchestrator pass.
# Ctrl-C safe: .state/ and .queue/ persist across restarts.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$ROOT_DIR/.state"
LOGS="$ROOT_DIR/.logs"

TODO_PATH=""
TARGET_DIR=""
FROZEN_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --todo)
      TODO_PATH="$2"
      shift 2
      ;;
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --frozen)
      FROZEN_ARGS+=("--frozen" "$2")
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

if [[ -z "$TARGET_DIR" ]]; then
  echo "ERROR: --target <project-directory> is required" >&2
  exit 1
fi

if [[ ! -f "$TODO_PATH" ]]; then
  echo "ERROR: TODO.md not found at $TODO_PATH" >&2
  exit 1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "ERROR: Target directory not found at $TARGET_DIR" >&2
  exit 1
fi

mkdir -p "$LOGS"
LOOP_LOG="$LOGS/loop_$(date +%Y%m%d_%H%M%S).log"

cleanup() {
  echo "" | tee -a "$LOOP_LOG"
  echo "=== Loop stopped at $(date -Iseconds) ===" | tee -a "$LOOP_LOG"
  echo "State preserved in .state/ | Queue in .queue/ | Logs in .logs/" | tee -a "$LOOP_LOG"
  echo "Restart with: bash scripts/loop.sh --todo $TODO_PATH --target $TARGET_DIR" | tee -a "$LOOP_LOG"
  exit 0
}

trap cleanup INT TERM

echo "=== Execution Loop Started (PID: $$) ===" | tee "$LOOP_LOG"
echo "Root: $ROOT_DIR" | tee -a "$LOOP_LOG"
echo "Target: $TARGET_DIR" | tee -a "$LOOP_LOG"

iteration=0

while true; do
  iteration=$((iteration + 1))
  echo "========================================" | tee -a "$LOOP_LOG"
  echo "Iteration: $iteration" | tee -a "$LOOP_LOG"
  echo "========================================" | tee -a "$LOOP_LOG"

  # Write checkpoint before each iteration
  python3 -c "
import json, os
from datetime import datetime, timezone
d = {'loop_iteration': $iteration, 'last_run': datetime.now(timezone.utc).isoformat(), 'status': 'running'}
os.makedirs('$STATE', exist_ok=True)
json.dump(d, open('$STATE/loop_checkpoint.json', 'w'), indent=2)
" 2>/dev/null || true

  # Run orchestrator (forward --target and any --frozen args)
  "$ROOT_DIR/scripts/orchestrator.sh" --todo "$TODO_PATH" --target "$TARGET_DIR" "${FROZEN_ARGS[@]}" 2>&1 | tee -a "$LOOP_LOG"
  RESULT=$?

  # Update loop state
  python3 -c "
import json, os
from datetime import datetime, timezone
path = '$STATE/loop_state.json'
if os.path.exists(path):
    d = json.load(open(path))
else:
    d = {}
d['loop_iteration'] = $iteration
d['last_run'] = datetime.now(timezone.utc).isoformat()
d['last_status'] = 'ok' if $RESULT == 0 else 'failed'
json.dump(d, open(path, 'w'), indent=2)
" 2>/dev/null || true

  if [[ "$RESULT" -ne 0 ]]; then
    echo "Orchestrator failed (exit $RESULT). Check $LOOP_LOG" | tee -a "$LOOP_LOG"
    echo "State preserved. Fix the issue and restart." | tee -a "$LOOP_LOG"
    exit 1
  fi

  # Check if all phases complete
  PHASE_STATUS=$(python3 -c "
import json
d = json.load(open('$STATE/current_phase.json'))
print(d.get('status', 'unknown'))
" 2>/dev/null || echo "unknown")
  if [[ "$PHASE_STATUS" == "complete" ]]; then
    echo "All phases complete. Exiting." | tee -a "$LOOP_LOG"
    exit 0
  fi

  # Check for no-op detection
  NOOP=$(python3 -c "
import json
d = json.load(open('$STATE/churn_tracker.json'))
print(d.get('iterations_since_last_meaningful_change', 0))
" 2>/dev/null || echo "0")
  if [[ "$NOOP" -ge 5 ]]; then
    echo "[WARN] $NOOP consecutive iterations without meaningful change." | tee -a "$LOOP_LOG"
    echo "[WARN] Possible no-op autonomy. Check $LOOP_LOG" | tee -a "$LOOP_LOG"
  fi

  echo "Next pass in 2s (Ctrl-C to stop)..." | tee -a "$LOOP_LOG"
  sleep 2
done
