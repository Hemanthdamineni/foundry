"""API-key authentication for Foundry.

Provides a lightweight, no-dependency auth system using HMAC-salted
API keys stored on disk.  Designed for local / self-hosted tools.
"""

from foundry.core.auth.keys import AuthManager

__all__ = ["AuthManager"]
