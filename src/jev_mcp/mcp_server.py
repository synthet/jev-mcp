"""Maintained-SDK MCP adapter exposing TypeSafe System One judgments."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import version
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .client import JevClient
from .errors import JevMcpError, error
from .models import ToolEnvelope
from .packs import PACKS

INSTRUCTIONS = (
    "Jev evaluates bounded semantic questions using a paid external TypeSafe service. "
    "Use raw evidence as state and one narrow judgment per question. Question IDs are labels; "
    "put the full meaning in instructions. Batch independent questions over shared state. "
    "Include a no-match option when a Choice may have no suitable answer. Score criteria are "
    "ordered from low to high and scores range from 0 to N-1. A Noul near 0.5 is uncertainty. "
    "Confidence is not proof of correctness or authorization to act. Keep arithmetic, tests, "
    "permissions, and execution in host code. Read jev://packs/verify or jev://packs/rerank for examples. "
    "Images (experimental, Jev 1.14+): pass local PNG/JPEG paths in `images` as {alias: path}, put "
    '"{{image:alias}}" as a whole value in state, and refer to that state field in instructions. '
    "Images are sent to TypeSafe and are allowed only from server-configured "
    "directories. Box always "
    "returns a box; ask a Noul presence question too and gate on it."
)
Images = Annotated[
    dict[str, str] | None,
    Field(description=(
        'Optional {alias: local PNG/JPEG path}; reference as "{{image:alias}}" in state.'
    )),
]
ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=False, openWorldHint=True,
)
State = Annotated[Any, Field(description="Raw text or structured evidence to judge; omit secrets.")]
Instructions = Annotated[str, Field(description="One self-contained question, not a desired verdict.")]


def create_server(
    *,
    client: JevClient | None = None,
    client_factory: Callable[[], JevClient] | None = None,
    max_response_bytes: int = 512_000,
) -> MCPServer:
    mcp = MCPServer("jev-mcp", version=version("jev-mcp"), instructions=INSTRUCTIONS)

    def get_client() -> JevClient:
        if client is not None:
            return client
        if client_factory is not None:
            return client_factory()
        return JevClient()

    async def result(**kwargs: Any) -> ToolEnvelope:
        try:
            try:
                payload: ToolEnvelope = {"ok": True, "result": await get_client().asystem_one(**kwargs)}
            except JevMcpError as exc:
                payload = {"ok": False, "error": exc.as_dict()}
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > max_response_bytes:
                raise error(
                    "response_too_large",
                    "Response exceeded the configured MCP size limit.",
                    next_steps=["Narrow state or ask fewer questions in one call."],
                )
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
        return payload

    @mcp.tool(annotations=ANNOTATIONS)
    async def jev_choice(
        state: State,
        instructions: Instructions,
        criteria: dict[str, str | None],
        model: str | None = None,
        question_id: str = "answer",
        images: Images = None,
    ) -> ToolEnvelope:
        """Evaluate one Choice question against text/structured state and optional images."""
        return await result(
            state=state,
            questions={
                question_id: {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
            model=model,
            images=images,
        )

    @mcp.tool(annotations=ANNOTATIONS)
    async def jev_score(
        state: State,
        instructions: Instructions,
        criteria: Annotated[list[str], Field(description="Ordered rubric, low to high; 0 to N-1.")],
        model: str | None = None,
        question_id: str = "answer",
        images: Images = None,
    ) -> ToolEnvelope:
        """Evaluate one Score question against text/structured state and optional images."""
        return await result(
            state=state,
            questions={
                question_id: {
                    "type": "score",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
            model=model,
            images=images,
        )

    @mcp.tool(annotations=ANNOTATIONS)
    async def jev_noul(
        state: State,
        instructions: Instructions,
        criteria: dict[str, str] | None = None,
        model: str | None = None,
        question_id: str = "answer",
        images: Images = None,
    ) -> ToolEnvelope:
        """Evaluate one Noul (yes/no probability) question against state and optional images."""
        spec: dict[str, Any] = {"type": "noul", "instructions": instructions}
        if criteria is not None:
            spec["criteria"] = criteria
        return await result(
            state=state,
            questions={question_id: spec},
            model=model,
            images=images,
        )

    @mcp.tool(annotations=ANNOTATIONS)
    async def jev_system_one(
        state: State,
        questions: dict[str, Any],
        model: str | None = None,
        images: Images = None,
    ) -> ToolEnvelope:
        """Evaluate several typed Choice/Score/Noul/Box questions against one state.

        Box questions need images and return one box each."""
        return await result(state=state, questions=questions, model=model, images=images)

    @mcp.resource("jev://packs/verify", mime_type="application/json")
    def verification_pack() -> str:
        """Example evidence verification questions; no provider request."""
        return json.dumps(PACKS["verify"])

    @mcp.resource("jev://packs/rerank", mime_type="application/json")
    def reranking_pack() -> str:
        """Example independent relevance questions; sort scores in host code."""
        return json.dumps(PACKS["rerank"])

    return mcp


def run_stdio(
    *,
    client: JevClient | None = None,
    client_factory: Callable[[], JevClient] | None = None,
) -> None:
    from pathlib import Path

    from .dotenv_util import load_credential_env

    source_root = Path(__file__).resolve().parents[1]
    project_root = source_root.parent if source_root.name == "src" else Path.cwd()
    load_credential_env(project_root=project_root)
    server = create_server(client=client, client_factory=client_factory)
    server.run(transport="stdio")
