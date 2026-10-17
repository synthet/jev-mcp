import json

import pytest
from PIL import Image

from jev_mcp.cli import main
from jev_mcp.errors import JevMcpError


def test_prepare_orientation_padding_and_coordinate_roundtrip(tmp_path):
    from jev_mcp.vision.prepare import map_box, prepare_image

    source = tmp_path / "private-label.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (900, 100), "red").save(source, exif=exif)
    record = prepare_image(source, tmp_path / "out", max_side=600, quality=80)
    assert record["oriented_size"] == [100, 900]
    with Image.open(record["path"]) as image:
        assert image.size == (280, 600)
        assert image.mode == "RGB"
        assert not image.getexif()
        assert not image.info.get("progressive")
    original = {"top": 0.1, "bottom": 0.8, "left": 0.2, "right": 0.9}
    prepared = map_box(original, record)
    assert map_box(prepared, record, inverse=True) == pytest.approx(original)


def record(sample="s1", group="g1"):
    return {
        "sample_id": sample,
        "group_id": group,
        "dataset": "synthetic",
        "split": "test",
        "template_version": "v1",
        "inputs": {
            "state": {"evidence": "red"},
            "questions": {
                "class": {
                    "type": "choice",
                    "instructions": "Color?",
                    "criteria": {"red": None, "blue": None},
                }
            },
        },
        "annotations": {"class": "red"},
    }


def write_manifest(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_group_splits_and_isolation(tmp_path):
    from jev_mcp.vision.manifest import inference_inputs, load_manifest, split_group

    assert split_group("dataset", "g1", "seed") == split_group("dataset", "g1", "seed")
    row = record()
    assert "annotations" not in inference_inputs(row, tmp_path)
    path = tmp_path / "m.jsonl"
    duplicate = {**record("s2"), "split": "train"}
    write_manifest(path, [row, duplicate])
    with pytest.raises(JevMcpError):
        load_manifest(path)
    row["inputs"]["state"]["label"] = "red"
    with pytest.raises(JevMcpError):
        inference_inputs(row, tmp_path)


def test_offline_cli_never_constructs_provider(tmp_path, monkeypatch):
    from jev_mcp.client import JevClient

    monkeypatch.setattr(JevClient, "__init__", lambda *a, **k: pytest.fail("provider opened"))
    manifest = tmp_path / "m.jsonl"
    output = tmp_path / "runs.jsonl"
    write_manifest(manifest, [record()])
    assert main(["vision", "run", str(manifest), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "validated"
    assert main(["vision", "run", str(manifest), "--output", str(output), "--live"]) == 2


def test_live_resume_only_matching_successes_and_sanitizes(tmp_path):
    from jev_mcp.vision.runner import run_manifest

    manifest = tmp_path / "m.jsonl"
    output = tmp_path / "runs.jsonl"
    write_manifest(manifest, [record(), record("s2", "g2")])

    class FakeClient:
        calls = 0

        def system_one(self, **kwargs):
            self.calls += 1
            assert "annotations" not in json.dumps(kwargs)
            return {
                "model": "jev-1.14.0",
                "usage": {"input_tokens": 10, "output_tokens": 1},
                "answers": {
                    "class": {
                        "type": "choice",
                        "choice": "red",
                        "confidence": 0.9,
                        "probabilities": {"red": 0.9, "blue": 0.1},
                    }
                },
            }

    client = FakeClient()
    opts = dict(
        live=True,
        allow_export=True,
        limit=2,
        price_input=0.042,
        price_output=0.0,
        client_factory=lambda: client,
    )
    run_manifest(manifest, output, **opts)
    run_manifest(manifest, output, **opts)
    assert client.calls == 2
    damaged = [json.loads(line) for line in output.read_text().splitlines()]
    damaged[0]["result"]["answers"] = {}
    output.write_text("".join(json.dumps(row) + "\n" for row in damaged), encoding="utf-8")
    run_manifest(manifest, output, **opts)
    assert client.calls == 3
    rows = [json.loads(s) for s in output.read_text().splitlines()]
    assert rows[0]["price"]["input_per_million"] == 0.042
    assert rows[0]["versions"]["typesafe-sdk"]
    changed = record()
    changed["inputs"]["state"]["evidence"] = "blue"
    write_manifest(manifest, [changed])
    run_manifest(manifest, output, **opts)
    assert client.calls == 4

    class Broken:
        def system_one(self, **kwargs):
            raise RuntimeError("secret-token private-label.jpg")

    opts["client_factory"] = Broken
    changed["template_version"] = "v2"
    write_manifest(manifest, [changed])
    run_manifest(manifest, output, **opts)
    run_manifest(manifest, output, **opts)
    assert "secret-token" not in output.read_text()
    assert len(output.read_text().splitlines()) == 6


def test_metrics_presence_gating_and_calibration():
    from jev_mcp.vision.metrics import evaluate

    samples = [record()]
    samples[0]["annotations"] = {"class": "red", "present": False, "where": None}
    prediction = {
        "sample_id": "s1",
        "status": "success",
        "latency_seconds": 2.0,
        "price": {"input_per_million": 1.0, "output_per_million": 0.0},
        "result": {
            "usage": {"input_tokens": 100, "output_tokens": 2},
            "answers": {
                "class": {
                    "type": "choice",
                    "choice": "red",
                    "confidence": 0.8,
                    "probabilities": {"red": 0.8, "blue": 0.2},
                },
                "present": {"type": "noul", "noul": 0.2},
                "where": {
                    "type": "box",
                    "confidence": None,
                    "box": {"top": 0.0, "bottom": 1.0, "left": 0.0, "right": 1.0},
                },
            },
        },
    }
    samples[0]["localization"] = {"where": {"presence_question": "present"}}
    report = evaluate(samples, [prediction], presence_threshold=0.5)
    assert report["classification"]["accuracy"] == 1.0
    assert report["noul"]["brier"] == pytest.approx(0.04)
    assert report["localization"]["false_positives"] == 0
    assert report["cost"] == pytest.approx(0.0001)
    assert report["latency"]["p50"] == 2.0


def test_tiles_map_to_original(tmp_path):
    from jev_mcp.vision.prepare import map_box, prepare_image, tile_regions

    source = tmp_path / "large.png"
    Image.new("RGB", (1000, 1000)).save(source)
    regions = tile_regions(1000, 1000, 500)
    assert len(regions) == 4
    tile = prepare_image(source, tmp_path / "out", crop=regions[-1])
    assert map_box({"left": 0.0, "right": 1.0, "top": 0.0, "bottom": 1.0}, tile, inverse=True) == {
        "left": 0.5,
        "right": 1.0,
        "top": 0.5,
        "bottom": 1.0,
    }
