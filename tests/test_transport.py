import asyncio

import httpx2
import pytest

from jev_mcp.client import JevClient
from jev_mcp.errors import JevMcpError


class Stream(httpx2.AsyncByteStream):
    closed = False
    reads = 0

    async def __aiter__(self):
        for _ in range(10):
            self.reads += 1
            yield b"x" * 100

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("status", [200, 500])
async def test_response_stream_is_bounded_and_closed(status):
    from jev_mcp.transport import BoundedAsyncClient

    stream = Stream()
    transport = httpx2.MockTransport(lambda request: httpx2.Response(status, stream=stream))
    async with BoundedAsyncClient(transport=transport, max_response_bytes=200) as client:
        with pytest.raises(JevMcpError) as caught:
            await client.get("https://unit.test")
    assert caught.value.code == "response_too_large"
    assert stream.closed
    assert stream.reads == 3


class SlowSdk:
    def __init__(self, **kwargs):
        self.started = asyncio.Event()
        self.cancelled = False
        self.closed = False

    async def system_one(self, **kwargs):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True

    async def aclose(self):
        self.closed = True


async def test_deadline_stops_request_and_closes_client():
    sdk = SlowSdk()
    client = JevClient(api_key="test-key", timeout_seconds=0.03,
                       async_sdk_factory=lambda **kwargs: sdk)
    with pytest.raises(JevMcpError) as caught:
        await client.asystem_one(state="test", questions={
            "q": {"type": "noul", "instructions": "Yes?"},
        })
    assert caught.value.code == "request_timeout"
    assert sdk.cancelled and sdk.closed


async def test_caller_cancellation_propagates_and_closes_client():
    sdk = SlowSdk()
    client = JevClient(api_key="test-key", async_sdk_factory=lambda **kwargs: sdk)
    task = asyncio.create_task(client.asystem_one(state="test", questions={
        "q": {"type": "noul", "instructions": "Yes?"},
    }))
    await asyncio.wait_for(sdk.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sdk.cancelled and sdk.closed
