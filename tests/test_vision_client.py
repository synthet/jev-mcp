import base64
from io import BytesIO
from types import SimpleNamespace

import httpx2
import pytest
from typesafe_sdk import AsyncTypeSafeClient, TypeSafeClient

from jev_mcp.client import JevClient, default_model
from jev_mcp.errors import JevMcpError
from jev_mcp.normalize import normalize_response


def image_bytes(size=(300, 400), fmt="PNG"):
    from PIL import Image

    stream = BytesIO()
    Image.new("RGB", size, "red").save(stream, fmt)
    return stream.getvalue()


def assets(data=None):
    return {
        "photo": {
            "type": "image",
            "format": "png",
            "data_base64": base64.b64encode(data or image_bytes()).decode(),
        }
    }


QUESTIONS = {"q": {"type": "noul", "instructions": "Is it red?"}}


def test_default_and_environment_override():
    assert default_model({}) == "jev-1.14.0"
    assert default_model({"JEV_MODEL": "jev-1.13.0"}) == "jev-1.13.0"


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_real_sdk_multipart_and_headers(asynchronous):
    seen = []

    def handler(request):
        seen.append((request.headers, request.read()))
        return httpx2.Response(
            200,
            json={
                "model": "jev-1.14.0",
                "usage": {"input_tokens": 20, "output_tokens": 1},
                "answers": {"q": {"type": "noul", "noul": 0.9}},
            },
        )

    factory = AsyncTypeSafeClient if asynchronous else TypeSafeClient
    http_cls = httpx2.AsyncClient if asynchronous else httpx2.Client

    def sdk(**kwargs):
        return factory(**kwargs, http_client=http_cls(transport=httpx2.MockTransport(handler)))

    client = JevClient(api_key="unit-test", sdk_factory=sdk, async_sdk_factory=sdk)
    args = dict(
        state={"nested": [{"image": "{{image:photo}}"}]},
        questions={
            "q": {
                "type": "noul",
                "instructions": {"ask": "Compare {{image:photo}} to red"},
                "criteria": {"true": ["{{image:photo}}"], "false": "blue"},
            }
        },
        assets=assets(),
        allow_images=True,
        long_context=True,
    )
    result = await client.asystem_one(**args) if asynchronous else client.system_one(**args)
    assert result["answers"]["q"]["noul"] == 0.9
    headers, body = seen[0]
    assert headers["TypeSafe-Danger-Zone-Images"] == "true"
    assert headers["TypeSafe-Danger-Zone-Long-Context"] == "true"
    assert headers["content-type"].startswith("multipart/form-data")
    assert image_bytes() in body
    assert b"Compare" in body


@pytest.mark.parametrize(
    "data",
    [b"not image", b"\x89PNG\r\n\x1a\n", b"x" * (16 * 1024 * 1024 + 1)],
    ids=["invalid", "truncated", "oversized"],
)
def test_invalid_image_never_opens_sdk(data):
    client = JevClient(api_key="test", sdk_factory=lambda **kw: pytest.fail("provider called"))
    with pytest.raises(JevMcpError):
        client.system_one(
            state="{{image:photo}}", questions=QUESTIONS, assets=assets(data), allow_images=True
        )


def test_images_need_explicit_opt_in():
    with pytest.raises(JevMcpError) as caught:
        JevClient(api_key="test").system_one(
            state="{{image:photo}}", questions=QUESTIONS, assets=assets()
        )
    assert caught.value.code == "images_disabled"


@pytest.mark.parametrize("state", ["{{image:unknown}}", "unused image"])
def test_references_are_validated(state):
    with pytest.raises(JevMcpError):
        JevClient(api_key="test").system_one(
            state=state, questions=QUESTIONS, assets=assets(), allow_images=True
        )


def test_long_context_is_bounded():
    client = JevClient(api_key="test")
    client._prepare(state="a" * 1_000_001, questions=QUESTIONS, long_context=True)
    with pytest.raises(JevMcpError):
        client._prepare(state="a" * 4_000_001, questions=QUESTIONS, long_context=True)


