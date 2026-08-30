# Reference Material

The deep-dive reference docs that informed foundry's design live in the
**Helix monorepo** (`Hemanthdamineni/Helix.git`), which contains the broader
Helix/FoundryOS research corpus:

- `docs/reference-analysis/` — capability matrix and analyses of related
  systems (Claude Code family, LangGraph, Letta, OpenCode, Terax, Zed,
  Letta, infrastructure tooling)
- `docs/helix-architecture-research/` — best-of-breed analysis,
  capability atlas, custom components, external opportunities
- `docs/00_INDEX.html` through `docs/06_ROADMAP_MIGRATION.html` — the
  HTML design suite covering inheritance protocols, runtime profiles,
  context lifecycle, agents/governance/operations, and roadmap migration
- `docs/adr/` — 13 Architecture Decision Records covering the kernel's
  state machines, capability model, Chronicle schema, protocol traits,
  error handling, storage, shutdown, observability, resources,
  configuration, cache invalidation, and startup wiring
- `helix/docs/adr/` — 13 ADRs covering the Rust kernel crate's design
  decisions (state machines, capability model, protocol traits, etc.)

## For Foundry-Specific Documentation

- `docs/ARCHITECTURE.md` — the modernized runtime's authoritative architecture
- `docs/ROADMAP.md` — historical MVP roadmap (now complete)
- `docs/TODO.md` — 12-phase TODO with sub-tasks; the canonical "what's next" list
- `docs/design/plan-original.md` — original 2,000-line SDLC MCP design plan
  with a cross-reference table mapping original concepts to their
  modernized locations
- `docs/history/PHASE-{0..4}-execution.md` — phase-by-phase execution
  checklists used during the MVP build (all phases `[x]` complete)
- `docs/history/MVP-COMPLETION.md` — the 9-gate MVP completion evidence

## Archived Installer (Historical Reference Only)

The original `sdlc-mcp` server and npm installer (frozen at 2026-07-17) is
preserved at `Hemanthdamineni/foundry-installer.git` (21 commits). The
modernized runtime supersedes it; the archive is kept for reference
only. The local copy of the installer remains at `foundry/installer/`
inside this repo as a nested independent git repository.
