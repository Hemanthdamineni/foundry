from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sdlc.adapters.base import ToolAdapter, ToolCapability
from sdlc.log import get_logger

log = get_logger("graphify_adapter")


class GraphifyAdapter(ToolAdapter):
    """ToolAdapter wrapping Graphify CLI for knowledge graph generation.

    Graphify provides codebase-to-knowledge-graph conversion via tree-sitter,
    whisper, and LLM semantic extraction. This adapter wraps its CLI interface.

    No architectural coupling: this is a ToolAdapter like any other.
    If Graphify is unavailable, the system degrades gracefully.
    """

    name: str = "graphify"
    capability: ToolCapability = ToolCapability.CODE_GRAPH

    def __init__(
        self,
        graphify_path: str = "graphify",
        workspace_path: str | Path | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._graphify_path = graphify_path
        self._workspace = Path(workspace_path) if workspace_path else None
        self._cache_dir = Path(cache_dir) if cache_dir else Path("data/code_graph")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def validate(self, task: Any) -> bool:
        if isinstance(task, dict):
            return "path" in task or self._workspace is not None
        return self._workspace is not None

    async def execute(self, task: Any) -> dict[str, Any]:
        workspace = self._resolve_workspace(task)
        if not workspace:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": "No workspace path provided",
                "details": {},
            }

        available = await self.healthcheck()
        if not available:
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": "Graphify CLI not available",
                "details": {"hint": "Install with: graphify opencode install"},
            }

        mode = task.get("mode", "incremental") if isinstance(task, dict) else "incremental"
        output = (
            task.get("output", str(self._cache_dir / "graph.json"))
            if isinstance(task, dict)
            else str(self._cache_dir / "graph.json")
        )

        try:
            result = await self._run_graphify(workspace, mode, output)
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": result.get("returncode", -1) == 0,
                "summary": result.get("summary", f"Graphify {mode} index completed"),
                "details": result,
            }
        except (TimeoutError, FileNotFoundError, OSError, ValueError) as e:
            log.warning("Graphify execution failed: %s", e)
            return {
                "adapter": self.name,
                "capability": self.capability.value,
                "passed": False,
                "summary": f"Graphify execution failed: {e}",
                "details": {"error": str(e)},
            }

    async def healthcheck(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._graphify_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0 and bool(stdout.strip())
        except (TimeoutError, FileNotFoundError, OSError):
            return False

    async def query_graph(self, query: str, graph_path: str | None = None) -> dict[str, Any]:
        path = Path(graph_path or str(self._cache_dir / "graph.json"))
        if not path.exists():
            return {"error": "Graph not found", "hint": "Run graphify index first"}
        try:
            proc = await asyncio.create_subprocess_exec(
                self._graphify_path,
                "query",
                query,
                "--graph",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            result = json.loads(stdout.decode()) if stdout else {}
            if stderr:
                result["stderr"] = stderr.decode()[:500]
        except (TimeoutError, FileNotFoundError, json.JSONDecodeError, OSError) as e:
            return {"error": str(e)}
        else:
            return result

    async def get_graph_summary(self, graph_path: str | None = None) -> dict[str, Any]:
        path = Path(graph_path or str(self._cache_dir / "graph.json"))
        if not path.exists():
            return {"error": "Graph not found"}
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            nodes = data.get("nodes", data.get("elements", []))
            edges = data.get("edges", data.get("links", []))
            return {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "path": str(path),
                "available": True,
            }
        except (json.JSONDecodeError, OSError) as e:
            return {"error": str(e)}

    def _resolve_workspace(self, task: Any) -> Path | None:
        if isinstance(task, dict):
            raw = task.get("path", "")
            if raw:
                return Path(raw)
        return self._workspace

    async def _run_graphify(
        self,
        workspace: Path,
        mode: str,
        output: str,
    ) -> dict[str, Any]:
        cmd = [
            self._graphify_path,
            "index",
            "--workspace", str(workspace),
            "--output", output,
        ]

        if mode == "incremental":
            cmd.append("--incremental")
        elif mode == "full":
            cmd.append("--full")

        sha_cache = self._cache_dir / "sha_cache.json"
        if sha_cache.exists():
            cmd.extend(["--sha-cache", str(sha_cache)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return {
                "returncode": -1,
                "summary": "Graphify index timed out after 120s",
                "stdout": (stdout or b"").decode()[:1000],
                "stderr": (stderr or b"").decode()[:500],
            }

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
        returncode = proc.returncode or 0

        return {
            "returncode": returncode,
            "summary": f"Graphify {mode} index: {'OK' if returncode == 0 else 'FAILED'}",
            "stdout": stdout_str[:1000],
            "stderr": stderr_str[:500],
        }
