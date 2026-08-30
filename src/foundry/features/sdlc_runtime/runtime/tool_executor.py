"""Tool execution reliability layer — timeout, retry, normalization, health checks.

TODO #4: The actual "truth layer" — makes tool execution deterministic and reliable.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from foundry.features.sdlc_runtime.adapters.base import ToolAdapter
from foundry.core.logging import get_logger
from foundry.features.sdlc_runtime.runtime.permission_governor import FilePermissionGovernor, PermissionDenied

logger = get_logger("runtime.tool_executor")


def is_binary_content(data: bytes) -> bool:
    """Check whether *data* appears to be binary content.

    A file is considered binary if it contains a null byte (``\\x00``)
    within the first 8 KiB.  This is a reliable heuristic for
    distinguishing binary files from text files.
    """
    return b"\x00" in data[:8192]


def is_binary_file(path: str) -> bool:
    """Check whether the file at *path* is a binary file.

    Reads the first 8 KiB of the file and checks for null bytes.
    Returns ``False`` if the file does not exist or cannot be read
    (e.g. it is a directory or permission is denied).

    Args:
        path: Absolute or relative filesystem path.

    Returns:
        True if the file exists and contains null bytes in its header.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return False


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

    Sandbox path restrictions:
    - denied_paths: paths completely forbidden for any tool operation
    - readonly_paths: paths restricted from tool modification
    - writable_paths: paths that define the allowed working zone

    Path traversal protection:
    - workspace_root: the allowed root directory; any path that resolves
      outside this root is rejected with PermissionError.
    """

    def __init__(
        self,
        *,
        default_timeout_s: float = 120.0,
        max_retries: int = 2,
        backoff_base_s: float = 2.0,
        restricted_paths: list[str] | None = None,
    ) -> None:
        self._adapters: dict[str, ToolAdapter] = {}
        self._default_timeout = default_timeout_s
        self._max_retries = max_retries
        self._backoff_base = backoff_base_s
        self._health: dict[str, bool] = {}
        self._history: list[ToolResult] = []
        self._restricted_paths: list[str] = [str(p) for p in (restricted_paths or [])]
        self._denied_paths: list[str] = list(self._restricted_paths)
        self._readonly_paths: list[str] = []
        self._writable_paths: list[str] = []
        self._sandbox_enabled: bool = bool(restricted_paths)
        self._file_hash_cache: dict[str, dict[str, str]] = {}  # workspace_path -> {rel_path: sha256}
        self._workspace_root: str | None = None
        self._permission_governor: FilePermissionGovernor | None = None

    def register(self, adapter: ToolAdapter) -> None:
        """Register a tool adapter."""
        self._adapters[adapter.name] = adapter

    def set_restricted_paths(self, paths: list[str]) -> None:
        """Set restricted paths that tools are not allowed to operate on.

        This also updates denied_paths for sandbox consistency and enables
        sandbox enforcement if paths are provided.
        """
        self._restricted_paths = [str(p) for p in paths]
        self._denied_paths = list(self._restricted_paths)
        if paths:
            self._sandbox_enabled = True

    def configure_sandbox(
        self,
        *,
        enabled: bool = False,
        denied_paths: list[str] | None = None,
        readonly_paths: list[str] | None = None,
        writable_paths: list[str] | None = None,
    ) -> None:
        """Configure sandbox path restrictions from a SandboxConfig-like source.

        Sets denied, readonly, and writable path categories and updates the
        combined restricted_paths list used for runtime enforcement.

        Args:
            enabled: Whether sandbox enforcement is active.
            denied_paths: Paths completely forbidden for any tool operation.
            readonly_paths: Paths restricted from tool modification.
            writable_paths: Paths that define the allowed working zone.
        """
        self._sandbox_enabled = enabled
        self._denied_paths = [str(p) for p in (denied_paths or [])]
        self._readonly_paths = [str(p) for p in (readonly_paths or [])]
        self._writable_paths = [str(p) for p in (writable_paths or [])]

        # Combine denied and readonly as the full restricted set
        combined: list[str] = []
        seen: set[str] = set()
        for p in self._denied_paths + self._readonly_paths:
            if p not in seen:
                seen.add(p)
                combined.append(p)
        self._restricted_paths = combined

    # ── Permission Governor ───────────────────────────────────

    def set_permission_governor(self, governor: FilePermissionGovernor | None) -> None:
        """Attach a ``FilePermissionGovernor`` for write permission checks.

        When set, ``check_write_permission`` is called during ``execute()``
        to verify that the target path is permitted for write operations.
        Pass ``None`` to disable permission governance.
        """
        self._permission_governor = governor

    def get_permission_governor(self) -> FilePermissionGovernor | None:
        """Return the attached permission governor, or None."""
        return self._permission_governor

    def check_write_permission(self, path: str) -> bool:
        """Check whether a write to *path* is permitted by the governor.

        If no governor is attached, all writes are permitted.

        Returns:
            True if permitted, False if denied.
        """
        if self._permission_governor is None:
            return True
        return self._permission_governor.check_write(path)

    # ── Sandbox Config ─────────────────────────────────────────

    def load_sandbox_config(self, config_path: str) -> None:
        """Load sandbox configuration from a YAML file and apply it.

        Reads the YAML file, extracts sandbox settings (enabled, denied,
        readonly, writable paths), and applies them via ``configure_sandbox``.

        Args:
            config_path: Path to the sandbox YAML configuration file.

        Raises:
            FileNotFoundError: If the config file does not exist.
            yaml.YAMLError: If the YAML content is malformed.
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Sandbox config not found: {config_path}")

        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.configure_sandbox(
            enabled=bool(data.get("enabled", False)),
            denied_paths=list(data.get("denied_paths", [])),
            readonly_paths=list(data.get("readonly_paths", [])),
            writable_paths=list(data.get("writable_paths", [])),
        )

        workspace_root = data.get("workspace_root")
        if workspace_root:
            self.set_workspace_root(str(workspace_root))

        # Also load permission governance rules from the same sandbox config
        permission_rules = data.get("permission_rules")
        if permission_rules is not None:
            if self._permission_governor is None:
                self._permission_governor = FilePermissionGovernor()
            self._permission_governor.configure_from_dict(permission_rules)
            logger.info(
                "Permission governance rules loaded from %s",
                config_path,
                extra={"rule_count": len(self._permission_governor._rules)},
            )

    def set_workspace_root(self, root: str | None) -> None:
        """Set the workspace root for path traversal protection.

        When set, any path supplied to ``execute()`` that resolves outside
        this root directory is rejected with ``PermissionError``.  Pass
        ``None`` to disable traversal protection.

        Args:
            root: Absolute path to the allowed workspace directory, or None.
        """
        self._workspace_root = str(Path(root).resolve()) if root else None

    def _validate_path_no_traversal(self, path: str) -> str:
        """Validate that a path does not escape the workspace root.

        Resolves ``..`` components and symlinks, then checks that the
        resulting canonical path is a subpath of ``_workspace_root``.

        Args:
            path: The filesystem path to validate.

        Returns:
            The resolved canonical path as a string (safe to use).

        Raises:
            PermissionError: If the path resolves outside the workspace root.
        """
        if self._workspace_root is None:
            return path

        workspace = Path(self._workspace_root).resolve()
        resolved = Path(path).resolve()

        try:
            resolved.relative_to(workspace)
        except ValueError:
            raise PermissionError(
                f"Path traversal blocked: '{path}' resolves to '{resolved}' "
                f"which is outside the workspace root '{workspace}'"
            )
        return str(resolved)

    def _check_sandbox_path(self, path: str) -> None:
        """Validate that a path is not restricted for tool execution.

        Checks against denied_paths and readonly_paths when sandbox is enabled.
        Uses _restricted_paths as the combined enforcement list.

        Raises:
            PermissionError: If the path is under a restricted path.
        """
        if not self._restricted_paths or not self._sandbox_enabled:
            return
        resolved = Path(path).resolve()
        for restricted in self._restricted_paths:
            restricted_resolved = Path(restricted).resolve()
            try:
                resolved.relative_to(restricted_resolved)
                raise PermissionError(
                    f"Path '{path}' is under restricted path '{restricted}' "
                    f"and is not allowed for tool execution"
                )
            except ValueError:
                continue

    def _check_binary_path(self, path: str) -> None:
        """Reject operations on existing binary files.

        Any tool execution targeting a path that resolves to an existing
        binary file is blocked with ``PermissionError``.  Non-existent
        paths are allowed (the file being created is not yet binary).

        Raises:
            PermissionError: If *path* points to an existing binary file.
        """
        if is_binary_file(path):
            raise PermissionError(
                f"Binary file modification blocked: '{path}' is a binary file. "
                "Binary files cannot be modified through tool execution."
            )

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
        env_retries = os.environ.get("SDLC_TOOL_EXECUTOR_MAX_RETRIES")
        if env_retries is not None:
            retries = int(env_retries)
        else:
            retries = max_retries if max_retries is not None else self._max_retries

        # Sandbox path check — reject restricted / traversing paths before any execution
        if isinstance(task, dict) and "path" in task:
            path_str = str(task["path"])
            try:
                # Path traversal validation (resolves .. and symlinks, checks workspace)
                safe_path = self._validate_path_no_traversal(path_str)
                # Sandbox restriction check
                self._check_sandbox_path(safe_path)
                # Binary file guard — prevent modification of existing binary files
                self._check_binary_path(safe_path)
                # File permission governance check — verify writes are permitted
                if not self.check_write_permission(safe_path):
                    raise PermissionDenied(safe_path, operation="write")
            except PermissionError as e:
                result = ToolResult(
                    tool=tool_name,
                    passed=False,
                    failure_class="permanent",
                    errors=str(e),
                )
                self._history.append(result)
                return result
            # Update task with the resolved safe path so adapters get the canonical form
            if safe_path != path_str:
                task = dict(task)
                task["path"] = safe_path

        last_error = ""

        for attempt in range(retries + 1):
            # Test support: inject transient failures for deterministic retry testing
            inject_str = os.environ.get("SDLC_INJECT_TRANSIENT_TOOL_FAILURES", "")
            if inject_str:
                inject_count = int(inject_str)
                if inject_count > 0:
                    os.environ["SDLC_INJECT_TRANSIENT_TOOL_FAILURES"] = str(inject_count - 1)
                    elapsed = 0.0
                    result = ToolResult(
                        tool=tool_name,
                        passed=False,
                        failure_class="transient",
                        errors=f"Simulated transient failure for testing (remaining: {inject_count})",
                        retries=attempt,
                        duration_ms=elapsed,
                    )
                    self._history.append(result)
                    last_error = result.errors
                    if attempt == retries:
                        return result
                    await asyncio.sleep(self._backoff_base * (2 ** attempt))
                    continue
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

    def detect_changed_files(
        self,
        workspace_path: str,
        *,
        pattern: str = "**/*.py",
    ) -> list[str]:
        """Detect files that have changed since last check using SHA256 hashing.

        Args:
            workspace_path: Root directory to scan for changes.
            pattern: Glob pattern to match files (default: **/*.py).

        Returns:
            List of relative file paths that have changed (or are new).
        """
        root = Path(workspace_path)
        if not root.is_dir():
            logger.warning("Workspace path not found: %s", workspace_path)
            return []

        cache = self._file_hash_cache.get(workspace_path, {})
        changed: list[str] = []
        current_hashes: dict[str, str] = {}

        for fpath in sorted(root.rglob(pattern)):
            if not fpath.is_file():
                continue
            rel_path = str(fpath.relative_to(root))
            try:
                digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
            except OSError:
                continue
            current_hashes[rel_path] = digest
            cached_hash = cache.get(rel_path)
            if cached_hash is None or cached_hash != digest:
                changed.append(rel_path)

        self._file_hash_cache[workspace_path] = current_hashes
        return changed

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
