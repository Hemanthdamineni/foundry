# Budget and Resource Control

> Token tracking, time limits, retry budgets, debate budgets, violation severities, hard ceilings, and the economics of autonomous execution.

---

## Why Budgets Are Non-Negotiable

Without hard limits, an autonomous agent can:
- Retry the same failing approach indefinitely, consuming tokens
- Run debates that never converge, burning time and money
- Enter infinite replan loops where each replan triggers another replan
- Execute for hours or days without producing useful output

Budgets are the **fundamental safety mechanism** that bounds autonomous execution. Every budget parameter is a hard ceiling, not an advisory limit.

---

## Budget Policy Model

```python
class BudgetPolicy(BaseModel):
    max_total_tokens: int = 100_000        # Total tokens across all phases
    max_review_cycles: int = 8             # Maximum judge rejections before abort
    max_debate_rounds: int = 3             # Maximum debate rounds per phase
    max_runtime_minutes: int = 60          # Wall-clock time limit
    fallback_depth: int = 2               # Model fallback chain depth
    max_debate_budget_tokens: int = 15_000  # Token budget specifically for debate
    memory_enabled: bool = False           # Cross-task memory (opt-in)
```

### Parameter Rationale

| Parameter | Default | Why This Value |
|---|---|---|
| `max_total_tokens` | 100K | Typical feature task uses 30-60K tokens; 100K provides margin |
| `max_review_cycles` | 8 | After 8 rejections, the approach is fundamentally wrong |
| `max_debate_rounds` | 3 | 3 rounds (independent → deliberation → final) is the protocol design |
| `max_runtime_minutes` | 60 | Most tasks complete in 10-30 min; 60 catches runaway execution |
| `fallback_depth` | 2 | Primary → fallback1 → fallback2; more depth rarely helps |
| `max_debate_budget_tokens` | 15K | Debate is evaluation, not generation; 15K is generous |
| `memory_enabled` | False | Memory adds overhead; opt-in for long-running workflows |

---

## Budget Controller (`runtime/budget_controller.py`, 294 lines)

### Tracking Model

The budget controller tracks four resource dimensions:

```python
class BudgetController:
    # Token tracking
    _token_count: int = 0                  # Cumulative tokens consumed
    _token_estimates: dict[str, int] = {}  # Per-phase token estimates
    
    # Time tracking
    _start_time: datetime                  # When task started
    _phase_durations: dict[str, int] = {}  # Per-phase duration in ms
    
    # Retry tracking
    _retry_counts: dict[str, int] = {}     # Per-phase retry attempts
    _total_retries: int = 0                # Aggregate retry count
    
    # Debate tracking
    _debate_tokens: int = 0               # Tokens consumed by debates
    _debate_rounds: dict[str, int] = {}   # Per-phase debate rounds
```

### Enforcement Points

Budget is checked at multiple points during execution:

```python
def should_continue(self, task: Task) -> tuple[bool, list[BudgetViolation]]:
    violations = []
    
    # 1. Token ceiling
    if self._token_count >= task.budget.max_total_tokens:
        violations.append(BudgetViolation(
            resource="tokens",
            current=self._token_count,
            limit=task.budget.max_total_tokens,
            severity="critical",
        ))
    
    # 2. Token warning (80%)
    elif self._token_count >= task.budget.max_total_tokens * 0.8:
        violations.append(BudgetViolation(
            resource="tokens",
            severity="warning",
        ))
    
    # 3. Runtime ceiling
    elapsed_minutes = (datetime.now(UTC) - self._start_time).total_seconds() / 60
    if elapsed_minutes >= task.budget.max_runtime_minutes:
        violations.append(BudgetViolation(
            resource="runtime",
            current=elapsed_minutes,
            limit=task.budget.max_runtime_minutes,
            severity="critical",
        ))
    
    # 4. Review cycle ceiling
    if task.iteration_count >= task.budget.max_review_cycles:
        violations.append(BudgetViolation(
            resource="review_cycles",
            severity="critical",
        ))
    
    has_critical = any(v.severity == "critical" for v in violations)
    return (not has_critical), violations
```

### Violation Severities

```python
class BudgetViolation(BaseModel):
    resource: str          # "tokens", "runtime", "review_cycles", "debate_tokens"
    current: float = 0     # Current consumption
    limit: float = 0       # Configured ceiling
    severity: str          # "warning", "error", "critical"
    message: str = ""      # Human-readable description
```

| Severity | Meaning | System Response |
|---|---|---|
| `warning` | Approaching ceiling (80% tokens) | Log warning, continue execution |
| `error` | Phase-level limit exhausted (retry count) | Escalate to next recovery level |
| `critical` | Absolute ceiling hit | **Abort task immediately** (`status=stalled`) |

### Recording Consumption

```python
def record_phase_tokens(self, phase: str, tokens: int):
    self._token_count += tokens
    self._token_estimates[phase] = self._token_estimates.get(phase, 0) + tokens

def record_phase_duration(self, phase: str, duration_ms: int):
    self._phase_durations[phase] = self._phase_durations.get(phase, 0) + duration_ms

def record_debate_tokens(self, phase: str, tokens: int):
    self._debate_tokens += tokens
    self._token_count += tokens  # Debate tokens also count toward total

def record_retry(self, phase: str):
    self._retry_counts[phase] = self._retry_counts.get(phase, 0) + 1
    self._total_retries += 1
```

