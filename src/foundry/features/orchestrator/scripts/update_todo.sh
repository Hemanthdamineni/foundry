#!/usr/bin/env bash
# update_todo.sh - Update TODO.md and run docs gap analysis.

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT_DIR/scripts"

"$S/run_agent.sh" todo_manager
"$S/run_agent.sh" docs_gap

echo "TODO updated."
