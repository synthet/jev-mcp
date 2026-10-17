"""Frozen JSONL manifests with inference and evaluator data kept separate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..errors import error

MAX_LINE_BYTES = 48 * 1024 * 1024


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def split_group(dataset: str, group: str, seed: str = "v1") -> str:
    bucket = int(fingerprint([seed, dataset, group])[:8], 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def read_jsonl(path: Path) -> list[dict]:
    records = []
    try:
        with path.open("rb") as stream:
            while line := stream.readline(MAX_LINE_BYTES + 1):
                if len(line) > MAX_LINE_BYTES:
                    raise error("request_too_large", "JSONL line exceeds the local budget.")
                if line.strip():
                    row = json.loads(line, parse_constant=lambda _: _bad_json())
                    if not isinstance(row, dict):
                        raise error("invalid_manifest", "JSONL records must be objects.")
                    records.append(row)
    except (ValueError, OSError) as exc:
        raise error("invalid_manifest", "Could not read valid JSONL records.") from exc
    return records


def _bad_json():
    raise ValueError("Nonfinite JSON")


def load_manifest(path: Path) -> list[dict]:
    rows = read_jsonl(path)
    seen, groups = set(), {}
    for row in rows:
        for field in ("sample_id", "group_id", "dataset", "split", "template_version"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise error("invalid_manifest", f"Manifest requires {field}.")
        if row["sample_id"] in seen or row["split"] not in ("train", "validation", "test"):
            raise error("invalid_manifest", "Sample IDs must be unique; use a frozen split.")
        seen.add(row["sample_id"])
        key = row["dataset"], row["group_id"]
        if key in groups and groups[key] != row["split"]:
            raise error("invalid_manifest", "A group cannot cross frozen splits.")
        groups[key] = row["split"]
        if not isinstance(row.get("annotations", {}), dict):
            raise error("invalid_manifest", "Annotations must be an evaluator-only object.")
        inference_inputs(row, path.parent)
    return rows


def inference_inputs(row: dict, base: Path) -> dict:
    inputs = row.get("inputs")
    if (
        not isinstance(inputs, dict)
        or not {"state", "questions"} <= inputs.keys()
        or inputs.keys() - {"state", "questions", "assets", "long_context"}
    ):
        raise error("invalid_manifest", "inputs accepts state, questions, assets and long_context.")
    if not isinstance(inputs["questions"], dict) or not inputs["questions"]:
        raise error("invalid_manifest", "A manifest needs typed questions.")

    def check(value):
        if isinstance(value, dict):
            if value.keys() & {"annotations", "label", "labels", "ground_truth", "source_filename"}:
                raise error("annotation_leak", "Evaluator labels or filenames found in state.")
            for v in value.values():
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)

    check(inputs["state"])
    result = {
        "state": inputs["state"],
        "questions": inputs["questions"],
        "long_context": inputs.get("long_context", False),
    }
    if "assets" in inputs:
        if not isinstance(inputs["assets"], dict):
            raise error("invalid_manifest", "assets must be an object.")
        assets = {}
        for alias, source in inputs["assets"].items():
            if isinstance(source, str):
                source = str((base / source).resolve())
            elif isinstance(source, dict) and set(source) == {"path"}:
                source = {"path": str((base / source["path"]).resolve())}
            assets[alias] = source
        result["assets"] = assets
        result["allow_images"] = True
    return result
