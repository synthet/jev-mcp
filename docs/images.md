---
type: Runbook
title: Image inputs
description: Explicit image and Box opt-ins, validated assets, references and path boundaries.
resource: images.md
tags: [docs, mcp, images, box]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.1
---

# Image inputs (experimental)

Install optional decoding support with `uv sync --extra vision` (development and evaluation
extras also include Pillow). TypeSafe labels images, Box and long context experimental.
They remain disabled by default. See the [API contract](api.md) and [evaluation workflow](evaluation.md).

Every tool takes `assets`, `allow_images=false` and `long_context=false`.
Assets map simple aliases to either absolute local paths, `{path: absolute_path}`, or
`{type: "image", data_base64: "...", format: "png"|"jpg"|"jpeg"}`.
References use `{{image:alias}}` anywhere inside nested state, instructions or criteria,
including inside text. Unknown, malformed and unused references are rejected.
The earlier `images` local-path map remains supported; pass only one asset map.

Local files require `JEV_IMAGE_ROOTS`: absolute allowed directories separated by `;` on Windows
and `:` elsewhere. Paths must be absolute and resolve inside a configured root, including
symlinks and junctions. Without roots, local files are disabled; base64 assets still work.
Every image request separately requires `allow_images=true`. The server sends only the
documented `TypeSafe-Danger-Zone-Images: true` header, never arbitrary caller headers.

```json
{
  "state": {"photo": "{{image:photo}}"},
  "assets": {"photo": {"type": "image", "format": "png", "data_base64": "<base64 PNG>"}},
  "allow_images": true,
  "model": "jev-1.14.0",
  "questions": {
    "present": {"type": "noul", "instructions": "Is a red mug visible in state.photo?"},
    "where": {"type": "box", "instructions": "The red mug in state.photo"}
  }
}
```

The client uses SDK Image objects and multipart transport for both input styles.
Only decoded bytes leave the machine; local asset filenames are not sent.
Instructions may include references such as `"Compare state.photo with {{image:reference}}"`.

| Check | Enforced policy |
|---|---|
| Format | Fully decoded PNG/JPEG stills; animated PNGs, truncated and damaged files rejected |
| Dimensions | Each side 280–1568 pixels; preprocessing is explicit |
| File size | 16 MiB decoded per image, 32 MiB aggregate, at most 16 aliases |
| Request expansion | 32 MiB local multipart/expanded safeguard, accounting for repeated references and decoded RGB size |
| Image model | Pinned Jev 1.13+ or `jev-preview`; Box requires 1.14+ |
| Box answer | Finite normalized edges, strictly positive area, nullable finite confidence |
| Long context | Independent `long_context=true` enables the documented long-context header and a bounded 4 MB text budget |

The local expansion estimate is conservative. Provider re-encoding and token counting may still
reject a locally valid request. Server responses and errors remain bounded and sanitized.

Box always returns a location even for missing targets. MCP preserves raw boxes; application code
must gate optional targets using the companion Noul and a validated threshold.
Images count toward returned `usage.input_tokens`; compute cost from actual usage and recorded price.

Upstream: [images and limits](https://docs.typesafe.ai/images),
[Box](https://docs.typesafe.ai/primitives/box), and [long context](https://docs.typesafe.ai/models).
