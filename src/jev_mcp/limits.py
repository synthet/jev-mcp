"""Local request and response budgets, independent of model token limits."""

import json
from typing import Any

from .errors import error

MAX_REQUEST_BYTES = 1_000_000
MAX_QUESTIONS = 128
MAX_RESPONSE_BYTES = 512_000


def validate_request(state: Any, questions: dict[str, Any], model: str) -> None:
    if len(questions) > MAX_QUESTIONS:
        raise error("request_too_large", f"Use at most {MAX_QUESTIONS} questions per call.")
    size = 0
    try:
        # Count incrementally; never silently truncate caller evidence.
        encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)
        for chunk in encoder.iterencode({"state": state, "questions": questions, "model": model}):
            size += len(chunk.encode("utf-8"))
            if size > MAX_REQUEST_BYTES:
                raise error("request_too_large", "Request exceeds the 1,000,000-byte budget.",
                            next_steps=["Shorten state or split questions into separate requests."])
    except (TypeError, ValueError, RecursionError) as exc:
        raise error("invalid_input", "State and questions must contain finite JSON values.") from exc
