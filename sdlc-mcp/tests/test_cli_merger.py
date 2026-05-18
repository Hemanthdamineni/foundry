"""Tests for config merger and template system."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sdlc_mcp.cli.merger import deep_merge, merge_opencode_json


class TestDeepMerge:
    def test_scalar_override(self) -> None:
        base = {"a": 1}
        result = deep_merge(base, {"a": 2})
        assert result["a"] == 2

    def test_nested_dict_merge(self) -> None:
        base = {"a": {"b": 1, "c": 2}}
        deep_merge(base, {"a": {"b": 99, "d": 3}})
        assert base["a"] == {"b": 99, "c": 2, "d": 3}

    def test_list_append_no_dupes(self) -> None:
        base = {"items": [1, 2]}
        deep_merge(base, {"items": [2, 3]})
        assert base["items"] == [1, 2, 3]

    def test_list_append_dict_items(self) -> None:
        base = {"agent": [{"name": "foundry", "mode": "primary"}]}
        new = {"agent": [{"name": "reviewer", "mode": "secondary"}]}
        deep_merge(base, new)
        assert len(base["agent"]) == 2
        assert base["agent"][1]["name"] == "reviewer"

    def test_new_key_added(self) -> None:
        base = {"a": 1}
        deep_merge(base, {"b": 2})
        assert base == {"a": 1, "b": 2}

    def test_empty_overlay(self) -> None:
        base = {"a": 1}
        deep_merge(base, {})
        assert base == {"a": 1}

    def test_deep_nested(self) -> None:
        base = {"mcp": {"sdlc": {"command": ["foo"]}}}
        deep_merge(base, {"mcp": {"sdlc": {"enabled": True}}})
        assert base["mcp"]["sdlc"] == {"command": ["foo"], "enabled": True}


class TestMergeOpencodeJson:
    def test_creates_new_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            fragment = {"mcp": {"test": {"command": ["foo"]}}}
            changed = merge_opencode_json(target, fragment)
            assert changed is True
            assert target.exists()
            data = json.loads(target.read_text())
            assert data["mcp"]["test"]["command"] == ["foo"]

    def test_merges_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            target.write_text(json.dumps({"existing": True}))
            fragment = {"new_key": "value"}
            changed = merge_opencode_json(target, fragment)
            assert changed is True
            data = json.loads(target.read_text())
            assert data["existing"] is True
            assert data["new_key"] == "value"

    def test_no_change_when_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            fragment = {"key": "value"}
            target.write_text(json.dumps(fragment))
            changed = merge_opencode_json(target, {"key": "value"})
            assert changed is False

    def test_no_create_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            changed = merge_opencode_json(target, {"a": 1}, create_if_missing=False)
            assert changed is False
            assert not target.exists()

    def test_merge_mcp_server_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            fragment = {
                "mcp": {
                    "foundry-orchestrator": {
                        "type": "local",
                        "command": ["sdlc-mcp"],
                        "enabled": True,
                    },
                },
            }
            merge_opencode_json(target, fragment)
            data = json.loads(target.read_text())
            srv = data["mcp"]["foundry-orchestrator"]
            assert srv["command"] == ["sdlc-mcp"]

    def test_merge_preserves_user_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            target.write_text(json.dumps({"agent": {"user-agent": {"mode": "primary"}}}))
            fragment = {"agent": {"foundry": {"mode": "primary"}}}
            merge_opencode_json(target, fragment)
            data = json.loads(target.read_text())
            assert "user-agent" in data["agent"]
            assert "foundry" in data["agent"]

    def test_merge_adds_plugins_no_dupes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opencode.json"
            target.write_text(json.dumps({"plugins": ["plugin-a"]}))
            fragment = {"plugins": ["plugin-b"]}
            merge_opencode_json(target, fragment)
            data = json.loads(target.read_text())
            assert data["plugins"] == ["plugin-a", "plugin-b"]
