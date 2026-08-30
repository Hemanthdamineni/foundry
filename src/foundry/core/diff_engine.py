"""DiffEngine — safe code modification with patch generation and application.

Provides diff/patch operations for safe code modification. Generates unified
diffs that can be previewed before application, and validates patches against
the repository before committing.

Architecture reference:
    L4 Repository Execution — "How is code safely modified?"
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from foundry.core.logging import get_logger

log = get_logger("foundry.diff_engine")


# --------------------------------------------------------------------------- #
#  Diff types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DiffHunk:
    """A single hunk in a diff (contiguous block of changes)."""

    start_line: int
    end_line: int
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]

    @property
    def is_addition(self) -> bool:
        return len(self.old_lines) == 0 and len(self.new_lines) > 0

    @property
    def is_deletion(self) -> bool:
        return len(self.new_lines) == 0 and len(self.old_lines) > 0

    @property
    def is_modification(self) -> bool:
        return len(self.old_lines) > 0 and len(self.new_lines) > 0


@dataclass(frozen=True)
class DiffResult:
    """Result of generating a diff between two texts."""

    file_path: str
    old_content: str
    new_content: str
    hunks: tuple[DiffHunk, ...]
    unified_diff: str
    old_checksum: str
    new_checksum: str

    @property
    def has_changes(self) -> bool:
        return len(self.hunks) > 0

    @property
    def lines_added(self) -> int:
        return sum(len(h.new_lines) for h in self.hunks)

    @property
    def lines_removed(self) -> int:
        return sum(len(h.old_lines) for h in self.hunks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "has_changes": self.has_changes,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "hunks": len(self.hunks),
            "unified_diff": self.unified_diff,
            "old_checksum": self.old_checksum,
            "new_checksum": self.new_checksum,
        }


@dataclass(frozen=True)
class PatchResult:
    """Result of applying a patch."""

    file_path: str
    success: bool
    old_content: str | None = None
    new_content: str | None = None
    error: str | None = None
    backup_path: str | None = None


# --------------------------------------------------------------------------- #
#  DiffEngine
# --------------------------------------------------------------------------- #


class DiffEngine:
    """Safe code modification with diff generation and patch application.

    Usage::

        engine = DiffEngine(workspace_path="/path/to/repo")

        # Generate a diff
        diff = engine.diff_file("src/auth.py", old_text, new_text)
        print(diff.unified_diff)

        # Apply a patch (with backup)
        result = engine.apply_patch("src/auth.py", new_content)
        if result.success:
            print(f"Patch applied, backup at {result.backup_path}")

        # Apply from unified diff string
        result = engine.apply_unified_diff("src/auth.py", diff_string)
    """

    BACKUP_SUFFIX = ".bak"

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        self._workspace = Path(workspace_path) if workspace_path else Path.cwd()

    # -- Diff generation ---------------------------------------------------- #

    def diff_file(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> DiffResult:
        """Generate a diff between old and new content for a file."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        # Generate unified diff — use \n as lineterm
        unified = "\n".join(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        ))

        # Parse hunks from the unified diff
        hunks = self._parse_unified_diff(unified)

        # Compute checksums
        old_checksum = hashlib.sha256(old_content.encode("utf-8")).hexdigest()[:16]
        new_checksum = hashlib.sha256(new_content.encode("utf-8")).hexdigest()[:16]

        return DiffResult(
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            hunks=tuple(hunks),
            unified_diff=unified,
            old_checksum=old_checksum,
            new_checksum=new_checksum,
        )

    def diff_file_on_disk(self, file_path: str, new_content: str) -> DiffResult | None:
        """Generate a diff for a file on disk against new content."""
        full_path = self._workspace / file_path
        if not full_path.exists():
            return None

        old_content = full_path.read_text(encoding="utf-8")
        return self.diff_file(file_path, old_content, new_content)

    def diff_strings(self, old: str, new: str, label: str = "content") -> str:
        """Generate a unified diff between two strings."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        return "".join(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
            lineterm="",
        ))

    # -- Patch application -------------------------------------------------- #

    def apply_patch(
        self,
        file_path: str,
        new_content: str,
        *,
        create_backup: bool = True,
        validate: bool = True,
    ) -> PatchResult:
        """Apply a patch by replacing file content.

        Creates a backup of the original before modifying.
        """
        full_path = self._workspace / file_path

        # Read old content
        if full_path.exists():
            old_content = full_path.read_text(encoding="utf-8")
        else:
            old_content = ""
            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate the patch (basic checks)
        if validate:
            validation = self._validate_patch(old_content, new_content, file_path)
            if not validation["valid"]:
                return PatchResult(
                    file_path=file_path,
                    success=False,
                    error=validation.get("error", "Validation failed"),
                )

        # Create backup
        backup_path = None
        if create_backup and old_content:
            backup_path = str(full_path) + self.BACKUP_SUFFIX
            full_path.rename(backup_path)

        try:
            full_path.write_text(new_content, encoding="utf-8")
            log.info("patch applied: %s", file_path)
            return PatchResult(
                file_path=file_path,
                success=True,
                old_content=old_content,
                new_content=new_content,
                backup_path=backup_path,
            )
        except Exception as exc:
            # Restore from backup if write failed
            if backup_path:
                try:
                    Path(backup_path).rename(full_path)
                except Exception:
                    log.error("failed to restore backup: %s", backup_path)
            log.error("patch failed: %s — %s", file_path, exc)
            return PatchResult(
                file_path=file_path,
                success=False,
                error=str(exc),
            )

    def apply_unified_diff(
        self,
        file_path: str,
        diff_text: str,
        *,
        create_backup: bool = True,
    ) -> PatchResult:
        """Apply a unified diff string to a file on disk."""
        full_path = self._workspace / file_path

        if not full_path.exists():
            return PatchResult(
                file_path=file_path,
                success=False,
                error=f"File not found: {file_path}",
            )

        old_content = full_path.read_text(encoding="utf-8")
        old_lines = old_content.splitlines(keepends=True)

        # Apply the diff using difflib
        new_lines = list(difflib.restore(
            diff_text.splitlines(keepends=True),
            fromfile=1,
            tofile=2,
        ))

        new_content = "".join(new_lines)

        return self.apply_patch(
            file_path,
            new_content,
            create_backup=create_backup,
        )

    def revert(self, file_path: str) -> bool:
        """Revert a file from its backup."""
        full_path = self._workspace / file_path
        backup_path = full_path.with_suffix(full_path.suffix + self.BACKUP_SUFFIX)

        if backup_path.exists():
            backup_path.rename(full_path)
            log.info("reverted: %s from backup", file_path)
            return True
        return False

    # -- Validation --------------------------------------------------------- #

    def _validate_patch(
        self,
        old_content: str,
        new_content: str,
        file_path: str,
    ) -> dict[str, Any]:
        """Validate a patch before application."""
        # Basic checks
        if not new_content.strip() and old_content.strip():
            return {"valid": False, "error": "Patch would empty the file"}

        # Check for syntax errors in Python files
        if file_path.endswith(".py"):
            try:
                compile(new_content, file_path, "exec")
            except SyntaxError as exc:
                return {"valid": False, "error": f"Syntax error: {exc}"}

        return {"valid": True}

    def _parse_unified_diff(self, unified: str) -> list[DiffHunk]:
        """Parse unified diff text into DiffHunk objects."""
        hunks: list[DiffHunk] = []
        lines = unified.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for hunk header: @@ -start,end +start,end @@
            hunk_match = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if hunk_match:
                start_line = int(hunk_match.group(1))
                old_lines: list[str] = []
                new_lines: list[str] = []
                j = i + 1

                while j < len(lines):
                    if lines[j].startswith("@@") or lines[j].startswith("diff "):
                        break
                    # Strip trailing newline for comparison
                    raw = lines[j]
                    content = raw.rstrip("\n")
                    if content.startswith("-"):
                        old_lines.append(content[1:])
                    elif content.startswith("+"):
                        new_lines.append(content[1:])
                    elif content.startswith(" "):
                        # Context line — skip for now
                        pass
                    j += 1

                hunks.append(DiffHunk(
                    start_line=start_line,
                    end_line=start_line + len(old_lines) - 1,
                    old_lines=tuple(old_lines),
                    new_lines=tuple(new_lines),
                ))

                i = j
            else:
                i += 1

        return hunks

    # -- File operations ---------------------------------------------------- #

    def read_file(self, file_path: str) -> str | None:
        """Read a file from the workspace."""
        full_path = self._workspace / file_path
        if not full_path.exists():
            return None
        return full_path.read_text(encoding="utf-8")

    def list_files(self, glob_pattern: str = "**/*.py") -> list[str]:
        """List files matching a glob pattern."""
        return [
            str(p.relative_to(self._workspace))
            for p in self._workspace.glob(glob_pattern)
            if p.is_file() and not any(
                part.startswith(".")
                for part in p.relative_to(self._workspace).parts
            )
        ]
