"""SecretsProvider — resolve credentials from env, file, or keychain."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, Optional, Protocol

from foundry.core.exceptions import SecretsError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pluggable backend protocol
# ---------------------------------------------------------------------------


class SecretBackend(Protocol):
    """Optional interface for file / keychain credential backends."""

    def get(self, key: str) -> str | None:
        """Return the secret for *key*, or *None* if not found."""
        ...


# ---------------------------------------------------------------------------
# Built-in file-based backend (one of the optional backends)
# ---------------------------------------------------------------------------


class FileBackend:
    """Reads secrets from ``key=value`` lines in a file.

    Expects a simple ``KEY=VALUE`` format, one per line.  Blank lines and
    lines starting with ``#`` are ignored.  Values are **not** shell-quoted;
    everything after the first ``=`` is taken verbatim (leading/trailing
    whitespace is stripped from both key and value).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._cache: Dict[str, str] = {}
        self._loaded = False
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        if not self._loaded:
            self._load()
        return self._cache.get(key)

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            if not self._path.is_file():
                logger.debug("Secrets file not found: %s", self._path)
                self._loaded = True
                return
            raw = self._path.read_text(encoding="utf-8")
            for lineno, line in enumerate(raw.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if "=" not in stripped:
                    logger.warning(
                        "Skipping malformed line %d in %s: %r",
                        lineno,
                        self._path,
                        stripped,
                    )
                    continue
                k, _, v = stripped.partition("=")
                self._cache[k.strip()] = v.strip()
            self._loaded = True
            logger.debug("Loaded %d secrets from %s", len(self._cache), self._path)


_DO_NOT_CACHE: set[str] = set()


# ---------------------------------------------------------------------------
# Singleton provider
# ---------------------------------------------------------------------------

_INSTANCE: SecretsProvider | None = None


class SecretsProvider:
    """Process-wide credential resolver with in-memory caching.

    Resolution order (first match wins):

    1. Environment variable (``os.environ[key]``).
    2. Optional file / keychain backend resolved at construction time.

    Secrets are cached in memory for the lifetime of the process.  The cache
    can be bypassed per-key via *no_cache*.
    """

    def __init__(
        self,
        backend: SecretBackend | None = None,
    ) -> None:
        self._backend = backend
        self._cache: Dict[str, str] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, *, no_cache: bool = False) -> str | None:
        """Look up *key*.

        Returns the value or *None* if the key is not found in any source.
        """
        # 1. In-memory cache (unless bypassed)
        if not no_cache:
            cached = self._from_cache(key)
            if cached is not None:
                return cached

        # 2. Environment variable
        value = os.environ.get(key)
        if value is not None:
            self._set_cache(key, value)
            return value

        # 3. Optional backend
        if self._backend is not None:
            value = self._backend.get(key)
            if value is not None:
                self._set_cache(key, value)
                return value

        return None

    def get_or_raise(self, key: str, *, no_cache: bool = False) -> str:
        """Like :meth:`get` but raises :class:`SecretsError` on miss."""
        value = self.get(key, no_cache=no_cache)
        if value is None:
            raise SecretsError(
                f"Required secret {key!r} is not set. "
                f"Set the {key} environment variable or configure a backend."
            )
        return value

    # ------------------------------------------------------------------
    # Cache internals
    # ------------------------------------------------------------------

    def _from_cache(self, key: str) -> str | None:
        return self._cache.get(key)

    def _set_cache(self, key: str, value: str) -> None:
        with self._lock:
            self._cache[key] = value

    # ------------------------------------------------------------------
    # Global singleton access
    # ------------------------------------------------------------------

    @staticmethod
    def instance() -> SecretsProvider:
        """Return the process-global :class:`SecretsProvider`.

        Lazy-initialised with no backend (env-var only).
        """
        global _INSTANCE
        if _INSTANCE is None:
            _INSTANCE = SecretsProvider()
        return _INSTANCE

    @staticmethod
    def set_instance(provider: SecretsProvider) -> None:
        """Override the global singleton (useful in tests)."""
        global _INSTANCE
        _INSTANCE = provider
