"""Unit tests for the secrets provider module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from foundry.core.exceptions import SecretsError
from foundry.core.secrets.provider import FileBackend, SecretsProvider


# ======================================================================
# Helpers
# ======================================================================


class DictBackend:
    """In-memory backend for testing, implements SecretBackend protocol."""

    def __init__(self, data: Dict[str, str] | None = None) -> None:
        self._data = dict(data or {})

    def get(self, key: str) -> str | None:
        return self._data.get(key)


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Reset the global singleton before and after every test."""
    SecretsProvider.set_instance(SecretsProvider())
    yield
    SecretsProvider.set_instance(SecretsProvider())


# ======================================================================
# SecretsProvider — get
# ======================================================================


class TestGet:
    def test_returns_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_SECRET", "s3cret!")
        sp = SecretsProvider()
        assert sp.get("MY_SECRET") == "s3cret!"

    def test_returns_none_when_missing(self) -> None:
        sp = SecretsProvider()
        assert sp.get("NONEXISTENT_KEY_XYZ") is None

    def test_prefers_env_over_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DUPLICATE", "from-env")
        backend = DictBackend({"DUPLICATE": "from-backend"})
        sp = SecretsProvider(backend=backend)
        assert sp.get("DUPLICATE") == "from-env"

    def test_falls_through_to_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BACKEND_ONLY", raising=False)
        backend = DictBackend({"BACKEND_ONLY": "from-backend"})
        sp = SecretsProvider(backend=backend)
        assert sp.get("BACKEND_ONLY") == "from-backend"

    def test_backend_none_returns_none(self) -> None:
        sp = SecretsProvider(backend=None)
        assert sp.get("ANYTHING") is None

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def test_caches_value_after_first_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CACHED_KEY", "original")
        sp = SecretsProvider()
        assert sp.get("CACHED_KEY") == "original"
        monkeypatch.delenv("CACHED_KEY")
        # Should still return cached value
        assert sp.get("CACHED_KEY") == "original"

    def test_no_cache_bypasses_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BYPASS", "first")
        sp = SecretsProvider()
        assert sp.get("BYPASS") == "first"
        monkeypatch.setenv("BYPASS", "second")
        # Without no_cache, cached value is returned
        assert sp.get("BYPASS") == "first"
        # With no_cache, env is re-read
        assert sp.get("BYPASS", no_cache=True) == "second"

    # ------------------------------------------------------------------
    # Thread safety (basic)
    # ------------------------------------------------------------------

    def test_concurrent_cache_writes_do_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import concurrent.futures

        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        monkeypatch.setenv("C", "3")
        sp = SecretsProvider()

        def read(key: str) -> str | None:
            return sp.get(key)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(read, k) for k in ["A", "B", "C"] * 20]
            results = [f.result() for f in futures]

        assert results.count("1") == 20
        assert results.count("2") == 20
        assert results.count("3") == 20


# ======================================================================
# SecretsProvider — get_or_raise
# ======================================================================


class TestGetOrRaise:
    def test_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REQUIRED", "present")
        sp = SecretsProvider()
        assert sp.get_or_raise("REQUIRED") == "present"

    def test_raises_SecretsError_when_missing(self) -> None:
        sp = SecretsProvider()
        with pytest.raises(SecretsError, match="REQUIRED_MISSING"):
            sp.get_or_raise("REQUIRED_MISSING")

    def test_raises_from_backend_miss(self) -> None:
        sp = SecretsProvider(backend=DictBackend({}))
        with pytest.raises(SecretsError, match="NOT_THERE"):
            sp.get_or_raise("NOT_THERE")

    def test_no_cache_parameter_passed_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RENEW", "old")
        sp = SecretsProvider()
        assert sp.get_or_raise("RENEW") == "old"
        monkeypatch.setenv("RENEW", "new")
        assert sp.get_or_raise("RENEW", no_cache=True) == "new"


