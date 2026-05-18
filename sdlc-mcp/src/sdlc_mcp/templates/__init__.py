"""Embedded templates for SDLC-MCP bootstrap."""

from __future__ import annotations

# ── opencode.json fragment ──────────────────────────────────────────────

OPENCODE_FRAGMENT: dict = {
    "$schema": "https://opencode.ai/config.json",
    "mcp": {
        "foundry-orchestrator": {
            "type": "local",
            "command": ["sdlc-mcp"],
            "enabled": True,
            "environment": {},
        },
    },
    "agent": {
        "foundry": {
            "mode": "primary",
            "description": (
                "Foundry workspace-aware SDLC orchestration agent with deterministic "
                "bootstrap, validation, tracing, and recovery."
            ),
            "prompt": "{file:.opencode/skills/foundry/SKILL.md}",
            "permission": {
                "edit": "allow",
                "bash": "ask",
                "task": "allow",
            },
        },
    },
    "instructions": [],
}

# ── SKILL.md ────────────────────────────────────────────────────────────

SKILL_MD = """---
name: foundry
description: "Foundry: workspace-aware autonomous SDLC runtime with phase-gated reviews, validation, debate, and cross-task memory."
trigger: /foundry
---

# Foundry: Structured Development Lifecycle Server

Foundry is an MCP server that enforces a phase-gated software development process.
It provides tools for creating tasks, transitioning through phases, evaluating
outputs, and maintaining cross-task context.

Run `sdlc-mcp` from your PATH. With no arguments it starts the Foundry MCP
server over stdio; `sdlc-mcp bootstrap` repairs the current workspace.

By default, all phase reasoning uses the model currently selected in OpenCode.
Runtime LLM providers are disabled unless `.sdlc/config/llm_config.yaml`
explicitly enables them.

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

- `sdlc_detect_workspace`: inspect execution and workspace roots
- `sdlc_bootstrap_workspace`: create or repair `.sdlc/` in the selected workspace
- `sdlc_create_task`: create a new task
- `sdlc_get_next_action`: get current phase context
- `sdlc_validate_phase`: validate phase output without mutation
- `sdlc_submit_output`: submit phase output for evaluation
- `sdlc_resume_task`: restore task state from checkpoint
- `sdlc_upgrade_workspace`: upgrade schema and generated integration files
- `sdlc_request_approval`: request or grant approval
- `sdlc_get_status`: current task status
- `sdlc_list_tasks`: list tasks filtered by status
- `sdlc_cancel_task`: cancel a task
- `sdlc_debate_output`: run multi-agent debate
- `sdlc_memory_store` / `sdlc_memory_query` / `sdlc_memory_stats`: cross-task memory
- `sdlc_index_repository` / `sdlc_index_files`: repository indexing
- `sdlc_get_dependency_context`: dependency graph for a file
- `sdlc_get_trace` / `sdlc_list_traces` / `sdlc_get_summaries`: trace inspection
- `sdlc_enforce_retention`: trace retention policy

## Usage

```
/foundry
```

Then describe what you want to build.

Call `sdlc_detect_workspace` first with no path. Inspect `execution_root`,
`workspace_root`, and `detection_reason`; if the selected workspace is not
ready, call `sdlc_bootstrap_workspace`. Do not pass parent paths or guessed
repository roots into MCP tools.
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
    "foundry": {
        "architecture.md": """# Foundry Architecture

## Layers

1. **Python Runtime**: MCP server providing Foundry SDLC tools
2. **OpenCode Integration**: auto-generated .opencode/ config
3. **Installer / Bootstrap**: sdlc-mcp CLI

## Key Components

- `ConsensusEngine`: pure logic for verdict aggregation
- `JudgeEngine`: LLM-based phase evaluation
- `DebateRuntime`: multi-agent debate orchestration
- `Acervo`: tag-based memory store
- `Engram`: structured memory entries
- `ModelRouter`: per-role LLM provider routing
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

LLM_CONFIG_YAML = """# Foundry runtime LLM configuration
#
# Default behavior:
#   enabled: false
#
# With runtime LLMs disabled, Foundry does not call Ollama, OpenAI, or any other
# Python-side model provider. OpenCode's currently selected model performs the
# phase work, while the runtime enforces deterministic validation, persistence,
# tracing, and recovery.
#
# To enable Python-side judge/debate calls, set enabled: true and configure a
# provider below. Environment variables can override YAML values, for example:
#   SDLC_LLM__ENABLED=true
#   SDLC_LLM__DEFAULT_PROVIDER=openai
#   SDLC_LLM__PROVIDERS__OPENAI__API_KEY=sk-...
#   SDLC_LLM__PROVIDERS__OPENAI__BASE_URL=https://api.openai.com/v1

llm:
  enabled: false
  default_provider: opencode
  default_model: opencode/current

  providers: {}

  # Example override:
  # providers:
  #   openai:
  #     type: openai
  #     base_url: https://api.openai.com/v1
  #     api_key: ""
  #     default_model: gpt-4o
  #
  # routing:
  #   judge:
  #     provider: openai
  #     model: gpt-4o

  routing: {}
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
