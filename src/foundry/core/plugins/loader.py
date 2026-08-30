"""Entry-point extension loader backed by ``importlib.metadata``.

A :class:`PluginLoader` discovers plugins registered as package entry points
(see ``pyproject.toml [project.entry-points]`` or ``setup.cfg [options.entry_points]``)
and also supports ad-hoc programmatic registration for testing and runtime use.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from typing import Any

from foundry.core.plugins.models import Plugin


class PluginLoader:
    """Discovers, loads, and registers plugins via importlib entry points."""

    def __init__(self) -> None:
        #: name -> entry-point string (e.g. ``"mypkg.mymod:func"``)
        self._registered: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, group: str) -> list[Plugin]:
        """Return every :class:`Plugin` registered under *group*.

        This inspects installed packages that declare an entry-point group
        matching *group* and also includes any plugins previously added via
        :meth:`register`.
        """
        entries: list[Plugin] = []

        for ep in importlib.metadata.entry_points(group=group):
            entries.append(self._ep_to_plugin(ep))

        # Merge programmatic registrations (skip duplicates from real packages).
        known_names = {p.name for p in entries}
        for name, ep_str in self._registered.items():
            if name not in known_names:
                entries.append(
                    Plugin(
                        name=name,
                        version="0.0.0",
                        entry_point=ep_str,
                        description="",
                    )
                )

        return entries

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self, plugin_name: str) -> Any:
        """Import and return the module (or callable) behind *plugin_name*.

        Resolution order
        -----------------
        1. Programmatic registrations (:meth:`register`).
        2. Installed entry points across **all** groups.

        Raises :class:`LookupError` when *plugin_name* cannot be found.
        """
        # 1. Check programmatic registrations.
        if plugin_name in self._registered:
            ep_str = self._registered[plugin_name]
            return self._import_entry_point(ep_str)

        # 2. Search every installed entry point by name.
        all_eps = importlib.metadata.entry_points()
        # Python 3.9–3.11 returns a dict-of-groups; 3.12+ returns a flat list.
        if isinstance(all_eps, dict):
            iterable: list = sum(all_eps.values(), [])  # type: ignore[assignment]
        else:
            iterable = all_eps  # type: ignore[assignment]

        for ep in iterable:
            if ep.name == plugin_name:
                return ep.load()

        raise LookupError(f"Plugin not found: {plugin_name!r}")

    # ------------------------------------------------------------------
    # Programmatic registration
    # ------------------------------------------------------------------

    def register(self, name: str, entry_point: str) -> None:
        """Register a plugin by *name* with its *entry_point* string.

        ``entry_point`` should be a standard dotted import path,
        e.g. ``"foundry.core.plugins.loader:PluginLoader"``.
        """
        self._registered[name] = entry_point

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ep_to_plugin(ep: importlib.metadata.EntryPoint) -> Plugin:
        """Convert an ``importlib.metadata.EntryPoint`` to a :class:`Plugin`."""
        return Plugin(
            name=ep.name,
            version=ep.dist.version if ep.dist else "0.0.0",
            entry_point=ep.value,
            description=ep.dist.metadata.get("Summary", "") if ep.dist else "",
        )

    @staticmethod
    def _import_entry_point(ep_str: str) -> Any:
        """Import and return the target of an entry-point string.

        Supports both ``"module"`` and ``"module:attr"`` forms.
        """
        module_name, _, attr = ep_str.partition(":")
        mod = importlib.import_module(module_name)
        return getattr(mod, attr) if attr else mod
