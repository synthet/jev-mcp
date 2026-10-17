---
type: Runbook
title: Vision evaluation foundation
description: Offline image preparation, frozen manifests, bounded live runs, and reproducible evaluation.
resource: evaluation.md
tags: [docs, evaluation, images]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.1
---

# Evaluation foundation (experimental)

Install with `uv sync --extra dev --extra evaluation`. The `vision` extra provides Pillow;
`evaluation` adds matplotlib. No command downloads datasets or installs conventional models.
The supplied scenes and answers are synthetic smoke fixtures, not measurements of Jev quality.

## Offline walkthrough

The checkout includes runnable [synthetic manifests](examples/vision/manifest.jsonl),
[templates](examples/vision/templates.json), and
[synthetic answers](examples/vision/synthetic-answers.jsonl).
Regenerate them, if needed, with:

```text
uv run python -m jev_mcp.vision.fixtures docs/examples/vision
```

Set `JEV_IMAGE_ROOTS` to the absolute `docs/examples/vision` directory in your environment.
This authorizes local image reads, separately from export. Then run:

```text
uv run jev-mcp vision run docs/examples/vision/manifest.jsonl --output .agent/vision/validated.jsonl
uv run jev-mcp vision evaluate docs/examples/vision/manifest.jsonl docs/examples/vision/synthetic-answers.jsonl --output .agent/vision/metrics.json --plot .agent/vision/metrics.png --overlay-dir .agent/vision/overlays
```

`run` defaults to validation only: no credentials, provider construction, or network calls.
Offline records have status `validated`, which never qualifies for a live resume.
Evaluation and overlays also run offline. The synthetic records deliberately have zero price
and fabricated usage/latency; use actual recorded runs to measure a model.

## Prepare and compare image variants

```text
uv run jev-mcp vision prepare photo.jpg --output .agent/vision/prepared --max-side 784 --max-side 1568 --quality 70 --quality 90
uv run jev-mcp vision prepare photo.jpg --output .agent/vision/tiles --tile-side 784
```

Preparation applies EXIF orientation, converts to RGB, shrinks proportionally, centers padding to
reach 280 pixels on each small side, strips metadata, and emits baseline JPEG or `--format png`.
Repeated resolution and quality options form a grid. All variants of a scene must retain the same
group ID and split. Output names are content hashes. `preparation.jsonl` records source/output
SHA-256 hashes, original/oriented/output sizes, crop, padding, and the affine matrix.

`prepare_image(..., crop=[left, top, right, bottom])` accepts oriented pixel edges. `tile_regions`
generates non-overlapping crops. Use an initial decision to select a tile, then explicitly run
refinement over that tile. There is no automatic paid refinement loop.
`map_box(box, receipt)` maps original fractional edges into prepared coordinates;
`inverse=True` maps model boxes back, including tiles and all EXIF orientations. It does not clip
padding into the source image. Annotations and evaluation boxes use **prepared fractional edges**;
map original annotations before writing the frozen manifest.

## Manifest contract

Each UTF-8 JSONL record contains:

| Field | Contract |
|---|---|
| `sample_id` | Unique stable identifier; do not encode labels |
| `group_id` | Shared by related scenes, variants, crops, or identities |
| `dataset` | Experiment task identifier |
| `split` | Frozen `train`, `validation`, or `test` |
| `template_version` | Version of the fixed question template |
| `inputs` | Only `state`, `questions`, optional `assets`, optional `long_context` |
| `annotations` | Evaluator-only mapping from question ID to label, binary event, score or box |
| `localization` | Box question ID → `{presence_question, image_alias}` |
| `local_predictions` | Optional evaluator-only precomputed baseline labels |

Asset paths in a manifest resolve relative to the manifest; the client still enforces
`JEV_IMAGE_ROOTS`. The runner exports validated in-memory bytes, never asset filenames.
`split_group(dataset, group_id, seed)` deterministically assigns 70/15/15 percent hash buckets.
Use the same dataset/group/seed across variants and freeze the result in each row. The loader
rejects duplicate IDs and groups crossing splits. Grouping must reflect real leakage risks:
the code cannot infer whether two different IDs represent the same subject.

Only `inputs` are used for inference. Reserved annotation/label/source-filename fields in state
are rejected. Keep source filenames and labels out of free text too; semantic leakage cannot be
detected deterministically. Criteria may legitimately name candidate categories. For hybrid
routing, explicitly place a precomputed local prediction in state, with its model/version,
and retain truth only in annotations. The starter hybrid and decomposed-reasoning manifests
demonstrate fixed independent questions; combine dependent decisions in application code.

## Optional live execution

Live studies are separate from this implementation. After explicit approval for the dataset
export, use all of `--live`, `--allow-export`, `--limit`, `--price-input` and `--price-output`.
Prices are currency units per million tokens, both recorded explicitly even when output is free.
They are not fetched or assumed. Use one currency throughout an experiment.

```text
uv run jev-mcp vision run manifest.jsonl --output runs.jsonl --live --allow-export --limit 10 --price-input 0.042 --price-output 0
```

This is an example price, not a billing guarantee. Experiments pin `jev-1.14.0` irrespective of
`JEV_MODEL`. Runs record actual typed answers, returned usage/model, latency, package/Python
versions, template and image hashes, request fingerprint, price, and sanitized failures.
Only matching successful records resume. Changed bytes, alias assignments, inputs, template,
model or runtime versions invalidate resume. Failed records retry; the sample limit bounds each
invocation. Use separate output files for different experiments. Do not run concurrent writers
against the same output file.

## Metrics and interpretation

Evaluation reports applicable Choice accuracy, macro F1, multiclass Brier/log loss and
confidence calibration; Noul accuracy, Brier, log loss, ROC AUC and equal-width ECE bins;
Score MAE/RMSE; localization IoU/precision/recall; confidence coverage-risk curves;
latency p50/p95; returned input/output tokens; and total cost from recorded usage and price.
Missing usage/prices yield unknown cost, never a guessed token estimate.

Box always returns coordinates. Configure a Noul presence companion for every optional target;
the evaluator discards boxes below `--presence-threshold` (default 0.5), then applies
`--iou-threshold` (default 0.5). An absent target uses annotation `null`; present targets use
fractional edges. Missed positive targets contribute zero IoU. Wrong retained locations count as
both a missed positive and a false positive. MCP responses retain the original Box judgment.
Tune thresholds on validation groups, then freeze them for test evaluation.

All outputs are local. Dataset downloads, conventional-model training/installation, paid studies,
and production deployment remain separate work.
