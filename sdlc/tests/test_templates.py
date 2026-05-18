"""Tests for template content integrity."""

from __future__ import annotations

from sdlc.templates import (
    CONTEXT_SDLC_FILES,
    GRAPH_FILES,
    LLM_CONFIG_YAML,
    OPENCODE_FRAGMENT,
    PROMPT_FILES,
    SKILL_MD,
)


class TestOpencodeFragment:
    def test_has_mcp_server(self) -> None:
        assert "mcpServers" in OPENCODE_FRAGMENT
        assert "sdlc-orchestrator" in OPENCODE_FRAGMENT["mcpServers"]

    def test_has_primary_agent(self) -> None:
        assert "agents" in OPENCODE_FRAGMENT
        assert "dev-sdlc" in OPENCODE_FRAGMENT["agents"]
        assert OPENCODE_FRAGMENT["agents"]["dev-sdlc"]["mode"] == "primary"

    def test_mcp_server_has_required_keys(self) -> None:
        srv = OPENCODE_FRAGMENT["mcpServers"]["sdlc-orchestrator"]
        for key in ("type", "command", "args", "env"):
            assert key in srv

    def test_mcp_server_uses_stdio(self) -> None:
        assert OPENCODE_FRAGMENT["mcpServers"]["sdlc-orchestrator"]["type"] == "stdio"

    def test_mcp_server_command_is_sdlc_mcp(self) -> None:
        assert OPENCODE_FRAGMENT["mcpServers"]["sdlc-orchestrator"]["command"] == "sdlc-mcp"


class TestSkillMd:
    def test_has_frontmatter(self) -> None:
        assert SKILL_MD.startswith("---")

    def test_has_phase_table(self) -> None:
        assert "## Phases" in SKILL_MD
        assert "Chatting" in SKILL_MD
        assert "Specs" in SKILL_MD
        assert "Coding" in SKILL_MD
        assert "Review" in SKILL_MD
        assert "Done" in SKILL_MD

    def test_has_tool_list(self) -> None:
        assert "sdlc_create_task" in SKILL_MD
        assert "sdlc_get_next_action" in SKILL_MD
        assert "sdlc_submit_output" in SKILL_MD


class TestPromptFiles:
    def test_all_phases_have_prompts(self) -> None:
        for phase in ("chatting", "specs", "planning", "coding", "review", "testing", "done"):
            assert f"{phase}.md" in PROMPT_FILES, f"Missing prompt for {phase}"

    def test_prompts_are_non_empty(self) -> None:
        for name, content in PROMPT_FILES.items():
            assert len(content.strip()) > 50, f"Prompt {name} is too short"


class TestContextFiles:
    def test_has_project_readme(self) -> None:
        assert "project" in CONTEXT_SDLC_FILES
        assert "README.md" in CONTEXT_SDLC_FILES["project"]

    def test_has_architecture_doc(self) -> None:
        assert "sdlc" in CONTEXT_SDLC_FILES
        assert "architecture.md" in CONTEXT_SDLC_FILES["sdlc"]

    def test_architecture_mentions_key_components(self) -> None:
        arch = CONTEXT_SDLC_FILES["sdlc"]["architecture.md"]
        for component in ("ConsensusEngine", "JudgeEngine", "DebateRuntime", "Acervo", "ModelRouter"):
            assert component in arch


class TestGraphFiles:
    def test_has_sdlc_phases_graph(self) -> None:
        assert "sdlc-phases.yaml" in GRAPH_FILES

    def test_graph_has_required_nodes(self) -> None:
        graph = GRAPH_FILES["sdlc-phases.yaml"]
        for phase in ("Chatting", "Specs", "Planning", "Coding", "Review", "Testing", "Done"):
            assert phase in graph

    def test_graph_has_iteration_edge(self) -> None:
        graph = GRAPH_FILES["sdlc-phases.yaml"]
        assert "iteration" in graph


class TestLlmConfigYaml:
    def test_has_default_provider(self) -> None:
        assert "llm:" in LLM_CONFIG_YAML
        assert "default_provider:" in LLM_CONFIG_YAML

    def test_has_providers_section(self) -> None:
        assert "providers:" in LLM_CONFIG_YAML
        assert "ollama:" in LLM_CONFIG_YAML
        assert "openai:" in LLM_CONFIG_YAML

    def test_has_routing_section(self) -> None:
        assert "routing:" in LLM_CONFIG_YAML
        assert "judge:" in LLM_CONFIG_YAML
        assert "debate_agent:" in LLM_CONFIG_YAML
        assert "debate_consensus:" in LLM_CONFIG_YAML
