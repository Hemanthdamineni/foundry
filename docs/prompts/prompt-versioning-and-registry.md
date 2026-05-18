# Prompt Versioning and Registry

> PromptRegistry internals, hash-based deduplication, version management, compatibility tracking, and prompt lifecycle.

---

## PromptRegistry (`engine/prompt_registry.py`)

### Purpose

The PromptRegistry manages versioned prompt templates with hash-based deduplication. It ensures that:
- Prompts can be updated without breaking running tasks (locked prompts)
- Duplicate content is detected and collapsed
- Version history is preserved for audit and rollback
- Model compatibility metadata is tracked

### Data Model

```python
class PromptVersion(BaseModel):
    version: int                     # Monotonically increasing
    content: str                     # Full prompt text
    content_hash: str                # SHA256 hash (16 chars)
    created_at: str                  # ISO timestamp
    compatible_models: list[str]     # Models validated against this prompt
    tags: list[str]                  # Metadata tags (e.g., "judge", "debate")
    active: bool                     # Whether this is the current version
```

### Registration

```python
def register(self, name: str, content: str, compatible_models=None, tags=None) -> int:
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    # Dedup check: if content hash matches an existing version, return that version
    existing = self._find_by_hash(name, content_hash)
    if existing:
        return existing.version
    
    # Create new version
    version = self._next_version(name)
    entry = PromptVersion(
        version=version,
        content=content,
        content_hash=content_hash,
        active=True,
        ...
    )
    
    # Deactivate previous versions
    for prev in self._prompts[name]:
        prev.active = False
    
    self._prompts[name].append(entry)
    return version
```

### Retrieval

```python
def get_active(self, name: str) -> str | None:
    """Get the active version of a prompt."""
    for entry in reversed(self._prompts.get(name, [])):
        if entry.active:
            return entry.content
    return None

def get_version(self, name: str, version: int) -> str | None:
    """Get a specific version of a prompt."""
    for entry in self._prompts.get(name, []):
        if entry.version == version:
            return entry.content
    return None

def all_hashes(self) -> dict[str, str]:
    """Get content hashes for all active prompts."""
    return {name: entries[-1].content_hash for name, entries in self._prompts.items() if entries}
```

### Rollback

```python
def rollback(self, name: str, to_version: int) -> bool:
    for entry in self._prompts.get(name, []):
        entry.active = (entry.version == to_version)
    return True
```

Rollback changes which version is active but preserves all history.

---

## Hash-Based Deduplication

If the same prompt content is registered again, the registry detects the duplicate and returns the existing version instead of creating a new one. This prevents version inflation from redundant registrations.

```
register("judge_specs", "Evaluate specs for completeness...")  → v1
register("judge_specs", "Evaluate specs for completeness...")  → v1 (same content, same hash)
register("judge_specs", "Evaluate specs for completeness AND correctness...")  → v2 (new content)
```

---

## Compatibility Manager

The compatibility manager tracks which model + prompt combinations have been validated:

```python
class PromptCompatibility(BaseModel):
    prompt_name: str
    prompt_version: int
    model: str
    tested: bool = False
    passed: bool = False
    notes: str = ""
```

### Purpose

When switching models (e.g., from `qwen3:8b` to `gpt-4o`), the compatibility manager can check whether the current judge prompts have been validated against the new model. If not, it produces warnings.

### Validation Flow

```python
# During model change
for prompt_name in registry.list_prompts():
    compat = compatibility_mgr.check(prompt_name, new_model)
    if not compat.tested:
        logger.warning(f"Prompt '{prompt_name}' not tested with model '{new_model}'")
```

---

## Prompt Anti-Patterns

The registry can detect known anti-patterns in prompt content:

| Anti-Pattern | Detection | Risk |
|---|---|---|
| Hardcoded model names | `"gpt-4"` in prompt text | Breaks with model changes |
| Role confusion | `"You are a coder"` in a judge prompt | Judge evaluates instead of generating |
| Unbounded instructions | No length/scope constraints | Produces unpredictable output length |
| Conflicting directives | `"Be strict" + "Be lenient"` | Inconsistent evaluation |
| Version-specific syntax | `"Use Python 3.8 features"` | Outdated language constraints |

---

## Prompt Lifecycle

```
1. Author writes prompt template → configs/prompts/judge_specs_to_planning.txt
2. Server loads at startup → settings.load_all_judge_prompts()
3. Task creation locks prompts → task.locked_prompts = {name: content}
4. Judge uses locked prompt → judge_engine.evaluate() looks up from task
5. Prompt edited on disk → affects only NEW tasks
6. PromptRegistry tracks versions → dedup, rollback, compatibility
```

---

## Prompt Sources

| Prompt Type | Source | Locked Per Task |
|---|---|---|
| Judge prompts | `configs/prompts/*.txt` | ✓ Yes |
| Phase prompts | Built dynamically from phase name + context | ✗ No (always current) |
| Debate system prompts | Built from `DebateAgentRole` | ✗ No |
| Consensus prompt | Hardcoded in `ConsensusEngine` | ✗ No |

Only judge prompts are locked because they are the primary quality gate. Phase and debate prompts are structural and less sensitive to version drift.

---

## Implementation Status

| Component | Status |
|---|---|
| PromptRegistry | **Implemented** — versioning, dedup, rollback |
| Hash-based deduplication | **Implemented** |
| Prompt locking on Task | **Implemented** |
| CompatibilityManager | **Implemented** — data model, tracking |
| Anti-pattern detection | **Partial** — categories defined, detection not automated |
| Prompt persistence | **Not implemented** — in-memory only, loaded from disk each startup |
