# Model Routing and Providers

> LLM provider abstraction, Ollama and OpenAI implementations, per-role model routing, fallback chains, and configuration.

---

## Provider Architecture

Foundry accesses LLMs through a thin abstraction layer — direct HTTP calls via `httpx`, no frameworks.

```
ModelRouter
    ├── route("judge")     → (OllamaProvider, "qwen3:8b")
    ├── route("debate")    → (OllamaProvider, "qwen3:8b")
    ├── route("consensus") → (OllamaProvider, "qwen3:8b")
    └── Per-role overrides:
        route("judge")     → (OpenAIProvider, "gpt-4o")
```

Total LLM integration: ~230 lines across `base.py` (30L), `providers.py` (160L), `routing.py` (61L).

---

## LLMProvider Protocol (`adapters/llm/base.py`)

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],   # OpenAI-format messages
        *,
        model: str | None = None,          # Override default model
        temperature: float = 0.0,          # Sampling temperature
        max_tokens: int | None = None,     # Response length cap
        response_format: dict | None = None, # JSON schema for structured output
    ) -> str: ...

    @abstractmethod
    async def healthcheck(self) -> bool: ...
```

**Invariants:** Messages are OpenAI-format. Return type is always `str`. All calls are async via httpx.

---

## OllamaProvider

Local inference via `/api/chat`:

```python
class OllamaProvider(LLMProvider):
    base_url = "http://localhost:11434"
    timeout_s = 120
    default_model = "qwen3:8b"
    max_retries = 1
```

- **Structured output:** `body["format"] = response_format` (Ollama-native)
- **Token limit:** `body["options"]["num_predict"] = max_tokens`
- **Retry:** Linear 1s backoff, configurable max_retries
- **Healthcheck:** GET `/api/tags` with 5s timeout

## OpenAIProvider

Cloud/compatible inference via `/chat/completions`:

```python
class OpenAIProvider(LLMProvider):
    api_key = ""  # From env var SDLC_LLM__PROVIDERS__OPENAI__API_KEY
    base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o"
    max_retries = 2  # More retries for network calls
```

- **Structured output:** `body["response_format"] = {"type": "json_object", "schema": ...}`
- **Compatible with:** OpenRouter, DeepSeek, Together, local vLLM — any OpenAI-compatible API
- **Healthcheck:** GET `/models` with API key header

---

## ModelRouter (`adapters/llm/routing.py`)

Routes runtime roles to specific provider + model combinations:

```python
class ModelRouter:
    def route(self, role: str) -> tuple[LLMProvider, str]:
        if role in self._overrides:
            return self._overrides[role]
        return self._default_provider, self._default_model
    
    def add_override(self, role: str, provider: LLMProvider, model: str): ...
    
    @classmethod
    def from_config(cls, default_provider, default_model, routing_config, provider_pool): ...
```

### Configuration

```yaml
# configs/llm_config.yaml
default_provider: ollama
default_model: qwen3:8b
providers:
  ollama:
    type: ollama
    base_url: http://localhost:11434
    default_model: qwen3:8b
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    default_model: gpt-4o
routing:
  judge_provider: ollama
  judge_model: qwen3:8b
  debate_agent_provider: ollama
  debate_consensus_provider: ollama
```

### Per-Phase Model Routing

```yaml
# configs/model_routing.yaml
defaults:
  model: qwen3:8b
  subagent: dev-sdlc
  fallback_models: [qwen3:4b]
phases:
  Coding:
    model: qwen3:8b
    subagent: dev-sdlc
    bash_allowed_patterns: [test, build, lint, format, install, "git *"]
  Testing:
    model: qwen3:8b
    subagent: dev-sdlc
```

Route resolution: `{**defaults, **phase_config}` — phase-specific overrides defaults.

---

## Who Calls LLMs

| Caller | Temperature | Purpose |
|---|---|---|
| Host agent (OpenCode) | Varies | Phase execution (Foundry provides prompt, agent produces output) |
| JudgeEngine | 0.0 | Output evaluation (deterministic) |
| DebateRuntime | 0.7 | Quality debate (diversity) |
| ConsensusEngine | 0.0 | Verdict synthesis (deterministic) |
| SchemaChecks | — | No LLM calls (regex-based) |
| ContextHarvester | — | No LLM calls (template-based) |

**Key insight:** Foundry only calls LLMs for evaluation. Phase execution is performed by the host agent.

---

## Provider Initialization

At server startup in `runtime/app.py`:

1. Load `llm_config.yaml`
2. Build provider pool (instantiate OllamaProvider/OpenAIProvider per config)
3. Select default provider
4. Build ModelRouter with overrides
5. Wire into JudgeEngine, DebateRuntime, ConsensusEngine

---

## Implementation Status

| Component | Status |
|---|---|
| LLMProvider ABC | **Implemented** |
| OllamaProvider | **Implemented** |
| OpenAIProvider | **Implemented** |
| ModelRouter | **Implemented** |
| YAML config loading | **Implemented** |
| Env var API keys | **Implemented** (pydantic_settings) |
| Fallback chain execution | **Partial** — field exists, auto-fallback not wired |
| Token counting from provider | **Not implemented** — character-based estimation |
