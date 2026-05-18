"""Prompt registry — versioned prompt management with hash tracking and rollback.

TODO #19: Every prompt has a content hash, version number, and compatibility record.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from sdlc.log import get_logger

logger = get_logger("engine.prompt_registry")


class PromptVersion(BaseModel):
    """A single version of a prompt template."""

    name: str
    version: int
    content: str
    content_hash: str
    created_at: str = ""
    deprecated: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptRegistry:
    """Versioned prompt management with hash-based dedup and rollback."""

    def __init__(self) -> None:
        self._registry: dict[str, list[PromptVersion]] = {}
        self._active: dict[str, int] = {}  # name → active version

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def register(self, name: str, content: str, **metadata: Any) -> PromptVersion:
        """Register a new prompt version (deduplicates by content hash)."""
        content_hash = self._hash(content)
        versions = self._registry.setdefault(name, [])

        # Check for duplicate content
        for v in versions:
            if v.content_hash == content_hash:
                return v  # Already registered

        version = len(versions) + 1
        pv = PromptVersion(
            name=name,
            version=version,
            content=content,
            content_hash=content_hash,
            created_at=datetime.now(UTC).isoformat(),
            metadata=metadata,
        )
        versions.append(pv)
        self._active[name] = version
        logger.info("Prompt registered", extra={"name": name, "version": version, "hash": content_hash})
        return pv

    def get(self, name: str, version: int | None = None) -> PromptVersion | None:
        """Get a specific version or the active version of a prompt."""
        versions = self._registry.get(name, [])
        if not versions:
            return None
        if version is None:
            version = self._active.get(name, len(versions))
        for v in versions:
            if v.version == version:
                return v
        return None

    def get_active(self, name: str) -> str:
        """Get the active prompt content."""
        pv = self.get(name)
        return pv.content if pv else ""

    def rollback(self, name: str, to_version: int) -> bool:
        """Rollback a prompt to a previous version."""
        versions = self._registry.get(name, [])
        if any(v.version == to_version for v in versions):
            self._active[name] = to_version
            logger.info("Prompt rolled back", extra={"name": name, "version": to_version})
            return True
        return False

    def list_versions(self, name: str) -> list[dict[str, Any]]:
        """List all versions of a prompt."""
        versions = self._registry.get(name, [])
        active = self._active.get(name, 0)
        return [
            {
                "version": v.version,
                "hash": v.content_hash,
                "created_at": v.created_at,
                "active": v.version == active,
                "deprecated": v.deprecated,
            }
            for v in versions
        ]

    def all_hashes(self) -> dict[str, str]:
        """Get the active content hash for every registered prompt."""
        result: dict[str, str] = {}
        for name in self._registry:
            pv = self.get(name)
            if pv:
                result[name] = pv.content_hash
        return result

    def load_from_dir(self, prompts_dir: str) -> int:
        """Load all .txt prompt files from a directory."""
        from pathlib import Path

        loaded = 0
        pdir = Path(prompts_dir)
        if not pdir.exists():
            return 0
        for f in sorted(pdir.iterdir()):
            if f.suffix == ".txt":
                content = f.read_text(encoding="utf-8")
                self.register(f.stem, content, source=str(f))
                loaded += 1
        return loaded

    def save_to_dir(self, prompts_dir: str) -> int:
        """Save all active prompts to a directory."""
        from pathlib import Path
        import json as _json

        pdir = Path(prompts_dir)
        pdir.mkdir(parents=True, exist_ok=True)
        saved = 0
        for name in self._registry:
            pv = self.get(name)
            if pv:
                (pdir / f"{name}.txt").write_text(pv.content, encoding="utf-8")
                saved += 1
        # Write manifest
        manifest = {
            name: {"version": self._active.get(name, 0), "hash": pv.content_hash}
            for name in self._registry
            if (pv := self.get(name)) is not None
        }
        (pdir / "manifest.json").write_text(
            _json.dumps(manifest, indent=2), encoding="utf-8",
        )
        return saved


# ── Prompt Compatibility Manager ─────────────────────────────────────


class PromptCompatibility(BaseModel):
    """Compatibility record between a prompt and a specific model/phase."""

    prompt_name: str
    prompt_hash: str
    model: str
    phase: str
    compatible: bool = True
    tested_at: str = ""
    notes: str = ""


class PromptCompatibilityManager:
    """Validates prompt sets work together and detects stale prompts.

    Tracks which prompt versions have been tested with which models,
    and flags incompatibilities when prompts or models change.
    """

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry
        self._compat_records: list[PromptCompatibility] = []
        self._model_prompt_map: dict[str, dict[str, str]] = {}  # model → {prompt_name: hash}

    def record_compatibility(
        self,
        prompt_name: str,
        model: str,
        phase: str,
        *,
        compatible: bool = True,
        notes: str = "",
    ) -> PromptCompatibility:
        """Record that a prompt+model combination has been tested."""
        pv = self._registry.get(prompt_name)
        prompt_hash = pv.content_hash if pv else "unknown"

        record = PromptCompatibility(
            prompt_name=prompt_name,
            prompt_hash=prompt_hash,
            model=model,
            phase=phase,
            compatible=compatible,
            tested_at=datetime.now(UTC).isoformat(),
            notes=notes,
        )
        self._compat_records.append(record)

        # Update model→prompt mapping
        model_map = self._model_prompt_map.setdefault(model, {})
        model_map[prompt_name] = prompt_hash

        return record

    def check_compatibility(
        self,
        prompt_name: str,
        model: str,
    ) -> dict[str, Any]:
        """Check if a prompt is compatible with a model."""
        pv = self._registry.get(prompt_name)
        if pv is None:
            return {"status": "unknown", "reason": "Prompt not found"}

        # Check if this exact hash has been tested with this model
        for rec in reversed(self._compat_records):
            if (
                rec.prompt_name == prompt_name
                and rec.model == model
                and rec.prompt_hash == pv.content_hash
            ):
                return {
                    "status": "tested",
                    "compatible": rec.compatible,
                    "tested_at": rec.tested_at,
                    "notes": rec.notes,
                }

        # Check if a different version was tested
        for rec in reversed(self._compat_records):
            if rec.prompt_name == prompt_name and rec.model == model:
                return {
                    "status": "stale",
                    "reason": f"Prompt hash changed: {rec.prompt_hash} → {pv.content_hash}",
                    "last_tested_hash": rec.prompt_hash,
                    "current_hash": pv.content_hash,
                }

        return {"status": "untested", "reason": "No compatibility data"}

    def validate_prompt_set(
        self,
        prompt_names: list[str],
        model: str,
    ) -> dict[str, Any]:
        """Validate that a set of prompts is compatible with a model."""
        results: dict[str, dict[str, Any]] = {}
        all_compatible = True
        stale_count = 0
        untested_count = 0

        for name in prompt_names:
            check = self.check_compatibility(name, model)
            results[name] = check
            if check.get("status") == "stale":
                stale_count += 1
            elif check.get("status") == "untested":
                untested_count += 1
            elif not check.get("compatible", True):
                all_compatible = False

        return {
            "model": model,
            "all_compatible": all_compatible,
            "stale_count": stale_count,
            "untested_count": untested_count,
            "details": results,
        }

    def detect_stale_prompts(self) -> list[dict[str, Any]]:
        """Find prompts whose active version differs from last-tested version."""
        stale: list[dict[str, Any]] = []
        for model, prompt_map in self._model_prompt_map.items():
            for prompt_name, tested_hash in prompt_map.items():
                pv = self._registry.get(prompt_name)
                if pv and pv.content_hash != tested_hash:
                    stale.append({
                        "prompt": prompt_name,
                        "model": model,
                        "tested_hash": tested_hash,
                        "current_hash": pv.content_hash,
                    })
        return stale

