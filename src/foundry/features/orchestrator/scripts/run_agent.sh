#!/usr/bin/env bash
# run_agent.sh — Invoke opencode run for executor/verifier/repairer agents.
# Agents run from orchestrator root. All external paths come from --target.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export ROOT_DIR
STATE="$ROOT_DIR/.state"
TARGET_DIR=""
AGENT_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
    *)
      AGENT_NAME="$1"
      shift
      ;;
  esac
done

if [[ -z "$AGENT_NAME" ]]; then
  echo "ERROR: <agent-name> is required (executor|verifier|repairer)" >&2
  exit 1
fi

if [[ -z "$TARGET_DIR" ]]; then
  echo "ERROR: --target <project-directory> is required" >&2
  exit 1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "ERROR: Target directory not found at $TARGET_DIR" >&2
  exit 1
fi

TASK_FILE="$STATE/current_task.json"
TASK_TITLE=$(python3 -c "import json; print(json.load(open('$TASK_FILE')).get('title', ''))" 2>/dev/null || echo "")

if [[ -z "$TASK_TITLE" ]]; then
  echo "[$AGENT_NAME] ERROR: No task title found in $TASK_FILE" >&2
  exit 1
fi

echo "[$AGENT_NAME] Running on: $TASK_TITLE"
echo "[$AGENT_NAME] Target: $TARGET_DIR"
echo "[$AGENT_NAME] Invoking: opencode run --agent $AGENT_NAME"

opencode run \
  --agent "$AGENT_NAME" \
  --dangerously-skip-permissions \
  "Task: $TASK_TITLE

Target project: $TARGET_DIR
Orchestrator root: $ROOT_DIR

You are running from the orchestrator root.
- Modify code in the target project at $TARGET_DIR
- Read/write orchestrator state in .state/ (relative to CWD)
- Freeze zones: .state/freeze_zones.json
- Task definition: .state/current_task.json
- Plan: .state/current_plan.json (may not exist yet)
- Output runtime snapshot to: .state/runtime_snapshot.json
- Output verification to: .state/verification.json

Run tests in the target project using its test framework (e.g., cd to target project and run pytest).
Respect frozen paths listed in .state/freeze_zones.json."
