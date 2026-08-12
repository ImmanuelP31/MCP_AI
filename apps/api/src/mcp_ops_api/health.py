from __future__ import annotations

import socket
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from urllib.parse import urlparse

from mcp_ops_common.config import Settings
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from mcp_ops_api.db.session import create_database_engine


@dataclass(frozen=True, slots=True)
class ComponentCheck:
    name: str
    status: str
    details: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "details": self.details}


def readiness_checks(settings: Settings) -> dict[str, Any]:
    checks = [
        ComponentCheck("api", "ready", {"reason": "application_process_initialized"}),
        _postgres(settings),
        _tcp_url("redis", settings.redis_url),
        _tcp_host_port("kafka", settings.kafka_bootstrap_servers),
        _http("opensearch", settings.opensearch_url),
        _mcp_server("device-mcp", "mcp_ops_device_mcp.server"),
        _mcp_server("diagnostics-mcp", "mcp_ops_diagnostics_mcp.server"),
        _mcp_server("knowledge-mcp", "mcp_ops_knowledge_mcp.server"),
        _mcp_server("repository-mcp", "mcp_ops_repository_mcp.server"),
        _mcp_server("ticket-mcp", "mcp_ops_ticket_mcp.server"),
        _model_provider(settings),
    ]
    overall = "ready" if all(check.status == "ready" for check in checks) else "degraded"
    return {
        "status": overall,
        "components": {check.name: check.as_payload() for check in checks},
    }


def _postgres(settings: Settings) -> ComponentCheck:
    try:
        engine = create_database_engine(settings, connect_timeout_seconds=1)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return ComponentCheck("postgresql", "ready", {"host": settings.postgres_host})
    except SQLAlchemyError as exc:
        return ComponentCheck("postgresql", "unavailable", {"error": exc.__class__.__name__})


def _tcp_url(name: str, url: str) -> ComponentCheck:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    return _tcp_socket(name, host, port)


def _tcp_host_port(name: str, value: str) -> ComponentCheck:
    first = value.split(",", maxsplit=1)[0]
    host, _, port_text = first.partition(":")
    try:
        port = int(port_text or "9092")
    except ValueError:
        return ComponentCheck(name, "misconfigured", {"target": value})
    return _tcp_socket(name, host or "localhost", port)


def _tcp_socket(name: str, host: str, port: int) -> ComponentCheck:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return ComponentCheck(name, "ready", {"host": host, "port": port})
    except OSError as exc:
        return ComponentCheck(
            name,
            "unavailable",
            {"host": host, "port": port, "error": exc.__class__.__name__},
        )


def _http(name: str, url: str) -> ComponentCheck:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ComponentCheck(name, "misconfigured", {"url": url})
    connection_cls = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path_prefix = parsed.path.rstrip("/")
    health_path = f"{path_prefix}/_cluster/health" if path_prefix else "/_cluster/health"
    try:
        connection = connection_cls(parsed.hostname, port, timeout=0.75)
        try:
            connection.request("GET", health_path)
            response = connection.getresponse()
            status_code = response.status
        finally:
            connection.close()
        return ComponentCheck(name, "ready", {"url": url, "status_code": status_code})
    except Exception as exc:  # noqa: BLE001 - readiness reports dependency failures as data
        return ComponentCheck(name, "unavailable", {"url": url, "error": exc.__class__.__name__})


def _mcp_server(name: str, module_name: str) -> ComponentCheck:
    try:
        module = __import__(module_name, fromlist=["create_dispatcher"])
        dispatcher = module.create_dispatcher()
        return ComponentCheck(name, "ready", {"tools": len(dispatcher.list_tools())})
    except Exception as exc:  # noqa: BLE001 - readiness reports import/registration failures
        return ComponentCheck(name, "unavailable", {"error": exc.__class__.__name__})


def _model_provider(settings: Settings) -> ComponentCheck:
    provider = settings.llm_provider.lower()
    required_keys = {
        "gemini": (settings.gemini_api_key, "GEMINI_API_KEY"),
        "openrouter": (settings.openrouter_api_key, "OPENROUTER_API_KEY"),
        "openai": (settings.openai_api_key, "OPENAI_API_KEY"),
    }
    if provider in required_keys:
        key, env_name = required_keys[provider]
        if not key:
            return ComponentCheck(
                "model_provider",
                "misconfigured",
                {"provider": provider, "reason": f"{env_name} is not configured"},
            )
    return ComponentCheck("model_provider", "ready", {"provider": provider})
