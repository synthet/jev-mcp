"""Normalize TypeSafe System One responses into JSON-safe payloads."""

from __future__ import annotations

from typing import Any


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
        "legend": dict(legend) if legend is not None else {},
        "probabilities": dict(getattr(answer, "probabilities", None) or {}),
    }


def normalize_noul_answer(answer: Any) -> dict[str, Any]:
    return {
        "type": "noul",
        "noul": getattr(answer, "noul", None),
    }


def normalize_response(response: Any, *, question_ids: list[str] | None = None) -> dict[str, Any]:
    """Serialize a System One response.

    When ``question_ids`` is set, only those answers are included (in order).
    Otherwise all choice/score/noul answers are included.
    """
    answers: dict[str, Any] = {}
    choices = getattr(response, "choices", None) or {}
    scores = getattr(response, "scores", None) or {}
    nouls = getattr(response, "nouls", None) or {}

    if question_ids is not None:
        for qid in question_ids:
            if qid in choices:
                answers[qid] = normalize_choice_answer(choices[qid])
            elif qid in scores:
                answers[qid] = normalize_score_answer(scores[qid])
            elif qid in nouls:
                answers[qid] = normalize_noul_answer(nouls[qid])
    else:
        for qid, answer in choices.items():
            answers[qid] = normalize_choice_answer(answer)
        for qid, answer in scores.items():
            answers[qid] = normalize_score_answer(answer)
        for qid, answer in nouls.items():
            answers[qid] = normalize_noul_answer(answer)

    return {
        "model": getattr(response, "model", None),
        "usage": _usage(response),
        "answers": answers,
    }
