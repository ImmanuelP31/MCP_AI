from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentName = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    llm_provider: str = "deterministic"
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: int = 20

    github_token: str = Field(default="", repr=False)
    github_owner: str = ""
    github_repo: str = ""
    github_default_branch: str = "main"
    github_allowed_repositories: str = ""
    github_api_base_url: str = "https://api.github.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
