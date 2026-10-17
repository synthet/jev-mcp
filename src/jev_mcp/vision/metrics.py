"""Deterministic offline classification, calibration, localization and cost metrics."""

from __future__ import annotations

import math
import statistics

from ..errors import error
from .runner import sample_fingerprint


def _mean(values):
    return statistics.mean(values) if values else None


def _quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def calibration(pairs, bins=10):
    """Equal-width bins: ECE compares mean predicted probability with event frequency."""
    buckets = []
    for index in range(bins):
        values = [(p, y) for p, y in pairs if min(int(p * bins), bins - 1) == index]
        if values:
            buckets.append(
                {
                    "lower": index / bins,
                    "upper": (index + 1) / bins,
                    "n": len(values),
                    "probability": _mean([p for p, _ in values]),
                    "frequency": _mean([y for _, y in values]),
                }
            )
    return {
        "ece": sum(b["n"] * abs(b["probability"] - b["frequency"]) for b in buckets) / len(pairs)
        if pairs
        else None,
        "bins": buckets,
    }


def iou(a, b):
    intersection = max(0.0, min(a["right"], b["right"]) - max(a["left"], b["left"])) * max(
        0.0, min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    )

    def area(x):
        return (x["right"] - x["left"]) * (x["bottom"] - x["top"])

    union = area(a) + area(b) - intersection
    return intersection / union if union > 0 else 0.0


def _auc(pairs):
    # Average ranks handle ties; O(n log n), without optional ML dependencies.
    positive = sum(y for _, y in pairs)
    negative = len(pairs) - positive
    if not positive or not negative:
        return None
    ordered = sorted(pairs)
    rank_sum, index = 0.0, 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        rank_sum += ((index + 1 + end) / 2) * sum(y for _, y in ordered[index:end])
        index = end
    return (rank_sum - positive * (positive + 1) / 2) / (positive * negative)


