from copy import deepcopy
from types import SimpleNamespace

import pytest
from typesafe_sdk._core.response_types import SystemOneResponse

from jev_mcp.client import JevClient
from jev_mcp.errors import JevMcpError
from jev_mcp.normalize import normalize_response


def response(answer):
    return SystemOneResponse.model_validate({
        "model": "jev-1.13.0", "usage": {"input_tokens": 1, "output_tokens": 1},
        "answers": {"q": answer},
    })


CHOICE = {"type": "choice", "instructions": "Choose", "criteria": {"a": None, "b": None}}
ANSWER = {"type": "choice", "choice": "a", "confidence": 0.8,
          "probabilities": {"a": 0.9, "b": 0.1}}


@pytest.mark.parametrize("change", [
    {"choice": "unknown"}, {"choice": "b"},
    {"probabilities": {"a": 1.0}}, {"probabilities": {"a": 0.2, "b": 0.1}},
    {"probabilities": {"a": 1.2, "b": -0.2}}, {"confidence": float("nan")},
    {"type": "noul", "noul": 0.5},
], ids=["unknown-label", "wrong-winner", "missing-label", "bad-sum", "bad-range", "nan", "type"])
def test_reject_inconsistent_sdk_answers(change):
    answer = {**deepcopy(ANSWER), **change}
    # Deliberately bypass SDK validation to test the wrapper's trust boundary.
    grouped = SimpleNamespace(model="test", choices={}, scores={}, nouls={})
    bucket = "nouls" if answer["type"] == "noul" else "choices"
    getattr(grouped, bucket)["q"] = SimpleNamespace(**answer)
    with pytest.raises(JevMcpError) as caught:
        normalize_response(grouped, questions={"q": CHOICE})
    assert caught.value.code == "invalid_response"


def test_real_sdk_response_preserves_zero():
    raw = response({**ANSWER, "confidence": 0.0, "probabilities": {"a": 1.0, "b": 0.0}})
    result = normalize_response(raw, questions={"q": CHOICE})
    assert result["answers"]["q"]["confidence"] == 0
    assert result["answers"]["q"]["probabilities"]["b"] == 0


def test_unknown_confidence_stays_unknown():
    raw = SimpleNamespace(choices={"q": SimpleNamespace(**{**ANSWER, "confidence": None})})
    assert normalize_response(raw, questions={"q": CHOICE})["answers"]["q"]["confidence"] is None


def test_real_sdk_score_keys_and_mean():
    raw = response({"type": "score", "score": 0.8, "confidence": 0.7,
                    "legend": {0: "low", 1: "high"}, "probabilities": {0: 0.2, 1: 0.8}})
    questions = {"q": {"type": "score", "instructions": "Rate", "criteria": ["low", "high"]}}
    assert normalize_response(raw, questions=questions)["answers"]["q"]["score"] == 0.8


@pytest.mark.parametrize("state,questions", [
    ("x" * 1_000_001, {"q": CHOICE}),
    ("text", {f"q{i}": CHOICE for i in range(129)}),
    ({"number": float("nan")}, {"q": CHOICE}),
], ids=["byte-limit", "question-limit", "non-json-number"])
def test_bad_requests_never_open_sdk(state, questions):
    def forbidden(**kwargs):
        pytest.fail("Invalid request reached SDK")

    client = JevClient(api_key="test-key", sdk_factory=forbidden)
    with pytest.raises(JevMcpError) as caught:
        client.system_one(state=state, questions=questions)
    assert caught.value.code in {"request_too_large", "invalid_input"}
