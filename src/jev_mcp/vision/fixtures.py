"""Generate tiny synthetic datasets and explicitly synthetic offline answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .manifest import split_group
from .prepare import prepare_image
from .runner import MODEL, sample_fingerprint, versions


def generate(output: Path) -> None:
    from PIL import Image, ImageDraw

    output.mkdir(parents=True, exist_ok=True)
    # Synthetic scenes, no downloaded data or conventional model installation.
    images = []
    for index, color in enumerate(("red", "blue", "white")):
        image = Image.new("RGB", (400, 400), "white")
        if index < 2:
            ImageDraw.Draw(image).rectangle((100, 100, 299, 299), fill=color)
        source = output / f"scene-{index}.png"
        image.save(source)
        images.append(prepare_image(source, output / "images", format="png"))
    templates = {
        "product-identity": {
            "same": {
                "type": "noul",
                "instructions": {
                    "question": "Does the object in state.photo match the reference?",
                    "reference": "{{image:reference}}",
                },
            }
        },
        "classification": {
            "class": {
                "type": "choice",
                "instructions": "What color is the central object?",
                "criteria": {"red": "Red object", "blue": "Blue object", "none": "No object"},
            }
        },
        "inspection": {
            "fault": {"type": "noul", "instructions": "Is a blue object present?"},
            "severity": {
                "type": "score",
                "instructions": "Rate blue contamination.",
                "criteria": ["No blue", "Some blue", "Mostly blue"],
            },
        },
        "localization": {
            "present": {"type": "noul", "instructions": "Is a colored rectangle visible?"},
            "where": {"type": "box", "instructions": "The colored rectangle in state.photo"},
        },
        "decomposed-reasoning": {
            "colored": {"type": "noul", "instructions": "Is a colored object present?"},
            "red": {"type": "noul", "instructions": "Is a red object present?"},
        },
        "hybrid-routing": {
            "route": {
                "type": "choice",
                "instructions": "Does the precomputed local_prediction match the photo? "
                "Keep it only if supported; otherwise escalate.",
                "criteria": {"local": "Supported by image", "escalate": "Not supported"},
            },
            "class": {
                "type": "choice",
                "instructions": "What color is the central object?",
                "criteria": {"red": None, "blue": None, "none": "No object"},
            },
        },
    }
    (output / "templates.json").write_text(json.dumps(templates, indent=2), encoding="utf-8")
    rows, runs = [], []
    for dataset, questions in templates.items():
        task_rows = []
        for index, image in enumerate(images):
            assets = {"photo": Path(image["path"]).relative_to(output.resolve()).as_posix()}
            state = {"photo": "{{image:photo}}"}
            label = ("red", "blue", "none")[index]
            annotations = {}
            local_predictions = None
            if dataset == "product-identity":
                reference = Path(images[0]["path"]).relative_to(output.resolve())
                assets["reference"] = reference.as_posix()
                annotations = {"same": index == 0}
            elif dataset == "classification":
                annotations = {"class": label}
            elif dataset == "inspection":
                annotations = {"fault": index == 1, "severity": 2 if index == 1 else 0}
            elif dataset == "localization":
                annotations = {
                    "present": index < 2,
                    "where": {"left": 0.25, "right": 0.75, "top": 0.25, "bottom": 0.75}
                    if index < 2
                    else None,
                }
            elif dataset == "decomposed-reasoning":
                annotations = {"colored": index < 2, "red": index == 0}
            elif dataset == "hybrid-routing":
                state["local_prediction"] = {
                    "choice": "red",
                    "confidence": 0.7,
                    "model": "synthetic-local-v1",
                }
                local_predictions = {"class": "red"}
                annotations = {"route": "local" if index == 0 else "escalate", "class": label}
            row = {
                "sample_id": f"{dataset}-{index:03}",
                "group_id": f"scene-{index}",
                "dataset": dataset,
                "split": split_group(dataset, f"scene-{index}"),
                "template_version": "synthetic-v1",
                "inputs": {"state": state, "assets": assets, "questions": questions},
                "annotations": annotations,
            }
            if dataset == "localization":
                row["localization"] = {
                    "where": {"presence_question": "present", "image_alias": "photo"}
                }
            if local_predictions:
                row["local_predictions"] = local_predictions
            answers = {}
            for qid, question in questions.items():
                truth, kind = annotations[qid], question["type"]
                if kind == "choice":
                    answers[qid] = {
                        "type": kind,
                        "choice": truth,
                        "confidence": 0.9,
                        "probabilities": {k: float(k == truth) for k in question["criteria"]},
                    }
                elif kind == "noul":
                    answers[qid] = {"type": kind, "noul": 0.9 if truth else 0.1}
                elif kind == "score":
                    answers[qid] = {
                        "type": kind,
                        "score": truth,
                        "confidence": 0.9,
                        "legend": {str(i): v for i, v in enumerate(question["criteria"])},
                        "probabilities": {
                            str(i): float(i == truth) for i in range(len(question["criteria"]))
                        },
                    }
                else:
                    answers[qid] = {
                        "type": kind,
                        "confidence": None,
                        "box": truth or {"left": 0.1, "right": 0.2, "top": 0.1, "bottom": 0.2},
                    }
            runs.append(
                {
                    "sample_id": row["sample_id"],
                    "sample_fingerprint": sample_fingerprint(row),
                    "status": "success",
                    "synthetic": True,
                    "model": MODEL,
                    "versions": versions(),
                    "latency_seconds": 0.01,
                    "price": {"input_per_million": 0.0, "output_per_million": 0.0},
                    "result": {
                        "model": MODEL,
                        "usage": {"input_tokens": 100, "output_tokens": 1},
                        "answers": answers,
                    },
                }
            )
            rows.append(row)
            task_rows.append(row)
        _write(output / f"{dataset}.jsonl", task_rows)
    _write(output / "manifest.jsonl", rows)
    _write(output / "synthetic-answers.jsonl", runs)


def _write(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output.resolve())
