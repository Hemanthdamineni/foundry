"""Tests for Health — readiness/liveness probes and metrics."""

from __future__ import annotations

import pytest

from foundry.core.health import (
    ComponentHealth,
    HealthChecker,
    HealthReport,
    HealthStatus,
    check_store_health,
)


class TestComponentHealth:
    def test_healthy(self) -> None:
        h = ComponentHealth(name="db", status=HealthStatus.HEALTHY)
        assert h.status == HealthStatus.HEALTHY
        d = h.to_dict()
        assert d["name"] == "db"
        assert d["status"] == "healthy"

    def test_unhealthy(self) -> None:
        h = ComponentHealth(
            name="gateway",
            status=HealthStatus.UNHEALTHY,
            message="Connection refused",
        )
        assert h.status == HealthStatus.UNHEALTHY
        assert h.message == "Connection refused"


class TestHealthReport:
    def test_healthy_report(self) -> None:
        report = HealthReport(
            status=HealthStatus.HEALTHY,
            components=[],
        )
        assert report.healthy is True

    def test_unhealthy_report(self) -> None:
        report = HealthReport(
            status=HealthStatus.UNHEALTHY,
            components=[],
        )
        assert report.healthy is False

    def test_to_dict(self) -> None:
        report = HealthReport(
            status=HealthStatus.HEALTHY,
            components=[ComponentHealth(name="db", status=HealthStatus.HEALTHY)],
            uptime_s=100.0,
        )
        d = report.to_dict()
        assert d["status"] == "healthy"
        assert d["uptime_s"] == 100.0
        assert len(d["components"]) == 1


class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_register_and_check(self) -> None:
        checker = HealthChecker()

        async def check_db() -> ComponentHealth:
            return ComponentHealth(name="db", status=HealthStatus.HEALTHY)

        checker.register("db", check_db)
        report = await checker.check_all()

        assert report.healthy is True
        assert len(report.components) == 1
        assert report.components[0].name == "db"

    @pytest.mark.asyncio
    async def test_multiple_components(self) -> None:
        checker = HealthChecker()

        async def check_db() -> ComponentHealth:
            return ComponentHealth(name="db", status=HealthStatus.HEALTHY)

        async def check_cache() -> ComponentHealth:
            return ComponentHealth(name="cache", status=HealthStatus.DEGRADED, message="Slow")

        checker.register("db", check_db)
        checker.register("cache", check_cache)

        report = await checker.check_all()
        assert report.status == HealthStatus.DEGRADED
        assert len(report.components) == 2

    @pytest.mark.asyncio
    async def test_failing_check(self) -> None:
        checker = HealthChecker()

        async def failing_check() -> ComponentHealth:
            raise RuntimeError("Connection failed")

        checker.register("db", failing_check)
        report = await checker.check_all()

        assert report.status == HealthStatus.UNHEALTHY
        assert "failed" in report.components[0].message.lower()

    @pytest.mark.asyncio
    async def test_uptime(self) -> None:
        checker = HealthChecker()
        assert checker.uptime_s >= 0

    @pytest.mark.asyncio
    async def test_check_component(self) -> None:
        checker = HealthChecker()

        async def check_db() -> ComponentHealth:
            return ComponentHealth(name="db", status=HealthStatus.HEALTHY)

        checker.register("db", check_db)
        health = await checker.check_component("db")
        assert health is not None
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_unknown_component(self) -> None:
        checker = HealthChecker()
        health = await checker.check_component("unknown")
        assert health is None

    @pytest.mark.asyncio
    async def test_last_report(self) -> None:
        checker = HealthChecker()
        assert checker.last_report is None

        async def check_db() -> ComponentHealth:
            return ComponentHealth(name="db", status=HealthStatus.HEALTHY)

        checker.register("db", check_db)
        await checker.check_all()
        assert checker.last_report is not None
        assert checker.last_report.healthy is True


class TestBuiltInChecks:
    @pytest.mark.asyncio
    async def test_check_store_health(self) -> None:
        class MockStore:
            stats = {"tasks": 5}
        health = await check_store_health(MockStore())
        assert health.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_store_health_error(self) -> None:
        class BrokenStore:
            @property
            def stats(self):
                raise RuntimeError("DB locked")
        health = await check_store_health(BrokenStore())
        assert health.status == HealthStatus.UNHEALTHY