# ======================================================================
# Singleton
# ======================================================================


class TestSingleton:
    def test_instance_is_singleton(self) -> None:
        i1 = SecretsProvider.instance()
        i2 = SecretsProvider.instance()
        assert i1 is i2

    def test_set_instance_overrides(self) -> None:
        original = SecretsProvider.instance()
        custom = SecretsProvider(backend=DictBackend({"X": "y"}))
        SecretsProvider.set_instance(custom)
        assert SecretsProvider.instance() is custom
        assert SecretsProvider.instance() is not original
        assert SecretsProvider.instance().get("X") == "y"


# ======================================================================
# FileBackend
# ======================================================================


class TestFileBackend:
    def test_reads_key_value_lines(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text(
            "TOKEN=abc123\nAPI_KEY=xyz789\n", encoding="utf-8"
        )
        backend = FileBackend(secrets_file)
        assert backend.get("TOKEN") == "abc123"
        assert backend.get("API_KEY") == "xyz789"

    def test_ignores_comments_and_blanks(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text(
            "# this is a comment\n\nTOKEN=abc\n\n# another comment\nKEY=val\n",
            encoding="utf-8",
        )
        backend = FileBackend(secrets_file)
        assert backend.get("TOKEN") == "abc"
        assert backend.get("KEY") == "val"
        assert backend.get("NONEXISTENT") is None

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("  TOKEN  =  abc  \n", encoding="utf-8")
        backend = FileBackend(secrets_file)
        assert backend.get("TOKEN") == "abc"

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        backend = FileBackend(tmp_path / "does_not_exist.env")
        assert backend.get("ANYTHING") is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("", encoding="utf-8")
        backend = FileBackend(secrets_file)
        assert backend.get("ANYTHING") is None

    def test_loads_only_once(self, tmp_path: Path) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("KEY=first", encoding="utf-8")
        backend = FileBackend(secrets_file)
        assert backend.get("KEY") == "first"
        # Change file on disk — should NOT be re-read
        secrets_file.write_text("KEY=second", encoding="utf-8")
        assert backend.get("KEY") == "first"

    def test_skips_malformed_lines(self, tmp_path: Path, caplog) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text(
            "GOOD=yes\nno-equal-sign\nALSO_GOOD=ok\n", encoding="utf-8"
        )
        backend = FileBackend(secrets_file)
        assert backend.get("GOOD") == "yes"
        assert backend.get("no-equal-sign") is None
        assert backend.get("ALSO_GOOD") == "ok"
        # Check warning was logged
        assert any("malformed" in record.message for record in caplog.records)


# ======================================================================
# Integration — SecretsProvider with FileBackend
# ======================================================================


class TestIntegration:
    def test_env_takes_priority_over_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHARED", "env-value")
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("SHARED=file-value\n", encoding="utf-8")
        sp = SecretsProvider(backend=FileBackend(secrets_file))
        assert sp.get("SHARED") == "env-value"

    def test_file_backend_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FILE_ONLY", raising=False)
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("FILE_ONLY=from-file\n", encoding="utf-8")
        sp = SecretsProvider(backend=FileBackend(secrets_file))
        assert sp.get("FILE_ONLY") == "from-file"

    def test_get_or_raise_with_file_backend(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FROM_FILE", raising=False)
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("FROM_FILE=yes\n", encoding="utf-8")
        sp = SecretsProvider(backend=FileBackend(secrets_file))
        assert sp.get_or_raise("FROM_FILE") == "yes"

    def test_get_or_raise_missing_with_file_backend(
        self, tmp_path: Path
    ) -> None:
        secrets_file = tmp_path / ".env"
        secrets_file.write_text("EXISTS=1\n", encoding="utf-8")
        sp = SecretsProvider(backend=FileBackend(secrets_file))
        with pytest.raises(SecretsError, match="MISSING"):
            sp.get_or_raise("MISSING")
