"""TypeSafe System One client wrapper for Jev MCP."""

from __future__ import annotations

import os
from typing import Any, Protocol

from .errors import error
from .normalize import normalize_response

API_KEY_ENVS = ("JEV_TOKEN", "TYPESAFE_API_KEY")
DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_TIMEOUT_SECONDS = 30.0


class SystemOneClient(Protocol):
    def system_one(
        self,
        *,
        state: Any,
        questions: dict[str, Any],
        model: str | None = None,
    ) -> Any: ...


def resolve_api_key(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    for name in API_KEY_ENVS:
        value = env.get(name)
        if value:
            return value
    raise error(
        "missing_credential",
        "No TypeSafe API key found in the environment.",
        next_steps=[
            "Set JEV_TOKEN (preferred) or TYPESAFE_API_KEY in the environment.",
            "Copy env.example to .env and fill in the key; never commit secrets.",
        ],
    )


def default_model(environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    return (env.get("JEV_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def default_timeout(environ: dict[str, str] | None = None) -> float:
    env = environ if environ is not None else os.environ
    raw = env.get("JEV_TIMEOUT_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise error(
            "invalid_input",
            "JEV_TIMEOUT_SECONDS must be a positive number.",
            next_steps=["Set JEV_TIMEOUT_SECONDS to a positive float, e.g. 30."],
        ) from exc
    if value <= 0:
        raise error(
            "invalid_input",
            "JEV_TIMEOUT_SECONDS must be a positive number.",
            next_steps=["Set JEV_TIMEOUT_SECONDS to a positive float, e.g. 30."],
        )
    return value


def build_questions(raw_questions: dict[str, Any]) -> dict[str, Any]:
    """Build SDK question objects from a JSON-friendly mapping."""
    try:
        from typesafe_sdk import Choice, Noul, Score
    except ImportError as exc:
        raise error(
            "missing_typesafe_sdk",
            "Install typesafe-sdk to call System One.",
            next_steps=["pip install -e .  # or: pip install typesafe-sdk"],
        ) from exc

    if not isinstance(raw_questions, dict) or not raw_questions:
        raise error(
            "invalid_input",
            "questions must be a non-empty object keyed by question id.",
            next_steps=["Pass at least one question with type choice|score|noul."],
        )

    built: dict[str, Any] = {}
    for qid, spec in raw_questions.items():
        if not isinstance(qid, str) or not qid:
            raise error(
                "invalid_input",
                "Each question id must be a non-empty string.",
            )
        if not isinstance(spec, dict):
            raise error(
                "invalid_input",
                f"Question '{qid}' must be an object.",
                question_id=qid,
            )
        qtype = spec.get("type")
        instructions = spec.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise error(
                "invalid_input",
                f"Question '{qid}' requires non-empty instructions.",
                question_id=qid,
            )
        if qtype == "choice":
            criteria = spec.get("criteria")
            if not isinstance(criteria, dict) or not criteria:
                raise error(
                    "invalid_input",
                    f"Choice question '{qid}' requires a non-empty criteria object.",
                    question_id=qid,
                )
            built[qid] = Choice(instructions=instructions, criteria=criteria)
        elif qtype == "score":
            criteria = spec.get("criteria")
            if not isinstance(criteria, list) or not criteria:
                raise error(
                    "invalid_input",
                    f"Score question '{qid}' requires a non-empty criteria list.",
                    question_id=qid,
                )
            if not all(isinstance(item, str) for item in criteria):
                raise error(
                    "invalid_input",
                    f"Score question '{qid}' criteria must be a list of strings.",
                    question_id=qid,
                )
            built[qid] = Score(instructions=instructions, criteria=criteria)
        elif qtype == "noul":
            criteria = spec.get("criteria")
            if criteria is None:
                built[qid] = Noul(instructions=instructions)
            elif isinstance(criteria, dict):
                built[qid] = Noul(instructions=instructions, criteria=criteria)
            else:
                raise error(
                    "invalid_input",
                    f"Noul question '{qid}' criteria must be an object when provided.",
                    question_id=qid,
                )
        else:
            raise error(
                "invalid_input",
                f"Question '{qid}' has unsupported type '{qtype}'.",
                question_id=qid,
                next_steps=["Use type: choice, score, or noul."],
            )
    return built


def validate_state(state: Any) -> Any:
    if isinstance(state, (str, dict)):
        return state
    if isinstance(state, list) and all(isinstance(item, str) for item in state):
        return state
    raise error(
        "invalid_input",
        "state must be a string, object, or array of strings (text/structured only).",
        next_steps=[
            "Do not pass images, audio, or video; preprocess non-text into text fields.",
        ],
    )


class JevClient:
    """Thin wrapper around typesafe_sdk.TypeSafeClient."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        sdk_factory: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else resolve_api_key()
        self.model = model if model is not None else default_model()
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else default_timeout()
        )
        self._sdk_factory = sdk_factory

    def _open_sdk(self) -> Any:
        if self._sdk_factory is not None:
            return self._sdk_factory(
                api_key=self.api_key,
                model=self.model,
                timeout=self.timeout_seconds,
            )
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as exc:
            raise error(
                "missing_typesafe_sdk",
                "Install typesafe-sdk to call System One.",
                next_steps=["pip install -e .  # or: pip install typesafe-sdk"],
            ) from exc
        return TypeSafeClient(
            api_key=self.api_key,
            model=self.model,
            timeout=self.timeout_seconds,
        )

    def system_one(
        self,
        *,
        state: Any,
        questions: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        validated_state = validate_state(state)
        built = build_questions(questions)
        request_model = (model or self.model).strip() or self.model
        try:
            with self._open_sdk() as client:
                response = client.system_one(
                    state=validated_state,
                    questions=built,
                    model=request_model,
                )
        except Exception as exc:  # noqa: BLE001 — map SDK failures to structured errors
            from .errors import JevMcpError

            if isinstance(exc, JevMcpError):
                raise
            raise error(
                "typesafe_error",
                "TypeSafe System One request failed.",
                retryable=True,
                next_steps=[
                    "Retry if the failure was transient.",
                    "Verify JEV_TOKEN and network access to api.typesafe.ai.",
                ],
            ) from exc
        return normalize_response(response, question_ids=list(built.keys()))
