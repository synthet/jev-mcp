"""CLI entry for Jev MCP."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-mcp", description="TypeSafe Jev MCP server")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Run the stdio MCP server")
    args = parser.parse_args(argv)

    if args.command == "mcp":
        from pathlib import Path

        from .dotenv_util import load_credential_env
        from .mcp_server import run_stdio

        load_credential_env(project_root=Path(__file__).resolve().parents[1])
        run_stdio()
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
