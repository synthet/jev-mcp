"""Bounded paid runs with explicit export, offline validation, and safe resume."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import platform
import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ..client import JevClient, prepare_request
from ..errors import JevMcpError, error
from ..normalize import validate_judgment
from .manifest import fingerprint, inference_inputs, load_manifest, read_jsonl

MODEL = "jev-1.14.0"
HARNESS_VERSION = "1"


def versions() -> dict:
    result = {"python": platform.python_version(), "harness": HARNESS_VERSION}
    for package in ("jev-mcp", "typesafe-sdk", "Pillow"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = None
    return result


def sample_fingerprint(row: dict) -> str:
    return fingerprint(
        {
            k: v
            for k, v in row.items()
            if k not in ("annotations", "localization", "local_predictions")
        }
    )


def prepare_sample(row: dict, base: Path) -> tuple[dict, str, dict]:
    inputs = inference_inputs(row, base)
    _, _, _, options = prepare_request(**inputs, model=MODEL)
    # Paths/base64 never enter logs or the provider state. Fingerprint image bytes.
    loaded = dict(zip(inputs.get("assets", {}), options.get("assets", {}).values(), strict=True))
    images = {
        alias: hashlib.sha256(bytes(asset.data)).hexdigest() for alias, asset in loaded.items()
    }
    canonical = {**inputs, "assets": images}
    key = fingerprint(
        {
            "inputs": canonical,
            "template": row["template_version"],
            "model": MODEL,
            "versions": versions(),
        }
    )
    if loaded:
        # Freeze validated bytes so files cannot change between fingerprint and inference.
        inputs["assets"] = {
            alias: {
                "type": "image",
                "format": "png" if bytes(asset.data).startswith(b"\x89PNG") else "jpeg",
                "data_base64": base64.b64encode(bytes(asset.data)).decode("ascii"),
            }
            for alias, asset in loaded.items()
        }
    return inputs, key, {"images": images, "template_version": row["template_version"]}


def run_manifest(
    manifest: Path,
    output: Path,
    *,
    live: bool = False,
    allow_export: bool = False,
    limit: int | None = None,
    price_input: float | None = None,
    price_output: float | None = None,
    client_factory: Callable | None = None,
) -> dict:
    if live and (not allow_export or type(limit) is not int or limit <= 0):
        raise error("live_opt_in_required", "Live runs require --allow-export and --limit > 0.")
    if live and any(
        v is None or isinstance(v, bool) or not math.isfinite(v) or v < 0
        for v in (price_input, price_output)
    ):
        raise error(
            "invalid_input",
            "Record both nonnegative per-million token prices for live runs.",
        )
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise error("invalid_input", "Sample limit must be positive.")
    if output.resolve() == manifest.resolve():
        raise error("invalid_input", "Run output must differ from the manifest.")
    rows = load_manifest(manifest)
    previous = read_jsonl(output) if output.exists() else []
    by_id = {row["sample_id"]: row for row in rows}
    successful = set()
    for prior in previous:
        row = by_id.get(prior.get("sample_id"))
        if (
            not row
            or prior.get("status") != "success"
            or prior.get("synthetic")
            or prior.get("model") != MODEL
            or prior.get("result", {}).get("model") != MODEL
        ):
            continue
        try:
            validate_judgment(prior["result"], row["inputs"]["questions"])
        except JevMcpError:
            continue
        successful.add((prior["sample_id"], prior.get("request_fingerprint")))
    summary = {"validated": 0, "success": 0, "failed": 0, "resumed": 0, "live": live}
    output.parent.mkdir(parents=True, exist_ok=True)
    client = None
    attempted = 0
    with output.open("a", encoding="utf-8") as stream:
        for row in rows:
            if limit is not None and attempted >= limit:
                break
            attempted += 1
            receipt = {
                "sample_id": row["sample_id"],
                "group_id": row["group_id"],
                "dataset": row["dataset"],
                "split": row["split"],
                "model": MODEL,
                "sample_fingerprint": sample_fingerprint(row),
                "versions": versions(),
                "price": {"input_per_million": price_input, "output_per_million": price_output},
            }
            start = time.perf_counter()
            try:
                inputs, key, details = prepare_sample(row, manifest.parent)
                receipt.update(request_fingerprint=key, **details)
                if live and (row["sample_id"], key) in successful:
                    summary["resumed"] += 1
                    attempted -= 1
                    continue
                if live:
                    if client is None:
                        client = (client_factory or JevClient)()
                    result = client.system_one(**inputs, model=MODEL)
                    if result["model"] != MODEL:
                        raise error("model_mismatch", "Provider did not return the pinned model.")
                    result = validate_judgment(result, inputs["questions"])
                    receipt.update(status="success", result=result)
                else:
                    receipt["status"] = "validated"
            except Exception as exc:
                # Deliberately exclude exception text, source names, prompts and labels.
                receipt.update(
                    status="failed",
                    error={
                        "code": exc.code if isinstance(exc, JevMcpError) else "run_failed",
                        "message": "Sample validation or inference failed.",
                    },
                )
            receipt["latency_seconds"] = time.perf_counter() - start
            summary[receipt["status"]] += 1
            stream.write(json.dumps(receipt, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return summary
