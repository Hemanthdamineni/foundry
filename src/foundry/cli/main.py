"""foundry CLI — command dispatch and entry point."""

from __future__ import annotations

import sys


def main() -> None:
    """CLI entry point — dispatch based on first argument."""
    if len(sys.argv) < 2:
        print("Usage: foundry <command> [args...]", file=sys.stderr)
        print("Commands: init, doctor, mcp, serve, orchestrate, sdlc,", file=sys.stderr)
        print("          dashboard, eval, approve, workspaces, auth", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    # Everything after "foundry <cmd>" is the subcommand's args
    args = sys.argv[2:]

    match command:
        case "init":
            from foundry.cli.init import run_init
            sys.exit(run_init(force="--force" in args))

        case "doctor":
            from foundry.cli.doctor import run_doctor
            sys.exit(run_doctor())

        case "mcp":
            from foundry.features.mcp.server import app
            # Respect --transport and --port from args if provided
            transport = "stdio"
            host = "127.0.0.1"
            port = 8000
            for i, a in enumerate(args):
                if a == "--transport" and i + 1 < len(args):
                    transport = args[i + 1]
                elif a == "--host" and i + 1 < len(args):
                    host = args[i + 1]
                elif a == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
            if transport == "stdio":
                app.run(transport="stdio")
            else:
                app.settings.host = host
                app.settings.port = port
                app.run(transport=transport)

        case "serve":
            from foundry.cli.serve import main as serve_main
            serve_main(args)

        case "orchestrate":
            from foundry.cli.orchestrate import main as orchestrate_main
            orchestrate_main(args)

        case "sdlc":
            from foundry.cli.sdlc import main as sdlc_main
            sdlc_main(args)

        case "dashboard":
            from foundry.cli.dashboard import run_dashboard
            # Parse --port and --host from args
            port = 3000
            host = "127.0.0.1"
            for i, a in enumerate(args):
                if a == "--port" and i + 1 < len(args):
                    port = int(args[i + 1])
                elif a == "--host" and i + 1 < len(args):
                    host = args[i + 1]
            sys.exit(run_dashboard(port=port, host=host))

        case "eval":
            from foundry.cli.evaluate import main as evaluate_main
            evaluate_main(args)

        case "approve":
            from foundry.cli.approve import build_parser, run_approve
            parser = build_parser()
            parsed = parser.parse_args(args)
            sys.exit(run_approve(parsed))

        case "workspaces":
            from foundry.cli.workspaces import main as workspaces_main
            workspaces_main(args)

        case "auth":
            from foundry.cli.auth import main as auth_main
            auth_main(args)

        case _:
            print(f"foundry: unknown command '{command}'", file=sys.stderr)
            print("Commands: init, doctor, mcp, serve, orchestrate, sdlc,", file=sys.stderr)
            print("          dashboard, eval, approve, workspaces, auth", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
