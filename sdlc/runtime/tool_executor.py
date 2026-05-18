"""Tool execution reliability layer — timeout, retry, normalization, health checks.

TODO #4: The actual "truth layer" — makes tool execution deterministic and reliable.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from sdlc.adapters.base import ToolAdapter
from sdlc.log import get_logger

logger = get_logger("runtime.tool_executor")


class ToolResult(BaseModel):
    """Normalized tool execution result."""

    tool: str
    passed: bool
    returncode: int = 0
    output: str = ""
    errors: str = ""
    duration_ms: float = 0.0
    retries: int = 0
    failure_class: str = ""  # transient, permanent, timeout, not_found
    normalized: bool = True


class ToolExecutor:
    """Reliable tool execution with timeout, retry, normalization, and health checks.

    Wraps raw ToolAdapter calls with:
    - Timeout enforcement
    - Retry with backoff
    - Output normalization
    - Failure classification
    - Health check validation
    """

    def __init__(
        self,
        *,
        default_timeout_s: float = 120.0,
        max_retries: int = 2,
        backoff_base_s: float = 2.0,
    ) -> None:
        self._adapters: dict[str, ToolAdapter] = {}
        self._default_timeout = default_timeout_s
        self._max_retries = max_retries
        self._backoff_base = backoff_base_s
        self._health: dict[str, bool] = {}
        self._history: list[ToolResult] = []

    def register(self, adapter: ToolAdapter) -> None:
        """Register a tool adapter."""
        self._adapters[adapter.name] = adapter

    async def healthcheck_all(self) -> dict[str, bool]:
        """Run health checks on all registered tools."""
        for name, adapter in self._adapters.items():
            try:
                self._health[name] = await adapter.healthcheck()
            except Exception:
                self._health[name] = False
        return dict(self._health)

    async def execute(
        self,
        tool_name: str,
        task: Any,
        *,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> ToolResult:
        """Execute a tool with timeout enforcement, retry, and normalization."""
        adapter = self._adapters.get(tool_name)
        if adapter is None:
            result = ToolResult(
                tool=tool_name,
                passed=False,
                failure_class="not_found",
                errors=f"Tool not registered: {tool_name}",
            )
            self._history.append(result)
            return result

        timeout = timeout_s or self._default_timeout
        retries = max_retries if max_retries is not None else self._max_retries
        last_error = ""

        for attempt in range(retries + 1):
            start = time.monotonic()
            try:
                raw = await asyncio.wait_for(
                    adapter.execute(task),
                    timeout=timeout,
                )
                elapsed = (time.monotonic() - start) * 1000

                result = self._normalize(tool_name, raw, elapsed, attempt)
                self._history.append(result)
                if result.passed or result.failure_class == "permanent":
                    return result

                last_error = result.errors
            except asyncio.TimeoutError:
                elapsed = (time.monotonic() - start) * 1000
                last_error = f"Timed out after {timeout}s"
                result = ToolResult(
                    tool=tool_name,
                    passed=False,
                    duration_ms=elapsed,
                    retries=attempt,
                    failure_class="timeout",
                    errors=last_error,
                )
                if attempt == retries:
                    self._history.append(result)
                    return result
            except FileNotFoundError:
                result = ToolResult(
                    tool=tool_name,
                    passed=False,
                    failure_class="not_found",
                    errors=f"Tool binary not found: {tool_name}",
                    retries=attempt,
                )
                self._history.append(result)
                return result  # No retry — binary missing
            except Exception as e:
                last_error = str(e)
                if attempt == retries:
                    result = ToolResult(
                        tool=tool_name,
                        passed=False,
                        failure_class="transient",
                        errors=last_error,
                        retries=attempt,
                    )
                    self._history.append(result)
                    return result

            # Backoff before retry
            if attempt < retries:
                await asyncio.sleep(self._backoff_base * (2 ** attempt))

        # Should not reach here, but safety net
        result = ToolResult(
            tool=tool_name,
            passed=False,
            failure_class="transient",
            errors=last_error,
            retries=retries,
        )
        self._history.append(result)
        return result

    async def execute_gate(
        self,
        tools: list[str],
        task: Any,
    ) -> list[ToolResult]:
        """Execute tools in gate order — stop on first failure."""
        results: list[ToolResult] = []
        for tool_name in tools:
            result = await self.execute(tool_name, task)
            results.append(result)
            if not result.passed:
                break
        return results

    def _normalize(
        self,
        tool_name: str,
        raw: dict[str, Any],
        elapsed_ms: float,
        attempt: int,
    ) -> ToolResult:
        """Normalize raw tool output into a standard ToolResult."""
        passed = raw.get("passed", raw.get("returncode", 1) == 0)
        failure_class = ""
        if not passed:
            rc = raw.get("returncode", 1)
            if rc in {124, 137}:  # timeout/killed signals
                failure_class = "timeout"
            elif rc == 127:  # command not found
                failure_class = "not_found"
            else:
                failure_class = "permanent" if rc != 0 else "transient"

        return ToolResult(
            tool=tool_name,
            passed=passed,
            returncode=raw.get("returncode", 0),
            output=str(raw.get("output", ""))[-2000:],
            errors=str(raw.get("errors", ""))[-500:],
            duration_ms=elapsed_ms,
            retries=attempt,
            failure_class=failure_class,
        )

    @property
    def history(self) -> list[ToolResult]:
        return list(self._history)

    def get_stats(self) -> dict[str, Any]:
        total = len(self._history)
        passed = sum(1 for r in self._history if r.passed)
        return {
            "registered_tools": list(self._adapters.keys()),
            "health": dict(self._health),
            "total_executions": total,
            "passed": passed,
            "failed": total - passed,
            "by_failure_class": self._count_by("failure_class"),
        }

    def _count_by(self, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._history:
            val = getattr(r, field, "")
            if val:
                counts[val] = counts.get(val, 0) + 1
        return counts
