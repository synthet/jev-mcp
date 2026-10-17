import os
import subprocess

import pytest
from PIL import Image

from jev_mcp.errors import JevMcpError
from jev_mcp.vision.fixtures import generate
from jev_mcp.vision.manifest import load_manifest, read_jsonl
from jev_mcp.vision.metrics import calibration, evaluate, iou
from jev_mcp.vision.runner import prepare_sample


def test_fixture_metrics_and_cli_plots_overlays(tmp_path, monkeypatch):
    from jev_mcp.cli import main

    generate(tmp_path)
    monkeypatch.setenv("JEV_IMAGE_ROOTS", str(tmp_path))
    manifest, answers = tmp_path / "manifest.jsonl", tmp_path / "synthetic-answers.jsonl"
    report = evaluate(load_manifest(manifest), read_jsonl(answers))
    assert report["classification"]["accuracy"] == 1
    assert report["classification"]["macro_f1"] == 1
    assert report["noul"]["roc_auc"] == 1
    assert report["localization"]["mean_iou"] == 1
    assert report["localization"]["false_positives"] == 0
    assert report["tokens"]["input"] == 1800
    assert report["cost"] == 0
    validated = tmp_path / "validated.jsonl"
    assert main(["vision", "run", str(manifest), "--output", str(validated)]) == 0
    assert (
        main(
            [
                "vision",
                "evaluate",
                str(manifest),
                str(answers),
                "--output",
                str(tmp_path / "metrics.json"),
                "--plot",
                str(tmp_path / "plot.png"),
                "--overlay-dir",
                str(tmp_path / "overlays"),
            ]
        )
        == 0
    )
    assert len(list((tmp_path / "overlays").glob("*.png"))) == 2
    assert (tmp_path / "plot.png").stat().st_size > 100


def test_missing_usage_or_price_has_no_invented_cost(tmp_path):
    generate(tmp_path)
    samples = load_manifest(tmp_path / "manifest.jsonl")
    runs = read_jsonl(tmp_path / "synthetic-answers.jsonl")
    runs[0]["result"]["usage"] = None
    report = evaluate(samples, runs)
    assert report["cost"] is None and report["cost_records_missing"] == 1


def test_known_calibration_and_iou():
    assert calibration([(0.9, 1), (0.9, 0)])["ece"] == pytest.approx(0.4)
    a = {"top": 0, "bottom": 1, "left": 0, "right": 1}
    b = {"top": 0, "bottom": 0.5, "left": 0, "right": 0.5}
    assert iou(a, b) == 0.25


def test_offline_records_do_not_erase_success(tmp_path):
    generate(tmp_path)
    samples = load_manifest(tmp_path / "manifest.jsonl")
    runs = read_jsonl(tmp_path / "synthetic-answers.jsonl")
    offline = {**runs[0], "status": "validated"}
    assert evaluate(samples, runs + [offline])["success"] == len(samples)


@pytest.mark.parametrize("orientation", range(1, 9))
def test_all_exif_coordinate_roundtrips(tmp_path, orientation):
    from jev_mcp.vision.prepare import map_box, prepare_image

    source = tmp_path / "orientation.jpg"
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (800, 350)).save(source, exif=exif)
    prepared = prepare_image(source, tmp_path / "out", max_side=400)
    original = {"left": 0.1, "right": 0.8, "top": 0.2, "bottom": 0.7}
    assert map_box(map_box(original, prepared), prepared, inverse=True) == pytest.approx(original)


def test_image_fingerprints_freeze_bytes_and_bind_aliases(tmp_path, monkeypatch):
    generate(tmp_path)
    monkeypatch.setenv("JEV_IMAGE_ROOTS", str(tmp_path))
    row = load_manifest(tmp_path / "product-identity.jsonl")[1]
    inputs, original, _ = prepare_sample(row, tmp_path)
    assert "data_base64" in inputs["assets"]["photo"]
    sources = row["inputs"]["assets"]
    sources["photo"], sources["reference"] = sources["reference"], sources["photo"]
    assert prepare_sample(row, tmp_path)[1] != original


@pytest.mark.skipif(os.name != "nt", reason="Windows junction boundary")
def test_windows_junction_escape_rejected(tmp_path):
    from jev_mcp.images import load_images

    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    Image.new("RGB", (300, 300)).save(outside / "a.png")
    junction = allowed / "link"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True
    )
    with pytest.raises(JevMcpError):
        load_images({"a": str(junction / "a.png")}, [allowed])
