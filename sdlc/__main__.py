"""SDLC MCP server — entry point for `python -m sdlc`."""

from sdlc.runtime.app import app


def main() -> None:
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
