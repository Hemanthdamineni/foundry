"""Plugin data model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plugin:
    """Descriptor for a discovered or programmatically registered plugin.

    Attributes:
        name: Unique plugin identifier.
        version: Semantic version string from the distribution, or ``"0.0.0"``.
        entry_point: Dotted import path (e.g. ``"package.module:attr"``).
        description: One-line summary from the package metadata.
    """

    name: str
    version: str
    entry_point: str
    description: str
