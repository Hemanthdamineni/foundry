# Debate and Consensus

> Multi-agent quality review protocol: debate runtime, agent configuration, consensus evaluation, confidence gating, collapse detection, and minority report preservation.

---

## Why Debate Exists

A single LLM judge evaluating output quality has a fundamental problem: **it's a single point of failure for quality assessment**. The judge prompt may be poorly written, the model may have blind spots, or the evaluation criteria may not capture all quality dimensions.

Debate provides a **multi-perspective quality review** where multiple LLM calls with different role-specific prompts evaluate the same output. This catches issues that any single evaluator would miss.

Critically, debate is for **evaluation, not execution**. Debate agents review output; they don't produce code, run tests, or modify files.

---

## Debate Architecture

```
submit_output() detects judge rejection
    │
    ├── Check: debate configured for this phase?
    ├── Check: debate budget remaining?
    │
    ▼
DebateRuntime.run_debate()
    │
    ├── Select agent roles for this phase
    ├── Configure agent prompts
    │
    ├── Round 1: Independent Assessment
    │   ├── Agent A evaluates (no cross-agent context)
    │   ├── Agent B evaluates (no cross-agent context)
    │   └── Agent C evaluates (no cross-agent context)
    │
    ├── Round 2: Deliberation
    │   ├── Agent A sees all Round 1 responses
    │   ├── Agent B sees all Round 1 responses
    │   └── Agent C sees all Round 1 responses
    │
    ├── Round 3: Final Positions
    │   ├── Agent A sees all Round 2 responses
    │   ├── Agent B sees all Round 2 responses
    │   └── Agent C sees all Round 2 responses
    │
    └── Returns: DebateTranscript
            │
            ▼
ConsensusEngine.evaluate()
    │
    ├── LLM consensus judge (primary)
    │   OR
    ├── Majority vote fallback
    │
    ├── Collapse detection
    ├── Minority report extraction
    ├── Residual objection tracking
    │
    └── Returns: ConsensusResult
            │
            ▼
ConfidenceGate.evaluate()
    │
    ├── Vote normalization
    ├── Threshold enforcement
    │
    └── Returns: GateDecision (approve/reject/continue_debate/synthesize)
```

---

## Debate Runtime (`engine/debate_runtime.py`, 360 lines)

### Agent Configuration Per Phase

Each phase activates a specific set of agent roles. The roles are chosen to provide **complementary evaluation perspectives**:

```python
PHASE_AGENTS = {
    "Specs":    [specs, planning],           # Does the spec support planning?
    "Planning": [planning, coding, specs],   # Is the plan implementable? Does it match specs?
    "Coding":   [coding, review, testing],   # Is the code correct? Reviewable? Testable?
    "Review":   [review, coding, testing],   # Are issues valid? Is the code actually wrong?
    "Testing":  [testing, coding, review],   # Do tests cover the code? Are they correct?
}
```

### Agent Role Definitions

```python
class DebateAgentRole(StrEnum):
    SPECS     = "specs"       # Evaluates requirement coverage and spec compliance
    PLANNING  = "planning"    # Evaluates implementation feasibility and risk
    CODING    = "coding"      # Evaluates code quality, correctness, and patterns
    REVIEW    = "review"      # Evaluates maintainability, readability, and standards
    TESTING   = "testing"     # Evaluates test coverage, edge cases, and validation
    CONSENSUS = "consensus"   # Neutral judge for final verdict (not a debate participant)
```

### Agent Model Configuration

```python
class DebateAgentConfig(BaseModel):
    role: DebateAgentRole
    model: str = "qwen3:8b"       # Model for this agent's LLM calls
    system_prompt: str = ""        # Role-specific system prompt
    temperature: float = 0.7       # Higher than judge (0.0) for diverse perspectives
    max_tokens: int = 1024         # Response length cap
```

Note the temperature difference: judges use `0.0` for determinism; debate agents use `0.7` for diversity. This is intentional — debate value comes from different perspectives, not identical reasoning.

### Round Protocol

**Round 1: Independent Assessment**

Each agent receives:
- The phase output being evaluated
- Their role-specific system prompt
- The task description and phase context

Agents do NOT see each other's responses. This ensures genuine independent evaluation.

```python
for agent in agents:
    prompt = f"Evaluate this {phase} output. Focus on your expertise area: {agent.role}"
    response = await provider.generate(messages=[
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": f"{prompt}\n\nOutput:\n{output}"},
    ], model=agent.model, temperature=agent.temperature)
```

**Round 2: Deliberation**

Each agent receives:
- Everything from Round 1
- ALL Round 1 responses from ALL agents

This creates a deliberation dynamic: agents can acknowledge, disagree with, or build on each other's assessments.

