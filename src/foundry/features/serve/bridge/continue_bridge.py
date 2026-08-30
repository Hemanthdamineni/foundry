from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import shlex
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

if sys.stdout.encoding != "utf-8":
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

logger = logging.getLogger("ai_agent_server_v3.bridge")
if not logger.handlers:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(stream_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class ContinueExecutionError(RuntimeError):
    """Raised when Continue CLI execution fails."""


def _console_log(message: str, *, request_id: str | None = None, level: int = logging.INFO) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    prefix = f"[{ts}]"
    if request_id:
        prefix += f" [{request_id[:8]}]"
    logger.log(level, f"{prefix} {message}")


def _extract_json_object(text: str) -> dict[str, Any]:
    payload = text.strip()
    if not payload:
        raise ContinueExecutionError("empty Continue output")
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    for line in reversed(payload.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ContinueExecutionError("could not parse Continue JSON output")


@dataclass(frozen=True)
class ContinueCommandResult:
    output: dict[str, Any]
    logs: str
    exit_code: int


class ContinueCommandRunner:
    def __init__(self, command: str) -> None:
        parts = shlex.split(command.strip())
        if not parts:
            raise ContinueExecutionError("empty Continue command")
        self._base_cmd = self._sanitize_base_command(parts)

    @staticmethod
    def _config_path_exists(raw_path: str) -> bool:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.exists()

    def _sanitize_base_command(self, parts: list[str]) -> tuple[str, ...]:
        sanitized: list[str] = []
        dropped_config_paths: list[str] = []
        idx = 0
        while idx < len(parts):
            token = parts[idx]
            if token in {"--config", "-c"}:
                if idx + 1 >= len(parts):
                    sanitized.append(token)
                    idx += 1
                    continue
                config_path = parts[idx + 1]
                if self._config_path_exists(config_path):
                    sanitized.extend((token, config_path))
                else:
                    dropped_config_paths.append(config_path)
                idx += 2
                continue
            if token.startswith("--config="):
                config_path = token.split("=", 1)[1]
                if self._config_path_exists(config_path):
                    sanitized.append(token)
                else:
                    dropped_config_paths.append(config_path)
                idx += 1
                continue
            sanitized.append(token)
            idx += 1

        if not sanitized:
            raise ContinueExecutionError("empty Continue command after config sanitization")

        for missing_path in dropped_config_paths:
            _console_log(
                f"continue command config path not found; ignoring it: {missing_path}",
                level=logging.WARNING,
            )
        return tuple(sanitized)

    async def run_prompt(self, *, prompt: str, cwd: str | None) -> ContinueCommandResult:
        cmd = [*self._base_cmd, "-p", prompt, "--format", "json", "--silent"]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise ContinueExecutionError(f"failed to start Continue command in cwd={cwd!r}: {exc}") from exc
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = int(process.returncode or 0)
        logs = f"stdout:\n{stdout_text}\n\nstderr:\n{stderr_text}".strip()
        if exit_code != 0:
            raise ContinueExecutionError(f"Continue command exited with {exit_code}\n{logs}")
        output = _extract_json_object(stdout_text)
        return ContinueCommandResult(output=output, logs=logs, exit_code=exit_code)


class ContinueBridgeWorker:
    """Bridge worker that claims orchestration tool requests and executes them via Continue CLI."""

    def __init__(
        self,
        *,
        server_base_url: str,
        shared_key: str | None,
        worker_id: str,
        continue_command: str,
        poll_interval_seconds: float = 1.0,
        heartbeat_interval_seconds: float = 15.0,
        claim_wait_seconds: float = 15.0,
    ) -> None:
        self.server_base_url = server_base_url.rstrip("/")
        self.shared_key = shared_key
        self.worker_id = worker_id
        self.poll_interval_seconds = max(0.2, poll_interval_seconds)
        self.heartbeat_interval_seconds = max(1.0, heartbeat_interval_seconds)
        self.claim_wait_seconds = max(0.0, min(30.0, claim_wait_seconds))
        self.runner = ContinueCommandRunner(continue_command)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=30.0))

    def _resolve_repo_path(self, repo_path: str | None) -> str | None:
        if repo_path is None:
            return None
        raw = str(repo_path).strip()
        if not raw:
            return None
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            workspace_root = os.getenv("FOUNDRY_WORKSPACE_ROOT") or os.getenv("AI_AGENT_WORKSPACE_ROOT", "").strip()
            if workspace_root:
                candidate = Path(workspace_root).expanduser() / candidate
            else:
                candidate = Path.cwd() / candidate
        return str(candidate.resolve())

    async def run(self) -> None:
        heartbeat_task: asyncio.Task[None] | None = None
        try:
            _console_log(
                "bridge worker started "
                f"(worker_id={self.worker_id}, server={self.server_base_url}, poll={self.poll_interval_seconds}s)"
            )
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="continue-bridge-heartbeat")
            while True:
                try:
                    claimed = await self._claim_requests(max_items=1)
                    if not claimed:
                        if self.claim_wait_seconds <= 0:
                            await asyncio.sleep(self.poll_interval_seconds)
                        continue
                    for request in claimed:
                        await self._handle_request(request)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - retry loop for transient bridge/server issues
                    _console_log(f"bridge loop retry after error: {exc}", level=logging.WARNING)
                    await asyncio.sleep(self.poll_interval_seconds)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            _console_log("bridge worker stopped")
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.shared_key:
            headers["X-Bridge-Key"] = self.shared_key
        return headers

    async def _heartbeat(self) -> None:
        await self._client.post(
            f"{self.server_base_url}/internal/heartbeats",
            headers=self._headers(),
            json={"worker_id": self.worker_id, "metadata": {"bridge": "continue-cli"}},
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self._heartbeat()
            except Exception as exc:  # pragma: no cover - transient network/server issues
                _console_log(f"bridge heartbeat retry after error: {exc}", level=logging.WARNING)
            await asyncio.sleep(self.heartbeat_interval_seconds)

    async def _claim_requests(self, *, max_items: int) -> list[dict[str, Any]]:
        response = await self._client.post(
            f"{self.server_base_url}/internal/tool-requests/claim",
            headers=self._headers(),
            json={
                "worker_id": self.worker_id,
                "max_items": max_items,
                "wait_seconds": self.claim_wait_seconds,
            },
        )
        response.raise_for_status()
        payload = response.json()
        raw_requests = payload.get("requests")
        if not isinstance(raw_requests, list):
            return []
        requests = [item for item in raw_requests if isinstance(item, dict)]
        if requests:
            _console_log(f"claimed {len(requests)} request(s)")
        return requests

    def _phase_prompt(self, request: dict[str, Any]) -> tuple[str, str | None]:
        payload = request.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        phase = str(request.get("phase") or payload.get("phase") or "Planning")
        prompt = str(payload.get("prompt") or "")
        repo_path = str(payload.get("repo_path") or ".")
        allowed_next = payload.get("allowed_next")
        contract = payload.get("contract")
        contract_text = json.dumps(contract if isinstance(contract, dict) else {}, ensure_ascii=False)
        allowed_text = json.dumps(allowed_next if isinstance(allowed_next, list) else [], ensure_ascii=False)
        phase_outputs: dict[str, str] = {
            "Chatting": "next_phase, failure_class, confidence, reason, summary",
            "Specs": "requirements, constraints, acceptance_criteria",
            "Planning": "plan, decomposition, risk_notes, confidence",
            "Coding": "files, status, reason, failure_class",
            "Review": "decision, findings, confidence, risk_notes",
            "Done": "summary",
        }
        output_keys = phase_outputs.get(phase, "summary, suggested_next_phase, reason")
        full_prompt = (
            f"You are executing orchestration phase '{phase}'.\n"
            f"User task prompt:\n{prompt}\n\n"
            f"You may use Continue tools as needed. Return ONLY strict JSON with keys:\n"
            f"{output_keys}.\n"
            f"Allowed next phases: {allowed_text}\n"
            f"Contract: {contract_text}\n"
            "If a field is missing, return it with an empty or default value."
        )
        cwd = self._resolve_repo_path(repo_path)
        return (full_prompt, cwd)

    def _git_prompt(self, request: dict[str, Any]) -> tuple[str, str | None]:
        payload = request.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        op = str(payload.get("op") or "unknown")
        branch_name = str(payload.get("branch_name") or "")
        message = str(payload.get("message") or "")
        tag = str(payload.get("tag") or "")
        from_branch = str(payload.get("from_branch") or "")
        repo_path = str(payload.get("repo_path") or ".")
        prompt = (
            "Execute this git operation using Continue tools only.\n"
            f"Operation: {op}\n"
            f"branch_name: {branch_name}\n"
            f"from_branch: {from_branch}\n"
            f"tag: {tag}\n"
            f"message: {message}\n"
            "Return ONLY JSON with keys: next_phase, failure_class, confidence, reason."
        )
        return (prompt, self._resolve_repo_path(repo_path))

    async def _submit_result(
        self,
        *,
        request_id: str,
        claim_token: str,
        resume_token: str,
        version: int,
        output: dict[str, Any],
        logs: str,
        exit_code: int,
    ) -> None:
        response = await self._client.post(
            f"{self.server_base_url}/internal/tool-requests/{request_id}/result",
            headers=self._headers(),
            json={
                "worker_id": self.worker_id,
                "claim_token": claim_token,
                "resume_token": resume_token,
                "version": version,
                "output": output,
                "logs": logs,
                "exit_code": exit_code,
            },
        )
        if response.status_code in {200, 409}:
            return
        response.raise_for_status()

    async def _submit_failure(
        self,
        *,
        request_id: str,
        claim_token: str,
        resume_token: str,
        version: int,
        error_message: str,
        logs: str,
        failure_class: str = "execution_error",
        exit_code: int | None = None,
    ) -> None:
        response = await self._client.post(
            f"{self.server_base_url}/internal/tool-requests/{request_id}/fail",
            headers=self._headers(),
            json={
                "worker_id": self.worker_id,
                "claim_token": claim_token,
                "resume_token": resume_token,
                "version": version,
                "error_message": error_message,
                "failure_class": failure_class,
                "logs": logs,
                "exit_code": exit_code,
            },
        )
        if response.status_code in {200, 409}:
            return
        response.raise_for_status()

    async def _handle_request(self, request: dict[str, Any]) -> None:
        request_id = str(request.get("request_id") or "")
        tool_name = str(request.get("tool_name") or "")
        claim_token = str(request.get("claim_token") or "")
        resume_token = str(request.get("resume_token") or request_id)
        version = int(request.get("version") or 0)
        if not request_id or not claim_token:
            return

        try:
            _console_log(f"handling tool request: {tool_name}", request_id=request_id)
            if tool_name == "continue_phase_step":
                prompt, cwd = self._phase_prompt(request)
            elif tool_name == "continue_git_operation":
                prompt, cwd = self._git_prompt(request)
            else:
                raise ContinueExecutionError(f"unsupported tool request: {tool_name}")

            result = await self.runner.run_prompt(prompt=prompt, cwd=cwd)
            await self._submit_result(
                request_id=request_id,
                claim_token=claim_token,
                resume_token=resume_token,
                version=version,
                output=result.output,
                logs=result.logs,
                exit_code=result.exit_code,
            )
            _console_log(
                f"completed tool request: {tool_name} (exit_code={result.exit_code})",
                request_id=request_id,
            )
        except ContinueExecutionError as exc:
            failure_class = self._classify_execution_failure(str(exc))
            _console_log(
                f"tool request failed: {tool_name} ({exc})",
                request_id=request_id,
                level=logging.ERROR,
            )
            await self._submit_failure(
                request_id=request_id,
                claim_token=claim_token,
                resume_token=resume_token,
                version=version,
                error_message=str(exc),
                logs=str(exc),
                failure_class=failure_class,
                exit_code=1,
            )

    @staticmethod
    def _classify_execution_failure(message: str) -> str:
        normalized = message.strip().lower()
        if not normalized:
            return "execution_error"
        if "unsupported tool request" in normalized:
            return "unsupported_tool"
        if "enoent" in normalized or "no such file or directory" in normalized:
            return "environment_error"
        if "no credits remaining" in normalized or ("402" in normalized and "billing" in normalized):
            return "permission_denied"
        if "401" in normalized or "403" in normalized or "unauthorized" in normalized:
            return "permission_denied"
        if "empty continue output" in normalized or "could not parse continue json output" in normalized:
            return "invalid_output"
        if "failed to start continue command" in normalized:
            return "command_not_found"
        if "timed out" in normalized or "timeout" in normalized:
            return "timeout"
        return "execution_error"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Continue bridge worker")
    parser.add_argument("--server-url", default=os.getenv("FOUNDRY_SERVER_URL") or os.getenv("AI_AGENT_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--worker-id", default=os.getenv("FOUNDRY_BRIDGE_WORKER_ID") or os.getenv("AI_AGENT_BRIDGE_WORKER_ID", "bridge-worker-1"))
    parser.add_argument("--shared-key", default=os.getenv("FOUNDRY_BRIDGE_SHARED_KEY") or os.getenv("AI_AGENT_BRIDGE_SHARED_KEY"))
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=float(os.getenv("FOUNDRY_BRIDGE_HEARTBEAT_INTERVAL_SECONDS") or os.getenv("AI_AGENT_BRIDGE_HEARTBEAT_INTERVAL_SECONDS", "15.0")),
    )
    parser.add_argument(
        "--claim-wait",
        type=float,
        default=float(os.getenv("FOUNDRY_BRIDGE_CLAIM_WAIT_SECONDS") or os.getenv("AI_AGENT_BRIDGE_CLAIM_WAIT_SECONDS", "15.0")),
    )
    parser.add_argument("--continue-command", default=os.getenv("FOUNDRY_CONTINUE_CMD") or os.getenv("AI_AGENT_CONTINUE_CMD", "cn"))
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    worker = ContinueBridgeWorker(
        server_base_url=str(args.server_url),
        shared_key=str(args.shared_key) if args.shared_key else None,
        worker_id=str(args.worker_id),
        continue_command=str(args.continue_command),
        poll_interval_seconds=float(args.poll_interval),
        heartbeat_interval_seconds=float(args.heartbeat_interval),
        claim_wait_seconds=float(args.claim_wait),
    )
    await worker.run()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
