#!/usr/bin/env bash
# audit_phase.sh - Audit all subphases in the current phase.
# If overengineered, runs refactorer then re-verifies.

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT_DIR/scripts"
STATE="$ROOT_DIR/.state"
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

"$S/run_agent.sh" --target "$TARGET_DIR" auditor
A_STATUS=$(python3 -c "import json; print(json.load(open('$STATE/audit.json'))['audit_status'])" 2>/dev/null || echo "PASS")

if [[ "$A_STATUS" == "OVERENGINEERED" ]]; then
  echo "Overengineering detected. Running refactorer..."
  "$S/run_agent.sh" --target "$TARGET_DIR" refactorer

  # Track simplification event
  python3 -c "
import json, os
from datetime import datetime, timezone
path = '$STATE/simplify_tracker.json'
if os.path.exists(path):
    d = json.load(open(path))
else:
    d = {'simplify_events': [], 'iterations_since_last_simplify': 0,
         'last_simplify_iteration': None, 'last_simplify_reason': None, 'refactored_paths': []}
d['simplify_events'].append({
    'iteration': d.get('iterations_since_last_simplify', 0) + 1,
    'reason': 'OVERENGINEERED',
    'timestamp': datetime.now(timezone.utc).isoformat()
})
d['iterations_since_last_simplify'] = 0
d['last_simplify_iteration'] = d['simplify_events'][-1]['iteration']
d['last_simplify_reason'] = 'OVERENGINEERED'
json.dump(d, open(path, 'w'), indent=2)
print('Simplify event tracked.')
" 2>/dev/null || true

  echo "Re-verifying phase after refactor..."
  "$S/verify_phase.sh" || {
    echo "Phase verification failed after refactor."
    exit 1
  }
fi

echo "Phase audit: $A_STATUS"
