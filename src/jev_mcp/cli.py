"""CLI entry for Jev MCP."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jev-mcp", description="TypeSafe Jev MCP server")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Run the stdio MCP server")
    doctor = commands.add_parser("doctor", help="Check local readiness without calling TypeSafe")
    doctor.add_argument("--json", action="store_true", help="Print structured diagnostics")
    doctor.add_argument("--live", action="store_true", help="Make one live diagnostic API call")
    from .vision.cli import configure, execute
    configure(commands)
    args = parser.parse_args(argv)

    if args.command == "vision":
        return execute(args)

    if args.command == "doctor":
        import json
        from functools import partial
        from pathlib import Path

        import anyio

        from .doctor import diagnose
        from .dotenv_util import load_credential_env

        source_root = Path(__file__).resolve().parents[1]
        project_root = source_root.parent if source_root.name == "src" else Path.cwd()
        load_credential_env(project_root=project_root)
        report = anyio.run(partial(diagnose, project_root=project_root, live=args.live))
        print(json.dumps(report, indent=2) if args.json else
              "\n".join(f"{key}: {value}" for key, value in report.items()),
              file=sys.stdout if args.json else sys.stderr)
        return 0 if report["ready"] else 1

    if args.command == "mcp":
        from pathlib import Path

        from .dotenv_util import load_credential_env
        from .mcp_server import run_stdio

        source_root = Path(__file__).resolve().parents[1]
        project_root = source_root.parent if source_root.name == "src" else Path.cwd()
        load_credential_env(project_root=project_root)
        run_stdio()
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
