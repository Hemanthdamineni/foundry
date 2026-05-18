# Prompting Architecture

> Prompt strategy, phase prompt templates, judge prompts, debate prompts, prompt versioning, compatibility tracking, and anti-patterns.

---

## Prompt Architecture Overview

Foundry uses prompts at three distinct layers, each with different versioning and management requirements:

```
Layer 1: Phase Prompts (runtime-generated)
    │
    ├── Generated per-phase from templates + task description
    ├── Include constraints, requirements, restrictions
    └── NOT versioned (regenerated each call)

Layer 2: Judge Prompts (locked per task)
    │
    ├── Loaded from configs/prompts/ or locked_prompts dict
    ├── Content-hashed and locked at task creation
    └── VERSIONED via PromptRegistry

Layer 3: Debate Prompts (system prompts for agent roles)
    │
    ├── Hardcoded in debate_runtime.py as system prompt templates
    ├── Per-role system prompts (specs, coding, testing, etc.)
    └── Per-round context injection (independent → deliberation → final)
```

---

## Phase Prompts

### Generation

Phase prompts are generated at runtime by `get_next_action()`:

```python
def _phase_prompt(phase: str, description: str) -> str:
    return (
        f"You are executing the {phase} phase for this SDLC task:\n\n"
        f"{description}\n\n"
        f"{_phase_requirements(phase)}"
    )
```

### Phase Requirements

Each phase has specific output requirements embedded in the prompt:

| Phase | Required Output |
|---|---|
| Chatting | Clarify the task description and intent |
| ContextHarvesting | Must include `## Questions` and `## Constraints` sections. Ask every important question NOW — after spec approval no human questions are allowed |
| Specs | Must include `## Requirements`, `## Scope`, `## Constraints` sections |
| Planning | Must include `## Implementation Plan`, `## File Changes`, `## Risks` |
| Coding | Must reference specific files modified |
| Review | Must include `## Issues Found`, `## Severity`, `## Must Fix` sections |
| Testing | Must include `## Test Results`, `## Coverage`, `## Failed` sections |
| Done | Summarize what was accomplished |

### Phase Restrictions

Non-coding phases get explicit restrictions:

```python
def _phase_restrictions(phase: str) -> list[str]:
    if phase in {"Coding", "Testing"}:
        return []  # No restrictions — full tool access
    return ["Do not edit files in this phase.", "Do not run mutating shell commands."]
```

### Allowed Bash Patterns

Coding and Testing phases have explicit allowlists for shell commands:

```python
ALLOWED_PATTERNS = [
    "test", "build", "lint", "format", "install",
    "npm *", "pip *", "pixi *", "git *", "python *",
]
```

Custom patterns can be configured per-phase in `model_routing.yaml`:

```yaml
phases:
  Coding:
    bash_allowed_patterns:
      - "test"
      - "build"
      - "docker *"
      - "cargo *"
```

---

## Judge Prompts

### Prompt Key Mapping

Each phase transition has a specific judge prompt key:

```python
TRANSITION_PROMPT_KEYS = {
    ("Specs", "Planning"):    "judge_specs_to_planning",
    ("Planning", "Coding"):   "judge_planning_to_coding",
    ("Coding", "Review"):     "judge_coding_to_review",
    ("Review", "Coding"):     "judge_review_to_coding",
    ("Review", "Testing"):    "judge_review_to_testing",
}
```

### Prompt Locking

At task creation, judge prompts are loaded from the `configs/prompts/` directory and their content hashes are locked in the `Task.locked_prompts` dict:

```python
task = Task(
    locked_prompts={
        "judge_specs_to_planning": "<prompt_content_or_hash>",
        "judge_planning_to_coding": "<prompt_content_or_hash>",
        ...
    }
)
```

During execution, the judge engine uses the locked prompt. This guarantees that if a task is replayed, the same prompts are used — even if the prompt files have been modified.

### Default Judge Prompt Template

When no locked prompt exists for a transition:

```
Evaluate the output of the '{from_phase}' phase before it transitions to '{to_phase}'.
Determine if the output is complete, correct, and ready.

Output:
{output}

Return a JSON object with:
- 'passed' (bool)
- 'reason' (str)
- 'issues' (array of strings)
- 'severity' (info/warning/error/critical)
```

### Judge Output Schema

The judge is expected to return structured JSON:

```json
{
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "reason": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string", "enum": ["info", "warning", "error", "critical"]}
    },
    "required": ["passed", "reason"]
}
```

This schema is passed to the LLM via `response_format` parameter (Ollama `format=` or OpenAI `response_format`).

---

## Debate Prompts

### Consensus Judge Prompt

The consensus engine uses a specialized system prompt:

```
You are a neutral consensus judge evaluating a multi-agent debate.

Each agent independently reviewed the '{phase}' phase output.
Analyze their responses for:

1. GENUINE CONSENSUS — agents independently reached the same conclusion
   with distinct reasoning
2. SYCOPHANTIC COLLAPSE — agents are agreeing without substance
   (e.g. "I agree", "same here", no new reasoning)
3. MINORITY POSITIONS — dissenting views with valid reasoning that
   should be preserved
4. RESIDUAL OBJECTIONS — concerns raised but not fully addressed

Return JSON:
- "passed" (bool): output passes collective review
- "reason" (str): detailed analysis
- "disagreement_areas" (array): specific issues agents disagree on
- "agent_verdicts" (dict): mapping of agent_role -> passed bool
- "minority_positions" (array): {agent, position, severity}
- "sycophancy_risk" (str): "none" | "low" | "medium" | "high"
```

