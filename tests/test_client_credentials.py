from __future__ import annotations

import pytest

from jev_mcp.client import resolve_api_key
from jev_mcp.errors import JevMcpError


def test_resolve_api_key_prefers_jev_token():
    key = resolve_api_key({"JEV_TOKEN": "from-jev", "TYPESAFE_API_KEY": "from-typesafe"})
    assert key == "from-jev"


def test_resolve_api_key_falls_back_to_typesafe():
    key = resolve_api_key({"TYPESAFE_API_KEY": "from-typesafe"})
    assert key == "from-typesafe"


def test_resolve_api_key_missing_raises():
    with pytest.raises(JevMcpError) as caught:
        resolve_api_key({})
    assert caught.value.code == "missing_credential"
    assert "JEV_TOKEN" in caught.value.next_steps[0]
