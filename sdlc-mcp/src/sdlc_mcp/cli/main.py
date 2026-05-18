"""sdlc-mcp CLI entry point — bootstrap, doctor, models, repair, upgrade."""

import argparse
import os
import sys
from pathlib import Path

from sdlc_mcp.cli.doctor import run_doctor
from sdlc_mcp.cli.init import run_init
from sdlc_mcp.cli.models import run_models
from sdlc_mcp.cli.repair import run_repair
from sdlc_mcp.cli.upgrade import run_upgrade


def run_server(*, workspace: str | None = None) -> int:
    """Run the MCP server over stdio."""
    if workspace:
        os.environ["FOUNDRY_WORKSPACE"] = str(Path(workspace).expanduser().resolve())
    from sdlc_mcp.runtime.app import app

    app.run(transport="stdio")
    return 0


def cli(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        prog="sdlc-mcp",
        description="SDLC-MCP — structured development lifecycle runtime for OpenCode",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        help="Explicit Foundry workspace root; overrides current working directory",
    )
    sub = parser.add_subparsers(dest="command")

    def add_workspace_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--workspace",
            dest="command_workspace",
            default=None,
            help="Explicit Foundry workspace root; overrides current working directory",
        )

    sub.add_parser("serve", help="Run the MCP server over stdio")
    bootstrap_p = sub.add_parser("bootstrap", help="Bootstrap SDLC in current project")
    add_workspace_arg(bootstrap_p)

    init_p = sub.add_parser("init", help="Bootstrap SDLC in current project")
    init_p.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    init_p.add_argument(
        "--no-plugins", action="store_true", help="Skip OpenCode plugin installation"
    )
    add_workspace_arg(init_p)

    doctor_p = sub.add_parser("doctor", help="Validate environment and configuration")
    add_workspace_arg(doctor_p)

    models_p = sub.add_parser("models", help="Check and manage LLM models")
    models_p.add_argument(
        "--pull", nargs="*", default=None, help="Pull specified Ollama models"
    )

    repair_p = sub.add_parser("repair", help="Repair broken config or plugin setup")
    add_workspace_arg(repair_p)

    upgrade_p = sub.add_parser(
        "upgrade", help="Upgrade prompts, templates, and config safely"
    )
    add_workspace_arg(upgrade_p)

    args = parser.parse_args(argv)
    command_workspace = getattr(args, "command_workspace", None)
    workspace = command_workspace or args.workspace

    match args.command:
        case None:
            return run_server(workspace=workspace)
        case "serve":
            return run_server(workspace=workspace)
        case "bootstrap":
            return run_init(force=False, no_plugins=True, workspace=workspace)
        case "init":
            return run_init(
                force=args.force,
                no_plugins=args.no_plugins,
                workspace=workspace,
            )
        case "doctor":
            return run_doctor(workspace=workspace)
        case "models":
            return run_models(pull=args.pull)
        case "repair":
            return run_repair(workspace=workspace)
        case "upgrade":
            return run_upgrade(workspace=workspace)
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(cli())
