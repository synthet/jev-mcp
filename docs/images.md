---
type: Runbook
title: Image inputs
description: How to send local PNG/JPEG images and Box questions to Jev 1.14+ through the MCP tools, and the safety limits that apply.
resource: images.md
tags: [docs, mcp, images, box, jev-1.14]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.1
---

# Image inputs (experimental)

Jev 1.14 accepts PNG and JPEG images and adds a `box` question type. TypeSafe labels
both "Dreamer-ready", meaning not production-ready: request shape, limits and accuracy
may change. Treat answers as evidence, never as authorization to act.

## Enable

Images are **off by default**, because they are uploaded to a paid external service.
Set `JEV_IMAGE_ROOTS` in the server environment (for example the checkout `.env`) to
the directories images may be read from, separated by `;` on Windows and `:` elsewhere:

```text
JEV_IMAGE_ROOTS=D:\Projects\image-scoring-backend\.agent\scratch\neardupe-signals\crops
```

Reload the MCP client afterwards.

## Call

Every tool takes an optional `images` map of `{alias: local path}`. Put the exact
string `"{{image:<alias>}}"` as a **whole value** in `state`, and refer to that state
field by name in instructions:

```json
{
  "state": {"a": "{{image:a}}", "b": "{{image:b}}"},
  "images": {"a": "D:\\...\\crops\\69365_base.png", "b": "D:\\...\\crops\\69362_base.png"},
  "questions": {
    "same_head": {"type": "noul",
                  "instructions": "Does the bird's head face the same direction in `a` and `b`?"},
    "bird_present": {"type": "noul", "instructions": "Is a bird visible in `a`?"},
    "bird": {"type": "box", "instructions": "the bird in `a`"}
  },
  "model": "jev-1.14.0"
}
```

The server sends the `TypeSafe-Danger-Zone-Images: true` opt-in header for you.

## Rules enforced by the server

| Check | Behaviour |
|---|---|
| Allowed directories | Paths are resolved (symlinks, `..`) and must lie inside `JEV_IMAGE_ROOTS` |
| Format | `.png`/`.jpg`/`.jpeg` suffix and matching PNG/JPEG magic bytes |
| Size | Each side 280–1568 px (Jev rejects, never resizes); at most 16 MiB per image, 32 MiB total, 16 images |
| Placeholders | Unknown aliases and unused aliases are rejected |
| Model | Image requests need a pinned `jev-1.14.x`+ model or `jev-preview` |
| Box | Box questions need images; Box **always** returns a box, so ask a Noul presence question and gate on it in host code |

Images count as ordinary input tokens. Check `usage.input_tokens` in the response to
measure cost before running batches.
