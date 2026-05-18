# Security Considerations

## Secrets Management
- Never log or expose API keys, tokens, or credentials
- Never commit `.env` files or credential files
- Use environment variables (prefix: `SDLC_`) for configuration

## Sandbox
- Code execution is isolated via the `SandboxConfig` (when enabled)
- Network isolation defaults to `localhost` only
- Read-only paths protect system files from mutation
- Writable paths are scoped to workspace directories

## Input Validation
- All tool inputs are validated by Pydantic models
- File paths are validated before access
- Phase transitions validated against the phase graph
- Schema checks enforce output structure

## Error Safety
- Sensitive error details are logged, not returned to clients
- All exceptions are caught and wrapped in typed errors
- AST parse failures never crash the orchestrator
- LLM failures degrade gracefully with fallback strategies
