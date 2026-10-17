---
type: Source-of-Truth Map
title: Canonical Sources
description: Authority map — the single source of truth for each contract, convention, and config in this project.
resource: CANONICAL_SOURCES.md
tags: [docs, governance, authority]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Canonical sources

Agents and contributors must check this map before inventing API paths, schema names, config keys, or
status values. Fill in the right column as your project grows; the left column is the reusable
question.

| Contract / convention | Source of truth (fill in) |
|-----------------------|---------------------------|
| Public MCP tool names | [`../src/jev_mcp/mcp_server.py`](../src/jev_mcp/mcp_server.py) (`jev_choice`, `jev_score`, `jev_noul`, `jev_system_one`, `jev_box`) |
| Env keys (`JEV_TOKEN`, `TYPESAFE_API_KEY`, `JEV_MODEL`, `JEV_TIMEOUT_SECONDS`, `JEV_IMAGE_ROOTS`) | [`../env.example`](../env.example), [`../src/jev_mcp/client.py`](../src/jev_mcp/client.py) |
| Default Jev model pin | `JEV_MODEL` / `jev-1.14.0` in [`../src/jev_mcp/client.py`](../src/jev_mcp/client.py) |
| Public API shape | TypeSafe System One (`Choice` / `Score` / `Noul` / `Box`) via `typesafe-sdk` |
| Public tool parameters and budgets | [API reference](api.md), [image assets](images.md) |
| Frozen manifests and evaluation | [Evaluation workflow](evaluation.md), `src/jev_mcp/vision/` |
| Data model / schema | Normalized answer envelopes in [`../src/jev_mcp/normalize.py`](../src/jev_mcp/normalize.py) |
| Config keys | [`../env.example`](../env.example) |
| Status / state enums | Error codes in [`../src/jev_mcp/errors.py`](../src/jev_mcp/errors.py) |
| Domain vocabulary | TypeSafe System One docs (`docs.typesafe.ai`) |
| Build / test / lint commands | [`../AGENTS.md`](../AGENTS.md) |
| Codex project configuration | [`.codex/config.toml`](../.codex/config.toml) and [`.codex/README.md`](../.codex/README.md) |
| Optional file-search MCP (fff) | [fff repo](https://github.com/dmtrKovalenko/fff); template keys `fff-mcp` / `jev-fff` in [`.cursor/mcp.example.json`](../.cursor/mcp.example.json) |
| CLI tooling skills spec | [`.agent/cli-tools-skills-spec.md`](../.agent/cli-tools-skills-spec.md) |
| CLI install tier order | [`.claude/skills/cli-tools-overview/references/install-tiers.md`](../.claude/skills/cli-tools-overview/references/install-tiers.md) |
| Agent CLI environment (PATH, Cursor restart) | [`.claude/skills/cli-tools-overview/references/agent-environment.md`](../.claude/skills/cli-tools-overview/references/agent-environment.md) |
| Agent assets (rules/commands/skills/agents) | [`ai-workflow/README.md`](ai-workflow/README.md) |
| Safety rules | [`../.agent/SAFETY.md`](../.agent/SAFETY.md) |
| Wiki conventions | [`WIKI_SCHEMA.md`](WIKI_SCHEMA.md) |

**Rule:** code and the written contract must never disagree. If you change one, change the other in
the same PR (see [`../.agent/workflows/cross_repo_contract_change.md`](../.agent/workflows/cross_repo_contract_change.md)).
