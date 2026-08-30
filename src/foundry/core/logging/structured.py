"""Event-driven structured logger.

Absorbed from ``foundry.features.api_server.structured_logger`` into
the core logging package so all servers can share it.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from foundry.core.event_bus import Event, EventBus, EventType

__all__ = ["StructuredLogger"]


class StructuredLogger:
    """Log structured event data to a file (detailed) and optionally to stdout
    (concise human-readable lines).

    Subscribes to an :class:`EventBus` and produces two output streams:

    - **File** — every event type, with full data.
    - **Console** — curated subset relevant for real-time human monitoring.
    """

    def __init__(self, event_bus: EventBus, *, log_path: str, mirror_to_stdout: bool = True) -> None:
        target = Path(log_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        self.file_logger = logging.getLogger("foundry.structured.file")
        self.file_logger.handlers.clear()
        self.file_logger.setLevel(logging.INFO)
        self.file_logger.propagate = False
        file_handler = logging.FileHandler(target, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        self.file_logger.addHandler(file_handler)

        self.console_logger = logging.getLogger("foundry.structured.console")
        self.console_logger.handlers.clear()
        self.console_logger.setLevel(logging.INFO)
        self.console_logger.propagate = False
        if mirror_to_stdout:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(logging.Formatter("%(message)s"))
            self.console_logger.addHandler(console_handler)

        event_bus.subscribe(self.handle_event)

    def handle_event(self, event: Event) -> None:
        level = logging.ERROR if event.type == EventType.ERROR else logging.INFO
        detailed = self._detailed_message(event)
        if detailed:
            self.file_logger.log(level, detailed)

        concise = self._console_message(event)
        if concise:
            self.console_logger.log(level, concise)

    def _detailed_message(self, event: Event) -> str:
        prefix = self._prefix(event)
        if event.type == EventType.PHASE_START:
            return f"{prefix} START PHASE: {event.phase or '-'}"
        if event.type == EventType.PHASE_END:
            duration = self._extract_duration(event.data)
            return f"{prefix} END PHASE: {event.phase or '-'} (Duration: {duration:.2f}s)"
        if event.type == EventType.DEBATE_START:
            return f"{prefix} DEBATE START: {self._event_detail(event.data)}"
        if event.type == EventType.DEBATE_END:
            return f"{prefix} DEBATE END: {self._event_detail(event.data)}"
        if event.type == EventType.REQUEST_START:
            return f"{prefix} REQUEST START: {self._event_detail(event.data)}"
        if event.type == EventType.REQUEST_END:
            return f"{prefix} REQUEST END: {self._event_detail(event.data)}"
        if event.type == EventType.MODEL_WARM:
            return f"{prefix} MODEL WARM: {event.model or self._event_detail(event.data)}"
        if event.type == EventType.MODEL_UNLOAD:
            return f"{prefix} MODEL UNLOAD: {event.model or self._event_detail(event.data)}"
        if event.type == EventType.PREFETCH:
            return f"{prefix} PREFETCH: {self._event_detail(event.data)}"
        if event.type == EventType.DECISION:
            return f"{prefix} DECISION: {self._event_detail(event.data)}"
        if event.type == EventType.STREAM_START:
            return f"{prefix} STREAM START"
        if event.type == EventType.STREAM_END:
            return f"{prefix} STREAM END"
        if event.type == EventType.ERROR:
            return f"{prefix} ERROR: {self._event_detail(event.data)}"
        if event.type == EventType.LOG:
            return f"{prefix} LOG: {self._event_detail(event.data)}"
        return f"{prefix} EVENT[{event.type.value}]: {self._event_detail(event.data)}"

    def _console_message(self, event: Event) -> str | None:
        prefix = self._prefix(event)
        data = event.data if isinstance(event.data, dict) else {}

        # Keep internal debug chatter out of console, preserve in file log.
        if event.type == EventType.LOG:
            return None

        if event.type == EventType.REQUEST_START:
            endpoint = str(data.get("endpoint") or "-")
            stream = bool(data.get("stream"))
            model = str(data.get("model") or event.model or "-")
            tools = "yes" if bool(data.get("tools")) else "no"
            mode = "stream" if stream else "non-stream"
            return f"{prefix} REQUEST START: {endpoint} ({mode}) model={model} tools={tools}"

        if event.type == EventType.REQUEST_END:
            status = str(data.get("status") or "-")
            dur = int(data.get("duration_ms") or 0)
            retries = int(data.get("retries") or 0)
            chunks = data.get("chunks")
            if isinstance(chunks, int):
                return f"{prefix} REQUEST END: status={status} duration={dur}ms chunks={chunks} retries={retries}"
            return f"{prefix} REQUEST END: status={status} duration={dur}ms retries={retries}"

        if event.type == EventType.STREAM_START:
            return f"{prefix} STREAM START"

        if event.type == EventType.STREAM_END:
            return f"{prefix} STREAM END"

        if event.type == EventType.PHASE_START:
            return f"{prefix} START PHASE: {event.phase or '-'}"

        if event.type == EventType.PHASE_END:
            duration = self._extract_duration(data)
            return f"{prefix} END PHASE: {event.phase or '-'} (Duration: {duration:.2f}s)"

        if event.type == EventType.DEBATE_START:
            phase = str(data.get("phase") or event.phase or "-")
            rounds = data.get("rounds")
            agents = data.get("agents")
            if isinstance(agents, list):
                return f"{prefix} DEBATE START: {phase} (rounds={rounds} agents={len(agents)})"
            return f"{prefix} DEBATE START: {phase}"

        if event.type == EventType.DEBATE_END:
            phase = str(data.get("phase") or event.phase or "-")
            dur = data.get("duration_s")
            if isinstance(dur, (int, float)):
                return f"{prefix} DEBATE END: {phase} (Duration: {float(dur):.2f}s)"
            return f"{prefix} DEBATE END: {phase}"

        if event.type == EventType.MODEL_WARM:
            reason = str(data.get("reason") or "")
            status = str(data.get("status") or "loaded")
            if reason:
                return f"{prefix} MODEL READY: {event.model or '-'} ({status}; {reason})"
            return f"{prefix} MODEL READY: {event.model or '-'} ({status})"

        if event.type == EventType.MODEL_UNLOAD:
            reason = str(data.get("reason") or "")
            if reason:
                return f"{prefix} MODEL UNLOAD: {event.model or '-'} ({reason})"
            return f"{prefix} MODEL UNLOAD: {event.model or '-'}"

        if event.type == EventType.PREFETCH:
            component = str(data.get("component") or "")
            if component == "idle_warmer":
                action = str(data.get("action") or "idle")
                reason = str(data.get("reason") or "")
                if reason:
                    return f"{prefix} PREFETCH: idle/{action} ({reason})"
                return f"{prefix} PREFETCH: idle/{action}"

            phase = str(data.get("phase") or event.phase or "-")
            count = data.get("count")
            if isinstance(count, int):
                return f"{prefix} PREFETCH: {phase} (actions={count})"
            return f"{prefix} PREFETCH: {phase}"

        if event.type == EventType.DECISION:
            frm = str(data.get("from_phase") or "-")
            to = str(data.get("to_phase") or "-")
            failure = str(data.get("failure_class") or "none")
            return f"{prefix} DECISION: {frm} -> {to} ({failure})"

        if event.type == EventType.ERROR:
            return f"{prefix} ERROR: {self._event_detail(event.data)}"

        return f"{prefix} {event.type.value.upper()}"

    @staticmethod
    def _extract_duration(data: Any) -> float:
        if isinstance(data, dict):
            maybe = data.get("duration")
            if isinstance(maybe, (int, float)):
                return float(maybe)
        return 0.0

    @staticmethod
    def _event_detail(data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            parts = [f"{key}={value}" for key, value in data.items()]
            return ", ".join(parts)
        return str(data)

    @staticmethod
    def _prefix(event: Event) -> str:
        ts = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S.%f")[:-3]
        scope_id = event.request_id or event.task_id
        if scope_id:
            return f"[{ts}] [{scope_id[:8]}]"
        return f"[{ts}]"