### Agent Role System Prompts

Each debate agent role has a focused system prompt that directs its evaluation lens:

```python
# Constructed per-agent, per-round
system_prompt = (
    f"You are a {role} reviewer. "
    f"Evaluate the {phase} phase output for quality, correctness, and completeness. "
    f"Focus on your area of expertise: {role_description}. "
    f"Respond with PASS or FAIL followed by detailed reasoning."
)
```

### Round-Specific Context

- **Round 1 (Independent):** No previous context — agent evaluates output in isolation
- **Round 2 (Deliberation):** All Round 1 responses injected as context — agent sees all perspectives
- **Round 3 (Final):** All Round 2 responses injected — agent provides definitive verdict

---

## Prompt Registry

### Versioned Prompt Management

The `PromptRegistry` provides versioned prompt storage with content-hash deduplication:

```python
registry = PromptRegistry()

# Register a prompt
v1 = registry.register("judge_specs", "Evaluate specs output for completeness...")
# v1.version = 1, v1.content_hash = "a1b2c3d4..."

# Register same content → returns existing version (deduplication)
v1_again = registry.register("judge_specs", "Evaluate specs output for completeness...")
# v1_again.version = 1 (same object, no duplicate)

# Register new content → creates version 2
v2 = registry.register("judge_specs", "Evaluate specs output for completeness AND correctness...")
# v2.version = 2, v2.content_hash = "e5f6g7h8..."

# Active version is always latest
registry.get_active("judge_specs")  # Returns v2 content

# Rollback to v1
registry.rollback("judge_specs", 1)
registry.get_active("judge_specs")  # Returns v1 content
```

### Bulk Operations

```python
# Load all .txt files from a directory
count = registry.load_from_dir("configs/prompts/")

# Save all active prompts to a directory
count = registry.save_to_dir("configs/prompts/")
# Also writes manifest.json with version → hash mappings

# Get all active content hashes
hashes = registry.all_hashes()
# {"judge_specs": "a1b2c3d4", "judge_planning": "i9j0k1l2", ...}
```

### Compatibility Manager

The `PromptCompatibilityManager` tracks which prompt versions have been tested with which models:

```python
compat_mgr = PromptCompatibilityManager(registry)

# Record that a prompt works with a model
compat_mgr.record_compatibility("judge_specs", "qwen3:8b", "Specs", compatible=True)

# Check compatibility
result = compat_mgr.check_compatibility("judge_specs", "qwen3:8b")
# {"status": "tested", "compatible": True, "tested_at": "...", "notes": ""}

# Detect stale prompts (content changed since last test)
stale = compat_mgr.detect_stale_prompts()
# [{"prompt": "judge_specs", "model": "qwen3:8b", "tested_hash": "old", "current_hash": "new"}]

# Validate entire prompt set for a model
validation = compat_mgr.validate_prompt_set(
    ["judge_specs", "judge_planning", "judge_coding"],
    model="qwen3:8b",
)
# {"all_compatible": True, "stale_count": 0, "untested_count": 1, "details": {...}}
```

---

## Model Routing

### Phase → Model Configuration

```yaml
# configs/model_routing.yaml
defaults:
  model: qwen3:8b
  subagent: dev-sdlc
  fallback_models:
    - qwen3:4b

phases:
  Chatting:
    model: qwen3:8b
  Specs:
    model: qwen3:8b
  Planning:
    model: qwen3:8b
  Coding:
    model: qwen3:8b
    subagent: dev-sdlc
    bash_allowed_patterns: [test, build, lint, git *]
  Review:
    model: qwen3:8b
  Testing:
    model: qwen3:8b
    subagent: dev-sdlc
```

### Route Resolution

```python
def _route_for(model_routing, phase):
    route = phases.get(phase, {})
    defaults = model_routing.get("defaults", {})
    return {**defaults, **route}  # Phase-specific overrides defaults
```

### Component-Level Routing

Different runtime components can use different models:

| Component | Default Model | Can Override? |
|---|---|---|
| Phase execution | `qwen3:8b` (from routing) | ✓ Per-phase config |
| Judge evaluation | `qwen3:8b` (from JudgeEngine init) | ✓ At server startup |
| Debate agents | `qwen3:8b` (from DebateAgentConfig) | ✓ Per-agent config |
| Consensus judge | `qwen3:8b` (from ConsensusEngine init) | ✓ At server startup |

---

## Prompt Anti-Patterns

### What to Avoid

| Anti-Pattern | Problem | Correct Approach |
|---|---|---|
| **Unlocked prompts** | Different executions use different prompts | Lock all prompts at task creation via `locked_prompts` |
| **Temperature > 0 for judges** | Judge output varies between runs | Always use `temperature=0.0` for judges |
| **Phase prompt with file editing** | Non-coding phases edit files | Use `_phase_restrictions()` to block file operations |
| **Unbounded output** | LLM generates unlimited text, consuming tokens | Use `max_tokens` parameter on all LLM calls |
| **Generic judge prompts** | Judge doesn't know what to look for | Use transition-specific prompts (Specs→Planning is different from Coding→Review) |
| **No fallback model** | If primary model is unavailable, execution stops | Configure `fallback_models` in routing |
| **Prompt injection in description** | User task description contains malicious instructions | Schema checks run before LLM judge; structural validation is deterministic |
| **Self-modifying prompts** | Prompts that change based on previous outputs | Prompt hash locking prevents mutation by design |
| **Same model for everything** | Expensive models wasted on simple tasks | Use model routing to assign appropriate models per role |
