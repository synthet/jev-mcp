from jev_mcp import create_server


def test_package_exports_create_server() -> None:
    assert callable(create_server)
