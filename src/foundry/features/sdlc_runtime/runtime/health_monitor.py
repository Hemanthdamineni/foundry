"""Adapter health monitoring with periodic polling and policy enforcement."""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from foundry.features.sdlc_runtime.adapters.base import ToolAdapter
from foundry.core.logging import get_logger

logger = get_logger("runtime.health_monitor")


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class AdapterHealth:
    """Health state for a single adapter."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: float = 0.0
    consecutive_failures: int = 0
    last_error: str = ""
    required: bool = True


class HealthMonitor:
    """Monitors adapter health via periodic polling and on-demand checks.

    Supports:
    - Periodic background healthcheck polling
    - Required vs optional adapter classification
    - Health status queries for gate enforcement
    - On-demand healthcheck triggering
    """

    def __init__(
        self,
        *,
        poll_interval_s: float = 30.0,
        failure_threshold: int = 3,
    ) -> None:
        self._adapters: dict[str, ToolAdapter] = {}
        self._health: dict[str, AdapterHealth] = {}
        self._poll_interval = poll_interval_s
        self._failure_threshold = failure_threshold
        self._poll_task: asyncio.Task[None] | None = None
        self._running = False

    def register(self, adapter: ToolAdapter, *, required: bool = True) -> None:
        """Register an adapter with health monitoring.

        Args:
            adapter: The tool adapter to monitor.
            required: If True, unhealthy status blocks gate execution.
                     If False, unhealthy adapter is skipped.
        """
        self._adapters[adapter.name] = adapter
        self._health[adapter.name] = AdapterHealth(
            name=adapter.name,
            required=required,
        )

    async def start_polling(self) -> None:
        """Start periodic healthcheck polling."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Health monitor polling started", extra={"interval_s": self._poll_interval})

    async def stop_polling(self) -> None:
        """Stop periodic healthcheck polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
            logger.info("Health monitor polling stopped")

    async def check_all(self) -> dict[str, AdapterHealth]:
        """Run healthcheck on all registered adapters."""
        for name, adapter in self._adapters.items():
            await self._check_adapter(name, adapter)
        return dict(self._health)

    async def check_adapter(self, name: str) -> AdapterHealth | None:
        """Run healthcheck on a specific adapter."""
        adapter = self._adapters.get(name)
        if adapter is None:
            return None
        await self._check_adapter(name, adapter)
        return self._health[name]

    def get_health(self, name: str) -> AdapterHealth | None:
        """Get cached health status for an adapter."""
        return self._health.get(name)

    def get_all_health(self) -> dict[str, AdapterHealth]:
        """Get cached health status for all adapters."""
        return dict(self._health)

    def is_healthy(self, name: str) -> bool:
        """Check if an adapter is currently healthy."""
        health = self._health.get(name)
        if health is None:
            return False
        return health.status == HealthStatus.HEALTHY

    def should_skip_gate(self, adapter_name: str) -> bool:
        """Determine if a gate should be skipped due to adapter health.

        Returns True if:
        - Adapter is optional AND unhealthy (skip the gate)
        - Adapter is required AND unhealthy (fail-closed, don't skip but block)
        """
        health = self._health.get(adapter_name)
        if health is None:
            return False
        if health.status == HealthStatus.UNKNOWN:
            return False
        if not health.required:
            return health.status == HealthStatus.UNHEALTHY
        return False

    def should_fail_closed(self, adapter_name: str) -> bool:
        """Determine if gate execution should fail due to unhealthy required adapter.

        Returns True only if adapter is required AND unhealthy.
        """
        health = self._health.get(adapter_name)
        if health is None:
            return False
        return health.required and health.status == HealthStatus.UNHEALTHY

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._running:
            try:
                await self.check_all()
            except Exception:
                logger.exception("Health check polling error")
            await asyncio.sleep(self._poll_interval)

    async def _check_adapter(self, name: str, adapter: ToolAdapter) -> None:
        """Run healthcheck on a single adapter and update state."""
        health = self._health[name]
        try:
            ok = await adapter.healthcheck()
            health.last_check = time.monotonic()
            if ok:
                health.status = HealthStatus.HEALTHY
                health.consecutive_failures = 0
                health.last_error = ""
            else:
                health.consecutive_failures += 1
                health.last_error = "Healthcheck returned false"
                if health.consecutive_failures >= self._failure_threshold:
                    health.status = HealthStatus.UNHEALTHY
                    logger.warning(
                        "Adapter unhealthy",
                        extra={
                            "adapter": name,
                            "consecutive_failures": health.consecutive_failures,
                            "required": health.required,
                        },
                    )
        except Exception as e:
            health.last_check = time.monotonic()
            health.consecutive_failures += 1
            health.last_error = str(e)
            if health.consecutive_failures >= self._failure_threshold:
                health.status = HealthStatus.UNHEALTHY
                logger.warning(
                    "Adapter healthcheck exception",
                    extra={
                        "adapter": name,
                        "error": str(e),
                        "consecutive_failures": health.consecutive_failures,
                        "required": health.required,
                    },
                )
