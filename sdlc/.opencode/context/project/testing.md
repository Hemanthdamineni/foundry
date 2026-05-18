# Testing Conventions

## Framework
- pytest with pytest-asyncio for async tests
- Tests organized in `Test*` classes in `test_*.py` files
- All tests under `sdlc/tests/`

## Patterns
- Use `tmp_path` fixture for temporary file operations
- Use `pytest.mark.asyncio` for async tests
- Mock external dependencies (Ollama, filesystem) to keep tests fast
- Test both success and error paths
- Use `tmp_path` to test file I/O without polluting workspace

## What to Test
- Models: construction, defaults, serialization round-trips
- Engines: state transitions, edge cases, error handling
- Adapters: validation, execution, healthcheck, graceful degradation
- Integration: end-to-end flow through key paths

## Running Tests
```bash
python -m pytest sdlc/tests/ -q
python -m pytest sdlc/tests/test_phase5.py -v
```

## Pre-existing Test Skipping
Some tests require external tools (ruff, mypy) that may not be installed.
These are known failures and don't indicate problems with the code.
