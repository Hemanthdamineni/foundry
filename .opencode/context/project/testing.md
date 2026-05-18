# Testing Requirements

## Framework
- pytest + pytest-asyncio for all tests
- conftest.py provides shared fixtures (temp dirs, mock store, sample graphs)

## Coverage Targets
- Minimum 80% line coverage for core modules (engine/, runtime/)
- 100% coverage for schema_checks and phase_graph validation

## Test Types
- **Unit tests**: per module, mock external dependencies
- **Integration tests**: end-to-end phase transitions with real SQLite
- **Parametrized tests**: per-transition schema checks, per-template graph validation

## Naming Convention
- Test files: `test_<module>.py`
- Test functions: `test_<what>_<condition>_<expected>`
- Fixtures: descriptive names matching what they provide

## Async Testing
- Use `@pytest.mark.asyncio` for all async tests
- Use `asyncio_mode = "auto"` in pytest config
- Mock Ollama calls — never hit real LLM in tests
