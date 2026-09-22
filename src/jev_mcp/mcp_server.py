"""Maintained-SDK MCP adapter exposing TypeSafe System One judgments."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from .client import JevClient
from .errors import JevMcpError, error


def create_server(
    *,
    client: JevClient | None = None,
    client_factory: Callable[[], JevClient] | None = None,
    max_response_bytes: int = 512_000,
) -> MCPServer:
    mcp = MCPServer("jev-mcp")

    def get_client() -> JevClient:
        if client is not None:
            return client
        if client_factory is not None:
            return client_factory()
        return JevClient()

    def result(callable_: Callable[..., Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            payload: dict[str, Any] = {"ok": True, "result": callable_(*args, **kwargs)}
        except JevMcpError as exc:
            payload = {"ok": False, "error": exc.as_dict()}
        except Exception:
            payload = {
                "ok": False,
                "error": {
                    "code": "internal_error",
                    "message": "The operation failed internally.",
                    "details": {},
                    "retryable": False,
                    "next_steps": [],
                },
            }
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(encoded) > max_response_bytes:
            return {
                "ok": False,
                "error": error(
                    "response_too_large",
                    "Response exceeded the configured MCP size limit.",
                    next_steps=["Narrow state or ask fewer questions in one call."],
                ).as_dict(),
            }
        return payload

    @mcp.tool()
    def jev_choice(
        state: Any,
        instructions: str,
        criteria: dict[str, str | None],
        model: str | None = None,
        question_id: str = "answer",
    ) -> dict[str, Any]:
        """Evaluate one Choice question against text/structured state."""
        return result(
            get_client().system_one,
            state=state,
            questions={
                question_id: {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
            model=model,
        )

    @mcp.tool()
    def jev_score(
        state: Any,
        instructions: str,
        criteria: list[str],
        model: str | None = None,
        question_id: str = "answer",
    ) -> dict[str, Any]:
        """Evaluate one Score question against text/structured state."""
        return result(
            get_client().system_one,
            state=state,
            questions={
                question_id: {
                    "type": "score",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
            model=model,
        )

    @mcp.tool()
    def jev_noul(
        state: Any,
        instructions: str,
        criteria: dict[str, str] | None = None,
        model: str | None = None,
        question_id: str = "answer",
    ) -> dict[str, Any]:
        """Evaluate one Noul (yes/no probability) question against text/structured state."""
        spec: dict[str, Any] = {"type": "noul", "instructions": instructions}
        if criteria is not None:
            spec["criteria"] = criteria
        return result(
            get_client().system_one,
            state=state,
            questions={question_id: spec},
            model=model,
        )

    @mcp.tool()
    def jev_system_one(
        state: Any,
        questions: dict[str, Any],
        model: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate multiple typed Choice/Score/Noul questions against one state."""
        return result(get_client().system_one, state=state, questions=questions, model=model)

    return mcp


def run_stdio(
    *,
    client: JevClient | None = None,
    client_factory: Callable[[], JevClient] | None = None,
) -> None:
    server = create_server(client=client, client_factory=client_factory)
    server.run(transport="stdio")
