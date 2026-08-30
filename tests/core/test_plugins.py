"""Unit tests for the Foundry plugin loader."""

from __future__ import annotations

import dataclasses
from unittest import mock

import pytest

from foundry.core.plugins import Plugin, PluginLoader


# ======================================================================
# Plugin model
# ======================================================================


class TestPluginModel:
    def test_frozen_dataclass(self) -> None:
        """Plugin instances should be immutable."""
        p = Plugin(name="x", version="1.0.0", entry_point="mod:fn", description="X")
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.name = "y"  # type: ignore[misc]

    def test_default_description_is_empty(self) -> None:
        """Description is passed through as provided."""
        p = Plugin(name="x", version="0.0.0", entry_point="mod:fn", description="")
        assert p.description == ""

    def test_repr(self) -> None:
        p = Plugin(name="x", version="1.0", entry_point="mod:fn", description="desc")
        r = repr(p)
        assert "Plugin(" in r
        assert "name=" in r
        assert "x" in r


# ======================================================================
# PluginLoader — discovery, loading, registration
# ======================================================================


class TestPluginLoader:
    """Uses mocked entry points to avoid depending on installed packages."""

    # ------------------------------------------------------------------
    # discover
    # ------------------------------------------------------------------

    def test_discover_empty_group(self) -> None:
        """Unknown groups return an empty list."""
        loader = PluginLoader()
        plugins = loader.discover("nonexistent.group")
        assert plugins == []

    def test_discover_returns_plugins(self) -> None:
        """Entry points under a group are converted to Plugin objects."""
        fake_ep = _make_ep("my_plugin", "pkg.mod:func", "1.2.3", "My plugin")

        with mock.patch(
            "importlib.metadata.entry_points", return_value=[fake_ep]
        ) as mock_eps:
            loader = PluginLoader()
            plugins = loader.discover("foundry.plugins")

        mock_eps.assert_called_once_with(group="foundry.plugins")
        assert len(plugins) == 1
        assert plugins[0].name == "my_plugin"
        assert plugins[0].version == "1.2.3"
        assert plugins[0].entry_point == "pkg.mod:func"
        assert plugins[0].description == "My plugin"

    def test_discover_includes_registered_plugins(self) -> None:
        """Plugins added via register() appear in discover() output."""
        loader = PluginLoader()
        loader.register("prog_plug", "pkg:fn")

        with mock.patch("importlib.metadata.entry_points", return_value=[]):
            plugins = loader.discover("foundry.plugins")

        names = {p.name for p in plugins}
        assert "prog_plug" in names
        prog = next(p for p in plugins if p.name == "prog_plug")
        assert prog.entry_point == "pkg:fn"
        assert prog.version == "0.0.0"

    def test_discover_deduplicates_registered(self) -> None:
        """If a package already provides an entry point, the registered
        version does not create a duplicate."""
        fake_ep = _make_ep("my_plugin", "other.mod:fn", "1.0.0", "")

        loader = PluginLoader()
        loader.register("my_plugin", "other:fn")  # same name, different target

        with mock.patch(
            "importlib.metadata.entry_points", return_value=[fake_ep]
        ):
            plugins = loader.discover("foundry.plugins")

        # The package version wins (entry_points iterated first).
        assert len(plugins) == 1
        assert plugins[0].version == "1.0.0"

    # ------------------------------------------------------------------
    # load
    # ------------------------------------------------------------------

    def test_load_registered_plugin(self) -> None:
        """Loading a programmatically registered plugin imports and returns
        the target."""
        loader = PluginLoader()
        loader.register("dummy", "foundry.core.plugins.models:Plugin")

        result = loader.load("dummy")
        assert result is Plugin

    def test_load_registered_module_only(self) -> None:
        """Entry points without ``:attr`` import the module itself."""
        loader = PluginLoader()
        loader.register("modonly", "foundry.core.plugins.models")

        result = loader.load("modonly")
        assert result.__name__ == "foundry.core.plugins.models"

    def test_load_via_entry_point(self) -> None:
        """Loading via a discovered entry point calls ep.load()."""
        fake_ep = _make_ep(
            "target_plug", "foundry.core.plugins.models:Plugin", "1.0.0", ""
        )

        with mock.patch(
            "importlib.metadata.entry_points", return_value=[fake_ep]
        ):
            loader = PluginLoader()
            result = loader.load("target_plug")

        assert result is Plugin

    def test_load_raises_lookuperror_for_unknown(self) -> None:
        """An unknown plugin name raises LookupError."""
        loader = PluginLoader()
        with pytest.raises(LookupError, match="Plugin not found"):
            loader.load("does_not_exist")

    # ------------------------------------------------------------------
    # register
    # ------------------------------------------------------------------

    def test_register_stores_entry_point(self) -> None:
        """register() stores the mapping for later discovery/loading."""
        loader = PluginLoader()
        loader.register("plug_a", "some.mod:func")
        assert loader._registered["plug_a"] == "some.mod:func"

    def test_register_overwrites_existing(self) -> None:
        """Re-registering the same name overwrites the old entry point."""
        loader = PluginLoader()
        loader.register("plug_a", "first:fn")
        loader.register("plug_a", "second:fn")
        assert loader._registered["plug_a"] == "second:fn"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_discover_multiple_plugins(self) -> None:
        """Multiple entry points in a group are all returned."""
        eps = [
            _make_ep("a", "pkg.a:fn", "1.0.0", "A"),
            _make_ep("b", "pkg.b:fn", "1.0.0", "B"),
        ]
        loader = PluginLoader()
        with mock.patch("importlib.metadata.entry_points", return_value=eps):
            plugins = loader.discover("foundry.plugins")
        assert len(plugins) == 2
        assert {p.name for p in plugins} == {"a", "b"}

    def test_load_does_not_cache(self) -> None:
        """Each load() call imports fresh (no caching)."""
        loader = PluginLoader()
        loader.register("models", "foundry.core.plugins.models")
        r1 = loader.load("models")
        r2 = loader.load("models")
        assert r1 is r2  # same module object (Python caches imports)

    def test_discover_with_no_dist(self) -> None:
        """Plugin converts dist-less entry points gracefully."""
        ep = mock.MagicMock(spec=["name", "value", "dist", "group"])
        ep.name = "nodist"
        ep.value = "pkg:fn"
        ep.dist = None

        loader = PluginLoader()
        with mock.patch("importlib.metadata.entry_points", return_value=[ep]):
            plugins = loader.discover("g")
        assert plugins[0].version == "0.0.0"
        assert plugins[0].description == ""


# ======================================================================
# Helpers
# ======================================================================


def _make_ep(
    name: str,
    value: str,
    version: str,
    summary: str,
) -> mock.MagicMock:
    """Build a mock ``importlib.metadata.EntryPoint``-like object.

    ``ep.load`` is set as a MagicMock with a lazy ``side_effect`` so that
    tests that never call ``load()`` can use non-importable values without
    raising at fixture-creation time.
    """
    dist = mock.MagicMock()
    dist.version = version
    dist.metadata = {"Summary": summary}

    ep = mock.MagicMock(spec=["name", "value", "dist", "group", "load"])
    ep.name = name
    ep.value = value
    ep.dist = dist
    ep.group = "foundry.plugins"

    # Defer the actual import to call time.
    ep.load = mock.MagicMock(
        side_effect=lambda: _resolve_entry_point(value)
    )

    return ep


def _resolve_entry_point(value: str):
    """Resolve an entry-point string to its actual object.

    Supports ``"module"`` and ``"module:attr"`` forms.
    """
    mod_name, _, attr = value.partition(":")
    mod = __import__(mod_name, fromlist=[attr] if attr else [])
    return getattr(mod, attr) if attr else mod
