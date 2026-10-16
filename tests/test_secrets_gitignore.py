"""Guardrails: gitignored secret paths must never be tracked."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MUST_NOT_BE_TRACKED = frozenset(
    {
        ".env",
        "secrets.json",
        ".cursor/mcp.json",
        ".claude/settings.local.json",
    }
)


def _tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def test_gitignored_secret_files_are_not_tracked():
    tracked = _tracked_paths()
    leaked = sorted(MUST_NOT_BE_TRACKED & tracked)
    assert not leaked, f"Remove from git index (keep local): {', '.join(leaked)}"


def test_secrets_ci_scan_passes():
    result = subprocess.run(
        [sys.executable, "scripts/ci/check_secrets.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
