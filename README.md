# Jev MCP

MCP server exposing TypeSafe Jev (System One) judgments to AI agents.

## Quick start

```bash
pip install -e ".[dev]"
cp env.example .env   # set JEV_TOKEN
jev-mcp mcp           # stdio MCP server
```

Or via the checkout launcher used by [`.mcp.json`](.mcp.json):

```bash
uv run --project . python scripts/run_jev_mcp.py
```

### Tools

| Tool | Purpose |
|------|---------|
| `jev_choice` | One Choice question |
| `jev_score` | One Score question |
| `jev_noul` | One Noul (yes/no probability) question |
| `jev_system_one` | Multiple typed questions against one state |

Secrets via env only (`JEV_TOKEN` preferred, `TYPESAFE_API_KEY` fallback). Default model pin: `jev-1.13.0` (`JEV_MODEL`).

### Workstation MCP (user-level)

Wire `jev-rw-systemone` into Claude Code, Claude Desktop, Cursor, Codex, Gemini, and Antigravity,
and install the portable `jev-mcp` skill into active sibling projects:

```bash
python scripts/install_jev_mcp_workstation.py
```

Requires `uv` on PATH. The installer points `JEV_ENV_FILE` at a local `.env` when found
(project `.env` or `D:\Projects\synthet-llm-wiki\.env`) and never writes the API key into config
files. Reload MCP in each client after running. Canonical skill: `.claude/skills/jev-mcp/`.

Agent scaffolding lives in `.claude/`, `.cursor/`, `.agents/`, `.codex/`, `.agent/`, and
`.agent-memory/`. Start with [`CLAUDE.md`](CLAUDE.md) and [`AGENTS.md`](AGENTS.md).
