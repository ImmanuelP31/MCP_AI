from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from mcp_ops_common.config import Settings
from pydantic import ValidationError
from pytest import MonkeyPatch


def test_dotenv_overrides_inherited_environment_for_local_project(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-stale-machine-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-stale-machine-key")
    monkeypatch.setenv("GEMINI_API_KEY", "stale-gemini-machine-key")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-project-file-key\n"
        "OPENROUTER_API_KEY=sk-or-project-file-key\n"
        "GEMINI_API_KEY=project-gemini-file-key\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.openai_api_key == "sk-project-file-key"
    assert settings.openrouter_api_key == "sk-or-project-file-key"
    assert settings.gemini_api_key == "project-gemini-file-key"


def test_staging_and_production_reject_local_only_secret_placeholders() -> None:
    with pytest.raises(ValidationError, match="local-only secret"):
        Settings(environment="production")

    with pytest.raises(ValidationError, match="jwt_secret_key"):
        Settings(
            environment="staging",
            postgres_password=_test_secret("postgres"),
            service_auth_shared_secret=_test_secret("service"),
        )


def test_non_local_environment_accepts_explicit_secrets_and_normalizes_modes() -> None:
    payload: dict[str, object] = {
        "environment": "PRODUCTION",
        "postgres_password": _test_secret("postgres"),
        "jwt_secret_key": _test_secret("jwt"),
        "service_auth_shared_secret": _test_secret("service"),
        "llm_provider": "GEMINI",
        "llm_planner_provider": "OPENROUTER",
        "embedding_provider": "OPENAI",
        "tool_discovery_index_backend": "OPENSEARCH",
        "knowledge_index_backend": "MEMORY",
    }

    settings = Settings(**cast(Any, payload))

    assert settings.environment == "production"
    assert settings.llm_provider == "gemini"
    assert settings.llm_planner_provider == "openrouter"
    assert settings.embedding_provider == "openai"
    assert settings.tool_discovery_index_backend == "opensearch"
    assert settings.knowledge_index_backend == "memory"


def test_invalid_provider_configuration_fails_at_startup() -> None:
    with pytest.raises(ValidationError):
        Settings(llm_provider="anthropic")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        Settings(knowledge_index_backend="sqlite")  # type: ignore[arg-type]


def _test_secret(name: str) -> str:
    return f"test-{name}-secret"
