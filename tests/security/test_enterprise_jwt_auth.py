from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mcp_ops_common.config import Settings, get_settings
from mcp_ops_mcp_gateway.app import create_app
from mcp_ops_mcp_gateway.auth import HmacJwtAuthenticator
from mcp_ops_mcp_gateway.errors import AuthenticationFailed


def test_hmac_jwt_authenticator_accepts_valid_enterprise_token() -> None:
    settings = _settings()
    token = _jwt(
        {
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "sub": "user-123",
            "role": "OPERATOR",
            "principal_type": "HUMAN",
            "exp": _future_timestamp(),
        },
        settings.jwt_secret_key,
    )

    principal = HmacJwtAuthenticator(settings).authenticate(token)

    assert principal.principal_id == "user-123"
    assert principal.role == "OPERATOR"
    assert principal.principal_type == "HUMAN"


def test_hmac_jwt_authenticator_rejects_tampered_signature() -> None:
    settings = _settings()
    token = _jwt(
        {
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "sub": "user-123",
            "role": "OPERATOR",
            "exp": _future_timestamp(),
        },
        settings.jwt_secret_key,
    )
    tampered = token.rsplit(".", maxsplit=1)[0] + ".bad-signature"

    with pytest.raises(AuthenticationFailed, match="signature"):
        HmacJwtAuthenticator(settings).authenticate(tampered)


def test_production_gateway_app_uses_enterprise_authenticator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "enterprise-secret")
    get_settings.cache_clear()

    try:
        app = create_app()
    finally:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        get_settings.cache_clear()

    assert isinstance(app.state.gateway.authenticator, HmacJwtAuthenticator)


def _settings() -> Settings:
    return Settings(
        environment="production",
        jwt_issuer="https://issuer.example.internal",
        jwt_audience="mcp-engineering-ops",
        jwt_secret_key="enterprise-secret",  # noqa: S106  # nosec B106 - deterministic test secret.
    )


def _future_timestamp() -> int:
    return int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())


def _jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = _b64(header) + "." + _b64(payload)
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256)
    return signing_input + "." + base64.urlsafe_b64encode(signature.digest()).decode().rstrip("=")


def _b64(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii").rstrip("=")
