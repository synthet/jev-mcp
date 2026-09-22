from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from mcp import Client

from jev_mcp.client import JevClient
from jev_mcp.errors import JevMcpError
from jev_mcp.mcp_server import create_server


class FakeSdk:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.last_call: dict[str, Any] | None = None

    def __enter__(self) -> FakeSdk:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def system_one(
        self,
        state: Any,
        questions: Any,
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> Any:
        self.last_call = {"state": state, "questions": questions, "model": model, **kwargs}
        return SimpleNamespace(
            model=model or "jev-1.13.0",
            usage=SimpleNamespace(input_tokens=10, output_tokens=2),
            choices={
                qid: SimpleNamespace(
                    choice="billing",
                    confidence=0.9,
                    probabilities={"billing": 0.9},
                )
                for qid, q in questions.items()
                if getattr(q, "type", None) == "choice" or q.__class__.__name__ == "Choice"
            },
            scores={
                qid: SimpleNamespace(
                    score=1.0,
                    confidence=0.8,
                    legend={"0": "a", "1": "b"},
                    probabilities={"0": 0.2, "1": 0.8},
                )
                for qid, q in questions.items()
                if getattr(q, "type", None) == "score" or q.__class__.__name__ == "Score"
            },
            nouls={
                qid: SimpleNamespace(noul=0.75)
                for qid, q in questions.items()
                if getattr(q, "type", None) == "noul" or q.__class__.__name__ == "Noul"
            },
        )


def _unwrap(payload: Any) -> dict[str, Any]:
    import json

    value = getattr(payload, "structured_content", None)
    if isinstance(value, dict) and set(value) == {"result"}:
        value = value["result"]
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict):
        return value
    if isinstance(payload, dict):
        return payload
    content = getattr(payload, "content", None)
    if content:
        for item in content:
            text = getattr(item, "text", None)
            if text:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and set(parsed) == {"result"}:
                    parsed = parsed["result"]
                assert isinstance(parsed, dict)
                return parsed
    raise AssertionError(f"unexpected tool payload: {payload!r}")

@pytest.mark.asyncio
async def test_mcp_lists_system_one_tools():
    client = JevClient(api_key="test-key", sdk_factory=FakeSdk)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        tools = await mcp_client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert {"jev_choice", "jev_score", "jev_noul", "jev_system_one"} <= names


@pytest.mark.asyncio
async def test_jev_choice_returns_normalized_envelope():
    client = JevClient(api_key="test-key", sdk_factory=FakeSdk)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        raw = await mcp_client.call_tool(
            "jev_choice",
            {
                "state": "I was charged twice.",
                "instructions": "What is this about?",
                "criteria": {"billing": "payments", "other": None},
            },
        )
        payload = _unwrap(raw)
        assert payload["ok"] is True
        assert payload["result"]["answers"]["answer"]["type"] == "choice"
        assert payload["result"]["answers"]["answer"]["choice"] == "billing"
        assert payload["result"]["model"] == "jev-1.13.0"


@pytest.mark.asyncio
async def test_jev_system_one_batch():
    client = JevClient(api_key="test-key", sdk_factory=FakeSdk)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        raw = await mcp_client.call_tool(
            "jev_system_one",
            {
                "state": {"message": "help ASAP"},
                "questions": {
                    "urgent": {"type": "noul", "instructions": "Is this urgent?"},
                    "dept": {
                        "type": "choice",
                        "instructions": "Which team?",
                        "criteria": {"billing": None, "tech": None},
                    },
                },
            },
        )
        payload = _unwrap(raw)
        assert payload["ok"] is True
        assert "urgent" in payload["result"]["answers"]
        assert "dept" in payload["result"]["answers"]


@pytest.mark.asyncio
async def test_invalid_state_is_structured_error():
    client = JevClient(api_key="test-key", sdk_factory=FakeSdk)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        raw = await mcp_client.call_tool(
            "jev_noul",
            {"state": 123, "instructions": "Is this text?"},
        )
        payload = _unwrap(raw)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_internal_errors_are_redacted(monkeypatch):
    client = JevClient(api_key="test-key", sdk_factory=FakeSdk)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("SECRET-INTERNAL-DETAIL")

    monkeypatch.setattr(client, "system_one", boom)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        raw = await mcp_client.call_tool(
            "jev_noul",
            {"state": "ok", "instructions": "yes?"},
        )
        payload = _unwrap(raw)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "internal_error"
        assert "SECRET" not in str(payload)


def test_missing_credential_on_client_construct(monkeypatch):
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(JevMcpError) as caught:
        JevClient()
    assert caught.value.code == "missing_credential"