### Statistics

```python
def get_stats(self) -> dict:
    return {
        "total_tokens": self._token_count,
        "debate_tokens": self._debate_tokens,
        "total_retries": self._total_retries,
        "elapsed_minutes": elapsed,
        "per_phase_tokens": self._token_estimates,
        "per_phase_duration_ms": self._phase_durations,
        "per_phase_retries": self._retry_counts,
        "budget_utilization": self._token_count / budget.max_total_tokens,
    }
```

---

## Token Estimation

### How Tokens Are Counted

Foundry uses **estimates**, not precise token counts. Precise counting requires a tokenizer, which varies by model. Instead:

```python
# Rough estimation: 4 characters ≈ 1 token (English text)
def estimate_tokens(text: str) -> int:
    return len(text) // 4
```

Token estimates are recorded in `PhaseRecord.token_estimate` for each phase execution.

### Where Tokens Are Consumed

| Consumer | Typical Tokens | Budget Impact |
|---|---|---|
| Phase prompt generation | ~500 | Low |
| Context assembly (code chunks) | ~2,000-5,000 | Medium |
| LLM phase execution | ~3,000-15,000 | High |
| Judge evaluation | ~1,000-2,000 | Medium |
| Debate (3 agents × 3 rounds) | ~5,000-15,000 | High |
| Consensus evaluation | ~1,000 | Low |

### Typical Task Token Budgets

| Task Type | Expected Tokens | Safety Margin |
|---|---|---|
| Simple feature (1-2 files) | 20-40K | 60-80K remaining |
| Medium feature (3-5 files) | 40-70K | 30-60K remaining |
| Complex feature (5+ files) | 60-100K | Near ceiling |
| Bug fix | 15-30K | 70-85K remaining |
| Code review | 10-20K | 80-90K remaining |

---

## Debate Budget

Debate has its own sub-budget to prevent evaluation from consuming the execution budget:

```python
# Before debate starts
if self._debate_tokens >= budget.max_debate_budget_tokens:
    return None  # Skip debate — budget exhausted

# Between debate rounds
remaining = budget.max_debate_budget_tokens - self._debate_tokens
if remaining < estimated_round_cost:
    break  # End debate early
```

### Debate Cost Estimation

```
Per agent per round: ~500-1,000 tokens
3 agents × 3 rounds = ~4,500-9,000 tokens
Consensus evaluation: ~1,000 tokens
Total: ~5,500-10,000 tokens per debate

Default budget: 15,000 tokens → room for 1-2 debates per task
```

---

## Model Fallback Chain

When the primary model fails, the system falls back through a chain:

```yaml
# configs/model_routing.yaml
defaults:
  model: qwen3:8b
  fallback_models:
    - qwen3:4b        # Smaller, faster, less capable
```

The `fallback_depth` parameter limits how deep the fallback chain goes:

```python
# fallback_depth=2 means: primary → fallback1 → fallback2 → abort
if attempt > budget.fallback_depth:
    raise ModelError("All models exhausted")
```

### Fallback Strategy

| Fallback | Model | Tradeoff |
|---|---|---|
| Primary | `qwen3:8b` | Best quality, slowest |
| Fallback 1 | `qwen3:4b` | Lower quality, faster |
| Fallback 2 | (none configured) | Abort if reached |

Fallback is triggered by:
- Model timeout (`RETRYABLE_MODEL`)
- Model unavailable (Ollama not running, model not pulled)
- Model OOM (model too large for available VRAM)

---

## Budget Configuration

### Per-Task Override

Budget can be configured at task creation:

```python
task = Task(
    budget=BudgetPolicy(
        max_total_tokens=200_000,      # Double the default for complex tasks
        max_review_cycles=12,          # More patience for iterative refinement
        max_runtime_minutes=120,       # 2 hours for large codebases
    )
)
```

### YAML Configuration (Planned)

```yaml
# configs/budget_policy.yaml
default:
  max_total_tokens: 100000
  max_review_cycles: 8
  max_runtime_minutes: 60

profiles:
  simple:
    max_total_tokens: 50000
    max_review_cycles: 4
    max_runtime_minutes: 30
  
  complex:
    max_total_tokens: 200000
    max_review_cycles: 12
    max_runtime_minutes: 120
    memory_enabled: true
```

---

## Implementation Status

| Component | Status |
|---|---|
| BudgetPolicy model | **Implemented** — all fields, defaults, serialization |
| BudgetController | **Implemented** — token/time/retry tracking, violation detection |
| Token estimation | **Implemented** — character-based approximation |
| Budget check in submit_output | **Implemented** — checked before phase transition |
| Debate budget enforcement | **Implemented** — checked before and between rounds |
| Model fallback chain | **Partial** — fallback_models field exists, routing logic partial |
| YAML budget profiles | **Not implemented** — code loads from config but profiles not wired |
| Per-task budget override | **Implemented** — BudgetPolicy on Task model |
| Budget statistics API | **Partial** — stats computed but not exposed via MCP tool |
