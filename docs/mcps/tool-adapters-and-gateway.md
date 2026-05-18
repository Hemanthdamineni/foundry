# Tool Adapters and Gateway

> ToolAdapter protocol, concrete adapter implementations, ToolGate validation sequencing, capability model, and tool integration patterns.

---

## ToolAdapter Protocol (`adapters/base.py`)

Every external tool integration implements this interface:

```python
class ToolCapability(StrEnum):
    LINT       = "lint"         # Code style enforcement
    TYPING     = "typing"       # Static type checking
    TESTING    = "testing"      # Test execution
    CODE_GRAPH = "code_graph"   # Code analysis / indexing
    SANDBOX    = "sandbox"      # Execution isolation
    VERSIONING = "versioning"   # Version control
    WORKFLOW   = "workflow"     # External workflow integration

class ToolAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def capability(self) -> ToolCapability: ...

    @abstractmethod
    async def validate(self, task: Any) -> bool: ...

    @abstractmethod
    async def execute(self, task: Any) -> dict[str, Any]: ...

    @abstractmethod
    async def healthcheck(self) -> bool: ...
```

**Key design:** The orchestrator talks to **capabilities**, never to tools directly. If you replace Ruff with Black for linting, the orchestrator doesn't change — only the adapter behind `ToolCapability.LINT` changes.

---

## Concrete Adapters

### Linting: RuffAdapter (`adapters/tools/ruff.py`)

```python
class RuffAdapter(ToolAdapter):
    name = "ruff"
    capability = ToolCapability.LINT
```

Runs `ruff check` on specified files. Parses output for violation counts, categories, and auto-fixable issues.

### Type Checking: MypyAdapter (`adapters/tools/mypy.py`)

```python
class MypyAdapter(ToolAdapter):
    name = "mypy"
    capability = ToolCapability.TYPING
```

Runs `mypy` with `--no-color --no-error-summary`. Parses output for error locations, types, and severity.

### Testing: PytestAdapter (`adapters/tools/pytest.py`)

```python
class PytestAdapter(ToolAdapter):
    name = "pytest"
    capability = ToolCapability.TESTING
```

Runs `pytest --tb=short -q`. Parses output for pass/fail counts, failure details, and coverage if available.

### Security: BanditAdapter (`adapters/tools/bandit.py`)

```python
class BanditAdapter(ToolAdapter):
    name = "bandit"
    capability = ToolCapability.SANDBOX  # Security scanning
```

Runs `bandit -r` for Python security analysis. Detects: `eval()`, `exec()`, `pickle.loads()`, hardcoded passwords, SQL injection patterns.

### Security: SemgrepAdapter (`adapters/tools/semgrep.py`)

```python
class SemgrepAdapter(ToolAdapter):
    name = "semgrep"
    capability = ToolCapability.SANDBOX
```

Runs Semgrep with auto-config rules. Provides broader language support than Bandit.

### Coverage: CoverageAdapter (`adapters/tools/coverage.py`)

```python
class CoverageAdapter(ToolAdapter):
    name = "coverage"
    capability = ToolCapability.TESTING  # Test-adjacent
```

Runs `coverage report`. Parses for line coverage percentage and uncovered file list.

### Benchmarks: BenchmarkAdapter (`adapters/tools/benchmarks.py`)

```python
class BenchmarkAdapter(ToolAdapter):
    name = "benchmarks"
    capability = ToolCapability.TESTING
```

Runs benchmark suites. Captures execution times, memory usage, regression detection.

### Code Graph: TreeSitterAdapter (`adapters/tools/tree_sitter.py`)

```python
class TreeSitterAdapter(ToolAdapter):
    name = "tree_sitter"
    capability = ToolCapability.CODE_GRAPH
```

Uses Tree-sitter for high-fidelity AST parsing. Provides more accurate symbol extraction than regex-based fallbacks.

### Code Graph: GraphifyAdapter (`adapters/tools/graphify.py`)

```python
class GraphifyAdapter(ToolAdapter):
    name = "graphify"
    capability = ToolCapability.CODE_GRAPH
```

