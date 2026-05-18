"""Standalone bootstrap entry: python -m sdlc_mcp.bootstrap"""

from sdlc_mcp.bootstrap.engine import BootstrapEngine


def main() -> int:
    engine = BootstrapEngine()
    changed = engine.ensure_workspace()
    print(f"Bootstrap {'complete' if changed else 'already up to date'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
