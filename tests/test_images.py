from __future__ import annotations

import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp import Client

from jev_mcp.client import JevClient
from jev_mcp.errors import JevMcpError
from jev_mcp.images import IMAGES_HEADER, image_size, load_images, substitute_images
from jev_mcp.mcp_server import create_server


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg(width: int, height: int) -> bytes:
    from io import BytesIO

    from PIL import Image
    stream = BytesIO()
    Image.new("RGB", (width, height), "blue").save(stream, "JPEG")
    return stream.getvalue()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "a.png").write_bytes(png(300, 400))
    (allowed / "b.jpg").write_bytes(jpeg(640, 480))
    (allowed / "tiny.png").write_bytes(png(100, 400))
    (allowed / "fake.png").write_bytes(b"not an image at all")
    (tmp_path / "outside.png").write_bytes(png(300, 300))
    return allowed


def test_image_size_reads_png_and_jpeg_headers(root: Path):
    assert image_size((root / "a.png").read_bytes()) == ("png", 300, 400)
    assert image_size((root / "b.jpg").read_bytes()) == ("jpeg", 640, 480)


def test_images_are_disabled_without_allowed_roots(root: Path):
    with pytest.raises(JevMcpError) as exc:
        load_images({"a": str(root / "a.png")}, roots=[])
    assert exc.value.code == "images_disabled"


@pytest.mark.parametrize("name", ["../outside.png", "fake.png", "tiny.png", "missing.png"])
def test_unsafe_or_invalid_images_are_rejected(root: Path, name: str):
    with pytest.raises(JevMcpError) as exc:
        load_images({"a": str(root / name)}, roots=[root])
    assert exc.value.code == "invalid_input"


def test_placeholders_must_match_aliases_exactly(root: Path):
    loaded = load_images({"a": str(root / "a.png")}, roots=[root])
    with pytest.raises(JevMcpError):
        substitute_images({"x": "{{image:b}}"}, loaded)  # unknown alias
    with pytest.raises(JevMcpError):
        substitute_images({"x": "no images here"}, loaded)  # unused alias
    state, assets = substitute_images({"x": "{{image:a}}", "note": "see {{image:a}}"}, loaded)
    assert state["x"].__class__.__name__ == "Image"
    assert "{{image:a}}" not in state["note"]
    assert str(list(assets.values())[0]) in state["note"]


class FakeImageSdk:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def aclose(self) -> None:
        return None

    async def system_one(self, state: Any, questions: Any, *, model: str | None = None,
                         **kwargs: Any) -> Any:
        FakeImageSdk.calls.append(
            {"state": state, "questions": questions, "model": model, **kwargs})
        return SimpleNamespace(
            model=model, usage=SimpleNamespace(input_tokens=1500, output_tokens=3),
            choices={}, scores={},
            nouls={q: SimpleNamespace(noul=0.2) for q, v in questions.items()
                   if v.__class__.__name__ == "Noul"},
            boxes={q: SimpleNamespace(box=SimpleNamespace(top=0.1, bottom=0.6, left=0.2, right=0.7),
                                      confidence=0.8)
                   for q, v in questions.items() if v.__class__.__name__ == "Box"},
        )


def _payload(raw: Any) -> dict[str, Any]:
    value = raw.structured_content
    return value["result"] if set(value) == {"result"} else value


@pytest.mark.asyncio
async def test_image_request_sends_assets_header_and_normalizes_box(root: Path, monkeypatch):
    monkeypatch.setenv("JEV_IMAGE_ROOTS", str(root))
    FakeImageSdk.calls.clear()
    client = JevClient(api_key="test-key", async_sdk_factory=FakeImageSdk)
    async with Client(create_server(client=client)) as mcp_client:
        raw = await mcp_client.call_tool("jev_system_one", {
            "state": {"a": "{{image:a}}", "b": "{{image:b}}"},
            "images": {"a": str(root / "a.png"), "b": str(root / "b.jpg")},
            "questions": {
                "same_head": {"type": "noul",
                              "instructions": "Does the bird face the same way in `a` and `b`?"},
                "bird": {"type": "box", "instructions": "the bird in `a`"},
            },
            "model": "jev-1.14.0",
            "allow_images": True,
        })
    payload = _payload(raw)
    assert payload["ok"] is True, payload
    answers = payload["result"]["answers"]
    assert answers["same_head"] == {"type": "noul", "noul": 0.2}
    assert answers["bird"]["type"] == "box"
    assert answers["bird"]["box"] == {"top": 0.1, "bottom": 0.6, "left": 0.2, "right": 0.7}
    call = FakeImageSdk.calls[-1]
    assert call["extra_headers"] == {IMAGES_HEADER: "true"}
    assert call["state"]["a"].__class__.__name__ == "Image"


@pytest.mark.asyncio
async def test_image_request_requires_a_pinned_image_model(root: Path, monkeypatch):
    monkeypatch.setenv("JEV_IMAGE_ROOTS", str(root))
    client = JevClient(api_key="test-key", model="jev-1.12.0", async_sdk_factory=FakeImageSdk)
    async with Client(create_server(client=client)) as mcp_client:
        raw = await mcp_client.call_tool("jev_noul", {
            "state": {"a": "{{image:a}}"}, "images": {"a": str(root / "a.png")},
            "allow_images": True,
            "instructions": "Is a bird visible in `a`?",
        })
    payload = _payload(raw)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_box_without_images_is_rejected(monkeypatch):
    client = JevClient(api_key="test-key", async_sdk_factory=FakeImageSdk)
    async with Client(create_server(client=client)) as mcp_client:
        raw = await mcp_client.call_tool("jev_system_one", {
            "state": "text only",
            "allow_images": True,
            "questions": {"bird": {"type": "box", "instructions": "the bird"}},
        })
    assert _payload(raw)["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_text_only_requests_send_no_image_header():
    FakeImageSdk.calls.clear()
    client = JevClient(api_key="test-key", async_sdk_factory=FakeImageSdk)
    async with Client(create_server(client=client)) as mcp_client:
        raw = await mcp_client.call_tool(
            "jev_noul", {"state": "hi", "instructions": "Is this a greeting?"})
    assert _payload(raw)["ok"] is True
    assert "extra_headers" not in FakeImageSdk.calls[-1]
