from functools import lru_cache
from typing import Any, Literal, cast

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

EnvironmentName = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del settings_cls

        def dotenv_project_secrets() -> dict[str, Any]:
            data = dotenv_settings()
            return {
                key: data[key]
                for key in ("openai_api_key", "openrouter_api_key", "gemini_api_key")
                if key in data
            }

        return (
            init_settings,
            cast(PydanticBaseSettingsSource, dotenv_project_secrets),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    environment: EnvironmentName = "development"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "mcp_ops"
    postgres_user: str = "mcp_ops"
    postgres_password: str = Field(default="change-me-local-only", repr=False)

    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"
    opensearch_url: str = "http://localhost:9200"

    jwt_issuer: str = "http://localhost:8000"
    jwt_audience: str = "mcp-engineering-ops"
    jwt_secret_key: str = Field(default="change-me-local-only", repr=False)

    service_auth_shared_secret: str = Field(default="change-me-local-only", repr=False)
    approval_ttl_seconds: int = 3600
    mcp_gateway_url: str = "http://localhost:8002"
    mcp_gateway_timeout_seconds: int = 10
    mcp_gateway_transport_retries: int = 1
    mcp_gateway_client_mode: str = "auto"
    mcp_tool_execution_isolation: str = "auto"

    llm_provider: str = "deterministic"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4.1-mini"
    openrouter_api_key: str = Field(default="", repr=False)
    openrouter_model: str = "openrouter/auto"
    openrouter_app_url: str = "https://github.com/ImmanuelP31/MCP_AI"
    openrouter_app_name: str = "MCP Engineering Operations Platform"
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash"
    llm_timeout_seconds: int = 20
    llm_planner_provider: str = "deterministic"

    embedding_provider: str = "hashing"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_timeout_seconds: int = 20

    opensearch_tool_index: str = "mcp-tools"
    opensearch_knowledge_index: str = "engineering-knowledge"
    tool_discovery_index_backend: str = "memory"
    knowledge_index_backend: str = "memory"
    rag_include_repository_docs: bool = True
    tool_discovery_semantic_weight: float = 0.45
    tool_discovery_lexical_weight: float = 0.45
    tool_discovery_metadata_weight: float = 1.0
    tool_discovery_minimum_score: float = 0.12
    workflow_planner_tool_top_k: int = 8
    workflow_rag_tool_augmentation_min_score: float = 0.35

    github_token: str = Field(default="", repr=False)
    github_owner: str = ""
    github_repo: str = ""
    github_default_branch: str = "main"
    github_allowed_repositories: str = ""
    github_api_base_url: str = "https://api.github.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
