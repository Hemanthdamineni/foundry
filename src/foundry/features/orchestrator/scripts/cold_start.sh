#!/usr/bin/env bash
# cold_start.sh — One-shot state initialization for Foundry SDLC orchestrator.
# Run once before first invocation of loop.sh.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT_DIR
STATE="$ROOT_DIR/.state"
QUEUE="$ROOT_DIR/.queue"
LOGS="$ROOT_DIR/.logs"

TODO_PATH=""
TARGET_DIR=""
FROZEN_PATHS=()
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
      FROZEN_PATHS+=("$2")
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

export TARGET_DIR

mkdir -p "$STATE" "$QUEUE" "$LOGS"

echo "Initializing state in $STATE ..."

python3 -c "
import json, os
from datetime import datetime, timezone

state_dir = '$STATE'
os.makedirs(state_dir, exist_ok=True)

# loop_checkpoint.json
json.dump({'loop_iteration': 0, 'last_run': None, 'status': 'initialized'},
    open(os.path.join(state_dir, 'loop_checkpoint.json'), 'w'), indent=2)

# loop_state.json
json.dump({'loop_pid': None, 'started_at': None, 'status': 'initialized'},
    open(os.path.join(state_dir, 'loop_state.json'), 'w'), indent=2)

# churn.json
json.dump({
    'file_modification_frequency': {},
    'phase_rewrite_frequency': {},
    'reopened_todos': 0,
    'operational_progress_events': 0,
    'operational_progress_per_iteration': 0,
}, open(os.path.join(state_dir, 'churn.json'), 'w'), indent=2)

# churn_tracker.json
json.dump({
    'file_modification_count': {},
    'file_modification_by_phase': {},
    'task_reopen_count': {},
    'phase_rewrite_count': {},
    'iterations_since_last_meaningful_change': 0,
    'last_meaningful_change_iteration': None,
    'no_op_iterations': [],
}, open(os.path.join(state_dir, 'churn_tracker.json'), 'w'), indent=2)

# simplify_tracker.json
json.dump({
    'simplify_events': [],
    'iterations_since_last_simplify': 0,
    'last_simplify_iteration': None,
    'last_simplify_reason': None,
    'refactored_paths': [],
}, open(os.path.join(state_dir, 'simplify_tracker.json'), 'w'), indent=2)
"

# freeze_zones.json — merge defaults with CLI --frozen paths
FREEZE_FILE="$STATE/freeze_zones.json"
python3 -c "
import json, os

state_dir = '$STATE'
os.makedirs(state_dir, exist_ok=True)
fp = os.path.join(state_dir, 'freeze_zones.json')

defaults = {
    'frozen_paths': [
        'scripts/orchestrator.sh', 'scripts/loop.sh', 'scripts/run_agent.sh',
        'scripts/enforce_freeze.sh', 'scripts/track_churn.sh',
        '.prompts/planner.md', '.prompts/executor.md', '.prompts/verifier.md',
        '.prompts/repairer.md', '.prompts/auditor.md', '.prompts/refactorer.md',
        '.prompts/docs_gap.md', '.prompts/todo_manager.md'
    ],
    'semi_frozen_paths': [],
    'approval_required_paths': [],
}

if os.path.exists(fp):
    zones = json.load(open(fp))
    for k in defaults:
        zones.setdefault(k, defaults[k])
else:
    zones = dict(defaults)

json.dump(zones, open(fp, 'w'), indent=2)
print(f'freeze_zones.json: {len(zones[\"frozen_paths\"])} frozen paths')
"

# Merge CLI --frozen paths into freeze_zones.json
if [[ ${#FROZEN_PATHS[@]} -gt 0 ]]; then
  for fp_entry in "${FROZEN_PATHS[@]}"; do
    ABS_ENTRY=$(python3 -c "import os; print(os.path.abspath('$fp_entry'))")
    python3 -c "
import json, os
fp = '$FREEZE_FILE'
zones = json.load(open(fp))
if '$ABS_ENTRY' not in zones.get('frozen_paths', []):
    zones.setdefault('frozen_paths', []).append('$ABS_ENTRY')
json.dump(zones, open(fp, 'w'), indent=2)
print(f'  frozen: $ABS_ENTRY')
"
  done
fi

# Standard state stubs
echo '{"audit_status": "PASS", "suggestions": []}' > "$STATE/audit.json"
echo '{"status": "pending", "verified": false}' > "$STATE/verification.json"
echo '{"modified_files": [], "created_files": []}' > "$STATE/runtime_snapshot.json"
echo '{}' > "$STATE/simplify.json"

# Extract initial phase
echo "Extracting initial phase..."
"$ROOT_DIR/scripts/extract_phase.sh" --todo "$TODO_PATH"

# Extract initial subphase and queue tasks
echo "Extracting initial subphase..."
"$ROOT_DIR/scripts/extract_subphase.sh" --todo "$TODO_PATH"

echo ""
echo "Cold start complete."
echo "  Target: $TARGET_DIR"
echo "  State : $STATE"
echo "  Queue : $QUEUE"
echo "  Logs  : $LOGS"
echo ""
echo "Run: bash scripts/loop.sh --todo $TODO_PATH --target $TARGET_DIR"
