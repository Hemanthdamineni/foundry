# Coding Style Guide

## Python
- Python 3.12+, async-first design
- Type hints on all public functions and methods
- Use `from __future__ import annotations` in every module
- Pydantic models for all data shapes — no raw dicts in public APIs
- `ruff` for linting (all rules enabled), `mypy` strict mode
- Use `structlog` patterns for logging

## Naming
- snake_case for functions, variables, modules
- PascalCase for classes
- UPPER_SNAKE for constants and enums
- Private methods prefixed with `_`

## Error Handling
- All exceptions inherit from `SDLCError`
- Never use bare `except:` — always catch specific types
- Use `FailureType` taxonomy for classification
- Log errors with structured context (task_id, phase, span_id)

## Async Patterns
- Prefer `asyncio.gather` for parallel work
- Use `asyncio.TaskGroup` for structured concurrency (Python 3.11+)
- Never block the event loop with synchronous I/O
- Use `aiosqlite` for database access

## Imports
- Standard library → third-party → local, separated by blank lines
- Use absolute imports from `sdlc.` package root
- TYPE_CHECKING guard for circular import prevention
