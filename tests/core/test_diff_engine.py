"""Tests for DiffEngine — safe code modification."""

from __future__ import annotations

import pytest

from foundry.core.diff_engine import DiffEngine, DiffHunk, DiffResult, PatchResult


class TestDiffHunk:
    def test_is_addition(self) -> None:
        hunk = DiffHunk(start_line=1, end_line=0, old_lines=(), new_lines=("line1",))
        assert hunk.is_addition is True
        assert hunk.is_deletion is False
        assert hunk.is_modification is False

    def test_is_deletion(self) -> None:
        hunk = DiffHunk(start_line=1, end_line=1, old_lines=("line1",), new_lines=())
        assert hunk.is_deletion is True
        assert hunk.is_addition is False

    def test_is_modification(self) -> None:
        hunk = DiffHunk(start_line=1, end_line=1, old_lines=("old",), new_lines=("new",))
        assert hunk.is_modification is True


class TestDiffEngineDiff:
    def test_diff_same_content(self) -> None:
        engine = DiffEngine()
        diff = engine.diff_file("test.py", "hello\n", "hello\n")
        assert diff.has_changes is False
        assert len(diff.hunks) == 0

    def test_diff_with_changes(self) -> None:
        engine = DiffEngine()
        diff = engine.diff_file("test.py", "line1\nline2\n", "line1\nline3\n")
        assert diff.has_changes is True
        assert diff.lines_removed == 1
        assert diff.lines_added == 1

    def test_diff_string(self) -> None:
        engine = DiffEngine()
        result = engine.diff_strings("abc", "abd")
        assert "+abd" in result
        assert "-abc" in result

    def test_diff_checksums_differ(self) -> None:
        engine = DiffEngine()
        diff = engine.diff_file("test.py", "old", "new")
        assert diff.old_checksum != diff.new_checksum

    def test_diff_to_dict(self) -> None:
        engine = DiffEngine()
        diff = engine.diff_file("test.py", "a", "b")
        d = diff.to_dict()
        assert d["file_path"] == "test.py"
        assert d["has_changes"] is True
        assert "unified_diff" in d


class TestDiffEnginePatch:
    def test_apply_patch(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("old_content = 1\n")

        result = engine.apply_patch("test.py", "new_content = 2\n")
        assert result.success is True
        assert result.new_content == "new_content = 2\n"
        assert test_file.read_text() == "new_content = 2\n"
        # Backup should exist
        assert result.backup_path is not None

    def test_apply_patch_creates_backup(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("original_value = 1\n")

        engine.apply_patch("test.py", "modified_value = 2\n")
        backup = tmp_path / "test.py.bak"
        assert backup.exists()
        assert backup.read_text() == "original_value = 1\n"

    def test_apply_patch_no_backup(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("original_value = 1\n")

        result = engine.apply_patch("test.py", "modified_value = 2\n", create_backup=False)
        assert result.success is True
        assert result.backup_path is None

    def test_apply_patch_new_file(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        result = engine.apply_patch("new_file.py", "new_value = 1\n")
        assert result.success is True
        assert (tmp_path / "new_file.py").read_text() == "new_value = 1\n"

    def test_apply_patch_syntax_error(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        result = engine.apply_patch("test.py", "def foo(:\n", validate=True)
        assert result.success is False
        assert "Syntax error" in result.error

    def test_revert(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("original_value = 1\n")

        engine.apply_patch("test.py", "modified_value = 2\n")
        assert test_file.read_text() == "modified_value = 2\n"

        engine.revert("test.py")
        assert test_file.read_text() == "original_value = 1\n"


class TestDiffEngineFileOps:
    def test_read_file(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        (tmp_path / "test.py").write_text("content")
        assert engine.read_file("test.py") == "content"

    def test_read_nonexistent(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        assert engine.read_file("nonexistent.py") is None

    def test_list_files(self, tmp_path) -> None:
        engine = DiffEngine(workspace_path=tmp_path)
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "c.txt").write_text("c")
        files = engine.list_files("*.py")
        assert len(files) == 2
        assert "a.py" in files
        assert "b.py" in files
