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

    async def aclose(self) -> None:
        return None

    async def system_one(
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
                    choice=next(iter(q.criteria)),
                    confidence=0.9,
                    probabilities={key: float(i == 0) for i, key in enumerate(q.criteria)},
                )
                for qid, q in questions.items()
                if getattr(q, "type", None) == "choice" or q.__class__.__name__ == "Choice"
            },
            scores={
                qid: SimpleNamespace(
                    score=0.8,
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
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
    server = create_server(client=client)
    async with Client(server) as mcp_client:
        tools = await mcp_client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert {"jev_choice", "jev_score", "jev_noul", "jev_system_one"} <= names


@pytest.mark.asyncio
async def test_jev_choice_returns_normalized_envelope():
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
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
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
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
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
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
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("SECRET-INTERNAL-DETAIL")

    monkeypatch.setattr(client, "asystem_one", boom)
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


@pytest.mark.parametrize("tool, arguments", [
    ("jev_choice", {"instructions": "Choose", "criteria": {"a": None}}),
    ("jev_score", {"instructions": "Score", "criteria": ["low", "high"]}),
    ("jev_noul", {"instructions": "Yes?"}),
    ("jev_system_one", {"questions": {"q": {"type": "noul", "instructions": "Yes?"}}}),
])
async def test_missing_credential_is_structured_at_tool_boundary(monkeypatch, tool, arguments):
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    async with Client(create_server()) as client:
        payload = _unwrap(await client.call_tool(tool, {"state": "text", **arguments}))
    assert payload["error"]["code"] == "missing_credential"


async def test_client_factory_error_is_redacted():
    def broken_factory():
        raise RuntimeError("SECRET-FACTORY-DETAIL")

    async with Client(create_server(client_factory=broken_factory)) as client:
        payload = _unwrap(await client.call_tool(
            "jev_noul", {"state": "text", "instructions": "Yes?"},
        ))
    assert payload["error"]["code"] == "internal_error"
    assert "SECRET" not in str(payload)


async def test_invalid_batch_criteria_is_input_error():
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
    async with Client(create_server(client=client)) as mcp_client:
        payload = _unwrap(await mcp_client.call_tool("jev_system_one", {
            "state": "text",
            "questions": {"q": {"type": "noul", "instructions": "Yes?",
                                "criteria": {"yes": 42}}},
        }))
    assert payload["error"]["code"] == "invalid_input"


@pytest.mark.parametrize(
    "status, retryable", [(400, False), (401, False), (429, True), (503, True)],
)
async def test_sdk_error_retryability_and_redaction(monkeypatch, status, retryable):
    import httpx2
    from typesafe_sdk import TypeSafeAPIError

    def fail(self, **kwargs):
        raise TypeSafeAPIError(status, {"message": "SECRET-REMOTE-BODY"}, httpx2.Headers())

    monkeypatch.setattr(FakeSdk, "system_one", fail)
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)
    async with Client(create_server(client=client)) as mcp_client:
        payload = _unwrap(await mcp_client.call_tool(
            "jev_noul", {"state": "text", "instructions": "Yes?"},
        ))
    assert payload["error"]["retryable"] is retryable
    assert "SECRET" not in str(payload)


@pytest.mark.parametrize("failure", [False, True])
async def test_response_limit_covers_success_and_error(monkeypatch, failure):
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)

    async def large_result(**kwargs):
        if failure:
            raise JevMcpError("invalid_input", "x" * 2000)
        return {"value": "x" * 2000}

    monkeypatch.setattr(client, "asystem_one", large_result)
    async with Client(create_server(client=client, max_response_bytes=1000)) as mcp_client:
        payload = _unwrap(await mcp_client.call_tool(
            "jev_noul", {"state": "text", "instructions": "Yes?"},
        ))
    assert payload["error"]["code"] == "response_too_large"


@pytest.mark.parametrize("value", [object(), float("nan")])
async def test_unserializable_result_is_redacted(monkeypatch, value):
    client = JevClient(api_key="test-key", async_sdk_factory=FakeSdk)

    async def bad_result(**kwargs):
        return {"value": value}

    monkeypatch.setattr(client, "asystem_one", bad_result)
    async with Client(create_server(client=client)) as mcp_client:
        payload = _unwrap(await mcp_client.call_tool(
            "jev_noul", {"state": "text", "instructions": "Yes?"},
        ))
    assert payload["error"]["code"] == "internal_error"
