"""File permission governance for workspace writes — enforces allow/deny rules on file paths.

The ``FilePermissionGovernor`` provides a rule-based permission system for
workspace file operations. Rules are evaluated in insertion order; the first
matching rule determines the result. If no rule matches, the default action
(default-deny for safety) is used.

Rules use ``fnmatch`` glob patterns for path matching, making them flexible
enough for most workspace layouts while staying simple to configure.

Integration
-----------
The governor is designed to be attached to ``ToolExecutor``, which checks write
permissions during tool execution. It can also be used standalone::

    governor = FilePermissionGovernor(default_deny=True)
    governor.add_allow_rule("/workspace/src/**")
    governor.add_deny_rule("/workspace/src/secrets/**")

    if not governor.check_write("/workspace/src/secrets/token.txt"):
        raise PermissionError("Write not permitted")
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger

logger = get_logger("runtime.permission_governor")


class PermissionDenied(PermissionError):
    """Raised when a file operation is denied by the permission governor."""

    def __init__(self, path: str, operation: str = "write", rule: str | None = None) -> None:
        self.operation = operation
        self.rule = rule
        msg = f"Permission denied: {operation} on '{path}'"
        if rule:
            msg += f" (matched rule: '{rule}')"
        super().__init__(msg)


class PermissionRule:
    """A single permission rule that matches paths via glob pattern.

    Attributes:
        pattern: ``fnmatch``-compatible glob pattern for path matching.
        permission: ``"allow"`` or ``"deny"``.
        operation: Operation type this rule applies to (``"read"``, ``"write"``,
            ``"execute"``, or ``"*"`` for all).
    """

    def __init__(self, pattern: str, permission: str, operation: str = "write") -> None:
        if permission not in ("allow", "deny"):
            msg = f"Permission must be 'allow' or 'deny', got '{permission}'"
            raise ValueError(msg)
        self.pattern = pattern
        self.permission = permission
        self.operation = operation

    def matches(self, path: str, operation: str) -> bool:
        """Return True if this rule applies to *path* for *operation*."""
        if self.operation != "*" and operation != self.operation:
            return False
        return fnmatch.fnmatch(path, self.pattern)

    def __repr__(self) -> str:
        return (
            f"PermissionRule(pattern='{self.pattern}', "
            f"permission='{self.permission}', operation='{self.operation}')"
        )


class FilePermissionGovernor:
    """Governs workspace file operations based on configurable permission rules.

    Rules are evaluated in insertion order. The first matching rule wins.
    If no rule matches, the default action is determined by ``default_deny``.

    Args:
        default_deny: When True (default), any path that does not match an
            explicit ``allow`` rule is denied. Set to False for a default-allow
            policy (not recommended for production).
    """

    def __init__(self, default_deny: bool = True) -> None:
        self._rules: list[PermissionRule] = []
        self._default_deny = default_deny

    # ── Rule Management ─────────────────────────────────────────

    def add_rule(self, pattern: str, permission: str, operation: str = "write") -> None:
        """Add a permission rule.

        Args:
            pattern: ``fnmatch`` glob pattern (e.g. ``"/workspace/src/**"``).
            permission: ``"allow"`` or ``"deny"``.
            operation: ``"read"``, ``"write"``, ``"execute"``, or ``"*"``.
        """
        self._rules.append(PermissionRule(pattern, permission, operation))

    def add_allow_rule(self, pattern: str, operation: str = "write") -> None:
        """Shorthand to add an allow rule."""
        self.add_rule(pattern, "allow", operation)

    def add_deny_rule(self, pattern: str, operation: str = "write") -> None:
        """Shorthand to add a deny rule."""
        self.add_rule(pattern, "deny", operation)

    def clear_rules(self) -> None:
        """Remove all permission rules."""
        self._rules.clear()

    @property
    def rules(self) -> list[PermissionRule]:
        """Return a copy of the current rule list."""
        return list(self._rules)

    # ── Permission Checks ───────────────────────────────────────

    def check(self, path: str, operation: str = "write") -> bool:
        """Check whether *operation* on *path* is permitted.

        Args:
            path: The filesystem path to check.
            operation: The operation type (``"read"``, ``"write"``, etc.).

        Returns:
            True if permitted, False if denied.
        """
        for rule in self._rules:
            if rule.matches(path, operation):
                allowed = rule.permission == "allow"
                logger.debug(
                    "Permission %s for '%s' (%s) — matched rule '%s'",
                    "granted" if allowed else "denied",
                    path,
                    operation,
                    rule.pattern,
                )
                return allowed

        # No rule matched — apply default
        allowed = not self._default_deny
        logger.debug(
            "Permission %s for '%s' (%s) — default %s",
            "granted" if allowed else "denied",
            path,
            operation,
            "allow" if allowed else "deny",
        )
        return allowed

    def check_write(self, path: str) -> bool:
        """Convenience: check if *write* on *path* is permitted.

        Equivalent to ``check(path, operation="write")``.
        """
        return self.check(path, operation="write")

    def assert_write_permitted(self, path: str) -> None:
        """Raise ``PermissionDenied`` if write on *path* is not permitted.

        Args:
            path: The filesystem path to check.

        Raises:
            PermissionDenied: If the write is denied by any rule or default.
        """
        if not self.check_write(path):
            # Find which rule denied it (for the error message)
            matching_rule: str | None = None
            for rule in self._rules:
                if rule.matches(path, "write") and rule.permission == "deny":
                    matching_rule = rule.pattern
                    break
            raise PermissionDenied(path, operation="write", rule=matching_rule)

    # ── Configuration ───────────────────────────────────────────

    def configure_from_dict(self, config: dict[str, Any]) -> None:
        """Configure rules from a dictionary.

        Expected format::

            {
                "default_deny": true,
                "rules": [
                    {"pattern": "/workspace/src/**", "permission": "allow", "operation": "write"},
                    {"pattern": "*.secret", "permission": "deny", "operation": "write"},
                ]
            }

        Args:
            config: Dictionary with optional ``default_deny`` and ``rules`` keys.
        """
        if "default_deny" in config:
            self._default_deny = bool(config["default_deny"])

        raw_rules = config.get("rules", [])
        for rule in raw_rules:
            self.add_rule(
                pattern=str(rule.get("pattern", "*")),
                permission=str(rule.get("permission", "deny")),
                operation=str(rule.get("operation", "write")),
            )

    def configure_from_yaml(self, yaml_path: str) -> bool:
        """Configure rules from a YAML file.

        Returns True if the file was loaded, False if it did not exist.

        Args:
            yaml_path: Path to a YAML configuration file.

        Raises:
            yaml.YAMLError: If the YAML content is malformed.
        """
        import yaml

        path = Path(yaml_path)
        if not path.exists():
            logger.warning("Permission governor config not found: %s", yaml_path)
            return False

        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self.configure_from_dict(data)
        logger.info(
            "Permission governor configured from %s (%d rules, default_deny=%s)",
            yaml_path,
            len(self._rules),
            self._default_deny,
        )
        return True

    # ── Reporting ───────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return a summary of the governor configuration."""
        return {
            "default_deny": self._default_deny,
            "rule_count": len(self._rules),
            "rules": [
                {
                    "pattern": r.pattern,
                    "permission": r.permission,
                    "operation": r.operation,
                }
                for r in self._rules
            ],
        }


__all__ = [
    "FilePermissionGovernor",
    "PermissionDenied",
    "PermissionRule",
]
