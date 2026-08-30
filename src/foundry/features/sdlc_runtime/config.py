"""Backward-compat — delegate to canonical core configuration."""
from foundry.core.config.settings import Settings, settings

__all__ = ["Settings", "settings"]
