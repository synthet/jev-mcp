---
type: Technical Reference
title: Jev MCP API
description: Public tool parameters, typed answers, opt-in features, and bounded request contracts.
resource: api.md
tags: [docs, api, mcp]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.1
---

# Jev MCP API

All five tools return `{ok: true, result: {model, usage, answers}}` or a sanitized
`{ok: false, error: {code, message, details, retryable, next_steps}}` envelope.
Usage is returned token usage or `null`; unavailable confidence remains `null`.

| Tool | Required parameters | Additional parameter |
|---|---|---|
| `jev_choice` | `state`, `instructions`, `criteria` (object) | `question_id="answer"` |
| `jev_score` | `state`, `instructions`, `criteria` (ordered array) | `question_id="answer"` |
| `jev_noul` | `state`, `instructions` | Optional `criteria` object, `question_id` |
| `jev_box` | `state`, `instructions`, image assets and opt-in | `question_id="answer"` |
| `jev_system_one` | `state`, `questions` keyed by ID | `type: choice|score|noul|box` per question |

Every tool accepts `model`, `assets`, `allow_images=false`, and `long_context=false`.
The earlier `images` local-path map remains an alias; do not pass both maps.
State is a string, JSON object, or array. Instructions and criteria accept nested JSON content.
Question IDs are identifiers; put the full semantic question in instructions.

Default model: **`jev-1.14.0`**. Environment `JEV_MODEL` overrides it, and a per-request `model`
overrides the client default. Set `JEV_MODEL=jev-1.13.0` to retain the previous model.
Images and long context remain disabled unless explicitly enabled, regardless of model.
Only the documented `TypeSafe-Danger-Zone-Images` and `TypeSafe-Danger-Zone-Long-Context`
headers can be enabled; arbitrary headers are not exposed.

Local text budgets are 1,000,000 UTF-8 JSON bytes normally and 4,000,000 with `long_context=true`.
Both retain a 128-question limit, finite JSON validation, response size limit (512,000 bytes),
timeouts, cancellation and cleanup. These are local byte safeguards, not token-limit guarantees.
TypeSafe additionally enforces its own token and image processing budgets.

Answers are typed as Choice (`choice`, `confidence`, `probabilities`), Score (`score`, `confidence`,
`legend`, `probabilities`), Noul (`noul`), or Box (`box`, `confidence`). Box edges
`top`, `bottom`, `left`, `right` are finite fractions in [0,1]; top < bottom and left < right.
Box confidence can be `null`. Optional-target presence gates belong in application code.

See [image inputs](images.md) for assets and [evaluation](evaluation.md) for offline experiments.
Upstream contracts: [images](https://docs.typesafe.ai/images),
[Box](https://docs.typesafe.ai/primitives/box), [models](https://docs.typesafe.ai/models),
[Python SDK assets](https://docs.typesafe.ai/sdk/python/api/types/assets).
