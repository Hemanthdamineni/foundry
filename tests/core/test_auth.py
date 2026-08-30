"""Unit tests for foundry.core.auth — API-key authentication."""

from __future__ import annotations

import json
import pytest

from pathlib import Path
from foundry.core.auth import AuthManager


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def auth(tmp_path: Path) -> AuthManager:
    """AuthManager backed by a temporary directory (no side effects)."""
    return AuthManager(secrets_dir=tmp_path)


# =========================================================================
# create_key
# =========================================================================

class TestCreateKey:
    def test_returns_string_starting_with_fndr(self, auth: AuthManager) -> None:
        key = auth.create_key()
        assert isinstance(key, str)
        assert key.startswith("fndr_")

    def test_default_role_is_operator(self, auth: AuthManager) -> None:
        key = auth.create_key()
        assert auth.validate_key(key) == "operator"

    def test_explicit_operator_role(self, auth: AuthManager) -> None:
        key = auth.create_key(role="operator")
        assert auth.validate_key(key) == "operator"

    def test_viewer_role(self, auth: AuthManager) -> None:
        key = auth.create_key(role="viewer")
        assert auth.validate_key(key) == "viewer"

    def test_invalid_role_raises(self, auth: AuthManager) -> None:
        with pytest.raises(ValueError, match="Invalid role"):
            auth.create_key(role="admin")

    def test_unique_each_time(self, auth: AuthManager) -> None:
        k1 = auth.create_key()
        k2 = auth.create_key()
        assert k1 != k2

    def test_key_not_stored_in_plaintext(self, auth: AuthManager, tmp_path: Path) -> None:
        key = auth.create_key()
        secrets_file = tmp_path / "keys.json"
        raw = secrets_file.read_text(encoding="utf-8")
        # The plaintext key must never appear in the store
        assert key not in raw


# =========================================================================
# validate_key
# =========================================================================

class TestValidateKey:
    def test_valid_key_returns_role(self, auth: AuthManager) -> None:
        key = auth.create_key(role="operator")
        assert auth.validate_key(key) == "operator"

    def test_valid_viewer_key(self, auth: AuthManager) -> None:
        key = auth.create_key(role="viewer")
        assert auth.validate_key(key) == "viewer"

    def test_invalid_key_returns_none(self, auth: AuthManager) -> None:
        auth.create_key()
        assert auth.validate_key("fndr_not-a-real-key-xxxxxxxxxxx") is None

    def test_non_string_returns_none(self, auth: AuthManager) -> None:
        assert auth.validate_key(None) is None          # type: ignore[arg-type]
        assert auth.validate_key(12345) is None          # type: ignore[arg-type]

    def test_empty_string_returns_none(self, auth: AuthManager) -> None:
        assert auth.validate_key("") is None

    def test_wrong_prefix_returns_none(self, auth: AuthManager) -> None:
        key = "sk_" + secrets_token_example()
        assert auth.validate_key(key) is None

    def test_revoked_key_returns_none(self, auth: AuthManager) -> None:
        key = auth.create_key()
        prefix = key[:20]
        auth.revoke_key(prefix)
        assert auth.validate_key(key) is None


# =========================================================================
# revoke_key
# =========================================================================

class TestRevokeKey:
    def test_removes_correct_key(self, auth: AuthManager) -> None:
        k1 = auth.create_key()
        k2 = auth.create_key()
        p1 = k1[:20]
        auth.revoke_key(p1)
        assert auth.validate_key(k1) is None
        assert auth.validate_key(k2) is not None

    def test_revoke_nonexistent_prefix_is_safe(self, auth: AuthManager) -> None:
        auth.create_key()
        auth.revoke_key("fndr_nonexistentprefix")
        # no crash — remaining keys unchanged
        assert len(auth.list_keys()) == 1


# =========================================================================
# list_keys
# =========================================================================

class TestListKeys:
    def test_empty_when_no_keys(self, auth: AuthManager) -> None:
        assert auth.list_keys() == []

    def test_returns_correct_count(self, auth: AuthManager) -> None:
        auth.create_key()
        auth.create_key(role="viewer")
        assert len(auth.list_keys()) == 2

    def test_entries_have_expected_keys(self, auth: AuthManager) -> None:
        key = auth.create_key(role="viewer")
        entries = auth.list_keys()
        entry = entries[0]
        assert set(entry.keys()) == {"prefix", "role", "created_at"}
        assert entry["prefix"] == key[:20]
        assert entry["role"] == "viewer"

    def test_never_exposes_full_key(self, auth: AuthManager) -> None:
        key = auth.create_key()
        entries = auth.list_keys()
        for entry in entries:
            assert key not in entry.values()

    def test_after_revoke_list_is_empty(self, auth: AuthManager) -> None:
        key = auth.create_key()
        prefix = key[:20]
        auth.revoke_key(prefix)
        assert auth.list_keys() == []


# =========================================================================
# Persistence
# =========================================================================

class TestPersistence:
    def test_keys_survive_manager_reload(self, tmp_path: Path) -> None:
        a1 = AuthManager(secrets_dir=tmp_path)
        k1 = a1.create_key(role="viewer")
        k2 = a1.create_key(role="operator")

        # Recreate — reads from the same file on disk
        a2 = AuthManager(secrets_dir=tmp_path)
        assert a2.validate_key(k1) == "viewer"
        assert a2.validate_key(k2) == "operator"
        assert len(a2.list_keys()) == 2

    def test_revoke_persists_across_reload(self, tmp_path: Path) -> None:
        a1 = AuthManager(secrets_dir=tmp_path)
        key = a1.create_key()
        prefix = key[:20]
        a1.revoke_key(prefix)

        a2 = AuthManager(secrets_dir=tmp_path)
        assert a2.validate_key(key) is None
        assert a2.list_keys() == []

    def test_keys_file_is_valid_json(self, auth: AuthManager, tmp_path: Path) -> None:
        auth.create_key()
        auth.create_key(role="viewer")
        raw = (tmp_path / "keys.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, list)
        assert len(data) == 2


# =========================================================================
# Helpers
# =========================================================================

def secrets_token_example() -> str:
    """Return a plausible-looking key body for testing."""
    import secrets
    return secrets.token_urlsafe(32)
