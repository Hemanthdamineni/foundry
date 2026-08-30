"""foundry workspaces [list|add|remove] -- multi-workspace management."""

from __future__ import annotations

import argparse
import sys


def main(args: list[str] | None = None) -> None:
    """Manage Foundry workspaces.

    Parameters
    ----------
    args:
        CLI arguments (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(description="Manage Foundry workspaces")
    sub = parser.add_subparsers(dest="action", help="Workspace action")

    sub.add_parser("list", help="List known workspaces")

    add_p = sub.add_parser("add", help="Register a new workspace")
    add_p.add_argument("path", nargs="?", default=None, help="Path to the workspace directory")

    rm_p = sub.add_parser("remove", help="Remove a workspace entry")
    rm_p.add_argument("path", help="Path to the workspace to remove")

    parsed = parser.parse_args(args)

    from foundry.core.store.workspace_registry import (
        add_workspace, get_current_workspace, list_workspaces, remove_workspace,
    )

    match parsed.action:
        case "list":
            workspaces = list_workspaces()
            if not workspaces:
                print("No workspaces found. Run 'foundry init' to create one.")
                return
            current = get_current_workspace()
            print(f"Found {len(workspaces)} workspace(s):")
            for ws in workspaces:
                marker = "  (current)" if current and ws["path"] == current["path"] else ""
                size_kb = ws["size_bytes"] / 1024
                print(f"  {ws['path']}{marker}")
                print(f"    DB: {ws['db']} ({size_kb:.1f} KB)")

        case "add":
            result = add_workspace(parsed.path)
            print(f"Workspace initialized: {result['path']}")
            print(f"  Database: {result['db']}")

        case "remove":
            remove_workspace(parsed.path)
            print(f"Workspace removed: {parsed.path}")

        case _:
            parser.print_help()
            sys.exit(1)
