"""Published MCP output types; preserve the existing JSON envelopes."""

from typing import Annotated, Any, Literal

from pydantic import Field
from typing_extensions import Required, TypedDict

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ChoiceAnswer(TypedDict):
    type: Literal["choice"]
    choice: str
    confidence: Probability | None
    probabilities: dict[str, Probability]


class ScoreAnswer(TypedDict):
    type: Literal["score"]
    score: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    confidence: Probability | None
    probabilities: dict[str, Probability]
    legend: dict[str, Any]


class NoulAnswer(TypedDict):
    type: Literal["noul"]
    noul: Probability


class Usage(TypedDict):
    input_tokens: int
    output_tokens: int


class Judgment(TypedDict):
    model: str | None
    usage: Usage | None
    answers: dict[str, Annotated[ChoiceAnswer | ScoreAnswer | NoulAnswer, Field(discriminator="type")]]


class ErrorDetails(TypedDict):
    code: str
    message: str
    details: dict[str, Any]
    retryable: bool
    next_steps: list[str]


class ToolEnvelope(TypedDict, total=False):
    ok: Required[bool]
    result: Judgment
    error: ErrorDetails
