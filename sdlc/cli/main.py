"""sdlc-mcp CLI entry point — bootstrap, doctor, models, repair, upgrade."""

import argparse
import sys

from sdlc.cli.doctor import run_doctor
from sdlc.cli.init import run_init
from sdlc.cli.models import run_models
from sdlc.cli.repair import run_repair
from sdlc.cli.upgrade import run_upgrade


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sdlc-mcp",
        description="SDLC-MCP — structured development lifecycle runtime for OpenCode",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Bootstrap SDLC in current project")
    init_p.add_argument(
        "--force", action="store_true", help="Overwrite existing files"
    )
    init_p.add_argument(
        "--no-plugins", action="store_true", help="Skip OpenCode plugin installation"
    )

    sub.add_parser("doctor", help="Validate environment and configuration")

    models_p = sub.add_parser("models", help="Check and manage LLM models")
    models_p.add_argument(
        "--pull", nargs="*", default=None, help="Pull specified Ollama models"
    )

    sub.add_parser("repair", help="Repair broken config or plugin setup")

    sub.add_parser(
        "upgrade", help="Upgrade prompts, templates, and config safely"
    )

    args = parser.parse_args(argv)

    match args.command:
        case "init":
            return run_init(force=args.force, no_plugins=args.no_plugins)
        case "doctor":
            return run_doctor()
        case "models":
            return run_models(pull=args.pull)
        case "repair":
            return run_repair()
        case "upgrade":
            return run_upgrade()
        case _:
            parser.print_help()
            return 1


if __name__ == "__main__":
    sys.exit(cli())
