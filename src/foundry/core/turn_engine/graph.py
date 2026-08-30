"""
RoleGraph protocol and Terminal sentinel for the Foundry turn engine.

Defines the contract for role-based conversation graphs where each turn
belongs to a named role, and the graph determines the next role (or
termination) based on the current role and the output produced.
"""

from __future__ import annotations

import typing
from typing import Protocol, runtime_checkable


class Terminal:
    """Sentinel class that signals the conversation is complete.

    Returning ``Terminal`` (or a subclass) from ``next_role`` tells the
    turn engine to stop dispatching further turns in this session.
    """

    __slots__ = ()


@runtime_checkable
class RoleGraph(Protocol):
    """Protocol for a role-transition graph.

    Implementations must provide the three methods below.  The
    ``context`` parameter is an opaque object that the caller supplies
    (e.g. a session state, a message store, or a configuration handle).
    """

    def initial_role(self, context: typing.Any) -> str:
        """Return the name of the first role for a fresh conversation.

        Parameters
        ----------
        context:
            Opaque caller-supplied state (session, config, etc.).

        Returns
        -------
        str
            The initial role label (e.g. ``"planner"``).
        """
        ...

    def prompt_for(self, role: str, context: typing.Any) -> str:
        """Return the system prompt that should be used for *role*.

        Parameters
        ----------
        role:
            The current role label.
        context:
            Opaque caller-supplied state.

        Returns
        -------
        str
            The prompt text to feed to the language model.
        """
        ...

    def next_role(
        self,
        current_role: str,
        output: str,
        context: typing.Any,
    ) -> str | None | type[Terminal]:
        """Determine the next role after *current_role* has produced *output*.

        Parameters
        ----------
        current_role:
            The role that just finished.
        output:
            The text produced by the language model under *current_role*.
        context:
            Opaque caller-supplied state.

        Returns
        -------
        str | None | type[Terminal]
            - A ``str``: the next role to dispatch.
            - ``None``: re-dispatch the same role (e.g. for retries).
            - ``Terminal`` (the class itself, not an instance): end the
              conversation.
        """
        ...
