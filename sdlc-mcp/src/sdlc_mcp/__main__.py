"""SDLC-MCP module entry point."""

from sdlc_mcp.cli.main import cli


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
