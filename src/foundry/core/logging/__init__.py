"""Unified logging for the Foundry platform.

Provides structured JSON logging with configurable output, level, and format.
Replaces feature-specific logging in api_server and sdlc_runtime.

Usage:
    from foundry.core.logging import get_logger

    logger = get_logger("my_module")
    logger.info("hello", extra={"key": "value"})
"""

from foundry.core.logging.config import LoggingConfig, setup_logging, bootstrap_logging
from foundry.core.logging.format import JsonFormatter
from foundry.core.logging._core import get_logger
from foundry.core.logging.structured import StructuredLogger

__all__ = [
    "LoggingConfig",
    "JsonFormatter",
    "StructuredLogger",
    "get_logger",
    "setup_logging",
    "bootstrap_logging",
]
