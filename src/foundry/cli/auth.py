"""foundry auth [create-key|list|revoke] -- API key management."""

from __future__ import annotations

import sys


def main(args: list[str] | None = None) -> None:
    """Manage API keys (create, list, revoke).

    Parameters
    ----------
    args:
        CLI arguments (defaults to sys.argv[1:]).
    """
    if args is None:
        args = sys.argv[2:]

    from foundry.core.auth.keys import AuthManager

    manager = AuthManager()

    if not args or args[0] in ("--help", "-h", "help"):
        print("Usage: foundry auth <action>")
        print("Actions: create-key, list, revoke <prefix>")
        sys.exit(1 if not args else 0)

    match args[0]:
        case "create-key":
            role = args[1] if len(args) > 1 and args[1] in ("operator", "viewer") else "operator"
            key = manager.create_key(role)
            print(key)
        case "list":
            keys = manager.list_keys()
            if not keys:
                print("No API keys found.")
                return
            for k in keys:
                print(f"  {k['prefix']}  {k['role']}  {k['created_at']}")
        case "revoke":
            if len(args) < 2:
                print("Usage: foundry auth revoke <key-prefix>")
                sys.exit(1)
            manager.revoke_key(args[1])
            print(f"Key with prefix '{args[1]}' revoked.")
        case _:
            print(f"Unknown auth action: {args[0]}")
            print("Actions: create-key, list, revoke <prefix>")
            sys.exit(1)
