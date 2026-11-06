# AI Agents Configuration — Jev MCP

## Overview

This repo ships agent scaffolding for Claude Code, Cursor, and Codex: commands, skills, subagents,
safety rules, an `.agent/` governance hub, a project-memory subsystem, and OKF docs tooling. This
file is the **source of truth** for how agents build/test/run and which tools they may use.

## Authoring & skill source of truth

- **Canonical** assets are authored under `.claude/` (+ `.agent/`).
- The **`.cursor/`** tree and Codex-native **`.agents/skills/`** + **`.codex/agents/`** trees are
  **generated** by `python scripts/sync_assistant_trees.py` — do not hand-edit generated files.
- When you change a skill/command/agent, run the sync and commit all generated mirrors in the **same PR**
  (see [`.agent/SKILL_CHANGE_AST10_REVIEW.md`](.agent/SKILL_CHANGE_AST10_REVIEW.md)).

## Commands

```bash
pip install -e ".[dev]"   # build + test deps
python -m pytest          # unit tests (mocked TypeSafe; no live API)
ruff check src tests      # lint
jev-mcp mcp               # stdio MCP server (requires JEV_TOKEN)
```

## MCP servers

- Define project servers in [`.mcp.json`](.mcp.json) (Claude Code), copy
  [`.cursor/mcp.example.json`](.cursor/mcp.example.json) → `.cursor/mcp.json` (gitignored) for Cursor,
  and use [`.codex/config.toml`](.codex/config.toml) or `~/.codex/config.toml` for Codex.
- **Naming:** `<scope>-<role>-*` (e.g. `jev-data`, `jev-diag`).
- **Surface:** prefer a compact **`search` + `dispatch`** pair over dozens of raw tools when the
  domain is large.
- **Secrets via env only**, never CLI args. Reload the MCP client after changing keys.
- User-level `~/.cursor/mcp.json` holds cross-repo tools; project keys live in this repo.

### Workstation bootstrap (`jev-rw-systemone` + `jev-mcp` skill)

One command wires the **same** stdio server and copies the **`jev-mcp`** decision skill to active
projects and user-level Codex/Gemini skill dirs:

```bash
python scripts/install_jev_mcp_workstation.py   # requires uv; optional JEV_MCP_ROOT
jev-mcp doctor                                  # credential + MCP handshake (no live API spend)
```

| Client | Config updated by installer |
|--------|-----------------------------|
| **Cursor** | `~/.cursor/mcp.json` + this repo's `.cursor/mcp.json` |
| **Claude Code** | `~/.claude.json` + project [`.mcp.json`](.mcp.json) |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **Codex** | `~/.codex/config.toml` (`[mcp_servers.jev-rw-systemone]`) + `~/.codex/skills/jev-mcp/` |
| **Gemini CLI** | `~/.gemini/settings.json` + `~/.gemini/skills/jev-mcp/` |
| **Antigravity** | `~/.gemini/antigravity/mcp_config.json` and `~/.gemini/config/mcp_config.json` |

Reload MCP in each IDE/CLI after install. Secrets stay in checkout `.env` via `JEV_ENV_FILE`; the
installer never writes tokens into JSON/TOML.

**Decision-making:** agents should load the **`jev-mcp`** skill (canonical:
[`.claude/skills/jev-mcp/SKILL.md`](.claude/skills/jev-mcp/SKILL.md); mirrored under `.cursor/` and
`.agents/` after sync) whenever routing, reranking, evidence checks, or yes/no gates need typed
System One judgments instead of invented probabilities.


