"""AuthManager for lightweight API-key authentication.

Key lifecycle:
  1.  create_key(role)  -- generates a ``fndr_``-prefixed key, stores its
      HMAC-SHA256 digest, and returns the plaintext key (shown once).
  2.  validate_key(key) -- constant-time HMAC comparison against stored
      digests; returns the role string on match, *None* otherwise.
  3.  revoke_key(prefix) -- removes any key whose stored prefix matches.
  4.  list_keys()       -- returns metadata for every active key (no
      plaintext secrets are ever exposed).

Key format
----------
``fndr_<base64-url-43-chars>``

The first 20 characters (``fndr_`` + 15 base64 chars) serve as the
**prefix** used for listing and revocation.  The full key is never
stored in plaintext.

Storage
-------
A ``keys.json`` file is written to ``foundry/core/secrets/`` (or an
explicit path).  Each entry contains the prefix (plaintext), an
HMAC-SHA256 digest of the full key, the assigned role, and a UTC
ISO-8601 creation timestamp.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_KEY_PREFIX = "fndr_"                     # visible prefix on every key
_KEY_BYTES = 32                           # 256 bits of entropy
_PREFIX_LEN = 20                          # "fndr_" + 15 chars for lookup
_HMAC_LABEL = b"foundry-api-key-hmac-v1"  # app-specific HMAC key material

_VALID_ROLES = ("operator", "viewer")

_DEFAULT_SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"
_KEYS_FILENAME = "keys.json"


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """Manage API key registration, validation, and revocation.

    Parameters
    ----------
    secrets_dir : str or Path, optional
        Directory that holds (or will hold) ``keys.json``.
        Defaults to ``foundry/core/secrets/``.
    """

    def __init__(self, secrets_dir: Optional[str | Path] = None) -> None:
        self._secrets_dir = Path(secrets_dir) if secrets_dir else _DEFAULT_SECRETS_DIR
        self._secrets_dir.mkdir(parents=True, exist_ok=True)
        self._keys_file = self._secrets_dir / _KEYS_FILENAME
        self._keys: List[dict] = []
        self._load()

    # -- public API ---------------------------------------------------------

    def create_key(self, role: str = "operator") -> str:
        """Generate a new API key and persist it.

        Parameters
        ----------
        role : str
            One of ``"operator"`` (default, all actions) or
            ``"viewer"`` (read-only dashboard).

        Returns
        -------
        str
            The full plaintext API key.  This is the **only** time the
            plaintext is available; it is not stored.
        """
        if role not in _VALID_ROLES:
            raise ValueError(
                f"Invalid role {role!r}.  Must be one of {_VALID_ROLES}"
            )

        raw = secrets.token_urlsafe(_KEY_BYTES)
        full_key = f"{_KEY_PREFIX}{raw}"
        prefix = full_key[:_PREFIX_LEN]
        digest = _hmac(full_key)

        self._keys.append({
            "prefix": prefix,
            "digest": digest,
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()
        return full_key

    def validate_key(self, key: str) -> Optional[str]:
        """Return the role of *key* if it matches a stored digest.

        Performs a constant-time HMAC comparison so that timing does not
        leak information about stored digests.

        Returns
        -------
        str or None
            ``"operator"``, ``"viewer"``, or *None* if no match.
        """
        if not isinstance(key, str) or not key.startswith(_KEY_PREFIX):
            return None
        digest = _hmac(key)
        for entry in self._keys:
            if hmac.compare_digest(entry["digest"], digest):
                return entry["role"]
        return None

    def revoke_key(self, key_prefix: str) -> None:
        """Remove the key whose stored prefix matches *key_prefix*.

        Parameters
        ----------
        key_prefix : str
            The 20-character prefix (e.g. ``fndr_AbCdEfGhIjKlM``)
            returned by :meth:`list_keys`.
        """
        self._keys = [k for k in self._keys if k["prefix"] != key_prefix]
        self._save()

    def list_keys(self) -> List[dict]:
        """Return metadata for every active key.

        Returns
        -------
        list[dict]
            Each dict contains ``prefix``, ``role``, and ``created_at``.
            **No plaintext secrets are exposed.**
        """
        return [
            {"prefix": k["prefix"], "role": k["role"],
             "created_at": k["created_at"]}
            for k in self._keys
        ]

    # -- internal helpers ---------------------------------------------------

    def _load(self) -> None:
        if self._keys_file.exists():
            raw = self._keys_file.read_text(encoding="utf-8")
            self._keys = json.loads(raw)
        else:
            self._keys = []

    def _save(self) -> None:
        self._keys_file.write_text(
            json.dumps(self._keys, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _hmac(value: str) -> str:
    """Return the hex-encoded HMAC-SHA256 of *value*."""
    return hmac.new(_HMAC_LABEL, value.encode(), hashlib.sha256).hexdigest()
