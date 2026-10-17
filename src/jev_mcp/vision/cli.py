"""CLI adapters for the offline vision workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..errors import JevMcpError, error


def configure(commands):
    vision = commands.add_parser("vision", help="Experimental offline-first vision evaluation")
    actions = vision.add_subparsers(dest="vision_command", required=True)
    prepare = actions.add_parser("prepare", help="Orient, resize, pad, and strip image metadata")
    prepare.add_argument("images", nargs="+", type=Path)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument(
        "--max-side", action="append", type=int, help="Repeat for resolution variants"
    )
    prepare.add_argument("--quality", action="append", type=int, help="Repeat for JPEG variants")
    prepare.add_argument("--format", choices=("png", "jpeg"), default="jpeg")
    prepare.add_argument("--tile-side", type=int, help="Also prepare tiles in oriented coordinates")
    run = actions.add_parser("run", help="Validate offline; explicit options enable paid execution")
    run.add_argument("manifest", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--live", action="store_true")
    run.add_argument("--allow-export", action="store_true")
    run.add_argument("--limit", type=int)
    run.add_argument("--price-input", type=float, help="Currency units per million input tokens")
    run.add_argument("--price-output", type=float, help="Currency units per million output tokens")
    evaluate = actions.add_parser("evaluate", help="Compute metrics from recorded answers, offline")
    evaluate.add_argument("manifest", type=Path)
    evaluate.add_argument("runs", type=Path)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--presence-threshold", type=float, default=0.5)
    evaluate.add_argument("--iou-threshold", type=float, default=0.5)
    evaluate.add_argument("--plot", type=Path)
    evaluate.add_argument("--overlay-dir", type=Path)


def execute(args) -> int:
    try:
        if args.vision_command == "prepare":
            from .prepare import prepare_image, tile_regions

            records = []
            for source in args.images:
                for side in args.max_side or [1568]:
                    for quality in args.quality or [90]:
                        prepared = prepare_image(
                            source, args.output, max_side=side, quality=quality, format=args.format
                        )
                        records.append(prepared)
                        if args.tile_side:
                            for crop in tile_regions(*prepared["oriented_size"], args.tile_side):
                                records.append(
                                    prepare_image(
                                        source,
                                        args.output,
                                        max_side=side,
                                        quality=quality,
                                        format=args.format,
                                        crop=crop,
                                    )
                                )
            receipt = args.output / "preparation.jsonl"
            receipt.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            report = {"prepared": len(records), "receipt": str(receipt)}
        elif args.vision_command == "run":
            from .runner import run_manifest

            report = run_manifest(
                args.manifest,
                args.output,
                live=args.live,
                allow_export=args.allow_export,
                limit=args.limit,
                price_input=args.price_input,
                price_output=args.price_output,
            )
        else:
            from .manifest import load_manifest, read_jsonl
            from .metrics import evaluate, plot_report

            if args.output.resolve() in (args.manifest.resolve(), args.runs.resolve()):
                raise error("invalid_input", "Evaluation output must differ from its inputs.")
            if args.plot and args.plot.resolve() in (
                args.manifest.resolve(),
                args.runs.resolve(),
                args.output.resolve(),
            ):
                raise error("invalid_input", "Plot output must differ from data and report paths.")
            samples, runs = load_manifest(args.manifest), read_jsonl(args.runs)
            report = evaluate(
                samples,
                runs,
                presence_threshold=args.presence_threshold,
                iou_threshold=args.iou_threshold,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
            if args.plot:
                plot_report(report, args.plot)
            if args.overlay_dir:
                _overlays(
                    samples, runs, args.manifest.parent, args.overlay_dir, args.presence_threshold
                )
        print(json.dumps(report, allow_nan=False))
        return 1 if report.get("failed") else 0
    except JevMcpError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}), file=sys.stderr)
        return 2
    except (OSError, ValueError, KeyError, TypeError):
        err = {"code": "vision_failed", "message": "Invalid vision input or inaccessible output."}
        print(json.dumps({"ok": False, "error": err}), file=sys.stderr)
        return 2


def _overlays(samples, runs, base, output, threshold):
    from .manifest import fingerprint, inference_inputs
    from .prepare import overlay
    from .runner import sample_fingerprint

    output.mkdir(parents=True, exist_ok=True)
    latest = {}
    for run in runs:
        latest[run["sample_id"]] = run
    for sample in samples:
        run = latest.get(sample["sample_id"], {})
        if run.get("status") != "success" or run.get("sample_fingerprint") != sample_fingerprint(
            sample
        ):
            continue
        answers = run["result"]["answers"]
        for qid, config in sample.get("localization", {}).items():
            if answers[config["presence_question"]]["noul"] < threshold:
                continue
            alias = config.get("image_alias", "photo")
            source = inference_inputs(sample, base).get("assets", {}).get(alias)
            if isinstance(source, dict):
                source = source.get("path")
            if isinstance(source, str):
                name = fingerprint([sample["sample_id"], qid])
                overlay(Path(source), [answers[qid]["box"]], output / f"{name}.png")
