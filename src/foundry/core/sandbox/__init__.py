"""foundry.core.sandbox -- isolated subprocess execution.

Provides a configurable subprocess sandbox that restricts the execution
environment, enforces timeouts, and captures output.  Designed as a
stepping stone to full container isolation (see ``executor`` module docs
for the provider interface).
"""

from foundry.core.sandbox.executor import SandboxedExecutor
from foundry.core.sandbox.models import SandboxConfig, SandboxResult

__all__ = [
    "SandboxConfig",
    "SandboxResult",
    "SandboxedExecutor",
]
