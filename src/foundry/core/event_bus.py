"""Event bus — lightweight publish/subscribe for structured observability."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    REQUEST_START = "request_start"
    REQUEST_END = "request_end"
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    DEBATE_START = "debate_start"
    DEBATE_END = "debate_end"
    DECISION = "decision"
    PREFETCH = "prefetch"
    MODEL_WARM = "model_warm"
    MODEL_UNLOAD = "model_unload"
    STREAM_START = "stream_start"
    STREAM_END = "stream_end"
    ERROR = "error"
    LOG = "log"


@dataclass(frozen=True)
class Event:
    type: EventType
    data: Any
    timestamp: float = field(default_factory=time.time)
    request_id: str | None = None
    task_id: str | None = None
    phase: str | None = None
    model: str | None = None


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[Event], None]] = []

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, event: Event) -> None:
        if not self._subscribers:
            return
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception as exc:  # pragma: no cover - defensive guard
                logging.getLogger("foundry.event_bus").error(
                    "event bus subscriber failed: %s",
                    exc,
                )
