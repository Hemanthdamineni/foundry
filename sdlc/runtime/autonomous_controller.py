"""Long-run autonomous controller — pause/resume, stagnation detection, watchdog.

TODO #24: Manages extended autonomous execution with safety controls.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel

from sdlc.log import get_logger

logger = get_logger("runtime.autonomous_controller")


class ControllerState(BaseModel):
    """Current state of the autonomous controller."""

    mode: str = "supervised"  # supervised, semi-autonomous, full-autonomous, paused, overnight
    paused: bool = False
    pause_reason: str = ""
    started_at: float = 0.0
    total_runtime_s: float = 0.0
    tasks_completed: int = 0
    stagnation_detected: bool = False
    last_progress_at: float = 0.0
    watchdog_triggered: bool = False


class AutonomousController:
    """Controls long-running autonomous execution with safety mechanisms.

    Features:
    - Pause/resume with state preservation
    - Stagnation detection (no progress for N seconds)
    - Watchdog timer (max total runtime)
    - Overnight mode (reduced logging, auto-checkpoint)
    """

    def __init__(
        self,
        max_runtime_s: float = 3600,
        stagnation_timeout_s: float = 300,
    ) -> None:
        self._max_runtime_s = max_runtime_s
        self._stagnation_timeout_s = stagnation_timeout_s
        self._state = ControllerState(started_at=time.monotonic())
        self._state.last_progress_at = time.monotonic()
        self._callbacks: dict[str, Any] = {}

    @property
    def state(self) -> ControllerState:
        self._state.total_runtime_s = time.monotonic() - self._state.started_at
        return self._state

    def set_mode(self, mode: str) -> None:
        """Set the autonomy mode."""
        valid_modes = {"supervised", "semi-autonomous", "full-autonomous", "paused", "overnight"}
        if mode not in valid_modes:
            msg = f"Invalid mode: {mode}. Valid: {valid_modes}"
            raise ValueError(msg)
        self._state.mode = mode
        if mode == "paused":
            self._state.paused = True
        else:
            self._state.paused = False
        logger.info("Controller mode changed", extra={"mode": mode})

    def pause(self, reason: str = "User requested") -> None:
        """Pause autonomous execution."""
        self._state.paused = True
        self._state.pause_reason = reason
        logger.info("Controller paused", extra={"reason": reason})

    def resume(self) -> None:
        """Resume autonomous execution."""
        self._state.paused = False
        self._state.pause_reason = ""
        self._state.last_progress_at = time.monotonic()
        logger.info("Controller resumed")

    def record_progress(self) -> None:
        """Record that progress was made (resets stagnation timer)."""
        self._state.last_progress_at = time.monotonic()
        self._state.stagnation_detected = False

    def record_task_complete(self) -> None:
        """Record a task completion."""
        self._state.tasks_completed += 1
        self.record_progress()

    def check_health(self) -> dict[str, Any]:
        """Check controller health — stagnation and watchdog."""
        now = time.monotonic()
        state = self.state
        issues: list[str] = []

        # Stagnation check
        time_since_progress = now - state.last_progress_at
        if time_since_progress > self._stagnation_timeout_s:
            self._state.stagnation_detected = True
            issues.append(
                f"Stagnation: no progress for {time_since_progress:.0f}s "
                f"(threshold: {self._stagnation_timeout_s}s)",
            )

        # Watchdog check
        if state.total_runtime_s > self._max_runtime_s:
            self._state.watchdog_triggered = True
            issues.append(
                f"Watchdog: runtime {state.total_runtime_s:.0f}s exceeds "
                f"max {self._max_runtime_s:.0f}s",
            )

        healthy = len(issues) == 0
        return {
            "healthy": healthy,
            "paused": state.paused,
            "mode": state.mode,
            "runtime_s": round(state.total_runtime_s, 1),
            "stagnation_detected": state.stagnation_detected,
            "watchdog_triggered": state.watchdog_triggered,
            "issues": issues,
        }

    def should_continue(self) -> bool:
        """Check if autonomous execution should continue."""
        if self._state.paused:
            return False
        if self._state.watchdog_triggered:
            return False
        if self._state.stagnation_detected and self._state.mode != "full-autonomous":
            return False
        return True

    async def run_watchdog_loop(
        self,
        interval_s: float = 30,
        on_stagnation: Any = None,
        on_watchdog: Any = None,
    ) -> None:
        """Background watchdog loop that checks health periodically."""
        while True:
            await asyncio.sleep(interval_s)
            health = self.check_health()
            if not health["healthy"]:
                logger.warning("Controller health issue", extra=health)
                if health["stagnation_detected"] and on_stagnation:
                    await on_stagnation()
                if health["watchdog_triggered"] and on_watchdog:
                    await on_watchdog()
                    break
