from __future__ import annotations

from types import SimpleNamespace

from jev_mcp.normalize import (
    normalize_choice_answer,
    normalize_noul_answer,
    normalize_response,
    normalize_score_answer,
)


def test_normalize_choice_answer():
    answer = SimpleNamespace(
        choice="billing",
        confidence=0.9,
        probabilities={"billing": 0.9, "other": 0.1},
    )
    assert normalize_choice_answer(answer) == {
        "type": "choice",
        "choice": "billing",
        "confidence": 0.9,
        "probabilities": {"billing": 0.9, "other": 0.1},
    }


def test_normalize_score_answer():
    answer = SimpleNamespace(
        score=1.2,
        confidence=0.7,
        legend={"0": "low", "1": "mid", "2": "high"},
        probabilities={"0": 0.1, "1": 0.6, "2": 0.3},
    )
    assert normalize_score_answer(answer) == {
        "type": "score",
        "score": 1.2,
        "confidence": 0.7,
        "legend": {"0": "low", "1": "mid", "2": "high"},
        "probabilities": {"0": 0.1, "1": 0.6, "2": 0.3},
    }


def test_normalize_noul_answer():
    answer = SimpleNamespace(noul=0.82)
    assert normalize_noul_answer(answer) == {"type": "noul", "noul": 0.82}


def test_normalize_response_includes_model_and_usage():
    response = SimpleNamespace(
        model="jev-1.13.0",
        usage=SimpleNamespace(input_tokens=12, output_tokens=3),
        choices={
            "category": SimpleNamespace(
                choice="a",
                confidence=0.8,
                probabilities={"a": 0.8, "b": 0.2},
            )
        },
        scores={},
        nouls={"urgent": SimpleNamespace(noul=0.9)},
    )
    payload = normalize_response(response, question_ids=["category", "urgent"])
    assert payload["model"] == "jev-1.13.0"
    assert payload["usage"] == {"input_tokens": 12, "output_tokens": 3}
    assert payload["answers"]["category"]["choice"] == "a"
    assert payload["answers"]["urgent"]["noul"] == 0.9
