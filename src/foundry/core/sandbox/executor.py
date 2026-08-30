"""Isolated subprocess execution with timeouts and environment restrictions.

Architecture
------------

Two isolation layers are supported:

1. **Subprocess sandbox** (this file) -- the fast path.  Commands are run via
   ``subprocess.Popen`` with a restricted ``PATH``, a process group for clean
   teardown, and a configurable timeout.  Suitable for CI, local development,
   and low-trust agent-generated commands where the main threat is runaways
   rather than deliberate escapes.

2. **Container isolation** (fast-follow) -- when a container runtime is
   configured, the executor delegates to ``SandboxProvider`` (see
   :mod:`foundry.core.sandbox.providers`).  The subprocess implementation is
   kept behind the same public interface so swapping is a configuration change.

Interface contract (for any future provider)::

    class SandboxProvider:
        def run(
            self,
            command: str,
            *,
            timeout: int = 30,
            config: SandboxConfig | None = None,
        ) -> SandboxResult:
            ...
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile

from foundry.core.sandbox.models import SandboxConfig, SandboxResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Restricted PATH
#
# The subprocess sandbox builds a temporary ``bin/`` directory containing
# symlinks to only the safe tools listed below.  The child's ``PATH`` is
# set exclusively to this directory, so dangerous tools (rm, dd, mkfs, ...)
# are not resolvable.
#
# This is a **safety net**, not a security boundary.  A determined process
# can still escape via absolute paths (/bin/rm) or by manipulating its own
# environment.  Full container isolation is the correct solution when a
# security boundary is required.
# ---------------------------------------------------------------------------

_SAFE_BINARIES = frozenset({
    "bash",
    "cat",
    "comm",
    "cp",
    "cut",
    "date",
    "dirname",
    "echo",
    "env",
    "expr",
    "false",
    "find",
    "grep",
    "head",
    "ls",
    "mkdir",
    "mv",
    "pwd",
    "printf",
    "sed",
    "sh",
    "sleep",
    "sort",
    "tail",
    "tee",
    "test",
    "touch",
    "tr",
    "true",
    "uname",
    "uniq",
    "wc",
    "whoami",
    "xargs",
    "yes",
})


def _build_safe_bindir() -> str:
    """Create a temporary directory with symlinks to safe executables.

    Returns the path to the ``bindir``.  The caller is responsible for
    calling :func:`_cleanup_safe_bindir` after the subprocess completes.
    """
    bindir = tempfile.mkdtemp(prefix="foundry-sandbox-")
    for tool in _SAFE_BINARIES:
        src = shutil.which(tool)
        if src:
            try:
                os.symlink(src, os.path.join(bindir, tool))
            except FileExistsError:
                pass
    return bindir


def _cleanup_safe_bindir(bindir: str) -> None:
    """Remove a temporary bindir created by :func:`_build_safe_bindir`."""
    try:
        shutil.rmtree(bindir)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SandboxedExecutor:
    """Run shell commands in a restricted subprocess environment.

    Parameters
    ----------
    config:
        Sandbox configuration.  If not provided a default-enabled config
        with a 30 s timeout is used.
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self._config = config or SandboxConfig()

    # ------------------------------------------------------------------
    # Public method
    # ------------------------------------------------------------------

    def run(
        self,
        command: str,
        *,
        timeout: int | None = None,
        config: SandboxConfig | None = None,
    ) -> SandboxResult:
        """Execute *command* in a sandboxed subprocess.

        Parameters
        ----------
        command:
            Shell command string to execute.
        timeout:
            Maximum wall-clock seconds before the process group is killed.
            Falls back to ``config.timeout``, then to the instance-level
            default.
        config:
            Per-call override of sandbox settings.  When provided, merged
            over the instance-level config (only the fields that are set on
            the override take effect).

        Returns
        -------
        SandboxResult
            Captured stdout, stderr, exit code, and timeout flag.
        """
        resolved_config = self._resolve_config(config)
        effective_timeout = timeout if timeout is not None else resolved_config.timeout

        if not resolved_config.enabled:
            return self._run_free(command, timeout=effective_timeout)

        return self._run_restricted(command, config=resolved_config, timeout=effective_timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_config(self, override: SandboxConfig | None) -> SandboxConfig:
        """Merge a per-call override into the instance config."""
        if override is None:
            return self._config

        # Copy instance defaults, then overlay explicitly-set override fields.
        merged = self._config.model_copy()
        for field_name in SandboxConfig.model_fields:
            override_val = getattr(override, field_name, None)
            if override_val is not None:
                setattr(merged, field_name, override_val)
        return merged

    @staticmethod
    def _build_restricted_env() -> tuple[dict[str, str], str]:
        """Build a restricted environment and return ``(env, bindir)``.

        The returned *bindir* path must be cleaned up with
        :func:`_cleanup_safe_bindir` after the subprocess completes.
        """
        bindir = _build_safe_bindir()

        env = os.environ.copy()
        env["PATH"] = bindir
        # Flatten PYTHONPATH so the subprocess doesn't accidentally import
        # project code with elevated privileges.
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        return env, bindir

    def _run_restricted(
        self,
        command: str,
        *,
        config: SandboxConfig,
        timeout: int,
    ) -> SandboxResult:
        """Run the command under sandbox restrictions."""
        env, bindir = self._build_restricted_env()

        if config.readonly_paths or config.writable_paths:
            logger.warning(
                "readonly_paths / writable_paths are set but the subprocess "
                "sandbox does not enforce filesystem restriction.  Use a "
                "container provider for actual filesystem isolation."
            )

        try:
            return self._run_process(command, env=env, timeout=timeout)
        finally:
            _cleanup_safe_bindir(bindir)

    def _run_free(self, command: str, *, timeout: int) -> SandboxResult:
        """Run the command with no sandbox restrictions."""
        return self._run_process(command, env=None, timeout=timeout)

    @staticmethod
    def _run_process(
        command: str,
        *,
        env: dict[str, str] | None,
        timeout: int,
    ) -> SandboxResult:
        """Spawn a subprocess, capture output, enforce timeout.

        The command is executed via ``shell=True`` so that shell syntax
        (redirects, pipes) is available.

        The child process is placed in its own process group (via
        ``preexec_fn=os.setsid``) so that we can kill the entire tree
        on timeout.
        """
        # fmt: off
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid,
            text=True,
        )
        # fmt: on

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            timed_out = False
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Kill the entire process group.
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # already gone
            stdout, stderr = proc.communicate()
            timed_out = True
            exit_code = proc.returncode

        return SandboxResult(
            stdout=stdout or "",
            stderr=stderr or "",
            exit_code=exit_code,
            timed_out=timed_out,
        )
