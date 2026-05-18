"""Safe config merger — merges into opencode.json without overwriting user config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *overlay* into *base* (mutates base). Lists are appended."""
    for key, val in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            deep_merge(base[key], val)
        elif key in base and isinstance(base[key], list) and isinstance(val, list):
            seen = {json.dumps(v, sort_keys=True) for v in base[key]}
            for item in val:
                key_repr = json.dumps(item, sort_keys=True)
                if key_repr not in seen:
                    base[key].append(item)
                    seen.add(key_repr)
        else:
            base[key] = val
    return base


def merge_opencode_json(
    target: Path,
    fragment: dict[str, Any],
    *,
    create_if_missing: bool = True,
) -> bool:
    """Merge *fragment* into *target* opencode.json.

    Returns True if the file was created or modified.
    """
    if target.exists():
        existing: dict[str, Any] = json.loads(target.read_text())
    elif create_if_missing:
        existing = {}
    else:
        return False

    before = json.dumps(existing, indent=2, sort_keys=True)
    deep_merge(existing, fragment)
    after = json.dumps(existing, indent=2, sort_keys=True)

    if before != after:
        target.write_text(after + "\n")
        return True
    return False


def merge_yaml_config(
    target: Path,
    fragment: dict[str, Any],
    *,
    create_if_missing: bool = True,
) -> bool:
    """Merge *fragment* into a YAML config file."""
    import yaml

    if target.exists():
        existing: dict[str, Any] = yaml.safe_load(target.read_text()) or {}
    elif create_if_missing:
        existing = {}
    else:
        return False

    before = yaml.dump(existing, default_flow_style=False, sort_keys=False)
    deep_merge(existing, fragment)
    after = yaml.dump(existing, default_flow_style=False, sort_keys=False)

    if before != after:
        target.write_text(after)
        return True
    return False
