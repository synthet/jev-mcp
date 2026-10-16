"""One-shot local installer: user-level MCP for Jev across agent hosts.

Not a product entrypoint — run manually for workstation setup.
Wires Claude Code, Claude Desktop, Cursor, Codex, Gemini, and Antigravity.
Secrets stay in the process environment (JEV_TOKEN / TYPESAFE_API_KEY); never written here.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import sys
import tomllib

ROOT = pathlib.Path(os.environ.get("JEV_MCP_ROOT", r"D:\Projects\jev-mcp")).resolve()
SERVER_KEY = "jev-rw-systemone"
SCRIPT = ROOT / "scripts" / "run_jev_mcp.py"
SKILL_NAME = "jev-mcp"
CANONICAL_SKILL = ROOT / ".claude" / "skills" / SKILL_NAME / "SKILL.md"

# First-party, recently active projects (exclude huge upstream mirrors like zed).
TARGET_PROJECTS = [
    "image-scoring",
    "image-scoring-pipeline",
    "image-scoring-gallery",
    "image-scoring-skills",
    "enshrouded-tools",
    "synthet-code-framework",
    "chronix",
    "project-twelve",
    "heroes-templates",
    "warp",
    "video-gallery",
    "subagent-orchestrator",
    "birdweather-telegram-bot",
    "nwn-modules",
    "image-scoring-ui",
    "image-scoring-model",
    "synthet-llm-wiki",
]


def resolve_uv() -> str:
    env = os.environ.get("UV_EXE")
    if env and pathlib.Path(env).exists():
        return env
    which = shutil.which("uv")
    if which:
        return which
    raise SystemExit("ERROR: uv not found on PATH (set UV_EXE or install uv)")


def mcp_entry() -> dict:
    entry: dict = {
        "command": resolve_uv(),
        "args": ["run", "--project", str(ROOT), "python", str(SCRIPT)],
        # Always point at the project .env path (gitignored). Launcher also loads
        # ROOT/.env directly; JEV_ENV_FILE is a fallback for clients that clear cwd.
        "env": {"JEV_ENV_FILE": str(ROOT / ".env")},
    }
    return entry


def _atomic_write_text(path: pathlib.Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def upsert_json_mcp(path: pathlib.Path, *, create: bool = False, dry_run: bool = False) -> bool:
    if not path.exists():
        if not create:
            print(f"SKIP missing {path}")
            return False
        data: dict = {"mcpServers": {}}
    else:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            print(f"SKIP non-object JSON {path}", file=sys.stderr)
            return False
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        print(f"SKIP mcpServers is not an object in {path}", file=sys.stderr)
        return False
    servers[SERVER_KEY] = mcp_entry()
    payload = json.dumps(data, indent=2) + "\n"
    if dry_run:
        print(f"DRY json mcp -> {path}")
        return True
    _atomic_write_text(path, payload)
    print(f"OK json mcp -> {path}")
    return True


def upsert_codex_toml(path: pathlib.Path, *, dry_run: bool = False) -> None:
    entry = mcp_entry()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    expected = tomllib.loads(text)
    expected.setdefault("mcp_servers", {})[SERVER_KEY] = entry
    escaped_key = re.escape(SERVER_KEY)
    server_key = rf'(?:{escaped_key}|"{escaped_key}"|\'{escaped_key}\')'
    for suffix in ("", ".env"):
        env_suffix = r'\s*\.\s*(?:env|"env"|\'env\')' if suffix else ""
        pattern = re.compile(
            rf"^[ \t]*\[[ \t]*mcp_servers\s*\.\s*{server_key}{env_suffix}[ \t]*\]"
            r"[^\n]*\n?[\s\S]*?(?=^[ \t]*\[|\Z)",
            re.MULTILINE,
        )
        text = pattern.sub("", text)
    block = (
        f"[mcp_servers.{SERVER_KEY}]\n"
        f"command = {json.dumps(entry['command'])}\n"
        f"args = {json.dumps(entry['args'])}\n"
    )
    env = entry.get("env") or {}
    if env:
        block += f"\n[mcp_servers.{SERVER_KEY}.env]\n"
        for key, value in env.items():
            block += f"{key} = {json.dumps(value)}\n"
    if text and not text.endswith("\n"):
        text += "\n"
    text += "\n" + block
    # Refuse unsupported table layouts rather than damaging unrelated settings.
    if tomllib.loads(text) != expected:
        raise ValueError("Cannot safely update Codex MCP tables; config was not changed.")
    if dry_run:
        print(f"DRY codex toml -> {path}")
        return
    _atomic_write_text(path, text)
    print(f"OK codex toml -> {path}")


def portable_skill_body() -> str:
    if not CANONICAL_SKILL.is_file():
        raise SystemExit(f"ERROR: canonical skill missing: {CANONICAL_SKILL}")
    return CANONICAL_SKILL.read_text(encoding="utf-8")


def write_skill(dest_dir: pathlib.Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    skill = dest_dir / "SKILL.md"
    # Keep jev-mcp's own canonical Claude skill; only install portable copies elsewhere.
    try:
        if dest_dir.resolve() == (ROOT / ".claude" / "skills" / SKILL_NAME).resolve():
            print(f"KEEP canonical skill -> {skill}")
            return
    except ValueError:
        pass
    skill.write_text(portable_skill_body(), encoding="utf-8", newline="\n")
    print(f"OK skill -> {skill}")


def install_project_skills(project: str) -> None:
    root = pathlib.Path(r"D:\Projects") / project
    if not root.is_dir():
        print(f"SKIP missing project {root}")
        return

    # Canonical skill lives under jev-mcp/.claude; mirrors come from sync_assistant_trees.
    if root.resolve() == ROOT.resolve():
        print(f"KEEP jev-mcp canonical skill tree -> {root / '.claude' / 'skills' / SKILL_NAME}")
        return

    targets: list[pathlib.Path] = []
    if (root / ".claude").exists() or (root / ".claude" / "skills").exists():
        targets.append(root / ".claude" / "skills" / SKILL_NAME)
    if (root / ".cursor" / "skills").exists():
        targets.append(root / ".cursor" / "skills" / SKILL_NAME)
    if (root / ".agents" / "skills").exists():
        targets.append(root / ".agents" / "skills" / SKILL_NAME)
    if not targets:
        targets.append(root / ".cursor" / "skills" / SKILL_NAME)

    for dest in targets:
        write_skill(dest)


def main() -> int:
    if not SCRIPT.is_file():
        print(f"ERROR: launcher missing: {SCRIPT}", file=sys.stderr)
        return 1
    project_env = ROOT / ".env"
    if not project_env.is_file():
        print(
            f"WARN: {project_env} missing — put JEV_TOKEN there (copy from env.example). "
            "MCP will not authenticate until the file exists.",
            file=sys.stderr,
        )
    elif not (os.environ.get("JEV_TOKEN") or os.environ.get("TYPESAFE_API_KEY")):
        print(
            f"NOTE: MCP entry uses JEV_ENV_FILE={project_env} "
            "(gitignored; secret not written into configs).",
            file=sys.stderr,
        )

    home = pathlib.Path.home()
    # Claude Code (user-scope), Cursor, Claude Desktop, Gemini CLI settings
    upsert_json_mcp(home / ".cursor" / "mcp.json")
    upsert_json_mcp(home / ".claude.json")
    upsert_json_mcp(home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json")
    upsert_json_mcp(home / ".gemini" / "settings.json")
    # Antigravity IDE (legacy path still active on this workstation) + shared config path
    upsert_json_mcp(home / ".gemini" / "antigravity" / "mcp_config.json", create=True)
    upsert_json_mcp(home / ".gemini" / "config" / "mcp_config.json", create=True)
    # Codex
    upsert_codex_toml(home / ".codex" / "config.toml")

    # Project-local Cursor MCP for this checkout
    proj_cursor = ROOT / ".cursor" / "mcp.json"
    if proj_cursor.exists():
        data = json.loads(proj_cursor.read_text(encoding="utf-8-sig"))
    else:
        example = ROOT / ".cursor" / "mcp.example.json"
        data = (
            json.loads(example.read_text(encoding="utf-8"))
            if example.exists()
            else {"mcpServers": {}}
        )
    data.setdefault("mcpServers", {})[SERVER_KEY] = mcp_entry()
    proj_cursor.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"OK project cursor mcp -> {proj_cursor}")

    # Portable skills into active sibling projects + user-level Gemini/Codex skill trees.
    for name in TARGET_PROJECTS:
        install_project_skills(name)
    for dest in (
        home / ".gemini" / "skills" / "jev-mcp",
        home / ".codex" / "skills" / "jev-mcp",
    ):
        write_skill(dest)

    print("DONE")
    print(f"Server key: {SERVER_KEY}")
    print(f"Launch: {json.dumps(mcp_entry())}")
    print("Reload MCP in each client after setting JEV_TOKEN in that client's environment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