```python
context = "Previous round responses:\n"
for role, response in round1_responses.items():
    context += f"\n[{role}]: {response}\n"

# Each agent evaluates with full cross-agent context
for agent in agents:
    prompt = f"Review the previous assessments. Refine your evaluation.\n{context}"
```

**Round 3: Final Positions**

Same structure as Round 2, but with Round 2 responses as context. Agents provide their definitive verdict. By this point, genuine disagreements should be clearly articulated and superficial agreements should be distinguishable from real consensus.

### Partial Completion

If an agent fails during a round (timeout, LLM error, parsing failure):

```python
try:
    response = await provider.generate(...)
    round_responses[agent.role] = response
except Exception as e:
    logger.warning(f"Agent {agent.role} failed in round {round_num}: {e}")
    # Continue with remaining agents — don't fail the entire debate
```

The debate continues with the remaining agents. The transcript records which agents participated in which rounds.

### Budget Enforcement

Before starting and between each round:

```python
if budget.max_debate_rounds and round_num > budget.max_debate_rounds:
    break  # End debate early

# Token budget checked against cumulative debate token estimate
if total_tokens > budget.max_debate_budget_tokens:
    break
```

---

## Consensus Engine (`engine/consensus.py`, 286 lines)

### Two Evaluation Modes

**Mode 1: LLM Consensus Judge (Primary)**

A neutral judge LLM evaluates all debate responses:

```python
system_prompt = """You are a neutral consensus judge evaluating a multi-agent debate.
Analyze their responses for:
1. GENUINE CONSENSUS — agents independently reached the same conclusion with distinct reasoning
2. SYCOPHANTIC COLLAPSE — agents agreeing without substance
3. MINORITY POSITIONS — dissenting views with valid reasoning
4. RESIDUAL OBJECTIONS — concerns raised but not fully addressed

Return JSON: {passed, reason, disagreement_areas, agent_verdicts, minority_positions, sycophancy_risk}"""
```

The consensus judge receives all agent responses across all rounds and produces a structured verdict.

**Mode 2: Majority Vote Fallback**

If the LLM consensus judge fails (timeout, parse error):

```python
def _majority_vote_fallback(self, responses):
    votes = {}
    for role, text in responses.items():
        text_upper = text.upper()
        if "PASS" in text_upper:
            votes[role] = True
        elif "FAIL" in text_upper:
            votes[role] = False
        else:
            votes[role] = True  # Default to pass if unclear
    
    pass_count = sum(1 for v in votes.values() if v)
    return pass_count > len(votes) / 2  # Simple majority
```

### Collapse Detection

Sycophantic collapse occurs when agents agree without genuine reasoning — they echo each other instead of independently analyzing.

**Detection mechanism:**

```python
COLLAPSE_KEYWORDS = [
    "i agree", "i concur", "same here", "ditto",
    "echo", "second that", "nothing to add",
]
COLLAPSE_THRESHOLD = 0.6  # 60% of agents using collapse keywords

def detect_collapse(responses: dict[str, str]) -> CollapseSignal:
    collapse_count = 0
    for response in responses.values():
        lower = response.lower()
        if any(kw in lower for kw in COLLAPSE_KEYWORDS):
            collapse_count += 1
    
    ratio = collapse_count / len(responses) if responses else 0
    return CollapseSignal(
        detected=ratio >= COLLAPSE_THRESHOLD,
        confidence=ratio,
        reason=f"{collapse_count}/{len(responses)} agents show collapse signals",
    )
```

**Minimum rounds for comparison:** Collapse detection requires at least 2 rounds (Round 1 responses are independent, so agreement in Round 1 is legitimate).

### Minority Report Extraction

When the majority passes but some agents disagree:

```python
def extract_minority_reports(responses, agent_verdicts):
    reports = []
    for role, passed in agent_verdicts.items():
        if not passed:  # This agent disagreed with the majority
            reports.append(MinorityReport(
                agent_role=role,
                objection=responses.get(role, ""),
                round_number=current_round,
                severity="warning",
            ))
    return reports
```

Minority reports are **preserved in the consensus result** and attached to the phase record. They provide auditability even when the majority overrides dissent.

### Residual Objection Tracking

Concerns raised in early rounds but still present in the final round:

```python
def extract_residual_objections(all_rounds):
    # Extract concerns from Round 1
    early_concerns = _extract_concerns(all_rounds[0])
    
    # Check if they're still present in the final round
    final_text = " ".join(all_rounds[-1].values()).lower()
    residual = [c for c in early_concerns if c.lower() in final_text]
    
    return residual
```

Residual objections indicate issues that the debate process **identified but did not resolve**. They serve as warnings for future phases.

