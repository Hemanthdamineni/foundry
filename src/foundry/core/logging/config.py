"""Logging configuration model and setup entry point."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from foundry.core.logging.format import JsonFormatter

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@dataclass
class LoggingConfig:
    """Configuration for Foundry's unified logging subsystem.

    Attributes:
        level:        Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format:  When *True* emit structured JSON lines; otherwise plain text.
        path:         Optional file path to write logs to (in addition to stdout).
        name:         Root logger name under which all child loggers are created.
        use_stderr:   When *True* (default) write to stderr; otherwise stdout.
    """

    level: LogLevel = "INFO"
    json_format: bool = True
    path: str | None = None
    name: str = "foundry"
    use_stderr: bool = True

    def __post_init__(self) -> None:
        normalized = self.level.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            msg = f"Invalid log level: {self.level!r} — use DEBUG/INFO/WARNING/ERROR/CRITICAL"
            raise ValueError(msg)
        object.__setattr__(self, "level", normalized)  # type: ignore[assignment]


def _build_handler(config: LoggingConfig) -> logging.Handler:
    """Create the primary stream handler based on *config*."""
    stream = sys.stderr if config.use_stderr else sys.stdout
    handler: logging.Handler = logging.StreamHandler(stream)

    if config.json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    return handler


def _build_file_handler(config: LoggingConfig) -> logging.Handler | None:
    """Create a file handler when *config.path* is set."""
    if not config.path:
        return None

    path = Path(config.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler: logging.Handler = logging.FileHandler(str(path))
    if config.json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    return handler


def setup_logging(config: LoggingConfig | None = None) -> logging.Logger:
    """Configure the root logger from *config* and return it.

    This replaces all existing handlers on the root logger so previous
    feature-level setup (if any) is discarded.

    Args:
        config:    Logging configuration.  When *None* defaults are used.

    Returns:
        The configured root logger (*config.name*).
    """
    if config is None:
        config = LoggingConfig()

    root = logging.getLogger(config.name)
    root.setLevel(config.level)
    root.handlers.clear()

    root.addHandler(_build_handler(config))

    file_handler = _build_file_handler(config)
    if file_handler:
        root.addHandler(file_handler)

    return root


def bootstrap_logging(
    *,
    level: str = "INFO",
    json_format: bool = True,
    path: str | None = None,
    name: str = "foundry",
) -> logging.Logger:
    """Legacy convenience wrapper — equivalent to constructing a
    :class:`LoggingConfig` and calling :func:`setup_logging`.

    Retained for backwards compatibility with existing call sites
    (e.g. ``foundry.features.sdlc_runtime.runtime.app``).
    """
    config = LoggingConfig(
        level=level,  # type: ignore[arg-type]
        json_format=json_format,
        path=path,
        name=name,
    )
    return setup_logging(config)
