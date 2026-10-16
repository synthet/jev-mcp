from __future__ import annotations

import os
from pathlib import Path

from jev_mcp.dotenv_util import load_credential_env, load_dotenv


def test_load_dotenv_sets_jev_token(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('JEV_TOKEN="unit-test-key"\n', encoding="utf-8")
    assert load_dotenv(env_file) == 1
    assert os.environ["JEV_TOKEN"] == "unit-test-key"


def test_project_env_preferred_over_jev_env_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("JEV_TOKEN", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".env").write_text("JEV_TOKEN=from-project\n", encoding="utf-8")
    other = tmp_path / "other.env"
    other.write_text("JEV_TOKEN=from-pointer\n", encoding="utf-8")
    monkeypatch.setenv("JEV_ENV_FILE", str(other))
    load_credential_env(project_root=project)
    assert os.environ["JEV_TOKEN"] == "from-project"
