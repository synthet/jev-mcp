"""Offline readiness checks; inference requires an explicit live option."""

import os
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

import anyio
from mcp import Client

from .client import JevClient, default_model, default_timeout
from .errors import JevMcpError
from .mcp_server import create_server


async def diagnose(*, project_root: Path, live: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {
        "live": live, "executable": sys.executable,
        "versions": {name: version(name) for name in ("jev-mcp", "mcp", "typesafe-sdk")},
        "credential_present": bool(
            os.environ.get("JEV_TOKEN") or os.environ.get("TYPESAFE_API_KEY")
        ),
        "env_files": {
            "project": (project_root / ".env").is_file(),
            **{key: bool(os.environ.get(key)) and Path(os.environ[key]).is_file()
               for key in ("JEV_ENV_FILE", "DOTENV_PATH")},
        },
        "mcp_handshake": False, "ready": False,
    }
    try:
        report.update(model=default_model(), timeout_seconds=default_timeout())
        with anyio.fail_after(10):
            async with Client(create_server()) as client:
                tools = await client.list_tools()
        report["tools"] = sorted(tool.name for tool in tools.tools)
        report["mcp_handshake"] = len(tools.tools) == 5
        if live:
            await JevClient().asystem_one(state="Diagnostic sample.", questions={
                "check": {"type": "noul", "instructions": "Is the state a short text?"},
            })
            report["live_ok"] = True
        report["ready"] = report["mcp_handshake"] and report["credential_present"]
    except JevMcpError as exc:
        report["error"] = exc.as_dict()
    except Exception:
        report["error"] = {"code": "diagnostic_failed", "message": "Local diagnostic failed."}
    return report