def evaluate(
    samples: list[dict],
    runs: list[dict],
    *,
    presence_threshold: float = 0.5,
    iou_threshold: float = 0.5,
) -> dict:
    if (
        not math.isfinite(presence_threshold)
        or not 0 <= presence_threshold <= 1
        or not math.isfinite(iou_threshold)
        or not 0 <= iou_threshold <= 1
    ):
        raise error("invalid_input", "Thresholds must be finite probabilities.")
    by_id = {s["sample_id"]: s for s in samples}
    latest = {}
    for run in runs:
        sample = by_id.get(run.get("sample_id"))
        if sample and run.get("status") == "success":
            fp = sample_fingerprint(sample)
            if run.get("sample_fingerprint", fp) == fp:
                latest[run["sample_id"]] = run
    classes, binary, confidence_pairs, latency = [], [], [], []
    overlaps, localization_tp, localization_fp, localization_fn = [], 0, 0, 0
    token_in = token_out = 0
    costs, missing_costs, success = [], 0, 0
    score_errors = []
    per_question = {}
    for sid, sample in by_id.items():
        run = latest.get(sid, {})
        if run.get("status") != "success":
            continue
        success += 1
        result = run["result"]
        latency.append(run["latency_seconds"])
        usage, price = result.get("usage"), run.get("price", {})
        if usage:
            token_in += usage["input_tokens"]
            token_out += usage["output_tokens"]
        if (
            usage
            and price.get("input_per_million") is not None
            and price.get("output_per_million") is not None
        ):
            costs.append(
                (
                    usage["input_tokens"] * price["input_per_million"]
                    + usage["output_tokens"] * price["output_per_million"]
                )
                / 1_000_000
            )
        else:
            missing_costs += 1
        answers = result["answers"]
        for qid, truth in sample.get("annotations", {}).items():
            answer = answers.get(qid)
            if not answer:
                continue
            kind = answer["type"]
            if kind == "choice" and truth is not None:
                probabilities = answer["probabilities"]
                if truth not in probabilities:
                    raise error("invalid_annotation", "Classification label is outside criteria.")
                classes.append((truth, answer["choice"], probabilities))
                correct = int(truth == answer["choice"])
                per_question.setdefault(qid, []).append(correct)
                if answer.get("confidence") is not None:
                    confidence_pairs.append((answer["confidence"], correct))
            elif kind == "noul" and truth is not None:
                if truth not in (True, False, 0, 1):
                    raise error("invalid_annotation", "Noul annotations must be binary.")
                binary.append((answer["noul"], int(truth)))
            elif kind == "score" and truth is not None:
                score_errors.append(answer["score"] - float(truth))
            elif kind == "box":
                gate = sample.get("localization", {}).get(qid)
                if not gate or gate.get("presence_question") not in answers:
                    raise error("missing_presence_gate", "Localization requires a companion Noul.")
                presence = answers[gate["presence_question"]]
                if presence.get("type") != "noul":
                    raise error("missing_presence_gate", "Presence gate must be a Noul.")
                kept = presence["noul"] >= presence_threshold
                if truth is None:
                    localization_fp += int(kept)
                else:
                    overlap = iou(answer["box"], truth) if kept else 0.0
                    overlaps.append(overlap)
                    hit = kept and overlap >= iou_threshold
                    localization_tp += int(hit)
                    localization_fn += int(not hit)
                    localization_fp += int(kept and not hit)
    labels = sorted({y for y, _, _ in classes} | {p for _, p, _ in classes})
    f1s = []
    for label in labels:
        tp = sum(y == p == label for y, p, _ in classes)
        fp = sum(y != label and p == label for y, p, _ in classes)
        fn = sum(y == label and p != label for y, p, _ in classes)
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)

    def clip(p):
        return min(1 - 1e-15, max(1e-15, p))

    # Threshold-based curve includes ties together and never accepts unknown confidence.
    curve = []
    for threshold in sorted({p for p, _ in confidence_pairs}, reverse=True):
        accepted = [correct for p, correct in confidence_pairs if p >= threshold]
        curve.append(
            {
                "threshold": threshold,
                "coverage": len(accepted) / len(classes),
                "risk": 1 - statistics.mean(accepted),
            }
        )
    return {
        "samples": len(samples),
        "synthetic_records": sum(bool(r.get("synthetic")) for r in latest.values()),
        "success": success,
        "coverage": success / len(samples) if samples else 0.0,
        "classification": {
            "n": len(classes),
            "accuracy": _mean([int(y == p) for y, p, _ in classes]),
            "macro_f1": _mean(f1s),
            "log_loss": _mean([-math.log(clip(probs[y])) for y, _, probs in classes]),
            "brier": _mean(
                [sum((p - int(k == y)) ** 2 for k, p in probs.items()) for y, _, probs in classes]
            ),
            "per_question_accuracy": {k: _mean(v) for k, v in per_question.items()},
            "calibration": calibration(confidence_pairs),
        },
        "noul": {
            "n": len(binary),
            "brier": _mean([(p - y) ** 2 for p, y in binary]),
            "accuracy": _mean([int((p >= 0.5) == bool(y)) for p, y in binary]),
            "log_loss": _mean(
                [-y * math.log(clip(p)) - (1 - y) * math.log(clip(1 - p)) for p, y in binary]
            ),
            "roc_auc": _auc(binary),
            "calibration": calibration(binary),
        },
        "score": {
            "n": len(score_errors),
            "mae": _mean([abs(v) for v in score_errors]),
            "rmse": math.sqrt(_mean([v * v for v in score_errors])) if score_errors else None,
        },
        "localization": {
            "n_positive": len(overlaps),
            "mean_iou": _mean(overlaps),
            "true_positives": localization_tp,
            "false_positives": localization_fp,
            "false_negatives": localization_fn,
            "presence_threshold": presence_threshold,
            "iou_threshold": iou_threshold,
            "precision": localization_tp / (localization_tp + localization_fp)
            if localization_tp + localization_fp
            else None,
            "recall": localization_tp / (localization_tp + localization_fn)
            if localization_tp + localization_fn
            else None,
        },
        "coverage_risk": curve,
        "latency": {"p50": _quantile(latency, 0.5), "p95": _quantile(latency, 0.95)},
        "tokens": {"input": token_in, "output": token_out},
        "cost": sum(costs) if success and not missing_costs else None,
        "cost_records_missing": missing_costs,
    }


def plot_report(report: dict, output) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise error(
            "missing_evaluation_dependency", "Install jev-mcp[evaluation] for plots."
        ) from exc
    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    title = "Synthetic smoke fixtures" if report.get("synthetic_records") else "Recorded evaluation"
    fig.suptitle(title)
    bins = report["noul"]["calibration"]["bins"]
    axes[0].plot([0, 1], [0, 1], "--", color="gray")
    axes[0].plot([b["probability"] for b in bins], [b["frequency"] for b in bins], "o-")
    axes[0].set(xlabel="Predicted probability", ylabel="Event frequency", title="Noul calibration")
    curve = report["coverage_risk"]
    axes[1].plot([p["coverage"] for p in curve], [p["risk"] for p in curve], "o-")
    axes[1].set(xlabel="Coverage", ylabel="Risk", title="Choice confidence thresholds")
    fig.tight_layout()
    for axis in axes:
        axis.set(xlim=(0, 1), ylim=(0, 1))
    fig.savefig(output)
    plt.close(fig)
