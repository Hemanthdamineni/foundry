"""Health — readiness/liveness probes and metrics for production deployment.

Provides standardized health check endpoints compatible with Kubernetes,
Docker health checks, and load balancers.

Architecture reference:
    OB Observability — "Health probes and metrics"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.health")


# --------------------------------------------------------------------------- #
#  Health status
# --------------------------------------------------------------------------- #


class HealthStatus:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: str
    message: str = ""
    last_check: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "last_check": self.last_check,
            "metadata": self.metadata,
        }


@dataclass
class HealthReport:
    """Aggregated health report across all components."""

    status: str
    components: list[ComponentHealth]
    timestamp: float = field(default_factory=time.time)
    uptime_s: float = 0.0

    @property
    def healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "uptime_s": self.uptime_s,
            "components": [c.to_dict() for c in self.components],
        }


# --------------------------------------------------------------------------- #
#  HealthChecker
# --------------------------------------------------------------------------- #


class HealthChecker:
    """Manages component health checks and generates reports.

    Usage::

        checker = HealthChecker()
        checker.register("database", check_database_health)
        checker.register("llm_gateway", check_gateway_health)

        report = await checker.check_all()
        if not report.healthy:
            log.error("System unhealthy: %s", report.status)
    """

    def __init__(self) -> None:
        self._checks: dict[str, Any] = {}
        self._start_time = time.time()
        self._last_report: HealthReport | None = None

    def register(
        self,
        name: str,
        check_fn: Any,
    ) -> None:
        """Register a health check function.

        Parameters
        ----------
        name:
            Component name (e.g. "database", "llm_gateway").
        check_fn:
            Async callable that returns a ComponentHealth.
        """
        self._checks[name] = check_fn
        log.info("health check registered: %s", name)

    async def check_all(self) -> HealthReport:
        """Run all registered health checks and return an aggregated report."""
        components: list[ComponentHealth] = []

        for name, check_fn in self._checks.items():
            try:
                health = await check_fn()
                components.append(health)
            except Exception as exc:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {exc}",
                ))

        # Aggregate status
        status = self._aggregate_status(components)

        report = HealthReport(
            status=status,
            components=components,
            uptime_s=time.time() - self._start_time,
        )

        self._last_report = report
        return report

    async def check_component(self, name: str) -> ComponentHealth | None:
        """Run a single component health check."""
        check_fn = self._checks.get(name)
        if check_fn is None:
            return None

        try:
            return await check_fn()
        except Exception as exc:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {exc}",
            )

    @property
    def last_report(self) -> HealthReport | None:
        return self._last_report

    @property
    def uptime_s(self) -> float:
        return time.time() - self._start_time

    def _aggregate_status(self, components: list[ComponentHealth]) -> str:
        """Determine overall status from component health."""
        if not components:
            return HealthStatus.HEALTHY

        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY


# --------------------------------------------------------------------------- #
#  Built-in health checks
# --------------------------------------------------------------------------- #


async def check_store_health(store: Any) -> ComponentHealth:
    """Check SQLite store health."""
    try:
        # Try a simple operation
        stats = store.stats if hasattr(store, "stats") else {}
        return ComponentHealth(
            name="store",
            status=HealthStatus.HEALTHY,
            metadata=stats,
        )
    except Exception as exc:
        return ComponentHealth(
            name="store",
            status=HealthStatus.UNHEALTHY,
            message=str(exc),
        )


async def check_gateway_health(gateway: Any) -> ComponentHealth:
    """Check LLM gateway health."""
    try:
        # Try a simple operation
        if hasattr(gateway, "list_ollama_model_names"):
            models = await gateway.list_ollama_model_names()
            return ComponentHealth(
                name="gateway",
                status=HealthStatus.HEALTHY,
                metadata={"model_count": len(models)},
            )
        return ComponentHealth(
            name="gateway",
            status=HealthStatus.HEALTHY,
        )
    except Exception as exc:
        return ComponentHealth(
            name="gateway",
            status=HealthStatus.DEGRADED,
            message=f"Gateway check failed: {exc}",
        )


async def check_chronicle_health(chronicle: Any) -> ComponentHealth:
    """Check Chronicle health."""
    try:
        if hasattr(chronicle, "verify_chain"):
            is_valid, last_seq = await chronicle.verify_chain()
            return ComponentHealth(
                name="chronicle",
                status=HealthStatus.HEALTHY if is_valid else HealthStatus.DEGRADED,
                metadata={"chain_valid": is_valid, "last_seq": last_seq},
            )
        return ComponentHealth(
            name="chronicle",
            status=HealthStatus.HEALTHY,
        )
    except Exception as exc:
        return ComponentHealth(
            name="chronicle",
            status=HealthStatus.UNHEALTHY,
            message=str(exc),
        )
