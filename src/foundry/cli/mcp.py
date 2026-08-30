"""CLI entry point for the MCP server."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Foundry MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1, used with sse transport)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind (default: 8765 for sse transport, unused for stdio)",
    )

    args = parser.parse_args()

    # SSE defaults to 8765 to avoid collision with serve server (8000)
    port = args.port if args.port is not None else 8765

    try:
        from foundry.features.mcp.server import app

        app.run(transport=args.transport, host=args.host, port=port)
    except ImportError as exc:
        print(f"Error importing MCP server: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
