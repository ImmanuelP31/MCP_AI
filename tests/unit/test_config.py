from __future__ import annotations

from pathlib import Path

from mcp_ops_common.config import Settings
from pytest import MonkeyPatch


def test_dotenv_overrides_inherited_environment_for_local_project(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-stale-machine-key")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-project-file-key\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.openai_api_key == "sk-project-file-key"
