---
name: jev-mcp
description: Use for TypeSafe Jev Choice, Score, Noul or Box judgments over text, structured evidence or opt-in images; reranking, evidence checks, routing, localization, or jev_choice, jev_score, jev_noul, jev_box and jev_system_one.
capability: "TypeSafe System One judgments and offline evaluation via jev-mcp"
side_effect_level: external_export
approval_required: true
requires_tools: "MCP server jev-rw-systemone; optional jev-mcp vision CLI"
output_schema: "Normalized judgment envelope with model, usage, and typed answers"
risk_class: high
---

# Jev MCP (System One)

Prefer tools from **jev-rw-systemone** when connected. Calls export supplied evidence to the paid
TypeSafe service. Obtain explicit approval for that export unless already authorized in the session.
Keep credentials in environment variables and omit secrets from evidence.

| Tool | Use |
|---|---|
| jev_choice | Select one label from fixed criteria |
| jev_score | Ordered rubric, score from 0 to N-1 |
| jev_noul | Probability of a yes/no proposition |
| jev_box | Experimental location as normalized top/bottom/left/right |
| jev_system_one | Batch independent questions over shared evidence |

The default is **jev-1.14.0**. Preserve existing environment/per-request overrides.
Set JEV_MODEL=jev-1.13.0 to retain the previous default. Image and long-context features remain
disabled until explicitly enabled on each request.

## Call workflow

1. Verify the server is connected. Do not invent probabilities when unavailable.
2. Supply bounded raw evidence in state, and the full question meaning in instructions.
3. Batch independent questions. Question IDs are labels; one answer cannot feed another in a batch.
4. Include a no-match Choice option when needed. Score criteria run from low to high.
5. Read ok/error envelopes. Return relevant typed answers, usage and model. Nullable confidence
   stays unknown. A Noul near 0.5 indicates uncertainty.
6. Keep execution, arithmetic, permissions and deterministic gates in host code. Confidence never
   grants authorization and never proves a claim.

## Images, Box and long context (experimental)

All five tools accept assets, allow_images=false and long_context=false.
Use assets={alias: absolute_path} or
assets={alias: {type: image, data_base64: "...", format: png|jpeg}}.
Local paths require server-configured JEV_IMAGE_ROOTS; roots alone do not opt into image export.
The earlier images local-path map is also accepted; do not pass both maps.

Set allow_images=true and reference **{{image:alias}}** inside state, instructions, or criteria,
including nested content and embedded text. Every asset must be referenced. PNG/JPEG stills must
decode successfully, have each side 280–1568 px, and fit the bounded request budgets.
Images work on Jev 1.13+; Box requires Jev 1.14+. The SDK uploads multipart image bytes.

Box always returns a box, even when the target is absent. Pair optional targets with a Noul presence
question and discard boxes below a host-configured threshold. MCP returns the raw Box judgment.
Do not treat a location as evidence of presence.

Set long_context=true only for a request needing the larger context. Local limits remain:
4,000,000 text bytes with opt-in, 1,000,000 otherwise, 128 questions and bounded responses.
There are no arbitrary header overrides. Audio/video need conversion into supported evidence.

## Offline evaluation

Use jev-mcp vision prepare|run|evaluate. Run defaults to offline validation and does not export data.
The vision extra installs image decoding; evaluation adds plots.
Prepare applies orientation, RGB conversion, resize/padding and metadata stripping.
Keep labels/source filenames in evaluator-only manifest fields; never put them in inference state.
Live studies require explicit export approval plus --live --allow-export --limit and recorded prices.
Use frozen group splits, pinned model/template versions, presence-gated localization and returned
usage for cost. Synthetic fixtures validate the workflow; they do not measure model quality.

For server installation use the repository README and scripts/install_jev_mcp_workstation.py.
Do not change workstation configuration as part of a judgment request.