[fff](https://github.com/dmtrKovalenko/fff) provides fast indexed repo search via MCP (`ffgrep`, `fffind`, `fff-multi-grep`). **Opt-in** — clones work without it.

1. Install `fff-mcp` from fff releases (Windows: `%LOCALAPPDATA%\fff-mcp\bin\fff-mcp.exe`; add to PATH).
2. Copy the `fff-mcp` entry from [`.cursor/mcp.example.json`](.cursor/mcp.example.json) `_examples` into gitignored `.cursor/mcp.json`, or register at user level as `fff`.
3. Rename server key to `jev-fff` in bootstrapped projects if desired.
4. Reload MCP in Cursor (Settings → MCP, or restart IDE).
5. Agents: prefer fff for repeated repo-wide search when connected; one-off probes may still use `rg`/`fd` (see `search-tool-selection` skill).

### Optional: Graphify knowledge-graph MCP

[Graphify](https://github.com/Graphify-Labs/graphify) turns a repo into a queryable local knowledge graph (`graphify-out/`). **Opt-in** — clones work without it. PyPI package is `graphifyy`; CLI is `graphify`.

1. `uv tool install graphifyy` (for MCP: `uv tool install "graphifyy[mcp]"`).
2. Build a graph in the project: `graphify .` (writes `graphify-out/`, gitignored in this scaffold).
3. Copy `_examples.proj-ro-graphify` from [`.cursor/mcp.example.json`](.cursor/mcp.example.json) / [`.mcp.json`](.mcp.json) into gitignored `.cursor/mcp.json` (or Claude `.mcp.json` `mcpServers`).
4. Reload MCP in Cursor (Settings → MCP, or restart IDE).
5. Agents: prefer Graphify for architecture / path / community questions when connected; keep text search on rg/fff (see `graphify-knowledge-graph` skill).
6. **Do not** run bare `graphify cursor install` or `graphify install --project` here — those fight `.claude/` → sync SoT. Prefer this docs + MCP path, or a user-global install outside the repo.

## Available tools

<!-- BEGIN MCP TOOL INVENTORY -->
| Server (example key) | Tools (when connected) | Notes |
|----------------------|------------------------|-------|
| `jev-rw-systemone` | `jev_choice`, `jev_score`, `jev_noul`, `jev_system_one`, `jev_box` | TypeSafe System One; set `JEV_TOKEN`; see `.mcp.json` |
| `fff-mcp` / `jev-fff` | `ffgrep`, `fffind`, `fff-multi-grep` | Opt-in; see `.cursor/mcp.example.json` |
| `graphify-mcp` / `jev-graphify` | `query_graph`, `get_node`, `get_neighbors`, `shortest_path`, … | Opt-in; needs `graphify-out/graph.json`; see `_examples.proj-ro-graphify` |
<!-- END MCP TOOL INVENTORY -->


## Default tool permissions

- **Default mode is read-only.** The active Claude Code allowlist in [`.claude/settings.json`](.claude/settings.json) permits only read-oriented operations: `git status`, `git diff:*`, `git log:*`, and `WebSearch`.
- **Opt into local writes intentionally.** When a maintainer wants an agent to stage or commit local repository changes, copy [`.claude/settings.write.example.json`](.claude/settings.write.example.json) to a local/user settings file or otherwise merge only the needed entries (`Bash(git add:*)`, `Bash(git commit:*)`) into the active allowlist. Do not broaden permissions by default.
- **Remote writes are higher risk than local writes.** `gh pr:*`, `gh issue:*`, and `gh project:*` can mutate GitHub state and notify collaborators. Enable them only for a specific task and verify the target repo/project before use.
- **External export requires explicit approval.** Sending source, prompts, logs, artifacts, or review bundles to external services/providers is not covered by local-write approval; get explicit approval for the export and exclude secrets.
- **Seeded projects inherit this safer default.** Because `.claude/settings.json` is part of the scaffold, newly bootstrapped projects start in read-only mode unless a maintainer deliberately opts into write permissions.

## Common workflows

`/spec → /plan → /implement → /test-and-fix → /pr-ready`. See
[`docs/ai-workflow/README.md`](docs/ai-workflow/README.md) for the full asset map and loop, and
[`.agent/workflows/`](.agent/workflows/) for playbooks.

## Git configuration — do not modify

Never modify `.git/config` or add non-standard git extensions (do not set
`extensions.worktreeConfig` or change `core.repositoryformatversion`). Embedded git libraries in
third-party tooling choke on non-standard extensions and break workspace resolution. If a worktree is
needed, use a temporary one and clean it up immediately.

## Test vocabulary

If the project has more than one test tier, disambiguate them here (one row per tier) so an agent
knows exactly which suite "E2E" means:

| You say | Canonical name | Where | How to run |
|---------|----------------|-------|------------|
| … | … | … | … |

## Coding-agent contract

- **Code style:** match the surrounding code; follow the repo's formatter/linter.
- **Package boundaries:** touch one module/package per task; use shared types. Do not reach across
  boundaries (UI ↔ data layer ↔ transport) without an explicit contract change.
- **Security (hard rules):** secrets via env/`secrets.json` only; validate external inputs;
  side-effecting/destructive ops require confirmation; never modify `.git/config`. See
  [`docs/security.md`](docs/security.md) and [`.agent/SAFETY.md`](.agent/SAFETY.md).
- **Change control:** minimal diffs, tests for behavior changes, no unrelated refactors.
- **Prohibited:** committing secrets, disabling/weakening tests to go green, drive-by reformatting,
  inventing API paths / config keys / schema names (check
  [`docs/CANONICAL_SOURCES.md`](docs/CANONICAL_SOURCES.md)).

## RCA / Failure Log

Append-only record of **non-obvious failures** and their root causes, so the next agent does not
re-debug them. Add an entry after `/test-and-fix` (or any debugging session) uncovers something
that was not obvious from the error message. Keep entries short: date, symptom, root cause, fix.

| Date | Symptom | Root cause | Fix / guard |
|------|---------|------------|-------------|
| _(none yet)_ | | | |
| 2026-09-22 | Missing credentials bypassed structured MCP errors; checkout `.env` was missed by CLI/direct stdio | Client construction preceded the error wrapper; package ancestry resolved to `src` | Construct inside wrapper; resolve checkout root; regression tests for all four tools and both entrypoints |
| 2026-09-22 | Reinstall could invalidate Codex config with duplicate server tables | Text replacement recognized only bare TOML table names | Handle quoted/whitespace headers and parse/compare the complete result before writing |
| 2026-10-16 | Workflow skills failed frontmatter validation with 186 findings | Command-derived wrappers omitted six metadata fields and retained command-relative/example links | Restore canonical command metadata, rebase real links, render hypothetical targets literally; validate before mirroring |

## AI workspace assets

| Asset | Location |
|-------|----------|
| Claude commands | `.claude/commands/*.md` |
| Claude skills | `.claude/skills/*/SKILL.md` |
| Claude subagents | `.claude/agents/*.md` |
| Claude rules | `.claude/rules/*.md` |
| Cursor mirror (generated) | `.cursor/{rules,commands,skills,agents}` |
| Codex skills (generated) | `.agents/skills/*/SKILL.md` |
| Codex subagents (generated) | `.codex/agents/*.toml` |
| Codex project config | `.codex/config.toml` |
| MCP templates/config | `.mcp.json`, `.cursor/mcp.example.json`, `.codex/config.toml` |
| Agent governance | `.agent/` |
| Project memory | `.agent-memory/` |
| Workflow playbooks | `.agent/workflows/*.md` |
| Workflow index | `docs/ai-workflow/README.md` |

<!-- BEGIN FRAMEWORK SETUP -->

## Shared agent setup

Project-specific instructions in this file and nested instruction files govern this workspace.
Reusable skills are authored in `.claude/skills/`; other harness trees are generated.
Run installed helpers relative to their skill directory; run project checks from this workspace.
Preserve user edits, credentials, model settings, permissions and unrelated configuration.
- Build: `uv sync`
- Test: `uv run pytest`
- Lint: `uv run ruff check .`

Installed library: 42 applicable skills. Synchronize explicitly; startup hooks never install updates.
<!-- END FRAMEWORK SETUP -->

<!-- FRAMEWORK RULE REFERENCES -->
Read the always-on project rules before working:
- `.claude/rules/karpathy-coding.md`
- `.claude/rules/safety-and-secrets.md`
- `.claude/rules/sdlc-core.md`
<!-- END FRAMEWORK RULE REFERENCES -->
