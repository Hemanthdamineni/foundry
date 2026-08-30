#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

TODO="../Foundry/TODO.md"
TARGET="../Foundry"
FROZEN="--frozen ../Foundry/sdlc/engine --frozen ../Foundry/sdlc/config.py --frozen ../Foundry/sdlc/models.py --frozen ../Foundry/sdlc/exceptions.py --frozen ../Foundry/sdlc/log.py --frozen ../Foundry/sdlc/validators --frozen ../Foundry/sdlc/adapters --frozen ../Foundry/sdlc/pyproject.toml --frozen ../Foundry/sdlc/.pre-commit-config.yaml --frozen ../Foundry/sdlc/.sdlc --frozen ../Foundry/sdlc-mcp --frozen ../Foundry/foundry --frozen ../Foundry/pyproject.toml --frozen ../Foundry/package.json --frozen ../Foundry/.pre-commit-config.yaml --frozen ../Foundry/opencode.json --frozen ../Foundry/.opencode --frozen ../Foundry/docs"

cd "$ROOT_DIR"

if [[ ! -f .state/loop_checkpoint.json ]]; then
    echo "Running cold start..."
    bash scripts/cold_start.sh --todo "$TODO" --target "$TARGET" $FROZEN
fi

echo "Starting loop..."
exec bash scripts/loop.sh --todo "$TODO" --target "$TARGET" $FROZEN
