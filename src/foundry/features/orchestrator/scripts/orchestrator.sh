#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT_DIR
STATE="$ROOT_DIR/.state"
QUEUE="$ROOT_DIR/.queue"
SCRIPTS="$ROOT_DIR/scripts"
MAX_RETRIES=3
MAX_IDLE_ITERATIONS=2
IDLE_COUNT=0

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

export TODO_PATH
export TARGET_DIR

# ── Freeze zone: merge CLI --frozen paths into freeze_zones.json ──────────
FREEZE_FILE="$STATE/freeze_zones.json"
if [[ ${#FROZEN_PATHS[@]} -gt 0 ]]; then
  for fp_entry in "${FROZEN_PATHS[@]}"; do
    ABS_ENTRY=$(python3 -c "import os; print(os.path.abspath('$fp_entry'))")
    if [[ -f "$FREEZE_FILE" ]]; then
      python3 -c "
import json, os
fp = '$FREEZE_FILE'
zones = json.load(open(fp))
if '$ABS_ENTRY' not in zones.get('frozen_paths', []):
    zones.setdefault('frozen_paths', []).append('$ABS_ENTRY')
json.dump(zones, open(fp, 'w'), indent=2)
"
    else
      echo '{"frozen_paths": [], "semi_frozen_paths": [], "approval_required_paths": []}' > "$FREEZE_FILE"
      python3 -c "
import json, os
fp = '$FREEZE_FILE'
zones = json.load(open(fp))
if '$ABS_ENTRY' not in zones.get('frozen_paths', []):
    zones.setdefault('frozen_paths', []).append('$ABS_ENTRY')
json.dump(zones, open(fp, 'w'), indent=2)
"
    fi
  done
fi

echo "Starting Orchestrator Loop (PID: $$)"
echo "{\"loop_pid\": $$, \"started_at\": \"$(date -u +%FT%TZ)\"}" > "$STATE/loop_state.json"

if [[ ! -f "$STATE/current_phase.json" ]]; then
  echo "No phase active. Exiting."
  exit 0
fi

PHASE_ID=$(python3 -c "import json; print(json.load(open('$STATE/current_phase.json'))['phase_id'])" 2>/dev/null || echo "")
if [[ -z "$PHASE_ID" ]]; then
  echo "ERROR: current_phase.json has no phase_id. Exiting."
  exit 1
fi
echo "Running phase: $PHASE_ID"

while true; do
  echo "Extracting next subphase..."
  "$SCRIPTS/extract_subphase.sh" --todo "$TODO_PATH"

  SUBPHASE_STATUS=$(python3 -c \
    "import json; print(json.load(open('$STATE/current_subphase.json'))['status'])" \
    2>/dev/null || echo "error")

  if [[ "$SUBPHASE_STATUS" == "no_subphase" ]]; then
    IDLE_COUNT=$((IDLE_COUNT + 1))
    echo "No pending work found (idle count: $IDLE_COUNT / $MAX_IDLE_ITERATIONS)."
    if [[ "$IDLE_COUNT" -ge "$MAX_IDLE_ITERATIONS" ]]; then
      echo "Phase $PHASE_ID complete (convergence confirmed)."
      echo "Running post-phase audit..."
      "$SCRIPTS/audit_phase.sh" --target "$TARGET_DIR" || true
      break
    fi
    sleep 2
    continue
  fi

  IDLE_COUNT=0

  QUEUE_DIR=$(python3 -c \
    "import json; print(json.load(open('$STATE/current_subphase.json')).get('queue', ''))" \
    2>/dev/null || echo "")

  if [[ -z "$QUEUE_DIR" || ! -d "$QUEUE_DIR" ]]; then
    echo "ERROR: Queue directory missing or invalid: '$QUEUE_DIR'. Exiting."
    exit 1
  fi

  PENDING_COUNT=0
  for task_file in "$QUEUE_DIR"/*.json; do
    [[ -f "$task_file" ]] || continue
    TASK_STATUS=$(python3 -c \
      "import json; print(json.load(open('$task_file')).get('status', 'pending'))" \
      2>/dev/null || echo "pending")
    if [[ "$TASK_STATUS" != "done" ]]; then
      PENDING_COUNT=$((PENDING_COUNT + 1))
    fi
  done

  if [[ "$PENDING_COUNT" -eq 0 ]]; then
    echo "All tasks in subphase already done. Continuing to next subphase..."
    # Reconcile TODO.md: mark any remaining unchecked tasks in this subphase as done
    # so extract_subphase.sh doesn't keep selecting it on the next pass
    python3 - "$STATE" "$TODO_PATH" << 'PYEOF' || true
import json, re, os, sys
state_dir = sys.argv[1]
todo_path = sys.argv[2]
if not os.path.exists(todo_path):
    sys.exit(0)
subphase_path = os.path.join(state_dir, "current_subphase.json")
if not os.path.exists(subphase_path):
    sys.exit(0)
d = json.load(open(subphase_path))
subphase_id = d.get("subphase_id", "")
if not subphase_id:
    sys.exit(0)
content = open(todo_path).read()
pattern = rf'^### {re.escape(subphase_id)}:.*?(?=^### |\Z)'
match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
if not match:
    sys.exit(0)
block = match.group(0)
unchecked = re.findall(r'^- \[ \] (.+)', block, re.MULTILINE)
if unchecked:
    for task in unchecked:
        escaped = re.escape(task.strip())
        content = re.sub(
            r'^- \[ \] ' + escaped + r'\s*$',
            '- [x] ' + task.strip(),
            content,
            flags=re.MULTILINE
        )
    with open(todo_path, 'w') as f:
        f.write(content)
    print(f"  ✓ TODO.md reconciled: marked {len(unchecked)} remaining task(s) done in {subphase_id}")
PYEOF
    continue
  fi

  for task_file in "$QUEUE_DIR"/*.json; do
    [[ -f "$task_file" ]] || continue

    TASK_STATUS=$(python3 -c \
      "import json; print(json.load(open('$task_file')).get('status', 'pending'))" \
      2>/dev/null || echo "pending")
    if [[ "$TASK_STATUS" == "done" ]]; then
      echo "Skipping already-done task: $task_file"
      continue
    fi

    TASK_TITLE=$(python3 -c \
      "import json; print(json.load(open('$task_file')).get('title', ''))" \
      2>/dev/null || echo "unknown")

    echo "┌─ Task: $TASK_TITLE"
    cp "$task_file" "$STATE/current_task.json"

    RETRIES=0
    SUCCESS=false

    while [[ "$RETRIES" -le "$MAX_RETRIES" ]]; do
      if [[ "$RETRIES" -eq 0 ]]; then
        echo "  → Executor running..."
        "$SCRIPTS/run_agent.sh" --target "$TARGET_DIR" executor || {
          echo "  ERROR: Executor failed."
          RETRIES=$((RETRIES + 1))
          continue
        }
      else
        echo "  → Repairer running (retry $RETRIES / $MAX_RETRIES)..."
        "$SCRIPTS/run_agent.sh" --target "$TARGET_DIR" repairer || {
          echo "  ERROR: Repairer failed."
          RETRIES=$((RETRIES + 1))
          continue
        }
      fi

      echo "  → Verifier running..."
      if "$SCRIPTS/run_agent.sh" --target "$TARGET_DIR" verifier; then
        echo "  ✓ Verified."
        SUCCESS=true
        break
      else
        echo "  ✗ Verification failed (retry $RETRIES / $MAX_RETRIES)."
        RETRIES=$((RETRIES + 1))
      fi
    done

    if [[ "$SUCCESS" == true ]]; then
      python3 -c \
        "import json; d=json.load(open('$task_file')); d['status']='done'; json.dump(d, open('$task_file','w'), indent=2)"

      python3 - "$TASK_TITLE" "$TODO_PATH" << 'PYEOF'
import sys, re, os
title = sys.argv[1]
todo_file = sys.argv[2] if len(sys.argv) > 2 else None
if not todo_file or not os.path.exists(todo_file):
    print(f"  ! TODO.md not found: {todo_file}")
    sys.exit(0)
try:
    content = open(todo_file).read()
    escaped = re.escape(title)
    new_content = re.sub(
        r'^- \[ \] ' + escaped + r'\s*$',
        '- [x] ' + title,
        content,
        flags=re.MULTILINE
    )
    if new_content != content:
        with open(todo_file, 'w') as f:
            f.write(new_content)
        print(f"  ✓ TODO.md updated: {title}")
    else:
        print(f"  ! TODO.md: no match for: {title}")
except Exception as e:
    print(f"  ! TODO.md update failed: {e}")
PYEOF

      ROOT_DIR="$ROOT_DIR" python3 "$SCRIPTS/update_churn.py" || true

      echo "└─ Done: $TASK_TITLE"
    else
      echo "└─ FAILED after $MAX_RETRIES retries: $TASK_TITLE"
      echo "HALT: Retry ceiling exhausted. Escalation required." >&2
      python3 -c "
import json
from datetime import datetime, timezone
path = '$STATE/loop_state.json'
try:
    d = json.load(open(path))
except:
    d = {}
d['last_failure'] = '$TASK_TITLE'
d['failed_at'] = datetime.now(timezone.utc).isoformat()
d['status'] = 'HALTED'
json.dump(d, open(path, 'w'), indent=2)
"
      exit 1
    fi

    sleep 0.5
  done

  echo "Subphase queue complete."
done

python3 -c "
import json
from datetime import datetime, timezone
path = '$STATE/loop_state.json'
try:
    d = json.load(open(path))
except:
    d = {}
d['status'] = 'FINISHED'
d['finished_at'] = datetime.now(timezone.utc).isoformat()
json.dump(d, open(path, 'w'), indent=2)
"
echo "Orchestrator finished cleanly."
