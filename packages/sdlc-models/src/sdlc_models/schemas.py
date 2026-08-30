"""Phase output schemas and code-index models for the SDLC pipeline.

Merges from:
- Helix/foundry/sdlc/models.py  (CodeSymbol, SymbolKind, ImportInfo, FileIndex, DependencyGraph, ContextChunk, WriteOp)
- Ai-Agent-Server/latest/src/schemas.py  (SpecOutput, PlanOutput, CodingOutput, ReviewOutput, DoneOutput, ReviewDecision)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from sdlc_models.judge import ReviewDecision


# ---------------------------------------------------------------------------
# Phase output schemas (from Ai-Agent-Server schemas.py)
# ---------------------------------------------------------------------------


class SpecOutput(BaseModel):
    """Output from the Specs phase: requirements, constraints, criteria."""

    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    """Output from the Planning phase: plan items and risk assessment."""

    plan: list[str] = Field(default_factory=list)
    decomposition: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CodingOutput(BaseModel):
    """Output from the Coding phase: produced files and status."""

    files: list[str] = Field(default_factory=list)
    status: str = "ok"
    reason: str = ""
    failure_class: str = "none"


class ReviewOutput(BaseModel):
    """Output from the Review phase: decision and findings."""

    decision: ReviewDecision
    findings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_notes: list[str] = Field(default_factory=list)


class DoneOutput(BaseModel):
    """Output from the Done phase: final summary."""

    summary: str


# ---------------------------------------------------------------------------
# Code-index models (from Helix models.py)
# ---------------------------------------------------------------------------


class SymbolKind(StrEnum):
    """Kinds of symbols tracked in the code index."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    IMPORT = "import"
    INTERFACE = "interface"
    TYPE_ALIAS = "type_alias"
    UNKNOWN = "unknown"


class CodeSymbol(BaseModel):
    """A single symbol extracted from source code."""

    name: str
    kind: SymbolKind = SymbolKind.UNKNOWN
    file_path: str
    start_line: int = 0
    end_line: int = 0
    parent: str | None = None
    docstring: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportInfo(BaseModel):
    """A single import statement extracted from source code."""

    source: str
    alias: str | None = None
    file_path: str
    line: int = 0
    is_relative: bool = False


class FileIndex(BaseModel):
    """Index entry for one file in the code graph."""

    path: str
    language: str = "unknown"
    symbols: list[CodeSymbol] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    mtime: float = 0.0
    sha256: str = ""
    size_bytes: int = 0
    indexed_at: str = ""


class DependencyGraph(BaseModel):
    """Full dependency graph across indexed files."""

    files: dict[str, FileIndex] = Field(default_factory=dict)
    import_edges: dict[str, list[str]] = Field(default_factory=dict)
    dependents: dict[str, list[str]] = Field(default_factory=dict)
    indexed_at: str = ""
    file_count: int = 0
    symbol_count: int = 0


class ContextChunk(BaseModel):
    """A relevant code chunk retrieved for an agent's context."""

    file_path: str
    language: str = "unknown"
    content: str
    start_line: int = 0
    end_line: int = 0
    symbol_name: str | None = None
    symbol_kind: str | None = None
    relevance_score: float = 0.0


class WriteOp(BaseModel):
    """A single write operation to be applied to a file."""

    target: str
    action: str
    payload: dict[str, Any]
    source_span: str | None = None


__all__ = [
    "SpecOutput",
    "PlanOutput",
    "CodingOutput",
    "ReviewOutput",
    "DoneOutput",
    "SymbolKind",
    "CodeSymbol",
    "ImportInfo",
    "FileIndex",
    "DependencyGraph",
    "ContextChunk",
    "WriteOp",
]

def message_content_to_text(content: str | list[dict[str, object]] | None) -> str:
    """Convert OpenAI-style message content (string or list of parts) to plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
            continue
        input_text = item.get("input_text")
        if isinstance(input_text, str):
            parts.append(input_text)
            continue
        nested = item.get("content")
        if isinstance(nested, str):
            parts.append(nested)
    return "\n".join(parts)
