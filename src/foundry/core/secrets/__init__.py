"""Secrets management for Foundry.

Provides a :class:`SecretsProvider` that resolves credentials from
environment variables first, then from a pluggable file / keychain
backend, with an in-memory cache for the process lifetime.
"""

from foundry.core.secrets.provider import SecretsProvider

__all__ = [
    "SecretsProvider",
]
