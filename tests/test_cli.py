import pytest

from jev_mcp import cli, mcp_server


@pytest.mark.parametrize("entrypoint", ["cli", "stdio"])
def test_cli_loads_checkout_env_from_another_directory(tmp_path, monkeypatch, entrypoint):
    checkout = tmp_path / "checkout"
    package = checkout / "src" / "jev_mcp"
    package.mkdir(parents=True)
    (checkout / ".env").write_text("JEV_TOKEN=test-checkout-key\n", encoding="utf-8")
    monkeypatch.setattr(cli, "__file__", str(package / "cli.py"))
    monkeypatch.setattr(mcp_server, "__file__", str(package / "mcp_server.py"))
    monkeypatch.chdir(tmp_path)
    for key in ("JEV_TOKEN", "TYPESAFE_API_KEY", "JEV_ENV_FILE", "DOTENV_PATH"):
        monkeypatch.delenv(key, raising=False)

    def start():
        from jev_mcp.client import resolve_api_key

        assert resolve_api_key() == "test-checkout-key"

    if entrypoint == "cli":
        monkeypatch.setattr(mcp_server, "run_stdio", start)
        assert cli.main(["mcp"]) == 0
    else:
        monkeypatch.setattr(mcp_server.MCPServer, "run", lambda *args, **kwargs: start())
        mcp_server.run_stdio()


def test_doctor_is_offline_and_does_not_expose_credentials(monkeypatch, capsys):
    from jev_mcp.client import JevClient

    monkeypatch.setenv("JEV_TOKEN", "test-secret-not-for-output")

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline doctor attempted inference")

    monkeypatch.setattr(JevClient, "asystem_one", forbidden)
    assert cli.main(["doctor", "--json"]) == 0
    output = capsys.readouterr().out
    import json

    report = json.loads(output)
    assert report["credential_present"] is True
    assert report["mcp_handshake"] is True
    assert report["live"] is False
    assert "test-secret" not in output
