"""ProcessWatchdog — tracks and cleans up spawned subprocesses."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from sdlc_mcp.log import get_logger

log = get_logger("watchdog")

_SIGTERM_GRACE_S = 2.0


class ProcessWatchdog:
    """Tracks child processes and ensures cleanup on shutdown.

    Usage:
        watchdog = ProcessWatchdog()
        watchdog.track(proc)  # after creating a subprocess
        # ... on shutdown:
        await watchdog.cleanup()
    """

    def __init__(self) -> None:
        self._pids: list[int] = []

    def track(self, proc: Any) -> None:
        pid = getattr(proc, "pid", None)
        if pid is not None:
            self._pids.append(pid)

    async def cleanup(self, *, force: bool = True) -> dict[str, int]:
        cleaned = 0
        forced = 0
        for pid in list(self._pids):
            if not self._pid_exists(pid):
                self._pids.remove(pid)
                continue

            try:
                os.kill(pid, signal.SIGTERM)
                cleaned += 1
            except OSError:
                pass

            if force:
                await asyncio.sleep(_SIGTERM_GRACE_S)
                if self._pid_exists(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                        forced += 1
                    except OSError:
                        pass

            if not self._pid_exists(pid):
                self._pids.remove(pid)

        return {"cleaned": cleaned, "force_killed": forced, "remaining": len(self._pids)}

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "tracked": len(self._pids),
            "pids": list(self._pids),
        }

    def clear(self) -> None:
        self._pids.clear()