---

## Consensus Result Model

```python
class ConsensusResult(BaseModel):
    reached: bool = False              # Was consensus reached at all?
    passed: bool = False               # Did the output pass collective review?
    reason: str = ""                   # Detailed analysis from consensus judge
    disagreement_areas: list[str]      # Specific areas of agent disagreement
    round_count: int = 0               # How many debate rounds ran
    agent_verdicts: dict[str, bool]    # Per-agent pass/fail
    minority_reports: list[MinorityReport]  # Dissenting views preserved
    collapse_signal: CollapseSignal    # Was sycophantic collapse detected?
    residual_objections: list[str]     # Unresolved concerns from early rounds
```

---

## Confidence Gate (`engine/confidence_gate.py`, 178 lines)

### Purpose

The confidence gate translates votes (with confidence scores) into binary approve/reject decisions. It handles cases where voters agree but with low confidence, or disagree but with varying conviction levels.

### Vote Model

```python
class ConfidenceVote(BaseModel):
    voter_id: str
    approved: bool
    confidence: float    # 0.0 (no confidence) to 1.0 (absolute certainty)
    reason: str = ""
```

### Gate Decision Matrix

| Condition | Action | Approved |
|---|---|---|
| All voters approve AND avg confidence ≥ 0.7 | `approve` | ✓ |
| Non-unanimous, disapprovals have confidence < 0.3 | `synthesize` | ✗ (but close) |
| Non-unanimous, disapprovals have confidence ≥ 0.3 | `continue_debate` | ✗ |
| Average confidence below threshold | `continue_debate` | ✗ |
| No votes received | `reject` | ✗ |

### Drift Detection

The confidence gate tracks vote history and can detect drift patterns:

```python
def detect_drift(self, window: int = 5) -> dict:
    """Analyze the last N gate decisions for patterns."""
    recent = self._history[-window:]
    approval_rate = sum(1 for d in recent if d.approved) / len(recent)
    avg_confidence = sum(d.avg_confidence for d in recent) / len(recent)
    
    return {
        "approval_trend": approval_rate,
        "confidence_trend": avg_confidence,
        "declining": approval_rate < 0.3 and avg_confidence < 0.5,
    }
```

Declining approval with declining confidence indicates that the output quality is systematically insufficient. This signal can trigger escalation to structural replanning.

---

## Debate vs. Judge: When Each Runs

```
Output submitted
    │
    ▼
JudgeEngine.evaluate()
    │
    ├── Passed → Accept output, no debate
    │
    └── Failed → Check debate configuration
                    │
                    ├── Debate not configured → Reject output
                    │
                    └── Debate configured → Run debate
                            │
                            ├── Consensus passed → OVERTURN judge rejection → Accept
                            │
                            └── Consensus failed → Reject output (judge + debate agree)
```

**Key design point:** Debate can **overturn** a judge rejection. This means:
- The judge is not the final authority on quality
- Multiple independent perspectives can collectively override a single evaluator
- This prevents a single bad judge prompt from blocking all progress

**Debate cannot overturn schema check failures.** Schema violations are terminal — they indicate structural problems that no amount of debate can resolve.

---

## Implementation Status

| Component | Status | Notes |
|---|---|---|
| DebateRuntime | **Implemented** | Full 3-round protocol with agent configuration |
| ConsensusEngine | **Implemented** | LLM + majority vote fallback, collapse detection |
| ConfidenceGate | **Implemented** | Vote normalization, threshold enforcement, drift detection |
| Debate ↔ Judge integration | **Implemented** | Debate runs on judge rejection in submit_output |
| Per-phase agent selection | **Implemented** | PHASE_AGENTS mapping |
| Partial completion | **Implemented** | Failed agents don't block debate |
| Token budget enforcement | **Implemented** | Checked between rounds |
| Collapse detection | **Implemented** | Keyword-based, threshold at 60% |
| Minority reports | **Implemented** | Extracted and preserved in ConsensusResult |
| Residual objections | **Implemented** | Tracked across rounds |
| Cross-task learning from debate | **Not implemented** | Would require memory store integration |
| Adaptive agent selection | **Not implemented** | Agents are static per phase |

---

## Known Limitations

1. **Collapse detection is keyword-based** — sophisticated sycophancy (rephrasing agreement without keywords) is not detected
2. **No semantic similarity** in objection tracking — relies on string matching
3. **Agent temperature is fixed** — no adaptive temperature based on debate quality
4. **No agent elimination** — underperforming agents participate in all rounds
5. **Debate results don't influence future debates** — each debate starts fresh without memory of past debate patterns
6. **LLM consensus judge uses same model as debate agents** — no independent evaluation model guarantee
