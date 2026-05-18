# Coding Style Guidelines

## General
- Follow PEP 8 for Python code
- Line length: 100 characters maximum
- Use type annotations for all function signatures
- Use `from __future__ import annotations` for deferred evaluation
- Prefer `Path` over `str` for file system paths

## Naming
- Classes: PascalCase
- Functions/methods: snake_case
- Constants: UPPER_SNAKE_CASE
- Private attributes: `_leading_underscore`
- Type variables: short PascalCase (`T`, `TResult`)

## Imports
- Group: stdlib → third-party → local, sorted within groups
- Use `TYPE_CHECKING` blocks for type-only imports
- Avoid `from module import *`

## Error Handling
- Raise specific exception types (subclass `SDLCError`)
- Use `msg = "..."` pattern before raises for lint compliance
- Prefer `contextlib.suppress` over bare `except: pass`

## Async
- Use `async def` for I/O-bound functions
- Use `await asyncio.to_thread()` for synchronous I/O calls
- Prefer `async with` for resource management
