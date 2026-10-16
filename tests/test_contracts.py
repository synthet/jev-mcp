import json

from mcp import Client

from jev_mcp.mcp_server import create_server


async def test_tools_publish_typed_output_and_annotation():
    async with Client(create_server()) as client:
        listed = await client.list_tools()
    assert len(listed.tools) == 4
    for tool in listed.tools:
        schema = tool.output_schema
        assert "ok" in schema["properties"]
        assert "answers" in json.dumps(schema)
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is True


async def test_question_packs_are_readable_without_credentials(monkeypatch):
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    async with Client(create_server()) as client:
        listed = await client.list_resources()
        assert {str(r.uri) for r in listed.resources} == {
            "jev://packs/verify", "jev://packs/rerank",
        }
        for resource in listed.resources:
            result = await client.read_resource(resource.uri)
            recipe = json.loads(result.contents[0].text)
            assert recipe["tool"] == "jev_system_one"
            assert recipe["arguments"]["questions"]
