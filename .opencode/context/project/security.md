# Security Requirements

## Sandbox
- All bash execution in Coding/Testing phases runs through bubblewrap sandbox
- Default-deny: `--unshare-all`, selective `--ro-bind` and `--bind`
- Network: localhost-only (Ollama on port 11434)
- No Docker socket, no SSH agent forwarding

## Input Validation
- All MCP tool inputs validated via Pydantic models
- Phase output size limit: 1MB soft, 5MB hard
- Task descriptions limited to 10,000 characters

## Secrets
- No secrets in config files — use environment variables
- API keys loaded via `SDLC_` prefixed env vars
- Never log secrets — redact in structured logging

## Agent Permissions
- Specs/Planning/Review agents: read-only (no edit, no bash)
- Code/Testing agents: edit + bash (sandboxed)
- Debate agents: read-only (no edit, no bash, no MCP mutations)

## Data Protection
- SQLite WAL mode with `BEGIN IMMEDIATE` for write isolation
- Plugin state files written atomically via rename()
- Checkpoint data stored separately from production database
