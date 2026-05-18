"""Embedded templates for SDLC-MCP bootstrap."""

from __future__ import annotations

# ── opencode.json fragment ──────────────────────────────────────────────

OPENCODE_FRAGMENT: dict = {
    "mcpServers": {
        "sdlc-orchestrator": {
            "type": "stdio",
            "command": "sdlc-mcp",
            "args": [],
            "env": {},
        },
    },
    "agents": {
        "dev-sdlc": {
            "mode": "primary",
            "prompt": "{file:.opencode/skills/sdlc/SKILL.md}",
        },
    },
    "plugins": [],
    "instructions": [],
}

# ── SKILL.md ────────────────────────────────────────────────────────────

SKILL_MD = """---
name: sdlc
description: "SDLC — Structured Software Development Lifecycle with phase-gated reviews, multi-agent debate, and cross-task memory."
trigger: /sdlc
---

# SDLC — Structured Development Lifecycle Server

SDLC is an MCP server that enforces a phase-gated software development process.
It provides tools for creating tasks, transitioning through phases, evaluating
outputs, and maintaining cross-task context.

Run `python -m sdlc` or use `sdlc-mcp` from your PATH.

## Phases

| Phase | Purpose |
|---|---|
| Chatting | Clarify task intent and scope |
| Specs | Requirements, scope, constraints |
| Planning | Implementation plan with risks |
| Coding | Write and modify code |
| Review | Code review for issues and quality |
| Testing | Run and evaluate tests |
| Done | Summarize accomplishments |

## Tools

- `sdlc_create_task` — create a new task
- `sdlc_get_next_action` — get current phase context
- `sdlc_submit_output` — submit phase output for evaluation
- `sdlc_request_approval` — request or grant approval
- `sdlc_get_status` — current task status
- `sdlc_list_tasks` — list tasks filtered by status
- `sdlc_cancel_task` — cancel a task
- `sdlc_debate_output` — run multi-agent debate
- `sdlc_memory_store` / `sdlc_memory_query` / `sdlc_memory_stats` — cross-task memory
- `sdlc_index_repository` / `sdlc_index_files` — repository indexing
- `sdlc_get_dependency_context` — dependency graph for a file
- `sdlc_get_trace` / `sdlc_list_traces` / `sdlc_get_summaries` — trace inspection
- `sdlc_enforce_retention` — trace retention policy

## Usage

```
/sdlc
```

Then describe what you want to build.
"""

# ── Prompt files ────────────────────────────────────────────────────────

PROMPT_FILES: dict[str, str] = {
    "chatting.md": """You are in the **Chatting** phase. Your goal is to clarify the task intent and scope.
Ask questions to understand what the user wants to build.
Identify ambiguities, constraints, and success criteria.
Do NOT write code or propose implementation details yet.
""",
    "specs.md": """You are in the **Specs** phase. Your goal is to define requirements.
Output must include:
- Functional requirements
- Non-functional requirements
- Scope (in/out)
- Constraints
- Success criteria

Be precise. Ambiguous specs lead to bad code.
""",
    "planning.md": """You are in the **Planning** phase. Your goal is to create an implementation plan.
Output must include:
- Files to create or modify
- Key design decisions
- Risks and mitigations
- Order of implementation

Do NOT write code. Focus on architecture and sequencing.
""",
    "coding.md": """You are in the **Coding** phase. Your goal is to implement the planned changes.
Follow the project's conventions for: naming, typing, imports, error handling.
Write clean, maintainable code. Add tests where appropriate.
Reference the plan from the Planning phase.
""",
    "review.md": """You are in the **Review** phase. Your goal is to review the code for issues.
Check for:
- Correctness and logic errors
- Security vulnerabilities
- Performance issues
- Style and convention violations
- Missing edge cases
- Test coverage

Be thorough. This is a quality gate.
""",
    "testing.md": """You are in the **Testing** phase. Your goal is to run and evaluate tests.
- Run the test suite
- Report results
- Identify failures and their root causes
- Suggest fixes for failing tests
""",
    "done.md": """You are in the **Done** phase. Your goal is to summarize what was accomplished.
Include:
- What was built or changed
- Key decisions made
- Known issues or limitations
- Future considerations
""",
}

# ── Context files ───────────────────────────────────────────────────────

CONTEXT_SDLC_FILES: dict[str, dict[str, str]] = {
    "project": {
        "README.md": "# Project\n\nThis project uses SDLC-MCP for structured development lifecycle management.\n",
    },
    "sdlc": {
        "architecture.md": """# SDLC Architecture

## Layers

1. **Python Runtime** — MCP server providing SDLC tools
2. **OpenCode Integration** — auto-generated .opencode/ config
3. **Installer / Bootstrap** — sdlc-mcp CLI

## Key Components

- `ConsensusEngine` — pure logic for verdict aggregation
- `JudgeEngine` — LLM-based phase evaluation
- `DebateRuntime` — multi-agent debate orchestration
- `Acervo` — tag-based memory store
- `Engram` — structured memory entries
- `ModelRouter` — per-role LLM provider routing
""",
    },
}

# ── Graph files ─────────────────────────────────────────────────────────

GRAPH_FILES: dict[str, str] = {
    "sdlc-phases.yaml": """name: sdlc-phases
description: Default SDLC phase graph

nodes:
  - id: Chatting
    type: start
  - id: Specs
    type: phase
  - id: Planning
    type: phase
  - id: Coding
    type: action
  - id: Review
    type: review
  - id: Testing
    type: phase
  - id: Done
    type: end

edges:
  - from: Chatting
    to: Specs
  - from: Specs
    to: Planning
  - from: Planning
    to: Coding
  - from: Coding
    to: Review
  - from: Review
    to: Testing
  - from: Testing
    to: Done
  - from: Review
    to: Coding
    label: iteration
""",
}

# ── LLM config ──────────────────────────────────────────────────────────

LLM_CONFIG_YAML = """# SDLC-MCP LLM Provider Configuration
#
# Multiple providers can be configured. Each provider is tried in order
# of definition when a role's primary provider is unavailable.
#
# Environment variables override YAML values:
#   SDLC_LLM__PROVIDERS__OPENAI__API_KEY=sk-...
#   SDLC_LLM__PROVIDERS__OPENAI__BASE_URL=https://api.openai.com/v1

llm:
  default_provider: ollama
  default_model: qwen2.5-coder:7b

  providers:
    ollama:
      type: ollama
      base_url: http://localhost:11434
      default_model: qwen2.5-coder:7b

    openai:
      type: openai
      base_url: https://api.openai.com/v1
      api_key: ""  # set via env SDLC_LLM__PROVIDERS__OPENAI__API_KEY
      default_model: gpt-4o

    deepseek:
      type: openai
      base_url: https://api.deepseek.com/v1
      api_key: ""  # set via env SDLC_LLM__PROVIDERS__DEEPSEEK__API_KEY
      default_model: deepseek-chat

  routing:
    judge:
      provider: ollama
      model: qwen2.5-coder:7b
    debate_agent:
      provider: ollama
      model: qwen2.5-coder:7b
    debate_consensus:
      provider: ollama
      model: qwen2.5-coder:7b
"""

# ── __all__ ─────────────────────────────────────────────────────────────

__all__ = [
    "CONTEXT_SDLC_FILES",
    "GRAPH_FILES",
    "LLM_CONFIG_YAML",
    "OPENCODE_FRAGMENT",
    "PROMPT_FILES",
    "SKILL_MD",
]
