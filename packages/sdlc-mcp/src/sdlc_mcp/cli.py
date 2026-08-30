"""Backward-compat — delegate to the canonical MCP server."""
from foundry.features.mcp.server import app


def main() -> None:
    """Run the canonical MCP server over stdio transport."""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
