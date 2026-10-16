"""Normalize TypeSafe System One responses into JSON-safe payloads."""

from __future__ import annotations

import math
from typing import Any

from .errors import error


def _usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is None and output_tokens is None:
        return None
    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
    }


def normalize_choice_answer(answer: Any) -> dict[str, Any]:
    return {
        "type": "choice",
        "choice": getattr(answer, "choice", None),
        "confidence": getattr(answer, "confidence", None),
        "probabilities": dict(getattr(answer, "probabilities", None) or {}),
    }


def normalize_score_answer(answer: Any) -> dict[str, Any]:
    legend = getattr(answer, "legend", None)
    return {
        "type": "score",
        "score": getattr(answer, "score", None),
        "confidence": getattr(answer, "confidence", None),
        "legend": {str(k): v for k, v in legend.items()} if legend is not None else {},
        "probabilities": {str(k): v for k, v in
                          (getattr(answer, "probabilities", None) or {}).items()},
    }


def normalize_noul_answer(answer: Any) -> dict[str, Any]:
    return {
        "type": "noul",
        "noul": getattr(answer, "noul", None),
    }


def normalize_box_answer(answer: Any) -> dict[str, Any]:
    box = getattr(answer, "box", None)
    return {
        "type": "box",
        # Box always returns coordinates, even when the target is absent: pair it
        # with a Noul presence question and gate on that in host code.
        "box": {edge: getattr(box, edge, None) for edge in ("top", "bottom", "left", "right")},
        "confidence": getattr(answer, "confidence", None),
    }


def normalize_response(
    response: Any, *, question_ids: list[str] | None = None,
    questions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a System One response.

    When ``question_ids`` is set, only those answers are included (in order).
    Otherwise all choice/score/noul/box answers are included.
    """
    answers: dict[str, Any] = {}
    choices = getattr(response, "choices", None) or {}
    scores = getattr(response, "scores", None) or {}
    nouls = getattr(response, "nouls", None) or {}
    boxes = getattr(response, "boxes", None) or {}

    if questions is not None:
        question_ids = list(questions)
        if (set(choices) | set(scores) | set(nouls) | set(boxes) != set(questions)
                or len(choices) + len(scores) + len(nouls) + len(boxes) != len(questions)):
            raise error("invalid_response", "Response answer IDs do not match the request.")

    if question_ids is not None:
        for qid in question_ids:
            if qid in choices:
                answers[qid] = normalize_choice_answer(choices[qid])
            elif qid in scores:
                answers[qid] = normalize_score_answer(scores[qid])
            elif qid in nouls:
                answers[qid] = normalize_noul_answer(nouls[qid])
            elif qid in boxes:
                answers[qid] = normalize_box_answer(boxes[qid])
            else:
                raise error(
                    "invalid_response",
                    "TypeSafe did not return an answer for every requested question.",
                    next_steps=["Check the requested question types and the provider response."],
                )
    else:
        for qid, answer in choices.items():
            answers[qid] = normalize_choice_answer(answer)
        for qid, answer in scores.items():
            answers[qid] = normalize_score_answer(answer)
        for qid, answer in nouls.items():
            answers[qid] = normalize_noul_answer(answer)
        for qid, answer in boxes.items():
            answers[qid] = normalize_box_answer(answer)

    if questions is not None:
        for qid, spec in questions.items():
            _validate_answer(answers[qid], spec)

    return {
        "model": getattr(response, "model", None),
        "usage": _usage(response),
        "answers": answers,
    }


def _number(value: Any, low: float, high: float) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and low <= value <= high)


def _validate_answer(answer: dict[str, Any], question: dict[str, Any]) -> None:
    invalid = error("invalid_response", "Provider answer is inconsistent with the question.")
    if answer["type"] != question["type"]:
        raise invalid
    if answer["type"] == "noul":
        if not _number(answer["noul"], 0, 1):
            raise invalid
        return
    if answer["type"] == "box":
        box = answer["box"]
        if (not all(_number(v, 0, 1) for v in box.values())
                or box["top"] > box["bottom"] or box["left"] > box["right"]
                or (answer["confidence"] is not None and not _number(answer["confidence"], 0, 1))):
            raise invalid
        return
    confidence = answer["confidence"]
    if confidence is not None and not _number(confidence, 0, 1):
        raise invalid
    criteria = question["criteria"]
    keys = set(criteria) if answer["type"] == "choice" else {str(i) for i in range(len(criteria))}
    probs = answer["probabilities"]
    if (set(probs) != keys or not all(_number(p, 0, 1) for p in probs.values())
            or abs(sum(probs.values()) - 1) > 0.01 + 1e-12):
        raise invalid
    if answer["type"] == "choice":
        if (answer["choice"] not in keys
                or probs[answer["choice"]] + 1e-9 < max(probs.values())):
            raise invalid
    else:
        count = len(criteria)
        if not _number(answer["score"], 0, count - 1) or set(answer["legend"]) != keys:
            raise invalid
        mean = sum(int(k) * p for k, p in probs.items())
        # Local tolerance for score and probabilities rounded to two decimals.
        # This is a validation policy, not a claim about provider precision.
        tolerance = 0.005 * (1 + sum(range(count))) + 1e-9
        if abs(mean - answer["score"]) > tolerance:
            raise invalid
