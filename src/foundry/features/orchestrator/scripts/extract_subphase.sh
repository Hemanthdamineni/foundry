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

PHASE_FILE="$ROOT_DIR/.state/current_phase.json"
SUBPHASE_STATE="$ROOT_DIR/.state/current_subphase.json"

_write_no_subphase() {
  local json='{"subphase_id": null, "subphase_title": null, "status": "no_subphase"}'
  echo "$json"
  echo "$json" > "$SUBPHASE_STATE"
  exit 0
}

PHASE_ID=$(python3 -c "import json; print(json.load(open('$PHASE_FILE'))['phase_id'])" 2>/dev/null || echo "")

if [[ -z "$PHASE_ID" ]]; then
  local_json='{"subphase_id": null, "subphase_title": null, "status": "no_phase"}'
  echo "$local_json"
  echo "$local_json" > "$SUBPHASE_STATE"
  exit 0
fi

FULL_ID=""
SUBPHASE_TITLE=""

while IFS= read -r line; do
  CANDIDATE_ID=$(echo "$line" | grep -oP "${PHASE_ID}-\K[0-9]+" || echo "")
  CANDIDATE_TITLE=$(echo "$line" | grep -oP ': \K.*' || echo "")
  [[ -z "$CANDIDATE_ID" ]] && continue

  COUNT=$(python3 - << PYEOF
import re
todo = open("$TODO_PATH").read()
pattern = rf'^### ${PHASE_ID}-${CANDIDATE_ID}:.*?(?=^### |\Z)'
match = re.search(pattern, todo, re.MULTILINE | re.DOTALL)
if match:
    block = match.group(0)
    tasks = re.findall(r'^- \[ \] (.+)', block, re.MULTILINE)
    print(len(tasks))
else:
    print(0)
PYEOF
)

  if [[ "$COUNT" -gt 0 ]]; then
    FULL_ID="${PHASE_ID}-${CANDIDATE_ID}"
    SUBPHASE_TITLE="$CANDIDATE_TITLE"
    break
  fi
done < <(grep -E "^### ${PHASE_ID}-[0-9]+:" "$TODO_PATH" 2>/dev/null || true)

if [[ -z "$FULL_ID" ]]; then
  _write_no_subphase
fi

QUEUE_DIR="$ROOT_DIR/.queue/$FULL_ID"

echo "{\"subphase_id\": \"${FULL_ID}\", \"subphase_title\": \"${SUBPHASE_TITLE}\", \"status\": \"active\", \"queue\": \"$QUEUE_DIR\"}" > "$SUBPHASE_STATE"

mkdir -p "$QUEUE_DIR"
rm -f "$QUEUE_DIR"/*.json 2>/dev/null || true

python3 - << PYEOF
import re, json, os

todo = open("$TODO_PATH").read()
full_id = "$FULL_ID"
queue_dir = "$QUEUE_DIR"

pattern = rf'^### {full_id}:.*?(?=^### |\Z)'
match = re.search(pattern, todo, re.MULTILINE | re.DOTALL)
if not match:
    exit(0)

block = match.group(0)
tasks = re.findall(r'^- \[ \] (.+)', block, re.MULTILINE)

written = 0
for i, task in enumerate(tasks):
    task_id = f'{full_id}-{i+1:03d}'
    task_file = os.path.join(queue_dir, f'{task_id}.json')

    if os.path.exists(task_file):
        try:
            existing = json.load(open(task_file))
            if existing.get('status') == 'done':
                print(f'[skip] {task_id} already done')
                continue
        except Exception:
            pass

    with open(task_file, 'w') as f:
        json.dump({"task_id": task_id, "title": task.strip(), "status": "pending"}, f, indent=2)
    print(f'[queue] {task_id} - {task.strip()}')
    written += 1
PYEOF

echo "Subphase: ${FULL_ID} - ${SUBPHASE_TITLE}"