@pytest.mark.parametrize(
    "edge,value",
    [("left", 0.7), ("top", 0.8), ("right", float("inf")), ("top", -0.1), ("bottom", 0.1)],
)
def test_invalid_boxes_rejected(edge, value):
    box = {"top": 0.1, "bottom": 0.8, "left": 0.2, "right": 0.7, edge: value}
    raw = SimpleNamespace(boxes={"q": SimpleNamespace(box=SimpleNamespace(**box), confidence=None)})
    with pytest.raises(JevMcpError):
        normalize_response(raw, questions={"q": {"type": "box"}})


def test_corrupt_and_animated_pngs_rejected():
    from PIL import Image

    from jev_mcp.images import image_size

    stream = BytesIO()
    Image.new("RGB", (300, 300), "red").save(
        stream,
        "PNG",
        save_all=True,
        append_images=[Image.new("RGB", (300, 300), "blue")],
        duration=100,
    )
    assert image_size(stream.getvalue()) is None
    assert image_size(image_bytes()[:-20]) is None


def test_local_paths_require_roots_and_absolute_paths(tmp_path):
    from jev_mcp.images import load_images

    path = tmp_path / "a.png"
    path.write_bytes(image_bytes())
    with pytest.raises(JevMcpError):
        load_images({"photo": str(path)}, [])
    with pytest.raises(JevMcpError):
        load_images({"photo": "a.png"}, [tmp_path])


def test_symlink_escape_rejected(tmp_path):
    from jev_mcp.images import load_images

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = tmp_path / "outside.png"
    source.write_bytes(image_bytes())
    link = allowed / "link.png"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("This Windows session cannot create symlinks")
    with pytest.raises(JevMcpError):
        load_images({"photo": str(link)}, [allowed])


def test_model_support_distinguishes_images_from_box():
    from jev_mcp.client import prepare_request

    prepare_request(
        state="{{image:photo}}",
        questions=QUESTIONS,
        assets=assets(),
        allow_images=True,
        model="jev-1.13.0",
    )
    with pytest.raises(JevMcpError):
        prepare_request(
            state="{{image:photo}}",
            questions={"q": {"type": "box", "instructions": "red square"}},
            assets=assets(),
            allow_images=True,
            model="jev-1.13.0",
        )


def test_repeated_images_have_expanded_request_budget():
    from jev_mcp.client import prepare_request

    with pytest.raises(JevMcpError) as caught:
        prepare_request(
            state=["{{image:photo}}"] * 5,
            questions=QUESTIONS,
            assets=assets(image_bytes((1568, 1568))),
            allow_images=True,
        )
    assert caught.value.code == "request_too_large"


@pytest.mark.parametrize("question", [None, [], "bad", {}])
def test_bad_question_map_is_structured_error(question):
    from jev_mcp.client import prepare_request

    with pytest.raises(JevMcpError):
        prepare_request(state="x", questions=question)


@pytest.mark.parametrize("instructions", ["  ", 3, False])
def test_instructions_require_content(instructions):
    from jev_mcp.client import prepare_request

    with pytest.raises(JevMcpError):
        prepare_request(state="x", questions={"q": {"type": "noul", "instructions": instructions}})


@pytest.mark.parametrize(
    "tool", ["jev_choice", "jev_score", "jev_noul", "jev_box", "jev_system_one"]
)
async def test_all_mcp_tools_accept_assets(tool):
    from mcp import Client

    from jev_mcp.mcp_server import create_server

    seen = []

    class Fake:
        async def asystem_one(self, **kwargs):
            seen.append(kwargs)
            return {"model": "jev-1.14.0", "usage": None, "answers": {}}

    arguments = {
        "state": {"photo": "{{image:photo}}"},
        "assets": assets(),
        "allow_images": True,
        "long_context": True,
    }
    if tool == "jev_system_one":
        arguments["questions"] = QUESTIONS
    else:
        arguments["instructions"] = {"image": "{{image:photo}}", "ask": "Is it red?"}
    if tool == "jev_choice":
        arguments["criteria"] = {"red": {"example": "{{image:photo}}"}}
    if tool == "jev_score":
        arguments["criteria"] = [{"example": "{{image:photo}}"}, "No red"]
    async with Client(create_server(client=Fake())) as client:
        await client.call_tool(tool, arguments)
    assert len(seen) == 1
    assert seen[0]["assets"] == arguments["assets"]
    assert seen[0]["allow_images"] is True and seen[0]["long_context"] is True
