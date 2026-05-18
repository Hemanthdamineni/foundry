"""Hierarchical phase graph — supports nested SYSTEM_PHASES → IMPLEMENTATION_PHASES → MICRO_TASKS.

This extends the flat PhaseGraph with a hierarchical execution model where each
implementation phase runs an inner loop: IMPLEMENT → LOCAL_TEST → REVIEW →
INTEGRATION_TEST → REGRESSION_TEST → CHECKPOINT → NEXT.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.hierarchical_graph")


# ── Models ───────────────────────────────────────────────────────────


class MicroTask(BaseModel):
    """An atomic unit of work within an implementation phase."""

    task_id: str
    name: str
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed, skipped
    dependencies: list[str] = Field(default_factory=list)
    test_plan: str = ""
    rollback_plan: str = ""
    files_affected: list[str] = Field(default_factory=list)
    validation_results: dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0
    max_iterations: int = 3


class ImplementationPhase(BaseModel):
    """A group of micro-tasks that together implement one logical chunk."""

    phase_id: str
    name: str
    description: str
    status: str = "pending"  # pending, in_progress, completed, failed
    micro_tasks: list[MicroTask] = Field(default_factory=list)
    integration_test_plan: str = ""
    regression_test_plan: str = ""
    checkpoint_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.micro_tasks if t.status == "completed")

    @property
    def progress(self) -> float:
        if not self.micro_tasks:
            return 0.0
        return (self.completed_tasks / len(self.micro_tasks)) * 100.0


class SystemPhase(BaseModel):
    """A top-level phase grouping implementation phases."""

    phase_id: str
    name: str
    description: str
    status: str = "pending"
    implementation_phases: list[ImplementationPhase] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)

    @property
    def progress(self) -> float:
        if not self.implementation_phases:
            return 0.0
        total = sum(p.progress for p in self.implementation_phases)
        return total / len(self.implementation_phases)


class HierarchicalPlan(BaseModel):
    """The full hierarchical execution plan for a task."""

    task_id: str
    system_phases: list[SystemPhase] = Field(default_factory=list)
    current_system_phase: int = 0
    current_impl_phase: int = 0
    current_micro_task: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed

    @property
    def progress(self) -> float:
        if not self.system_phases:
            return 0.0
        total = sum(p.progress for p in self.system_phases)
        return total / len(self.system_phases)

    @property
    def current_system(self) -> SystemPhase | None:
        if 0 <= self.current_system_phase < len(self.system_phases):
            return self.system_phases[self.current_system_phase]
        return None

    @property
    def current_impl(self) -> ImplementationPhase | None:
        sys_phase = self.current_system
        if sys_phase and 0 <= self.current_impl_phase < len(sys_phase.implementation_phases):
            return sys_phase.implementation_phases[self.current_impl_phase]
        return None

    @property
    def current_task(self) -> MicroTask | None:
        impl = self.current_impl
        if impl and 0 <= self.current_micro_task < len(impl.micro_tasks):
            return impl.micro_tasks[self.current_micro_task]
        return None


# ── Inner Loop States ────────────────────────────────────────────────

MICRO_TASK_LOOP = [
    "implement",
    "local_lint",
    "local_unit_test",
    "local_review",
    "checkpoint",
]

PHASE_INTEGRATION_LOOP = [
    "merge",
    "integration_test",
    "regression_test",
    "benchmark_check",
]


# ── Execution Runner ─────────────────────────────────────────────────


class MicroTaskRunner:
    """Manages the micro-task execution loop within an implementation phase.

    Execution pattern per micro-task:
        IMPLEMENT → LOCAL_LINT → LOCAL_UNIT_TEST → LOCAL_REVIEW → CHECKPOINT

    After all micro-tasks in a phase:
        MERGE → INTEGRATION_TEST → REGRESSION_TEST → BENCHMARK_CHECK
    """

    def __init__(self, max_retries: int = 3) -> None:
        self._max_retries = max_retries

    def next_step(self, plan: HierarchicalPlan) -> dict[str, Any]:
        """Determine the next step in the hierarchical execution."""
        if plan.status == "completed":
            return {"action": "done", "message": "All phases complete"}

        sys_phase = plan.current_system
        if sys_phase is None:
            return {"action": "done", "message": "No more system phases"}

        impl_phase = plan.current_impl
        if impl_phase is None:
            # All impl phases in this system phase done → phase integration
            return {
                "action": "phase_integration",
                "system_phase": sys_phase.name,
                "steps": PHASE_INTEGRATION_LOOP,
            }

        task = plan.current_task
        if task is None:
            # All micro-tasks in this impl phase done → move to phase integration
            return {
                "action": "phase_review",
                "system_phase": sys_phase.name,
                "impl_phase": impl_phase.name,
            }

        return {
            "action": "micro_task",
            "system_phase": sys_phase.name,
            "impl_phase": impl_phase.name,
            "micro_task": task.name,
            "micro_task_id": task.task_id,
            "description": task.description,
            "loop_steps": MICRO_TASK_LOOP,
            "iteration": task.iteration,
            "max_iterations": task.max_iterations,
            "progress": plan.progress,
        }

    def advance_micro_task(self, plan: HierarchicalPlan) -> bool:
        """Mark current micro-task complete and advance to next.

        Returns True if there's more work, False if all done.
        """
        task = plan.current_task
        if task:
            task.status = "completed"

        impl = plan.current_impl
        if impl is None:
            return self._advance_impl_phase(plan)

        plan.current_micro_task += 1
        if plan.current_micro_task >= len(impl.micro_tasks):
            plan.current_micro_task = 0
            return self._advance_impl_phase(plan)
        return True

    def fail_micro_task(self, plan: HierarchicalPlan, error: str) -> dict[str, Any]:
        """Handle micro-task failure with retry logic."""
        task = plan.current_task
        if task is None:
            return {"action": "abort", "reason": "No current task to fail"}

        task.iteration += 1
        if task.iteration >= task.max_iterations:
            task.status = "failed"
            return {
                "action": "escalate",
                "reason": f"Micro-task '{task.name}' failed after {task.max_iterations} attempts: {error}",
                "task_id": task.task_id,
            }

        task.status = "in_progress"
        return {
            "action": "retry",
            "task_id": task.task_id,
            "iteration": task.iteration,
            "max_iterations": task.max_iterations,
            "error": error,
        }

    def _advance_impl_phase(self, plan: HierarchicalPlan) -> bool:
        """Advance to next implementation phase or system phase."""
        sys_phase = plan.current_system
        if sys_phase is None:
            plan.status = "completed"
            return False

        plan.current_impl_phase += 1
        plan.current_micro_task = 0
        if plan.current_impl_phase >= len(sys_phase.implementation_phases):
            return self._advance_system_phase(plan)
        return True

    def _advance_system_phase(self, plan: HierarchicalPlan) -> bool:
        """Advance to next system phase."""
        plan.current_system_phase += 1
        plan.current_impl_phase = 0
        plan.current_micro_task = 0
        if plan.current_system_phase >= len(plan.system_phases):
            plan.status = "completed"
            return False
        return True

    def decompose_plan(
        self,
        task_id: str,
        plan_text: str,
    ) -> HierarchicalPlan:
        """Decompose a flat plan text into a hierarchical execution plan.

        This extracts structure from the plan output sections:
        - ## Implementation Plan → system phases
        - ## File Changes → micro-tasks per phase
        """
        plan = HierarchicalPlan(task_id=task_id, status="pending")

        # Parse sections from plan text
        sections = self._extract_sections(plan_text)

        impl_plan = sections.get("Implementation Plan", "")
        file_changes = sections.get("File Changes", "")

        # Create system phases from numbered items in implementation plan
        steps = self._extract_numbered_items(impl_plan)
        if not steps:
            # Fallback: single system phase
            sys_phase = SystemPhase(
                phase_id=f"{task_id}_sys_0",
                name="Implementation",
                description="Full implementation",
            )
            # Create micro-tasks from file changes
            files = self._extract_file_items(file_changes)
            if files:
                impl = ImplementationPhase(
                    phase_id=f"{task_id}_impl_0",
                    name="Core Implementation",
                    description="Implement all file changes",
                )
                for i, (filepath, desc) in enumerate(files):
                    impl.micro_tasks.append(
                        MicroTask(
                            task_id=f"{task_id}_mt_{i}",
                            name=f"Implement {filepath}",
                            description=desc,
                            files_affected=[filepath],
                        ),
                    )
                sys_phase.implementation_phases.append(impl)
            plan.system_phases.append(sys_phase)
        else:
            for i, step_text in enumerate(steps):
                sys_phase = SystemPhase(
                    phase_id=f"{task_id}_sys_{i}",
                    name=f"Phase {i + 1}",
                    description=step_text,
                )
                impl = ImplementationPhase(
                    phase_id=f"{task_id}_impl_{i}",
                    name=f"Implement Phase {i + 1}",
                    description=step_text,
                )
                impl.micro_tasks.append(
                    MicroTask(
                        task_id=f"{task_id}_mt_{i}_0",
                        name=f"Step {i + 1}",
                        description=step_text,
                    ),
                )
                sys_phase.implementation_phases.append(impl)
                plan.system_phases.append(sys_phase)

        return plan

    def _extract_sections(self, text: str) -> dict[str, str]:
        """Extract ##-headed sections from text."""
        sections: dict[str, str] = {}
        current_name = ""
        current_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                if current_name:
                    sections[current_name] = "\n".join(current_lines).strip()
                current_name = stripped[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_name:
            sections[current_name] = "\n".join(current_lines).strip()
        return sections

    def _extract_numbered_items(self, text: str) -> list[str]:
        """Extract numbered list items (1. xxx, 2. xxx)."""
        import re

        items: list[str] = []
        for line in text.splitlines():
            match = re.match(r"^\s*\d+\.\s+(.+)$", line.strip())
            if match:
                items.append(match.group(1))
        return items

    def _extract_file_items(self, text: str) -> list[tuple[str, str]]:
        """Extract file paths and descriptions from file changes section."""
        import re

        items: list[tuple[str, str]] = []
        for line in text.splitlines():
            # Match patterns like: - `path/to/file.py` — description
            match = re.match(r"^\s*[-*]\s+`?([^\s`]+)`?\s*[-—:]\s*(.+)$", line.strip())
            if match:
                items.append((match.group(1), match.group(2)))
            else:
                # Match bare file paths
                match2 = re.match(r"^\s*[-*]\s+`?([^\s`]+\.\w+)`?\s*$", line.strip())
                if match2:
                    items.append((match2.group(1), f"Modify {match2.group(1)}"))
        return items
