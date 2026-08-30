"""foundry serve — start the FastAPI model server.

This is the unified entry point for the Ai-Agent-Server's FastAPI application.
Uses the app factory pattern to defer initialization until the command runs.
"""

from __future__ import annotations

import argparse
import sys


def main(args: list[str] | None = None) -> None:
    """Start the Foundry HTTP server.

    Parameters
    ----------
    args:
        CLI arguments (defaults to sys.argv[1:]).
    """
    parser = argparse.ArgumentParser(description="Start the Foundry HTTP server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parsed = parser.parse_args(args)

    # Import the server module here (not at module level) because its
    # initialization reads YAML config files that may not exist at import time
    try:
        import uvicorn
        from foundry.features.serve.server import app
        print(f"foundry serve: starting server on {parsed.host}:{parsed.port}")
        uvicorn.run(app, host=parsed.host, port=parsed.port)
    except ImportError:
        print("foundry serve: fastapi/uvicorn not installed — install with: pip install foundry[server]")
        sys.exit(1)
    except RuntimeError as exc:
        print(f"foundry serve: initialization failed — {exc}")
        print("Ensure config files (model_routing.yaml, phase_graph.yaml, etc.) are present.")
        sys.exit(1)
