"""Core logger helpers."""

from __future__ import annotations

import logging


def get_logger(name: str, namespace: str = "foundry") -> logging.Logger:
    """Return a child logger of the *namespace* hierarchy.

    Args:
        name:       Dot-delimited sub-name (e.g. ``"engine.debate_runtime"``).
        namespace:  Root logger name (default ``"foundry"``).

    Returns:
        ``logging.getLogger(f"{namespace}.{name}")``
    """
    return logging.getLogger(f"{namespace}.{name}")
