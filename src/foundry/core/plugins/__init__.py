"""Entry-point extension loader for the Foundry plugin system."""

from foundry.core.plugins.loader import PluginLoader
from foundry.core.plugins.models import Plugin

__all__ = [
    "Plugin",
    "PluginLoader",
]
