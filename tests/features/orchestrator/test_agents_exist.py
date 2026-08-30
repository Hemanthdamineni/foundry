"""File-existence tests for orchestrator agent prompts and scripts."""

from pathlib import Path

# Resolve the feature directory relative to this test file's location.
TEST_DIR = Path(__file__).resolve().parent
FEATURE_DIR = TEST_DIR.parents[2] / "src" / "foundry" / "features" / "orchestrator"

# Expected agent prompt files (copied from Orchestrator/.prompts/)
EXPECTED_PROMPTS: list[str] = [
    "auditor.md",
    "docs_gap.md",
    "executor.md",
    "planner.md",
    "refactorer.md",
    "repairer.md",
    "todo_manager.md",
    "verifier.md",
]

# Expected shell scripts (copied from Orchestrator/scripts/)
EXPECTED_SCRIPTS: list[str] = [
    "audit_phase.sh",
    "cold_start.sh",
    "extract_phase.sh",
    "extract_subphase.sh",
    "loop.sh",
    "orchestrator.sh",
    "run_agent.sh",
    "start_service.sh",
    "update_todo.sh",
    "verify_phase.sh",
]


def test_all_agent_prompts_exist() -> None:
    """Every .md prompt file from Orchestrator/.prompts/ must be present."""
    agents_dir = FEATURE_DIR / "agents"
    for filename in EXPECTED_PROMPTS:
        assert (agents_dir / filename).is_file(), (
            f"Missing agent prompt: {agents_dir / filename}"
        )


def test_all_scripts_exist() -> None:
    """Every .sh script from Orchestrator/scripts/ must be present."""
    scripts_dir = FEATURE_DIR / "scripts"
    for filename in EXPECTED_SCRIPTS:
        assert (scripts_dir / filename).is_file(), (
            f"Missing script: {scripts_dir / filename}"
        )


def test_scripts_are_executable() -> None:
    """All shell scripts should have execute permission."""
    scripts_dir = FEATURE_DIR / "scripts"
    for filename in EXPECTED_SCRIPTS:
        fpath = scripts_dir / filename
        assert fpath.is_file(), f"Missing script: {fpath}"
        assert (fpath.stat().st_mode & 0o111) != 0, (
            f"Script not executable: {fpath}"
        )


def test_agent_dir_only_markdown() -> None:
    """agents/ directory should contain only .md files."""
    agents_dir = FEATURE_DIR / "agents"
    for fpath in agents_dir.iterdir():
        assert fpath.suffix == ".md", (
            f"Unexpected non-markdown file in agents/: {fpath.name}"
        )


def test_prompts_have_frontmatter() -> None:
    """Each prompt file should contain at least one heading (role marker)."""
    agents_dir = FEATURE_DIR / "agents"
    for filename in EXPECTED_PROMPTS:
        content = (agents_dir / filename).read_text()
        assert content.startswith("# "), (
            f"Prompt {filename} is missing a top-level heading"
        )