Generates visual dependency graphs using the Graphify CLI. Provides call-graph analysis beyond import-level dependencies.

### Memory: MemoryAdapter (`adapters/memory/engram.py`)

```python
class MemoryAdapter(ToolAdapter):
    name = "memory"
    capability = ToolCapability.CODE_GRAPH  # Reuses capability slot
```

Wraps Acervo for store/query operations via the ToolAdapter interface.

---

## ToolGate (`runtime/tool_gate.py`, 133 lines)

### Purpose

The ToolGate enforces an **ordered sequence of validation gates** with fail-fast semantics. If gate N fails, gates N+1 through M are skipped.

### Default Gate Sequence

```python
DEFAULT_GATES = ["lint", "types", "tests", "coverage", "security", "benchmarks"]
```

### Gate Evaluation

```python
class ToolGate:
    def __init__(self, adapters: dict[str, ToolAdapter], gate_sequence=None):
        self._adapters = adapters
        self._gates = gate_sequence or DEFAULT_GATES
    
    async def evaluate(self, task, phase, files=None):
        results = []
        for gate_name in self._gates:
            adapter = self._adapters.get(gate_name)
            if not adapter:
                continue  # Skip unconfigured gates
            
            # Phase exceptions
            if gate_name in self._phase_exceptions.get(phase, []):
                continue
            
            result = await adapter.execute({"files": files, "phase": phase})
            results.append({"gate": gate_name, **result})
            
            if not result.get("passed", True):
                break  # Fail-fast: stop at first failure
        
        all_passed = all(r.get("passed", True) for r in results)
        return {"passed": all_passed, "gates": results}
```

### Phase Exceptions

Not all gates apply to all phases:

```python
PHASE_EXCEPTIONS = {
    "Specs": ["lint", "types", "tests", "coverage", "security", "benchmarks"],  # No tool checks
    "Planning": ["lint", "types", "tests", "coverage", "security", "benchmarks"],
    "Review": ["tests", "benchmarks"],  # Lint and types only
    "Chatting": ["lint", "types", "tests", "coverage", "security", "benchmarks"],
}
# Coding and Testing: all gates active
```

### Gate History

```python
# Track pass/fail rates per gate
self._history.append({
    "gate": gate_name,
    "passed": result["passed"],
    "phase": phase,
    "timestamp": datetime.now(UTC).isoformat(),
})
```

---

## Adapter Healthcheck Pattern

Every adapter implements a healthcheck that verifies the underlying tool is available:

```python
# Typical healthcheck pattern
async def healthcheck(self) -> bool:
    try:
        result = subprocess.run(
            [self._binary, "--version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

Healthchecks are non-destructive, fast (5s timeout), and used at startup to determine which adapters are available.

---

## Adding a New Adapter

1. Create `adapters/tools/your_tool.py`
2. Implement `ToolAdapter` with name, capability, validate, execute, healthcheck
3. Register in the adapter pool during lifespan initialization
4. Add to ToolGate sequence if it's a validation gate
5. No other changes needed — the capability abstraction isolates the integration

---

## Implementation Status

| Adapter | Status | Capability |
|---|---|---|
| RuffAdapter | **Implemented** | LINT |
| MypyAdapter | **Implemented** | TYPING |
| PytestAdapter | **Implemented** | TESTING |
| BanditAdapter | **Implemented** | SANDBOX |
| SemgrepAdapter | **Implemented** | SANDBOX |
| CoverageAdapter | **Implemented** | TESTING |
| BenchmarkAdapter | **Implemented** | TESTING |
| TreeSitterAdapter | **Implemented** | CODE_GRAPH |
| GraphifyAdapter | **Implemented** | CODE_GRAPH |
| MemoryAdapter | **Implemented** | CODE_GRAPH |
| ToolGate | **Implemented** | — |
| Adapter ↔ ToolGate auto-wiring | **Partial** — adapters exist but not all wired into gate |
| Adapter healthcheck at startup | **Partial** — methods exist, not auto-called |
